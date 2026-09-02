"""
core/data/historical.py

بخش ۱۱-۱۲ سند: محدودیت سخت‌گیرانه تاریخ شروع Historical Data + Sync تدریجی
(فقط تاریخ‌های غایب دریافت شوند، نه کل تاریخچه هر بار).
"""
from __future__ import annotations

import datetime as dt

# طبق دستور صریح سند: هیچ داده تاریخی قبل از این تاریخ دریافت/وارد نشود.
# ۱۴۰۵/۰۱/۰۱ (شمسی) = ۲۰۲۶-۰۳-۲۱ (میلادی)
HISTORICAL_START_DATE_JALALI = "1405/01/01"
HISTORICAL_START_DATE = dt.date(2026, 3, 21)


def apply_historical_floor(df, date_column: str = "quote_date"):
    """
    هر ردیفی با تاریخ قبل از HISTORICAL_START_DATE را حذف می‌کند (Filter Out
    طبق بخش ۱۱ سند) — نه اینکه صرفاً هشدار بدهد؛ سند صراحتاً می‌گوید
    داده قدیمی‌تر نباید وارد سیستم شود.
    """
    import pandas as pd
    if df is None or df.empty or date_column not in df.columns:
        return df
    dates = pd.to_datetime(df[date_column], errors="coerce").dt.date
    mask = dates >= HISTORICAL_START_DATE
    return df[mask].copy()


def _stamp_metadata(option_df, meta: dict, dataset_name: str):
    """ردیف‌های تاریخی خروجی FimaProvider فقط OHLCV دارند؛ ستون‌های ثابت
    قرارداد (underlying/option_type/strike/expiry) که Fima برنمی‌گرداند
    و برای اسکیمای options_data ضروری‌اند (validator.REQUIRED_FIELDS) اینجا
    از متادیتای شناخته‌شده همان نماد (از یک Snapshot زنده موجود) روی ردیف‌ها
    Stamp می‌شود. dte هم از تفاضل expiry - quote_date محاسبه می‌شود.
    """
    import pandas as pd
    df = option_df.copy()
    df["underlying"] = meta["underlying"]
    df["option_type"] = meta["option_type"]
    df["strike"] = meta["strike"]
    df["expiry"] = meta["expiry"]
    df["instrument_id"] = None
    df["data_quality"] = "HISTORICAL"
    expiry_d = pd.to_datetime(meta["expiry"], errors="coerce")
    qd = pd.to_datetime(df["quote_date"], errors="coerce")
    df["dte"] = (expiry_d - qd).dt.days
    return df


def sync_history_for_symbol(dataset_name: str, symbol: str, provider=None) -> dict:
    """Sync تدریجی تاریخچه یک نماد اختیار معامله (بخش ۱۲ سند): فقط تاریخ‌های
    غایب را از FimaProvider می‌گیرد و به همان Dataset اضافه (append) می‌کند؛
    داده موجود هرگز بازنویسی/تکرار نمی‌شود.

    Returns: dict گزارش — در صورت خطا status=FAILED با پیام واضح (هیچ‌وقت
    Exception خام به بالادست پرتاب نمی‌شود، طبق اصل «Never Silently Fail
    ولی هم هیچ‌وقت داشبورد را نمی‌ترکاند»).
    """
    from core import database
    from core.data.providers.fima import FimaProvider
    from core.data.snapshot import save_snapshot

    provider = provider or FimaProvider()
    meta = database.get_contract_metadata(dataset_name, symbol)
    if meta is None:
        return {"status": "FAILED", "symbol": symbol,
                "error": f"متادیتای قرارداد «{symbol}» در Dataset «{dataset_name}» یافت نشد "
                         "(باید حداقل یک Snapshot زنده از این نماد قبلاً ذخیره شده باشد)."}

    try:
        option_df, underlying_df, fetch_report = provider.get_historical(symbol)
    except Exception as exc:  # noqa: BLE001 - خطای Provider شخص‌ثالث
        return {"status": "FAILED", "symbol": symbol, "error": str(exc)}

    if option_df is None or option_df.empty:
        return {"status": "NO_DATA", "symbol": symbol, "records_saved": 0}

    existing_dates = database.get_existing_quote_dates(dataset_name, symbol=symbol)
    available_dates = option_df["quote_date"].dropna().unique().tolist()
    missing = set(find_missing_dates(existing_dates, available_dates))
    if not missing:
        return {"status": "UP_TO_DATE", "symbol": symbol, "records_saved": 0}

    option_df = option_df[option_df["quote_date"].isin(missing)].copy()
    option_df = _stamp_metadata(option_df, meta, dataset_name)

    if underlying_df is not None and not underlying_df.empty:
        underlying_df = underlying_df.copy()
        underlying_df["underlying"] = meta["underlying"]
        underlying_df = underlying_df[underlying_df["quote_date"].isin(missing)]

    snap_report = save_snapshot(option_df, underlying_df, dataset_name, replace_existing=False)
    return {
        "status": "SUCCESS" if snap_report["records_valid"] > 0 else "PARTIAL",
        "symbol": symbol,
        "dates_added": sorted(missing),
        **snap_report,
    }


def sync_history_for_underlying(dataset_name: str, underlying: str, provider=None,
                                 progress_callback=None) -> dict:
    """نسخه دسته‌ای: تاریخچه همه نمادهای یک دارایی پایه در یک Dataset را
    Sync می‌کند. هر نماد مستقل پردازش می‌شود تا خطای یک نماد بقیه را متوقف
    نکند (بخش ۴۳ سند)."""
    from core import database
    from core.data.providers.fima import FimaProvider

    provider = provider or FimaProvider()
    symbols = database.list_symbols(dataset_name, underlying)

    results = []
    for i, sym in enumerate(symbols):
        res = sync_history_for_symbol(dataset_name, sym, provider=provider)
        results.append(res)
        if progress_callback:
            progress_callback(i + 1, len(symbols), sym, res)

    saved = sum(r.get("records_saved", 0) for r in results)
    failed = [r for r in results if r["status"] == "FAILED"]
    return {
        "underlying": underlying,
        "symbols_processed": len(symbols),
        "records_saved": saved,
        "failed_symbols": [(r["symbol"], r["error"]) for r in failed],
        "details": results,
    }


def find_missing_dates(existing_dates: list, available_dates: list) -> list:
    """
    برای Sync تدریجی (بخش ۱۲ سند): فقط تاریخ‌هایی که در Provider موجودند
    ولی در Database نیستند را برمی‌گرداند. idempotent و duplicate-safe —
    اگر existing_dates خالی باشد، همه available_dates (که از سقف تاریخی
    فیلتر نشده باشند) برگردانده می‌شوند.
    """
    existing = {str(d) for d in existing_dates}
    floor = HISTORICAL_START_DATE
    missing = []
    for d in available_dates:
        d_obj = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))
        if d_obj < floor:
            continue
        if str(d_obj) not in existing:
            missing.append(str(d_obj))
    return sorted(missing)
