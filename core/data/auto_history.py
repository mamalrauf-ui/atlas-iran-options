"""
تاریخچه خودکار — تاریخچه هر نماد از سرویس گرفته می‌شود، نه از Snapshotهای
دستی کاربر.

منطق قبلی این بود که کاربر باید هر روز دستی Snapshot ذخیره کند تا بک‌تست و
تحلیل تاریخی کار کنند؛ یعنی عملاً تا چند هفته هیچ‌کدام قابل استفاده نبودند.
منطق جدید: با یک بار ذخیره، تاریخچه از سرویس فراخوانی می‌شود و از آن پس
فقط به‌روزرسانی تدریجی انجام می‌گیرد.

اصول:
  - افزایشی: فقط تاریخ‌های غایب گرفته می‌شوند، نه کل تاریخچه در هر بار.
  - مقاوم: خطای یک نماد بقیه را متوقف نمی‌کند.
  - محدود به سقف تاریخی ۱۴۰۵/۰۱/۰۱.
  - هرگز داده موجود بازنویسی یا تکرار نمی‌شود.
  - OI تاریخی وجود ندارد و None می‌ماند (هرگز صفر نمی‌شود).
  - منبع، خودِ TSETMC است (همان Endpoint تاریخچه روزانه) و از InsCode
    ذخیره‌شده استفاده می‌کند؛ هیچ پکیج شخص‌ثالثی لازم نیست.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from core import database
from core.data.historical import apply_historical_floor
from core.data.snapshot import save_snapshot

# سقف تعداد نماد در یک اجرا — جلوگیری از انتظار نیم‌ساعته ناخواسته
DEFAULT_MAX_SYMBOLS = 400


class HistoryUnavailable(Exception):
    """منبع تاریخچه در دسترس نیست — پیام قابل نمایش مستقیم در UI."""


def _provider():
    """
    Provider تاریخچه: مستقیم از TSETMC، بدون وابستگی به پکیج شخص‌ثالث.

    از همان InsCode‌ای استفاده می‌کند که هنگام دریافت دیده‌بان بازار ذخیره
    شده، پس نه نگاشت نماد لازم است نه نصب چیزی جز requests.
    """
    from core.data.providers.tsetmc_history import TSETMCHistoryProvider
    p = TSETMCHistoryProvider()
    health = p.health_check()
    if health["status"] == "NOT_INSTALLED":
        raise HistoryUnavailable(health["error"])
    return p


# ---------------------------------------------------------------------------
# تاریخچه دارایی پایه
# ---------------------------------------------------------------------------
def _underlying_ins_code(dataset: str, underlying: str):
    """شناسه ابزار دارایی پایه، از همان داده‌ای که هنگام دریافت زنده ذخیره شد."""
    df = database.load_data(dataset_name=dataset, underlying=underlying)
    if df.empty or "underlying_id" not in df.columns:
        return None
    vals = df["underlying_id"].dropna()
    return str(vals.iloc[0]) if not vals.empty else None


def sync_underlying_history(dataset: str, underlying: str, provider=None) -> dict:
    """
    تاریخچه قیمت یک دارایی پایه.

    این پایه‌ای‌ترین تاریخچه است: بدون آن نه HV محاسبه می‌شود، نه IV Rank،
    نه بک‌تست. و چون تعداد دارایی‌های پایه کم است (حدود ۲۰ نماد)، همیشه
    به‌صورت خودکار گرفته می‌شود.
    """
    provider = provider or _provider()
    ins_code = _underlying_ins_code(dataset, underlying)
    if not ins_code:
        return {"status": "FAILED", "underlying": underlying, "rows_added": 0,
                "error": "شناسه ابزار این دارایی پایه در دیتابیس نیست — "
                         "ابتدا یک بار داده زنده بازار را دریافت کنید."}
    try:
        ua_df = provider.get_daily_history(ins_code)
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAILED", "underlying": underlying, "error": str(exc),
                "rows_added": 0}

    if ua_df is None or ua_df.empty:
        return {"status": "NO_DATA", "underlying": underlying, "rows_added": 0}

    ua_df = apply_historical_floor(ua_df.copy(), "quote_date")
    if ua_df.empty:
        return {"status": "NO_DATA", "underlying": underlying, "rows_added": 0,
                "note": "همه ردیف‌ها پیش از سقف تاریخی ۱۴۰۵/۰۱/۰۱ بودند."}

    ua_df["underlying"] = underlying
    existing = database.load_underlying_data(dataset_name=dataset, underlying=underlying)
    have = set(existing["quote_date"].astype(str)) if not existing.empty else set()
    new_rows = ua_df[~ua_df["quote_date"].astype(str).isin(have)]
    if new_rows.empty:
        return {"status": "UP_TO_DATE", "underlying": underlying, "rows_added": 0,
                "days_total": len(have)}

    n = database.save_underlying_dataframe(
        new_rows[["quote_date", "underlying", "close"]], dataset, replace_existing=False)
    return {"status": "SUCCESS", "underlying": underlying, "rows_added": n,
            "days_total": len(have) + n}


# ---------------------------------------------------------------------------
# تاریخچه قراردادهای اختیار
# ---------------------------------------------------------------------------
def sync_contract_history(dataset: str, symbol: str, provider=None) -> dict:
    """
    تاریخچه یک قرارداد اختیار.

    متادیتای ثابت قرارداد (نماد پایه، نوع، قیمت اعمال، سررسید) از Snapshot
    زنده موجود در دیتابیس برداشته و روی ردیف‌های تاریخی مهر می‌شود، چون
    منبع تاریخچه فقط OHLCV می‌دهد.
    """
    provider = provider or _provider()
    meta = database.get_contract_metadata(dataset, symbol)
    if meta is None:
        return {"status": "FAILED", "symbol": symbol, "rows_added": 0,
                "error": "متادیتای این قرارداد در دیتابیس نیست."}
    if not meta.get("instrument_id"):
        return {"status": "FAILED", "symbol": symbol, "rows_added": 0,
                "error": "شناسه ابزار این قرارداد ثبت نشده است."}

    try:
        opt_df = provider.get_daily_history(meta["instrument_id"])
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAILED", "symbol": symbol, "rows_added": 0, "error": str(exc)}
    ua_df = None

    if opt_df is None or opt_df.empty:
        return {"status": "NO_DATA", "symbol": symbol, "rows_added": 0}

    opt_df = apply_historical_floor(opt_df.copy(), "quote_date")
    existing = database.get_existing_quote_dates(dataset, symbol=symbol)
    have = {str(d) for d in existing}
    opt_df = opt_df[~opt_df["quote_date"].astype(str).isin(have)]
    if opt_df.empty:
        return {"status": "UP_TO_DATE", "symbol": symbol, "rows_added": 0}

    opt_df["symbol"] = symbol
    opt_df["underlying"] = meta["underlying"]
    opt_df["option_type"] = meta["option_type"]
    opt_df["strike"] = meta["strike"]
    opt_df["expiry"] = meta["expiry"]
    opt_df["contract_size"] = meta.get("contract_size")
    opt_df["data_quality"] = "HISTORICAL"
    opt_df["source"] = "FIMA_HISTORICAL"
    # DTE هر روز نسبت به همان روز، نه نسبت به امروز — شرط نبود Look-Ahead
    exp = pd.to_datetime(opt_df["expiry"], errors="coerce")
    qd = pd.to_datetime(opt_df["quote_date"], errors="coerce")
    opt_df["dte"] = (exp - qd).dt.days
    # OI تاریخی در این منبع وجود ندارد → None می‌ماند، هرگز صفر نمی‌شود
    opt_df["open_interest"] = None

    ua_out = None
    if ua_df is not None and not ua_df.empty:
        ua_df = apply_historical_floor(ua_df.copy(), "quote_date")
        if not ua_df.empty:
            ua_df["underlying"] = meta["underlying"]
            ex_ua = database.load_underlying_data(dataset_name=dataset,
                                                  underlying=meta["underlying"])
            have_ua = set(ex_ua["quote_date"].astype(str)) if not ex_ua.empty else set()
            ua_out = ua_df[~ua_df["quote_date"].astype(str).isin(have_ua)]
            ua_out = ua_out[["quote_date", "underlying", "close"]] if not ua_out.empty else None

    rep = save_snapshot(opt_df, ua_out, dataset, replace_existing=False)
    return {"status": "SUCCESS" if rep["records_valid"] else "PARTIAL",
            "symbol": symbol, "rows_added": rep["records_saved"],
            "rows_rejected": rep["records_rejected"]}


# ---------------------------------------------------------------------------
# ارکستراسیون
# ---------------------------------------------------------------------------
def bootstrap_history(dataset: str, underlyings=None, include_contracts: bool = True,
                      max_symbols: int = DEFAULT_MAX_SYMBOLS,
                      progress=None) -> dict:
    """
    تاریخچه یک مجموعه را از سرویس می‌سازد.

    underlyings: اگر None باشد همه دارایی‌های پایه موجود در مجموعه.
    include_contracts: تاریخچه تک‌تک قراردادها هم گرفته شود یا فقط پایه‌ها.
        تاریخچه پایه برای HV و IV Rank کافی است و سریع است؛ تاریخچه قراردادها
        برای بک‌تست لازم است ولی یک درخواست به‌ازای هر نماد می‌خواهد.
    progress: callable(done, total, label)
    """
    started = dt.datetime.now()
    try:
        provider = _provider()
    except HistoryUnavailable as exc:
        return {"status": "UNAVAILABLE", "error": str(exc),
                "underlyings": [], "contracts": [], "rows_added": 0}

    options_df = database.load_data(dataset_name=dataset)
    if options_df.empty:
        return {"status": "NO_DATA", "error": "این مجموعه هیچ قراردادی ندارد.",
                "underlyings": [], "contracts": [], "rows_added": 0}

    if underlyings:
        options_df = options_df[options_df["underlying"].isin(underlyings)]
        targets = list(underlyings)
    else:
        targets = sorted(options_df["underlying"].dropna().unique())

    symbols = []
    if include_contracts:
        symbols = sorted(options_df["symbol"].dropna().unique())[:max_symbols]

    total = len(targets) + len(symbols)
    done = 0
    ua_results, ct_results = [], []

    for u in targets:
        if progress:
            progress(done, total, f"تاریخچه دارایی پایه: {u}")
        ua_results.append(sync_underlying_history(dataset, u, provider))
        done += 1

    for sym in symbols:
        if progress:
            progress(done, total, f"تاریخچه قرارداد: {sym}")
        ct_results.append(sync_contract_history(dataset, sym, provider))
        done += 1

    rows = (sum(r.get("rows_added", 0) for r in ua_results)
            + sum(r.get("rows_added", 0) for r in ct_results))
    failed = [r for r in (ua_results + ct_results) if r["status"] == "FAILED"]

    database.record_sync(
        provider="FIMA_HISTORICAL",
        started_at=started.isoformat(timespec="seconds"),
        finished_at=dt.datetime.now().isoformat(timespec="seconds"),
        status="SUCCESS" if rows else ("PARTIAL" if not failed else "FAILED"),
        records_received=total, records_valid=rows, records_rejected=len(failed),
        error=None if not failed else f"{len(failed)} نماد ناموفق",
    )

    return {
        "status": "SUCCESS" if rows else ("UP_TO_DATE" if not failed else "PARTIAL"),
        "underlyings": ua_results, "contracts": ct_results,
        "rows_added": rows, "failed": failed,
        "symbols_attempted": len(symbols), "underlyings_attempted": len(targets),
        "truncated": include_contracts and len(
            sorted(options_df["symbol"].dropna().unique())) > max_symbols,
    }


def history_coverage(dataset: str, underlying: str = None) -> dict:
    """
    وضعیت واقعی تاریخچه یک مجموعه — مبنای تصمیم UI که آیا بک‌تست/تحلیل
    تاریخی قابل اجراست یا باید پیشنهاد دریافت تاریخچه داده شود.
    """
    opts = database.load_data(dataset_name=dataset)
    und = database.load_underlying_data(dataset_name=dataset)
    if underlying:
        opts = opts[opts["underlying"] == underlying] if not opts.empty else opts
        und = und[und["underlying"] == underlying] if not und.empty else und

    opt_dates = sorted(opts["quote_date"].dropna().astype(str).unique()) if not opts.empty else []
    und_dates = sorted(und["quote_date"].dropna().astype(str).unique()) if not und.empty else []
    covered = sorted(set(opt_dates) & set(und_dates))

    return {
        "option_days": len(opt_dates),
        "underlying_days": len(und_dates),
        "covered_days": len(covered),
        "covered": covered,
        "first": covered[0] if covered else None,
        "last": covered[-1] if covered else None,
        "symbols": int(opts["symbol"].nunique()) if not opts.empty else 0,
    }
