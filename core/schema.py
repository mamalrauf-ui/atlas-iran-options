"""
Canonical Data Model — مرجع واحد فیلدهای داده در سراسر ATLAS.

هدف: هیچ Provider (TSETMC زنده، Excel، ...) مستقیماً به Core/UI متصل
نمی‌شود؛ همه چیز از این Schema عبور می‌کند. این فایل هیچ منطق دریافت
داده‌ای ندارد — فقط قرارداد (Contract) بین لایه‌هاست.

طبق اصل «Missing Data ≠ Zero»: هر فیلدی که واقعاً موجود نیست باید
None/NaN باشد، نه صفر.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# وضعیت کیفیت داده — برای هر Metric مشخص می‌کند از کجا آمده و چقدر می‌شود
# به آن اعتماد کرد (بخش ۳۴ سند).
# ---------------------------------------------------------------------------
class DataQuality:
    CALCULATED = "CALCULATED"                          # توسط خود Atlas محاسبه شده (مثل IV, Greeks)
    IMPORTED = "IMPORTED"                               # از فایل اکسل وارد شده
    LIVE = "LIVE"                                        # لحظه‌ای از TSETMC
    HISTORICAL = "HISTORICAL"                            # از Snapshotهای ذخیره‌شده گذشته
    UNAVAILABLE = "UNAVAILABLE"                          # اصلاً در دسترس نیست
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"        # داده هست ولی برای این Metric کافی نیست
    STALE = "STALE"                                      # داده قدیمی است (Snapshot تازه نیست)


class DataSource:
    TSETMC_LIVE = "TSETMC_LIVE"
    TSETMC_HISTORY = "TSETMC_HISTORY"   # تاریخچه روزانه از خود TSETMC
    FIMA_HISTORICAL = "FIMA_HISTORICAL"  # مسیر جایگزین (اختیاری)
    EXCEL_IMPORT = "EXCEL_IMPORT"
    TSE_SCREENER_IMPORT = "TSE_SCREENER_IMPORT"
    UNDERLYING_IMPORT = "UNDERLYING_IMPORT"
    ATLAS_CALCULATED = "ATLAS_CALCULATED"


class ExerciseStyle:
    EUROPEAN = "European"  # بازار اختیار معامله ایران؛ Early Exercise در موتور لحاظ نمی‌شود.


class IVPriceSource:
    """قیمتی که برای محاسبه IV استفاده شده — بخش ۱۵ سند (اولویت: MID > LAST > CLOSE)."""
    MID = "MID"
    LAST = "LAST"
    CLOSE = "CLOSE"


# ---------------------------------------------------------------------------
# ستون‌های Canonical جدول options_data
# (RAW = مستقیماً از یک Provider می‌آید | DERIVED = توسط Atlas محاسبه می‌شود)
# ---------------------------------------------------------------------------
RAW_OPTION_FIELDS = [
    "instrument_id",       # شناسه پایدار قرارداد (فعلاً InsCode خود TSETMC)
    "underlying_id",       # شناسه پایدار دارایی پایه (uaInsCode)
    "symbol", "underlying", "option_type", "strike", "expiry",
    "contract_size", "exercise_style",
    "open", "high", "low",
    "close", "previous_close", "bid", "ask", "bid_size", "ask_size",
    "volume", "trade_count", "turnover",
    "open_interest", "previous_open_interest",
    "source", "data_quality", "snapshot_timestamp",
]

DERIVED_OPTION_FIELDS = [
    "dte", "oi_change",
    "iv", "iv_source", "iv_price_source", "iv_confidence",
    "delta", "gamma", "theta", "vega", "rho",
    "intrinsic_value", "time_value", "moneyness",
]

CANONICAL_OPTION_FIELDS = RAW_OPTION_FIELDS + DERIVED_OPTION_FIELDS

# فیلدهایی که همیشه باید وجود داشته باشند (بدونشان یک ردیف قرارداد بی‌معناست)
REQUIRED_OPTION_FIELDS = ["quote_date", "underlying", "option_type", "strike", "expiry", "close"]

RAW_UNDERLYING_FIELDS = [
    "instrument_id", "underlying", "open", "high", "low",
    "close", "previous_close", "volume",
    "source", "snapshot_timestamp",
]

# ستون‌هایی که قبل از این آپدیت هم در Database بودند — هرگز نباید حذف/تغییرنام شوند
LEGACY_OPTION_COLUMNS = [
    "dataset", "quote_date", "symbol", "underlying", "option_type",
    "strike", "expiry", "dte", "close", "bid", "ask",
    "volume", "open_interest", "iv",
    "delta", "gamma", "theta", "vega", "rho",
]

LEGACY_UNDERLYING_COLUMNS = ["dataset", "quote_date", "underlying", "close"]
