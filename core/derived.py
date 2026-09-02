"""
معیارهای مشتق ATLAS — چیزهایی که خود Atlas از داده خام می‌سازد.

جدایی صریح از داده خام (بخش ۱۰ سند): هیچ‌کدام از این مقادیر از Provider
نمی‌آید؛ همه اینجا و روی داده ذخیره‌شده محاسبه می‌شوند. یعنی اگر فردا فرمولی
عوض شود، نیازی به دریافت دوباره داده خام نیست.

قاعده حاکم: هر معیاری که ورودی لازمش موجود نباشد None می‌ماند. هیچ‌جا
صفر جایگزین «نمی‌دانم» نمی‌شود.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# آستانه‌ها
WIDE_SPREAD_PCT = 15.0        # اسپرد نسبی بالاتر از این یعنی عملاً غیرقابل‌معامله
MIN_DAYS_FOR_IV_RANK = 5      # حداقل تعداد روز برای معنادار بودن IV Rank
STALE_QUOTE_DAYS = 3          # اگر چند روز معامله نشده باشد، هشدار


def _num(v):
    """مقدار عددی معتبر یا None. صفر معتبر است."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _pos(v):
    """مقدار عددی مثبت یا None (صفر هم None می‌شود)."""
    f = _num(v)
    return f if f is not None and f > 0 else None


# ---------------------------------------------------------------------------
# ۱) تغییر موقعیت باز — داده‌اش در پاسخ API هست ولی استفاده نمی‌شد
# ---------------------------------------------------------------------------
def oi_change(current_oi, previous_oi) -> dict:
    """
    تغییر OI نسبت به روز قبل.

    منبع previous_open_interest خود پاسخ TSETMC است (yesterdayOP)، پس
    برای محاسبه‌اش به Snapshot دیروز نیاز نیست و از همان روز اول کار می‌کند.

    خروجی: {"change", "change_pct", "direction"}
    direction: build_up (ورود پول) / unwind (خروج) / flat / None
    """
    cur = _num(current_oi)
    prev = _num(previous_oi)
    if cur is None or prev is None:
        return {"change": None, "change_pct": None, "direction": None}

    change = cur - prev
    # درصد فقط وقتی معنا دارد که پایه مثبت باشد؛ رشد از صفر بی‌نهایت است
    change_pct = (change / prev * 100.0) if prev > 0 else None
    if change > 0:
        direction = "build_up"
    elif change < 0:
        direction = "unwind"
    else:
        direction = "flat"
    return {"change": change, "change_pct": change_pct, "direction": direction}


# ---------------------------------------------------------------------------
# ۲) اسپرد و عمق مظنه
# ---------------------------------------------------------------------------
def spread_metrics(bid, ask, bid_size=None, ask_size=None, close=None) -> dict:
    """
    کیفیت مظنه: اسپرد مطلق، اسپرد نسبی، میانه، و توازن عمق دو سمت.

    عمق (bid_size/ask_size) در بازار کم‌عمق ایران مهم است: اسپرد باریک با
    حجم یک قرارداد در هر سمت، نقدشوندگی نیست.
    """
    b, a = _pos(bid), _pos(ask)
    out = {"spread": None, "spread_pct": None, "mid": None,
           "depth_imbalance": None, "is_wide": None, "is_one_sided": None}

    # یک‌طرفه بودن خودش اطلاعات است: فقط خریدار هست یا فقط فروشنده
    if (b is None) != (a is None):
        out["is_one_sided"] = True
    elif b is not None and a is not None:
        out["is_one_sided"] = False

    if b is not None and a is not None and a >= b:
        mid = (a + b) / 2
        out["spread"] = a - b
        out["mid"] = mid
        ref = mid if mid > 0 else _pos(close)
        if ref:
            out["spread_pct"] = (a - b) / ref * 100
            out["is_wide"] = out["spread_pct"] > WIDE_SPREAD_PCT

    bs, asz = _num(bid_size), _num(ask_size)
    if bs is not None and asz is not None and (bs + asz) > 0:
        # +1 یعنی همه عمق سمت خرید، -1 یعنی همه سمت فروش
        out["depth_imbalance"] = (bs - asz) / (bs + asz)
    return out


# ---------------------------------------------------------------------------
# ۳) گردش نسبت به موقعیت باز
# ---------------------------------------------------------------------------
def volume_oi_ratio(volume, open_interest) -> float | None:
    """
    نسبت حجم به موقعیت باز — نشانه اینکه معاملات امروز موقعیت‌سازی جدید
    بوده یا صرفاً جابه‌جایی بین معامله‌گران.

    مقدار بالا (مثلاً بیش از ۱) یعنی فعالیت امروز نسبت به موقعیت‌های موجود
    غیرعادی زیاد بوده.
    """
    v = _num(volume)
    oi = _pos(open_interest)
    if v is None or oi is None:
        return None
    return v / oi


# ---------------------------------------------------------------------------
# ۴) ارزش زمانی روزانه — هزینه واقعی نگهداری
# ---------------------------------------------------------------------------
def time_value_per_day(time_value, dte) -> float | None:
    """
    ارزش زمانی تقسیم بر روز باقی‌مانده: خریدار روزانه چقدر می‌پردازد و
    فروشنده روزانه چقدر دریافت می‌کند. برای مقایسه قراردادهایی با سررسید
    متفاوت، از خود ارزش زمانی گویاتر است.
    """
    tv = _num(time_value)
    d = _num(dte)
    if tv is None or d is None or d <= 0:
        return None
    return tv / d


def time_value_pct(time_value, close) -> float | None:
    """سهم ارزش زمانی از کل قیمت — چند درصد از پول بابت زمان است."""
    tv = _num(time_value)
    px = _pos(close)
    if tv is None or px is None:
        return None
    return tv / px * 100


# ---------------------------------------------------------------------------
# ۵) بازده تا سررسید برای فروشنده (پوشش‌داده‌شده)
# ---------------------------------------------------------------------------
def premium_yield(close, underlying_close, dte) -> dict:
    """
    بازده دریافتی فروشنده Call پوشش‌داده نسبت به ارزش دارایی پایه.

    خروجی شامل نسخه سالانه‌شده است تا قراردادهایی با سررسید متفاوت
    قابل مقایسه شوند. سالانه‌سازی خطی است (نه مرکب) چون فرض تکرار
    موقعیت در بازار کم‌عمق ایران واقع‌بینانه نیست و مرکب‌کردن عدد را
    خوش‌بینانه‌تر از واقع نشان می‌دهد.
    """
    px = _pos(close)
    spot = _pos(underlying_close)
    d = _num(dte)
    if px is None or spot is None:
        return {"yield_pct": None, "annualized_pct": None}
    y = px / spot * 100
    ann = (y * 365.0 / d) if (d is not None and d > 0) else None
    return {"yield_pct": y, "annualized_pct": ann}


# ---------------------------------------------------------------------------
# ۶) فاصله تا نقطه سربه‌سر
# ---------------------------------------------------------------------------
def breakeven_distance(option_type, strike, close, underlying_close) -> dict:
    """
    نقطه سربه‌سر خریدار در سررسید و فاصله درصدی قیمت فعلی تا آن.

    برای خریدار Call:  strike + premium
    برای خریدار Put :  strike - premium
    فاصله درصدی نشان می‌دهد دارایی پایه چقدر باید حرکت کند تا خریدار
    به نقطه سر‌به‌سر برسد.
    """
    k = _pos(strike)
    px = _num(close)
    spot = _pos(underlying_close)
    if k is None or px is None or spot is None:
        return {"breakeven": None, "distance_pct": None}
    be = k + px if option_type == "call" else k - px
    if be <= 0:
        return {"breakeven": None, "distance_pct": None}
    return {"breakeven": be, "distance_pct": (be - spot) / spot * 100}


# ---------------------------------------------------------------------------
# ۷) موقعیت نسبت به قیمت پایه (درصد)
# ---------------------------------------------------------------------------
def moneyness_pct(strike, underlying_close) -> float | None:
    """
    فاصله درصدی قیمت اعمال از قیمت دارایی پایه.
    مثبت = بالاتر از قیمت فعلی، منفی = پایین‌تر.
    برخلاف برچسب ITM/ATM/OTM، این عدد پیوسته و قابل مرتب‌سازی است.
    """
    k = _pos(strike)
    spot = _pos(underlying_close)
    if k is None or spot is None:
        return None
    return (k - spot) / spot * 100


# ---------------------------------------------------------------------------
# ۸) IV Rank و IV Percentile — نیازمند تاریخچه
# ---------------------------------------------------------------------------
def iv_rank(history_series, current_iv) -> dict:
    """
    جایگاه IV امروز در تاریخچه خودش.

    rank       = (امروز − کمینه) / (بیشینه − کمینه)
    percentile = درصد روزهایی که IV کمتر از امروز بوده

    اگر تاریخچه کافی نباشد None برمی‌گردد با دلیل — نه عددی که به نظر
    معتبر بیاید ولی روی ۲ روز داده بنا شده باشد.
    """
    cur = _num(current_iv)
    s = pd.Series(list(history_series)).dropna() if history_series is not None else pd.Series(dtype=float)
    if cur is None:
        return {"rank": None, "percentile": None, "n_days": len(s),
                "reason": "نوسان ضمنی امروز محاسبه نشده"}
    if len(s) < MIN_DAYS_FOR_IV_RANK:
        return {"rank": None, "percentile": None, "n_days": len(s),
                "reason": f"حداقل {MIN_DAYS_FOR_IV_RANK} روز تاریخچه لازم است "
                          f"({len(s)} روز موجود)"}
    lo, hi = float(s.min()), float(s.max())
    rank = None if hi == lo else (cur - lo) / (hi - lo) * 100
    return {"rank": rank, "percentile": float((s < cur).mean() * 100),
            "n_days": len(s), "reason": None}


# ---------------------------------------------------------------------------
# ۹) اعمال روی کل زنجیره
# ---------------------------------------------------------------------------
DERIVED_COLUMNS = [
    "oi_change", "oi_change_pct", "oi_direction",
    "spread", "spread_pct", "mid_price", "depth_imbalance", "quote_one_sided",
    "volume_oi_ratio", "time_value_per_day", "time_value_pct",
    "premium_yield_pct", "premium_yield_annual_pct",
    "breakeven", "breakeven_distance_pct", "moneyness_pct",
    "traded_today",
]


def enrich_derived(df: pd.DataFrame) -> pd.DataFrame:
    """
    افزودن همه معیارهای مشتق به یک زنجیره enrich‌شده.

    روی DataFrame خالی یا ناقص هم امن است: هر ستونی که ورودی‌اش نباشد
    پر از None می‌شود، نه صفر.
    """
    if df is None or df.empty:
        out = df.copy() if df is not None else pd.DataFrame()
        for col in DERIVED_COLUMNS:
            if col not in out.columns:
                out[col] = pd.Series(dtype=object)
        return out

    out = df.copy()
    get = lambda row, key: row[key] if key in row else None  # noqa: E731

    records = []
    for _, row in out.iterrows():
        oi = oi_change(get(row, "open_interest"), get(row, "previous_open_interest"))
        sp = spread_metrics(get(row, "bid"), get(row, "ask"),
                            get(row, "bid_size"), get(row, "ask_size"),
                            get(row, "close"))
        py = premium_yield(get(row, "close"), get(row, "underlying_close"), get(row, "dte"))
        be = breakeven_distance(get(row, "option_type"), get(row, "strike"),
                                get(row, "close"), get(row, "underlying_close"))
        vol = _num(get(row, "volume"))
        records.append({
            "oi_change": oi["change"], "oi_change_pct": oi["change_pct"],
            "oi_direction": oi["direction"],
            "spread": sp["spread"], "spread_pct": sp["spread_pct"],
            "mid_price": sp["mid"], "depth_imbalance": sp["depth_imbalance"],
            "quote_one_sided": sp["is_one_sided"],
            "volume_oi_ratio": volume_oi_ratio(get(row, "volume"), get(row, "open_interest")),
            "time_value_per_day": time_value_per_day(get(row, "time_value"), get(row, "dte")),
            "time_value_pct": time_value_pct(get(row, "time_value"), get(row, "close")),
            "premium_yield_pct": py["yield_pct"],
            "premium_yield_annual_pct": py["annualized_pct"],
            "breakeven": be["breakeven"], "breakeven_distance_pct": be["distance_pct"],
            "moneyness_pct": moneyness_pct(get(row, "strike"), get(row, "underlying_close")),
            # تفکیک صریح «امروز معامله نشد» از «حجم را نمی‌دانیم»
            "traded_today": (None if vol is None else bool(vol > 0)),
        })

    derived = pd.DataFrame(records, index=out.index)
    for col in derived.columns:
        out[col] = derived[col]
    return out
