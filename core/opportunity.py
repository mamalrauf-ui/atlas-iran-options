"""
موتور Opportunity - قلب هوشمند ATLAS.

اصول (طبق Specification):
- هیچ Score یا Opportunity ساختگی تولید نمی‌شود.
- Score یک معماری وزن‌دار و Configurable روی مؤلفه‌های واقعاً قابل‌محاسبه است؛
  اگر مؤلفه‌ای (مثلاً Momentum که نیاز به داده تاریخی دارد) قابل‌محاسبه نباشد،
  از فرمول کنار گذاشته و وزن‌های باقی‌مانده Re-normalize می‌شوند - نه اینکه با
  صفر یا مقدار فرضی پر شود.
- Strategy Opportunities فقط از بین قالب‌هایی ساخته می‌شود که Strategy Engine
  (core/strategy.py) واقعاً پشتیبانی می‌کند.
"""
import numpy as np
import pandas as pd

from core import strategy as strat_engine

DEFAULT_WEIGHTS = {
    "liquidity": 0.20,
    "risk_reward": 0.20,
    "iv": 0.15,
    "probability": 0.15,
    "open_interest": 0.10,
    "mispricing": 0.10,
    "momentum": 0.10,
}


# حداقل تعداد مقدار متمایز لازم برای اینکه یک رتبه‌بندی نسبی معنا داشته باشد
MIN_DISTINCT_FOR_RANK = 3

# آستانه‌های مطلق: یک قرارداد فقط وقتی «نقدشونده» یا «دارای OI قوی» نامیده
# می‌شود که مقدار مطلقش هم واقعاً بالا باشد، نه صرفاً رتبه‌اش در گروه.
# بدون این، در گروهی که همه صفرند، همه برچسب High می‌گیرند.
MIN_ABS_VOLUME_FOR_LIQUID = 100      # قرارداد
MIN_ABS_OI_FOR_STRONG = 500          # قرارداد
MIN_ABS_VOLUME_FOR_UNUSUAL = 50

# حداقل سهم وزنی مؤلفه‌های محاسبه‌شده برای اینکه امتیاز اصلاً معنا داشته باشد.
# امتیازی که روی ۱۰٪ وزن‌ها بنا شده، عدد نیست؛ حدس است.
MIN_SCORE_COVERAGE_PCT = 25.0


def _pct_rank(series: pd.Series, value) -> float:
    """
    رتبه صدکی value درون series (۰ تا ۱۰۰).

    اگر سری «تباه» باشد (همه مقادیر یکسان، مثلاً وقتی حجم همه قراردادهای یک
    گروه صفر است)، رتبه‌بندی نسبی هیچ اطلاعاتی ندارد و None برمی‌گردد.

    این نکته حیاتی است: فرمول ساده (s <= value).mean() در سری ثابت برای
    *همه* مقدار ۱۰۰ می‌دهد، یعنی هزار قرارداد بی‌معامله همگی «رتبه صدک ۱۰۰»
    و امتیاز ۱۰۰ می‌گیرند و برچسب High Liquidity / High OI می‌خورند —
    یعنی دقیقاً همان هوش مالی جعلی که ممنوع است.
    """
    s = series.dropna()
    if s.empty or pd.isna(value):
        return None
    if s.nunique() < MIN_DISTINCT_FOR_RANK:
        return None
    return float((s <= value).mean() * 100)


def _is_positive(v) -> bool:
    return v is not None and pd.notna(v) and float(v) > 0


def _renormalize(components: dict) -> float:
    """جمع وزن‌دار مؤلفه‌های موجود (None حذف و وزن‌ها Re-normalize می‌شوند)."""
    available = {k: v for k, v in components.items() if v.get("score") is not None}
    if not available:
        return None
    total_w = sum(v["weight"] for v in available.values())
    if total_w <= 0:
        return None
    return sum(v["score"] * v["weight"] for v in available.values()) / total_w


# ---------------------------------------------------------------------------
# سطح ۱: Contract Opportunities
# ---------------------------------------------------------------------------

CONTRACT_CATEGORIES = [
    "Undervalued", "Overvalued", "High IV", "Low IV",
    "High Liquidity", "High OI", "Unusual Volume", "Unusual OI",
]


def detect_contract_opportunities(chain_df: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    """
    chain_df باید ستون‌های enrich_full_dataset را داشته باشد (iv, delta, oi, volume, ...).
    گروه‌بندی مقایسه‌ای برای هر معیار نسبی: (underlying, expiry, option_type) —
    یعنی یک قرارداد فقط با هم‌گروه‌های واقعی خودش مقایسه می‌شود، نه کل بازار.
    """
    weights = weights or DEFAULT_WEIGHTS
    if chain_df.empty:
        return pd.DataFrame()

    df = chain_df.copy()
    group_keys = ["underlying", "expiry", "option_type"]
    rows = []

    for _, group in df.groupby(group_keys):
        if len(group) < 3:
            continue  # برای مقایسه نسبی معنادار حداقل ۳ قرارداد هم‌گروه لازم است

        iv_median = group["iv"].median() if group["iv"].notna().sum() >= 3 else None
        vol_median = group["volume"].median() if group["volume"].notna().sum() >= 3 else None
        oi_median = group["open_interest"].median() if group["open_interest"].notna().sum() >= 3 else None

        for _, row in group.iterrows():
            # ------------------------------------------------------------
            # قابلیت معامله، پیش‌شرط «فرصت» بودن است.
            #
            # قراردادی که نه موقعیت بازی دارد و نه امروز معامله شده، عملاً
            # قابل ورود نیست؛ قیمت پایانی‌اش هم کهنه است و IV استخراج‌شده
            # از آن قابل اتکا نیست. نمایش چنین قراردادی به‌عنوان «فرصت با
            # امتیاز ۱۰۰» فقط به این دلیل که بالاترین IV گروهش را دارد،
            # گمراه‌کننده است.
            # ------------------------------------------------------------
            has_oi = _is_positive(row.get("open_interest"))
            has_vol = _is_positive(row.get("volume"))
            if not has_oi and not has_vol:
                continue

            categories = []

            iv_pct = _pct_rank(group["iv"], row.get("iv")) if iv_median is not None else None
            if iv_pct is not None:
                if iv_pct >= 75:
                    categories.append("High IV")
                elif iv_pct <= 25:
                    categories.append("Low IV")

            liq_score_raw = None
            vol_pct = _pct_rank(group["volume"], row.get("volume"))
            oi_pct = _pct_rank(group["open_interest"], row.get("open_interest"))
            row_volume = row.get("volume")
            row_oi = row.get("open_interest")

            # نقدشوندگی از رتبه نسبی *و* مقدار مطلق با هم ساخته می‌شود:
            # رتبه بالا در گروهی که همه‌اش کم‌معامله است، نقدشوندگی نیست.
            if vol_pct is not None and oi_pct is not None:
                liq_score_raw = (vol_pct + oi_pct) / 2
                if (liq_score_raw >= 75
                        and _is_positive(row_volume) and row_volume >= MIN_ABS_VOLUME_FOR_LIQUID
                        and _is_positive(row_oi) and row_oi >= MIN_ABS_OI_FOR_STRONG):
                    categories.append("High Liquidity")
            if (oi_pct is not None and oi_pct >= 80
                    and _is_positive(row_oi) and row_oi >= MIN_ABS_OI_FOR_STRONG):
                categories.append("High OI")

            # «حجم غیرعادی» روی پایه صفر بی‌معناست: ۲ در برابر میانه ۰
            # بی‌نهایت برابر است ولی خبر نیست.
            if (vol_median and vol_median > 0 and _is_positive(row_volume)
                    and row_volume >= MIN_ABS_VOLUME_FOR_UNUSUAL
                    and row_volume / vol_median >= 2.5):
                categories.append("Unusual Volume")
            if (oi_median and oi_median > 0 and _is_positive(row_oi)
                    and row_oi >= MIN_ABS_OI_FOR_STRONG
                    and row_oi / oi_median >= 2.5):
                categories.append("Unusual OI")

            # Mispricing نسبت به IV هم‌گروه: IV به‌طور معنادار پایین‌تر/بالاتر از میانه
            mispricing_score = None
            mispricing_direction = None
            if iv_median and iv_median > 0 and pd.notna(row.get("iv")):
                deviation = (row["iv"] - iv_median) / iv_median
                mispricing_score = min(100.0, abs(deviation) * 200)
                if deviation <= -0.15:
                    categories.append("Undervalued")
                    mispricing_direction = "زیر ارزش (IV پایین‌تر از هم‌گروه)"
                elif deviation >= 0.15:
                    categories.append("Overvalued")
                    mispricing_direction = "بالای ارزش (IV بالاتر از هم‌گروه)"

            if not categories:
                continue

            components = {
                "liquidity": {"score": liq_score_raw, "weight": weights["liquidity"]},
                "iv": {"score": iv_pct, "weight": weights["iv"]},
                "open_interest": {"score": oi_pct, "weight": weights["open_interest"]},
                "mispricing": {"score": mispricing_score, "weight": weights["mispricing"]},
                # Risk/Reward، Probability و Momentum در سطح Contract قابل‌محاسبه معنادار نیستند
                # (این‌ها مفاهیم سطح-استراتژی یا نیازمند داده تاریخی‌اند) — عمداً کنار گذاشته می‌شوند.
                "risk_reward": {"score": None, "weight": weights["risk_reward"]},
                "probability": {"score": None, "weight": weights["probability"]},
                "momentum": {"score": None, "weight": weights["momentum"]},
            }
            score = _renormalize(components)

            # سهم وزنی مؤلفه‌هایی که واقعاً محاسبه شدند. امتیاز ۱۰۰ که فقط
            # روی یک مؤلفه بنا شده با امتیاز ۱۰۰ که روی چهار مؤلفه بنا شده
            # یکی نیست؛ این عدد آن تفاوت را برای کاربر آشکار می‌کند.
            avail_w = sum(v["weight"] for v in components.values() if v.get("score") is not None)
            total_w = sum(v["weight"] for v in components.values())
            coverage_pct = (avail_w / total_w * 100) if total_w else 0.0

            # امتیاز بدون هیچ مؤلفه واقعی، عدد نیست — ردیف حذف می‌شود تا
            # جدول با فرصت‌های بی‌پشتوانه پر نشود.
            if score is None:
                continue

            why, risks = [], []
            if liq_score_raw is not None and liq_score_raw >= 75 and "High Liquidity" in categories:
                why.append("✓ نقدشوندگی بالا نسبت به هم‌گروه")
            if liq_score_raw is not None and liq_score_raw <= 20:
                risks.append("⚠ نقدشوندگی پایین")
            if mispricing_direction:
                why.append(f"✓ {mispricing_direction}")
            if "High OI" in categories:
                why.append("✓ موقعیت باز قوی")
            if not _is_positive(row_volume):
                risks.append("⚠ امروز هیچ معامله‌ای روی این قرارداد انجام نشده")
            if row.get("theta") is not None and pd.notna(row.get("theta")) and row["theta"] < 0:
                if abs(row["theta"]) / max(abs(row.get("close") or 1), 1) > 0.02:
                    risks.append("⚠ فرسایش زمانی (Theta) بالا")
            if pd.notna(row.get("bid")) and pd.notna(row.get("ask")) and row.get("close"):
                spread_pct = (row["ask"] - row["bid"]) / row["close"] if row["close"] else None
                if spread_pct and spread_pct > 0.15:
                    risks.append("⚠ اسپرد Bid/Ask گسترده")
            if iv_pct is not None and iv_pct >= 85:
                risks.append("⚠ نوسان ضمنی بسیار بالا")

            rows.append({
                "symbol": row.get("symbol"),
                "underlying": row["underlying"],
                "option_type": row["option_type"],
                "strike": row["strike"],
                "expiry": row["expiry"],
                "dte": row.get("dte"),
                "close": row.get("close"),
                "iv": row.get("iv"),
                "volume": row.get("volume"),
                "open_interest": row.get("open_interest"),
                "categories": categories,
                "score": round(score, 1) if score is not None else None,
                "score_coverage_pct": round(coverage_pct, 0),
                "tradeable": bool(has_oi or has_vol),
                "why": why,
                "risks": risks,
            })

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    # امتیازهایی که روی داده بسیار ناقص بنا شده‌اند کنار گذاشته می‌شوند.
    result = result[result["score_coverage_pct"] >= MIN_SCORE_COVERAGE_PCT]
    if result.empty:
        return result

    # مرتب‌سازی دو‌مرحله‌ای: امتیاز برابر، آن‌که بر پایه اطلاعات بیشتری
    # ساخته شده بالاتر می‌آید. بدون این، قراردادی که فقط یک مؤلفه‌اش
    # قابل محاسبه بوده می‌تواند بالای قراردادی بنشیند که همه‌چیزش معلوم است.
    result = result.sort_values(
        ["score", "score_coverage_pct"], ascending=[False, False], na_position="last"
    ).reset_index(drop=True)
    return result


# ---------------------------------------------------------------------------
# سطح ۲: Strategy Opportunities
# ---------------------------------------------------------------------------

def _default_index(strikes, rank, opt_type, s_ref):
    arr = np.array(strikes)
    if len(arr) == 0:
        return None
    atm_idx = int(np.argmin(np.abs(arr - s_ref)))
    if rank == "atm":
        return atm_idx
    step = 1 if rank == "otm" else 3
    idx = atm_idx + step if opt_type == "call" else atm_idx - step
    return max(0, min(len(arr) - 1, idx))


def detect_strategy_opportunities(chain_df: pd.DataFrame, underlying: str, expiry,
                                   s_ref: float, r: float, weights: dict = None) -> pd.DataFrame:
    """
    برای یک (underlying, expiry) مشخص، همه قالب‌های STRATEGY_TEMPLATES را با
    Strikeهای پیش‌فرض واقعی (از همان زنجیره) می‌سازد و امتیازدهی می‌کند.
    فقط استراتژی‌هایی که واقعاً قابل‌ساخت باشند (داده کافی Call/Put) نتیجه می‌دهند.
    """
    weights = weights or DEFAULT_WEIGHTS
    sub = chain_df[(chain_df["underlying"] == underlying) & (chain_df["expiry"] == expiry)]
    if sub.empty:
        return pd.DataFrame()

    calls = sub[sub["option_type"] == "call"].sort_values("strike").reset_index(drop=True)
    puts = sub[sub["option_type"] == "put"].sort_values("strike").reset_index(drop=True)
    sigma_ctx = float(sub["iv"].dropna().mean()) if sub["iv"].notna().any() else None
    dte_ctx = int(sub["dte"].dropna().iloc[0]) if sub["dte"].notna().any() else None

    rows = []
    for name, template in strat_engine.STRATEGY_TEMPLATES.items():
        if template is None:
            continue
        legs, liq_vals, iv_vals = [], [], []
        ok = True
        for role in template:
            # پایه سهام: قیمت ورود همان قیمت واقعی دارایی پایه است و
            # Strike برایش بی‌معناست (Covered Call / Collar).
            if role["option_type"] == "stock":
                legs.append(strat_engine.Leg("stock", role["side"], 0.0,
                                             float(s_ref), role.get("qty", 1)))
                continue
            book = calls if role["option_type"] == "call" else puts
            if book.empty:
                ok = False
                break
            idx = _default_index(book["strike"].values, role["rank"], role["option_type"], s_ref)
            if idx is None:
                ok = False
                break
            row = book.iloc[idx]
            legs.append(strat_engine.Leg(role["option_type"], role["side"], float(row["strike"]),
                                          float(row["close"]), role.get("qty", 1)))
            if pd.notna(row.get("volume")) and pd.notna(row.get("open_interest")):
                liq_vals.append(float(row["volume"]) + float(row["open_interest"]))
            if pd.notna(row.get("iv")):
                iv_vals.append(float(row["iv"]))
        if not ok or not legs:
            continue

        credit = strat_engine.net_premium(legs)
        mpl = strat_engine.max_profit_loss(legs, s_ref)
        pop = None
        if sigma_ctx and dte_ctx:
            pop = strat_engine.probability_of_profit(legs, s_ref, sigma_ctx, dte_ctx / 365, r)

        rr_score = None
        if not mpl["max_profit_is_unbounded"] and not mpl["max_loss_is_unbounded"] and mpl["max_loss"] != 0:
            ratio = abs(mpl["max_profit"] / mpl["max_loss"]) if mpl["max_loss"] else None
            if ratio is not None:
                rr_score = min(100.0, ratio * 40)  # نسبت ۲.۵ به بالا => نزدیک سقف امتیاز

        liq_score = min(100.0, (sum(liq_vals) / len(liq_vals)) / 50) if liq_vals else None
        iv_score = float(np.mean(iv_vals) * 100) if iv_vals else None  # فقط برای نمایش سطح IV، نه رتبه
        prob_score = float(pop * 100) if pop is not None else None

        components = {
            "liquidity": {"score": liq_score, "weight": weights["liquidity"]},
            "risk_reward": {"score": rr_score, "weight": weights["risk_reward"]},
            "probability": {"score": prob_score, "weight": weights["probability"]},
            "iv": {"score": None, "weight": weights["iv"]},  # سطح IV مطلق، نه رتبه قابل‌مقایسه معنادار در اینجا
            "open_interest": {"score": None, "weight": weights["open_interest"]},
            "mispricing": {"score": None, "weight": weights["mispricing"]},
            "momentum": {"score": None, "weight": weights["momentum"]},
        }
        score = _renormalize(components)

        why, risks = [], []
        if rr_score is not None and rr_score >= 60:
            why.append("✓ نسبت ریسک/بازده مناسب")
        if prob_score is not None and prob_score >= 60:
            why.append("✓ احتمال سودآوری (POP) بالا")
        if liq_score is not None and liq_score >= 60:
            why.append("✓ نقدشوندگی پایه‌ها مناسب")
        if liq_score is not None and liq_score < 25:
            risks.append("⚠ نقدشوندگی پایین در یک یا چند پایه")
        if mpl["max_loss_is_unbounded"]:
            risks.append("⚠ ریسک زیان نامحدود")
        if prob_score is not None and prob_score < 40:
            risks.append("⚠ احتمال سودآوری پایین")

        _avail_w = sum(v["weight"] for v in components.values() if v.get("score") is not None)
        _total_w = sum(v["weight"] for v in components.values())
        rows.append({
            "strategy": name,
            # همان مفهوم سطح قرارداد: امتیاز روی چند درصد از وزن‌ها بنا شده
            "score_coverage_pct": round((_avail_w / _total_w * 100) if _total_w else 0.0, 0),
            "underlying": underlying,
            "expiry": expiry,
            "credit_debit": round(credit, 1),
            "max_profit": "نامحدود" if mpl["max_profit_is_unbounded"] else round(mpl["max_profit"], 1),
            "max_loss": "نامحدود" if mpl["max_loss_is_unbounded"] else round(mpl["max_loss"], 1),
            "pop": round(pop * 100, 1) if pop is not None else None,
            "score": round(score, 1) if score is not None else None,
            "legs": legs,
            "why": why,
            "risks": risks,
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    # امتیازهایی که روی داده بسیار ناقص بنا شده‌اند کنار گذاشته می‌شوند.
    result = result[result["score_coverage_pct"] >= MIN_SCORE_COVERAGE_PCT]
    if result.empty:
        return result

    # مرتب‌سازی دو‌مرحله‌ای: امتیاز برابر، آن‌که بر پایه اطلاعات بیشتری
    # ساخته شده بالاتر می‌آید. بدون این، قراردادی که فقط یک مؤلفه‌اش
    # قابل محاسبه بوده می‌تواند بالای قراردادی بنشیند که همه‌چیزش معلوم است.
    result = result.sort_values(
        ["score", "score_coverage_pct"], ascending=[False, False], na_position="last"
    ).reset_index(drop=True)
    return result


# ---------------------------------------------------------------------------
# سطح ۳: اسکن استراتژی روی کل Universe بازار (بخش ۳۵ Master Prompt)
# ---------------------------------------------------------------------------
def scan_strategy_universe(chain_df: pd.DataFrame, r: float, weights: dict = None,
                           strategies: list = None, min_legs_liquidity: bool = False) -> pd.DataFrame:
    """
    پاسخ به پرسش «امروز بهترین <استراتژی>های بازار کدام‌اند؟».

    این تابع فرمول جدیدی اختراع نمی‌کند: صرفاً detect_strategy_opportunities را
    روی همه جفت‌های (underlying, expiry) موجود در Snapshot اجرا و نتایج را در
    یک رتبه‌بندی واحد ادغام می‌کند. امتیازدهی دقیقاً همان منطق موجود است.

    strategies: اگر داده شود، فقط همین نام‌ها نگه داشته می‌شوند.
    خروجی: DataFrame مرتب‌شده بر اساس score (نزولی).
    """
    weights = weights or DEFAULT_WEIGHTS
    if chain_df is None or chain_df.empty:
        return pd.DataFrame()

    frames = []
    for (underlying, expiry), group in chain_df.groupby(["underlying", "expiry"]):
        # مرجع قیمت: قیمت واقعی دارایی پایه. اگر موجود نباشد این جفت را
        # کنار می‌گذاریم — با میانه Strike جایگزین نمی‌کنیم چون آن یک
        # قیمتِ ساختگی است و Moneyness/POP را بی‌معنا می‌کند.
        s_ref = None
        if "underlying_close" in group.columns and group["underlying_close"].notna().any():
            s_ref = float(group["underlying_close"].dropna().iloc[0])
        if not s_ref or s_ref <= 0:
            continue

        res = detect_strategy_opportunities(group, underlying, expiry, s_ref, r, weights)
        if not res.empty:
            res = res.copy()
            res["spot"] = s_ref
            frames.append(res)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    if strategies:
        out = out[out["strategy"].isin(strategies)]
    if out.empty:
        return out
    return out.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)


def universe_coverage(chain_df: pd.DataFrame) -> dict:
    """
    گزارش شفاف پوشش اسکن: چند جفت (نماد، سررسید) قابل‌بررسی بودند و چند تا
    به‌دلیل نبود قیمت دارایی پایه کنار گذاشته شدند. برای اینکه UI بتواند
    صادقانه بگوید اسکن روی چه بخشی از بازار انجام شده.
    """
    if chain_df is None or chain_df.empty:
        return {"total_pairs": 0, "scanned_pairs": 0, "skipped_no_spot": 0}

    total = skipped = 0
    for _, group in chain_df.groupby(["underlying", "expiry"]):
        total += 1
        has_spot = ("underlying_close" in group.columns
                    and group["underlying_close"].notna().any()
                    and float(group["underlying_close"].dropna().iloc[0]) > 0)
        if not has_spot:
            skipped += 1
    return {"total_pairs": total, "scanned_pairs": total - skipped, "skipped_no_spot": skipped}
