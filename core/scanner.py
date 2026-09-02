"""
موتور Scanner - فیلتر کردن Dynamic کل Dataset (بدون بررسی دستی تک‌تک
قراردادها) به‌علاوه Presetهای آماده.

اصل مهم: یک Preset فقط وقتی روی داده اعمال می‌شود که ستون لازم برای آن
واقعاً در Dataset موجود و غیر-خالی باشد؛ در غیر این صورت آن Preset را
"غیرقابل‌اجرا روی این داده" اعلام می‌کنیم، نه اینکه ساکت نتیجه غلط بدهیم.
"""
import numpy as np
import pandas as pd


def _col_usable(df: pd.DataFrame, col: str, min_non_null: int = 3) -> bool:
    return col in df.columns and df[col].notna().sum() >= min_non_null


def available_filters(df: pd.DataFrame) -> dict:
    """چه فیلترهایی روی این Dataset معنا دارند (بر اساس ستون‌های واقعاً موجود)."""
    return {
        "underlying": "underlying" in df.columns,
        "option_type": "option_type" in df.columns,
        "expiry": "expiry" in df.columns,
        "dte": _col_usable(df, "dte"),
        "strike": _col_usable(df, "strike"),
        "iv": _col_usable(df, "iv"),
        "open_interest": _col_usable(df, "open_interest"),
        "volume": _col_usable(df, "volume"),
        "close": _col_usable(df, "close"),
        "delta": _col_usable(df, "delta"),
        "moneyness": _col_usable(df, "moneyness", min_non_null=1),
        # معیارهای مشتق ATLAS
        "oi_change": _col_usable(df, "oi_change"),
        "spread_pct": _col_usable(df, "spread_pct"),
        "volume_oi_ratio": _col_usable(df, "volume_oi_ratio"),
        "premium_yield_annual_pct": _col_usable(df, "premium_yield_annual_pct"),
        "breakeven_distance_pct": _col_usable(df, "breakeven_distance_pct"),
        "traded_today": "traded_today" in df.columns,
    }


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    فیلترهای Dynamic. filters یک dict است، هر کلید اختیاری:
      underlying (list), option_type (list), expiry (list),
      dte_min/dte_max, strike_min/strike_max, iv_min/iv_max,
      oi_min, volume_min, price_min/price_max, delta_min/delta_max,
      oi_change_pct_min/max, spread_pct_min/max, volume_oi_min/max,
      yield_min/max, be_distance_min/max, traded_today (bool),
      moneyness (list)
    """
    out = df.copy()
    if not filters:
        return out

    if filters.get("underlying"):
        out = out[out["underlying"].isin(filters["underlying"])]
    if filters.get("option_type"):
        out = out[out["option_type"].isin(filters["option_type"])]
    if filters.get("expiry"):
        out = out[out["expiry"].isin(filters["expiry"])]
    if filters.get("moneyness"):
        out = out[out["moneyness"].isin(filters["moneyness"])]

    def _range(colname, lo_key, hi_key):
        nonlocal out
        if colname not in out.columns:
            return
        lo, hi = filters.get(lo_key), filters.get(hi_key)
        if lo is not None:
            out = out[out[colname] >= lo]
        if hi is not None:
            out = out[out[colname] <= hi]

    _range("dte", "dte_min", "dte_max")
    _range("strike", "strike_min", "strike_max")
    _range("iv", "iv_min", "iv_max")
    _range("close", "price_min", "price_max")
    _range("delta", "delta_min", "delta_max")

    # معیارهای مشتق ATLAS
    _range("oi_change_pct", "oi_change_pct_min", "oi_change_pct_max")
    _range("spread_pct", "spread_pct_min", "spread_pct_max")
    _range("volume_oi_ratio", "volume_oi_min", "volume_oi_max")
    _range("premium_yield_annual_pct", "yield_min", "yield_max")
    _range("breakeven_distance_pct", "be_distance_min", "be_distance_max")

    if filters.get("oi_min") is not None and "open_interest" in out.columns:
        out = out[out["open_interest"] >= filters["oi_min"]]
    if filters.get("volume_min") is not None and "volume" in out.columns:
        out = out[out["volume"] >= filters["volume_min"]]

    # فیلتر «فقط قراردادهایی که امروز معامله شده‌اند».
    # در بازار ایران که چهارپنجم قراردادها روزانه معامله نمی‌شوند، این
    # پرکاربردترین فیلتر است: قیمت پایانی قرارداد بی‌معامله کهنه است و
    # IV و Greeks استخراج‌شده از آن قابل اتکا نیست.
    if filters.get("traded_today") and "traded_today" in out.columns:
        out = out[out["traded_today"] == True]  # noqa: E712

    return out


# ---------------------------------------------------------------------------
# Presetها - هر Preset یک تابع (df) -> df فیلترشده است تا بتواند بر اساس
# آمار واقعی همان Dataset (نه عدد ثابت دلخواه) تصمیم بگیرد.
# ---------------------------------------------------------------------------

def _preset_high_liquidity(df):
    if not (_col_usable(df, "volume") and _col_usable(df, "open_interest")):
        return None
    vol_thr = df["volume"].quantile(0.75)
    oi_thr = df["open_interest"].quantile(0.75)
    return df[(df["volume"] >= vol_thr) & (df["open_interest"] >= oi_thr)]


def _preset_high_iv(df):
    if not _col_usable(df, "iv"):
        return None
    thr = df["iv"].quantile(0.75)
    return df[df["iv"] >= thr]


def _preset_low_iv(df):
    if not _col_usable(df, "iv"):
        return None
    thr = df["iv"].quantile(0.25)
    return df[df["iv"] <= thr]


def _preset_high_oi(df):
    if not _col_usable(df, "open_interest"):
        return None
    thr = df["open_interest"].quantile(0.75)
    return df[df["open_interest"] >= thr]


def _preset_unusual_volume(df):
    """حجم به‌طور غیرعادی بالاتر از میانه همان نماد پایه (نسبت به بقیه قراردادهای همان Underlying)."""
    if not (_col_usable(df, "volume") and "underlying" in df.columns):
        return None
    med = df.groupby("underlying")["volume"].transform("median")
    med = med.replace(0, np.nan)
    ratio = df["volume"] / med
    return df[ratio >= 2.0]


def _preset_near_atm(df):
    """
    نزدیک‌ترین Strikeها به قیمت دارایی پایه خودشان (در بازه ۵٪ از Spot)، به‌جای
    تکیه بر تطابق دقیق ATM که به‌ندرت رخ می‌دهد. مقایسه Row-wise است چون
    Dataset ممکن است چند Underlying با Spot متفاوت داشته باشد.
    """
    if not (_col_usable(df, "strike") and "underlying_close" in df.columns and df["underlying_close"].notna().any()):
        return None
    valid = df[df["underlying_close"].notna() & (df["underlying_close"] > 0)]
    if valid.empty:
        return None
    band = 0.05 * valid["underlying_close"]
    return valid[(valid["strike"] - valid["underlying_close"]).abs() <= band]


def _preset_deep_otm(df):
    if not (_col_usable(df, "delta")):
        return None
    return df[df["delta"].abs() <= 0.15]


def _preset_cheap_options(df):
    if not _col_usable(df, "close"):
        return None
    thr = df["close"].quantile(0.25)
    return df[df["close"] <= thr]


def _preset_high_delta(df):
    if not _col_usable(df, "delta"):
        return None
    return df[df["delta"].abs() >= 0.7]


def _preset_low_theta(df):
    if not _col_usable(df, "theta"):
        return None
    return df[df["theta"].abs() <= df["theta"].abs().quantile(0.25)]


PRESETS = {
    "نقدشوندگی بالا (High Liquidity)": _preset_high_liquidity,
    "نوسان ضمنی بالا (High IV)": _preset_high_iv,
    "نوسان ضمنی پایین (Low IV)": _preset_low_iv,
    "موقعیت باز بالا (High OI)": _preset_high_oi,
    "حجم غیرعادی (Unusual Volume)": _preset_unusual_volume,
    "نزدیک قیمت فعلی (Near ATM)": _preset_near_atm,
    "خیلی دور از سود (Deep OTM)": _preset_deep_otm,
    "قراردادهای ارزان (Cheap Options)": _preset_cheap_options,
    "دلتای بالا (High Delta)": _preset_high_delta,
    "تتای پایین (Low Theta)": _preset_low_theta,
}


def apply_preset(df: pd.DataFrame, preset_name: str):
    """
    Returns: (result_df یا None, reason_if_none)
    None یعنی این Preset روی این Dataset قابل‌اجرا نیست (نه اینکه نتیجه‌اش خالی است).
    """
    fn = PRESETS.get(preset_name)
    if fn is None:
        return df.iloc[0:0], "Preset ناشناخته"
    result = fn(df)
    if result is None:
        return None, "داده لازم (ستون یا مقدار کافی) برای این Preset در Dataset موجود نیست."
    return result, None
