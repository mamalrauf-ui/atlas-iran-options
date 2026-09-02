"""
موتور Market Snapshot / Signals / Brief — قلب داشبورد EOD.

اصل حاکم (بخش ۲۶ و ۷۵ Master Prompt):
    Data → Rules/Analytics → Brief
هیچ جمله‌ای بدون پشتوانه عددیِ واقعاً محاسبه‌شده تولید نمی‌شود، هیچ سرویس
هوش‌مصنوعی بیرونی لازم نیست، و اگر داده کافی نباشد به‌جای پرکردن صفحه،
صراحتاً None/«داده کافی نیست» برمی‌گردد.

این ماژول عمداً در core است، نه در ui: صفحه فقط نتیجه را رندر می‌کند.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# آستانه‌های قابل‌تنظیم قوانین. اینها «وزن اختراعی» برای Score نیستند؛
# صرفاً حد آماری اعلام یک رویداد هستند و در UI هم شفاف اعلام می‌شوند.
THRESHOLDS = {
    "volume_move_pct": 15.0,      # تغییر معنادار حجم کل بازار
    "oi_move_pct": 5.0,           # تغییر معنادار موقعیت باز کل
    "iv_move_pct": 5.0,           # تغییر معنادار میانگین IV (نسبی)
    "contract_iv_expansion": 10.0,  # رشد IV یک قرارداد (نسبی، درصد)
    "contract_oi_buildup": 25.0,    # رشد OI یک قرارداد (درصد)
    "unusual_volume_x": 2.5,        # حجم نسبت به میانه هم‌گروه
    "iv_hv_high": 1.30,             # IV بالاتر از HV
    "iv_hv_low": 0.80,              # IV پایین‌تر از HV
    "cp_ratio_high": 1.50,
    "cp_ratio_low": 0.67,
    "min_group_size": 3,            # حداقل اندازه گروه برای مقایسه نسبی
    "atm_band_pct": 2.0,            # باند ATM حول قیمت پایه (بخش ۱۱)
}


# ---------------------------------------------------------------------------
# کمکی‌ها
# ---------------------------------------------------------------------------
def _sum_or_none(s: pd.Series):
    """جمع ستون؛ اگر هیچ مقدار معتبری نباشد None (نه صفرِ گمراه‌کننده)."""
    if s is None or s.dropna().empty:
        return None
    return float(s.dropna().sum())


def _mean_or_none(s: pd.Series):
    if s is None or s.dropna().empty:
        return None
    return float(s.dropna().mean())


def _median_or_none(s: pd.Series):
    """
    میانه به‌جای میانگین برای نوسان ضمنی.

    در بازار اختیار ایران، قراردادهای بسیار کم‌قیمت و دور از سررسید
    IVهای ۲۰۰٪ و بالاتر تولید می‌کنند. میانگین این مقادیر پرت، «نوسان
    ضمنی بازار» را به‌شدت بالاتر از واقع نشان می‌دهد — عددی که اگر مبنای
    تصمیم قرار بگیرد، بازار را گران‌تر از آنچه هست جلوه می‌دهد.
    میانه در برابر این مقادیر پرت مقاوم است.
    """
    if s is None or s.dropna().empty:
        return None
    return float(s.dropna().median())


def _pct_change(cur, prev):
    if cur is None or prev in (None, 0) or prev is None:
        return None
    return (cur - prev) / abs(prev) * 100.0


def moneyness_bucket(option_type: str, strike: float, spot, band_pct: float = None) -> str | None:
    """
    طبقه‌بندی ITM/ATM/OTM با باند درصدی.

    چرا اینجا و نه pricing.moneyness_status؟ آن تابع فقط برابری دقیق را ATM
    می‌گیرد (abs(K-S) < 1e-9) که در عمل هرگز رخ نمی‌دهد و ATM را در کل محصول
    نامرئی می‌کند. منطق قیمت‌گذاری موجود دست‌نخورده می‌ماند و این لایه فقط
    برای «نمایش/فیلتر» است.
    """
    if spot is None or strike is None:
        return None
    try:
        spot = float(spot)
        strike = float(strike)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(spot) or not np.isfinite(strike) or spot <= 0:
        return None

    band = (band_pct if band_pct is not None else THRESHOLDS["atm_band_pct"]) / 100.0
    if abs(strike - spot) / spot <= band:
        return "ATM"
    if option_type == "call":
        return "ITM" if spot > strike else "OTM"
    return "ITM" if spot < strike else "OTM"


def add_moneyness_bucket(df: pd.DataFrame, band_pct: float = None) -> pd.DataFrame:
    """ستون moneyness_bucket را به زنجیره اضافه می‌کند (ITM/ATM/OTM/None)."""
    out = df.copy()
    if out.empty:
        out["moneyness_bucket"] = pd.Series(dtype=object)
        return out
    spot_col = "underlying_close" if "underlying_close" in out.columns else None
    if spot_col is None:
        out["moneyness_bucket"] = None
        return out
    out["moneyness_bucket"] = [
        moneyness_bucket(t, k, s, band_pct)
        for t, k, s in zip(out["option_type"], out["strike"], out[spot_col])
    ]
    return out


def market_hv(underlying_hist: pd.DataFrame, min_points: int = 5):
    """
    HV بازار = میانگین HV هر نماد به‌صورت جداگانه.

    باگ رفع‌شده: محاسبه قبلی کل underlying_data را بدون groupby مرتب و
    log-return می‌گرفت، یعنی بازده بین قیمت دو نماد متفاوت هم وارد فرمول
    می‌شد و عدد بی‌معنا می‌داد.
    خروجی: (hv, n_symbols_used) — اگر داده کافی نباشد (None, 0).
    """
    if underlying_hist is None or underlying_hist.empty:
        return None, 0

    hvs = []
    for _, g in underlying_hist.groupby("underlying"):
        g = g.dropna(subset=["close"]).sort_values("quote_date")
        g = g[g["close"] > 0]
        if len(g) < min_points:
            continue
        ret = np.log(g["close"].astype(float) / g["close"].astype(float).shift(1)).dropna()
        if len(ret) < min_points - 1:
            continue
        sd = ret.std(ddof=1)
        if pd.notna(sd) and sd > 0:
            hvs.append(float(sd) * np.sqrt(252))

    if not hvs:
        return None, 0
    return float(np.mean(hvs)), len(hvs)


# ---------------------------------------------------------------------------
# ۱) شش KPI ثابت داشبورد (بخش ۲۵ — ترتیب هرگز تغییر نمی‌کند)
# ---------------------------------------------------------------------------
def compute_kpis(chain: pd.DataFrame, prior_chain: pd.DataFrame | None,
                 underlying_hist: pd.DataFrame | None) -> dict:
    """
    خروجی: dict با کلیدهای ثابت. هر KPI شامل value، change_pct و
    direction_meaningful (آیا رنگ سبز/قرمز برای تغییرش معنا دارد یا نه).
    """
    def kpi(value, change=None, meaningful=True, note=None):
        return {"value": value, "change_pct": change,
                "direction_meaningful": meaningful, "note": note}

    vol = _sum_or_none(chain.get("volume"))
    oi = _sum_or_none(chain.get("open_interest"))
    iv = _median_or_none(chain.get("iv"))
    active = int(len(chain)) if not chain.empty else 0

    p_vol = p_oi = p_iv = p_active = None
    if prior_chain is not None and not prior_chain.empty:
        p_vol = _sum_or_none(prior_chain.get("volume"))
        p_oi = _sum_or_none(prior_chain.get("open_interest"))
        p_iv = _median_or_none(prior_chain.get("iv"))
        p_active = int(len(prior_chain))

    # Call/Put حجم
    call_vol = _sum_or_none(chain[chain["option_type"] == "call"].get("volume"))
    put_vol = _sum_or_none(chain[chain["option_type"] == "put"].get("volume"))
    cp = round(call_vol / put_vol, 2) if (call_vol is not None and put_vol) else None
    cp_note = None
    if cp is None and (call_vol is None or put_vol is None):
        cp_note = "برای این Snapshot داده حجم هر دو سمت Call و Put موجود نیست."

    # IV/HV
    hv, n_sym = market_hv(underlying_hist)
    iv_hv = round(iv / hv, 2) if (iv is not None and hv) else None
    iv_hv_note = None
    if iv_hv is None:
        iv_hv_note = "برای محاسبه HV حداقل ۵ Snapshot قیمت دارایی پایه لازم است."
    else:
        iv_hv_note = f"HV بازار: {hv * 100:.1f}% (میانگین {n_sym} نماد)"

    return {
        "total_volume": kpi(vol, _pct_change(vol, p_vol)),
        "total_oi": kpi(oi, _pct_change(oi, p_oi)),
        "avg_iv": kpi(iv, _pct_change(iv, p_iv), meaningful=False,
                      note="میانه نوسان ضمنی استفاده می‌شود، نه میانگین — "
                           "چون قراردادهای کم‌قیمت IVهای پرت تولید می‌کنند. "
                           "افزایش IV هم ذاتاً مثبت یا منفی نیست."),
        "active_contracts": kpi(active, _pct_change(active, p_active), meaningful=False),
        "cp_ratio": kpi(cp, None, meaningful=False, note=cp_note),
        "iv_hv_ratio": kpi(iv_hv, None, meaningful=False, note=iv_hv_note),
        "_hv": hv,
    }


# ---------------------------------------------------------------------------
# ۲) سیگنال‌های بازار (بخش ۲۸) — هر سیگنال قابل Drill-down
# ---------------------------------------------------------------------------
def detect_signals(chain: pd.DataFrame, prior_chain: pd.DataFrame | None,
                   kpis: dict | None = None) -> list[dict]:
    """
    خروجی: لیستی از dict با کلیدهای:
        key, name, count, description, symbols (لیست نماد قرارداد), requires
    فقط سیگنال‌هایی برگردانده می‌شوند که داده لازمشان واقعاً موجود باشد.
    """
    signals: list[dict] = []
    if chain is None or chain.empty:
        return signals

    T = THRESHOLDS

    # --- سیگنال‌های نیازمند مقایسه با Snapshot قبلی ---
    if prior_chain is not None and not prior_chain.empty and "symbol" in chain.columns:
        prev_cols = [c for c in ["symbol", "iv", "open_interest", "close"] if c in prior_chain.columns]
        m = chain.merge(prior_chain[prev_cols], on="symbol", suffixes=("", "_prev"), how="inner")

        if not m.empty and "iv_prev" in m.columns:
            valid = m[(m["iv"].notna()) & (m["iv_prev"].notna()) & (m["iv_prev"] > 0)]
            if not valid.empty:
                grow = valid[(valid["iv"] - valid["iv_prev"]) / valid["iv_prev"] * 100 >= T["contract_iv_expansion"]]
                if len(grow):
                    signals.append({
                        "key": "iv_expansion", "name": "IV Expansion", "count": int(len(grow)),
                        "description": f"نوسان ضمنی این قراردادها نسبت به Snapshot قبلی حداقل {T['contract_iv_expansion']:.0f}٪ رشد کرده است.",
                        "symbols": grow["symbol"].dropna().tolist(),
                    })

        if not m.empty and "open_interest_prev" in m.columns:
            valid = m[(m["open_interest"].notna()) & (m["open_interest_prev"].notna()) & (m["open_interest_prev"] > 0)]
            if not valid.empty:
                build = valid[(valid["open_interest"] - valid["open_interest_prev"]) /
                              valid["open_interest_prev"] * 100 >= T["contract_oi_buildup"]]
                if len(build):
                    signals.append({
                        "key": "oi_buildup", "name": "OI Build-up", "count": int(len(build)),
                        "description": f"موقعیت باز این قراردادها حداقل {T['contract_oi_buildup']:.0f}٪ افزایش یافته — ورود پول جدید به این قراردادها.",
                        "symbols": build["symbol"].dropna().tolist(),
                    })

    # --- حجم غیرعادی: نسبت به میانه هم‌گروه (underlying, expiry, option_type) ---
    if "volume" in chain.columns and chain["volume"].notna().any():
        unusual = []
        for _, g in chain.groupby(["underlying", "expiry", "option_type"]):
            v = g["volume"].dropna()
            if len(v) < T["min_group_size"]:
                continue
            med = v.median()
            if not med or med <= 0:
                continue
            hit = g[g["volume"] >= med * T["unusual_volume_x"]]
            unusual.extend(hit["symbol"].dropna().tolist())
        if unusual:
            signals.append({
                "key": "unusual_volume", "name": "Unusual Volume", "count": len(unusual),
                "description": f"حجم معاملات حداقل {T['unusual_volume_x']}برابر میانه قراردادهای هم‌گروه (همان نماد، سررسید و نوع).",
                "symbols": unusual,
            })

    # --- واگرایی IV/HV در سطح بازار ---
    if kpis and kpis.get("iv_hv_ratio", {}).get("value") is not None:
        ratio = kpis["iv_hv_ratio"]["value"]
        if ratio >= T["iv_hv_high"]:
            signals.append({
                "key": "iv_hv_divergence_high", "name": "IV / HV Divergence", "count": None,
                "description": f"میانگین IV بازار {ratio} برابر HV است — اختیارها نسبت به نوسان تحقق‌یافته گران‌ترند.",
                "symbols": [],
            })
        elif ratio <= T["iv_hv_low"]:
            signals.append({
                "key": "iv_hv_divergence_low", "name": "IV / HV Divergence", "count": None,
                "description": f"میانگین IV بازار {ratio} برابر HV است — اختیارها نسبت به نوسان تحقق‌یافته ارزان‌ترند.",
                "symbols": [],
            })

    # --- عدم توازن Call/Put ---
    if kpis and kpis.get("cp_ratio", {}).get("value") is not None:
        cp = kpis["cp_ratio"]["value"]
        if cp >= T["cp_ratio_high"] or cp <= T["cp_ratio_low"]:
            side = "Call" if cp >= T["cp_ratio_high"] else "Put"
            signals.append({
                "key": "cp_skew", "name": "Call/Put Imbalance", "count": None,
                "description": f"نسبت حجم Call/Put برابر {cp} است؛ فعالیت به‌طور محسوس به سمت {side} متمایل شده.",
                "symbols": [],
            })

    return signals


# ---------------------------------------------------------------------------
# ۳) Market Brief (بخش ۲۶) — ۲ تا ۳ جمله، همه با پشتوانه عدد
# ---------------------------------------------------------------------------
def build_brief(kpis: dict, signals: list[dict], chain: pd.DataFrame,
                prior_chain: pd.DataFrame | None, prior_label: str | None = None) -> dict:
    """خروجی: {"sentences": [...], "chips": [{"text","tone"}...]}"""
    T = THRESHOLDS
    sentences: list[str] = []
    chips: list[dict] = []

    vol_ch = kpis["total_volume"]["change_pct"]
    oi_ch = kpis["total_oi"]["change_pct"]
    iv_ch = kpis["avg_iv"]["change_pct"]

    # جمله ۱ — فعالیت کلی
    if vol_ch is None:
        n_c = kpis["active_contracts"]["value"]
        n_u = chain["underlying"].nunique() if not chain.empty else 0
        sentences.append(
            f"این Snapshot شامل {n_c:,} قرارداد فعال روی {n_u} نماد پایه است. "
            "برای مقایسه با روز قبل و تولید تفسیر تغییرات، حداقل یک Snapshot تاریخی دیگر لازم است."
        )
    else:
        if vol_ch >= T["volume_move_pct"]:
            sentences.append(f"فعالیت بازار اختیار نسبت به Snapshot قبلی افزایش یافت؛ حجم کل {vol_ch:+.1f}٪ رشد کرد.")
            chips.append({"text": "Volume Expansion", "tone": "pos"})
        elif vol_ch <= -T["volume_move_pct"]:
            sentences.append(f"فعالیت بازار اختیار نسبت به Snapshot قبلی کاهش یافت؛ حجم کل {vol_ch:+.1f}٪ افت کرد.")
            chips.append({"text": "Volume Contraction", "tone": "neg"})
        else:
            sentences.append(f"حجم معاملات نسبت به Snapshot قبلی تغییر محسوسی نداشت ({vol_ch:+.1f}٪).")
            chips.append({"text": "Stable Volume", "tone": ""})

    # جمله ۲ — تمرکز فعالیت
    if "volume" in chain.columns and chain["volume"].notna().any():
        by_u = chain.groupby("underlying")["volume"].sum().sort_values(ascending=False)
        total = by_u.sum()
        # جمله تمرکز فقط وقتی خبر است که Top-3 زیرمجموعه واقعی بازار باشد؛
        # با ۳ نماد یا کمتر، «۱۰۰٪ حجم در ۳ نماد» یک این‌همان‌گویی است.
        if total and total > 0 and len(by_u) >= 5:
            top3 = by_u.head(3)
            share = top3.sum() / total * 100
            names = "، ".join(top3.index.tolist())
            sentences.append(
                f"{share:.0f}٪ از حجم بازار در ۳ نماد ({names}) از مجموع {len(by_u)} نماد متمرکز بود."
            )
            if share >= 70:
                chips.append({"text": "High Concentration", "tone": "warn"})

    # جمله ۳ — OI و IV
    parts = []
    if oi_ch is not None:
        if oi_ch >= T["oi_move_pct"]:
            parts.append(f"موقعیت باز کل {oi_ch:+.1f}٪ افزایش یافت")
            chips.append({"text": "OI Build-up", "tone": "pos"})
        elif oi_ch <= -T["oi_move_pct"]:
            parts.append(f"موقعیت باز کل {oi_ch:+.1f}٪ کاهش یافت")
            chips.append({"text": "OI Unwind", "tone": "neg"})
    if iv_ch is not None:
        if iv_ch >= T["iv_move_pct"]:
            parts.append(f"میانگین نوسان ضمنی {iv_ch:+.1f}٪ بالا رفت")
            chips.append({"text": "IV Expansion", "tone": ""})
        elif iv_ch <= -T["iv_move_pct"]:
            parts.append(f"میانگین نوسان ضمنی {iv_ch:+.1f}٪ پایین آمد")
            chips.append({"text": "IV Contraction", "tone": ""})
    if parts:
        sentences.append("همچنین " + " و ".join(parts) + ".")

    # اگر هیچ رویداد قابل‌ذکری نبود، جمله خنثی — نه متن پرکننده
    if len(sentences) == 1 and vol_ch is not None and not chips:
        sentences.append("هیچ رویداد آماری قابل‌توجه دیگری در این Snapshot شناسایی نشد.")

    if prior_label:
        sentences.append(f"مبنای مقایسه: Snapshot {prior_label}")

    return {"sentences": sentences, "chips": chips}


# ---------------------------------------------------------------------------
# ۴) Market Activity (بخش ۲۷)
# ---------------------------------------------------------------------------
def top_underlyings(chain: pd.DataFrame, prior_chain: pd.DataFrame | None, n: int = 6) -> pd.DataFrame:
    """رتبه‌بندی نمادهای پایه بر اساس حجم، همراه با تغییر OI نسبت به Snapshot قبلی."""
    if chain.empty:
        return pd.DataFrame()

    agg = {"contracts": ("symbol", "count")}
    if "volume" in chain.columns and chain["volume"].notna().any():
        agg["volume"] = ("volume", "sum")
    if "open_interest" in chain.columns and chain["open_interest"].notna().any():
        agg["open_interest"] = ("open_interest", "sum")
    if "iv" in chain.columns and chain["iv"].notna().any():
        agg["avg_iv"] = ("iv", "median")

    out = chain.groupby("underlying").agg(**agg).reset_index()
    sort_col = "volume" if "volume" in out.columns else ("open_interest" if "open_interest" in out.columns else "contracts")
    out = out.sort_values(sort_col, ascending=False).head(n)

    out["oi_change_pct"] = None
    if prior_chain is not None and not prior_chain.empty and "open_interest" in out.columns \
            and prior_chain["open_interest"].notna().any():
        prev = prior_chain.groupby("underlying")["open_interest"].sum()
        out["oi_change_pct"] = out["underlying"].map(
            lambda u: ((out.loc[out["underlying"] == u, "open_interest"].iloc[0] - prev[u]) / prev[u] * 100)
            if u in prev.index and prev[u] else None
        )
    return out.reset_index(drop=True)


def top_contracts(chain: pd.DataFrame, n: int = 6) -> pd.DataFrame:
    """پرمعامله‌ترین قراردادهای Snapshot جاری."""
    if chain.empty:
        return pd.DataFrame()
    sort_col = None
    if "volume" in chain.columns and chain["volume"].notna().any():
        sort_col = "volume"
    elif "open_interest" in chain.columns and chain["open_interest"].notna().any():
        sort_col = "open_interest"
    if sort_col is None:
        return pd.DataFrame()
    cols = [c for c in ["symbol", "underlying", "option_type", "strike", "volume",
                        "open_interest", "iv", "moneyness_bucket"] if c in chain.columns]
    return chain.nlargest(n, sort_col)[cols].reset_index(drop=True)
