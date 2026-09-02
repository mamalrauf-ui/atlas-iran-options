"""
core/data/sync.py

هر بار کاربر روی «دریافت آخرین اطلاعات بازار» کلیک می‌کند (Manual-only،
طبق بخش ۱۴ سند)، این تابع اجرا و در sync_log ثبت می‌شود.
"""
from __future__ import annotations

import datetime as dt

from core import database
from core.data.providers.base import ProviderError
from core.data.snapshot import save_snapshot


def run_manual_sync(provider, dataset_name: str, underlying: str = None,
                    prefetched=None):
    """
    provider: نمونه‌ای از OptionsDataProvider (مثلاً TSETMCProvider())
    prefetched: اگر UI قبلاً داده را برای پیش‌نمایش گرفته، همان ذخیره می‌شود
        تا دوباره درخواست زده نشود و کاربر دقیقاً همان چیزی را ذخیره کند
        که دیده است.
    خروجی: dict گزارش کامل (برای نمایش مستقیم در UI)
    """
    started = dt.datetime.now()
    try:
        if prefetched is not None:
            options_df, underlying_df, fetch_report = prefetched
        else:
            options_df, underlying_df, fetch_report = provider.get_option_chain(underlying=underlying)
    except ProviderError as exc:
        finished = dt.datetime.now()
        database.record_sync(
            provider=provider.name, started_at=started.isoformat(timespec="seconds"),
            finished_at=finished.isoformat(timespec="seconds"), status="FAILED",
            records_received=0, records_valid=0, records_rejected=0, error=str(exc),
        )
        return {"status": "FAILED", "error": str(exc)}

    # ------------------------------------------------------------------
    # replace_existing=False حیاتی است.
    #
    # پیش‌فرض save_snapshot مقدار True است و کل Dataset را پاک می‌کند.
    # با آن، هر بار دریافت داده تمام Snapshotهای قبلی نابود می‌شد و
    # مجموعه همیشه فقط یک روز داشت — که باعث می‌شد بک‌تست بگوید
    # «فقط ۱ Snapshot موجود است» و HV و همه سیگنال‌های تغییر هم
    # هرگز قابل محاسبه نباشند.
    #
    # برای جلوگیری از رکورد تکراری، Snapshot همان تاریخ ابتدا حذف
    # می‌شود، نه کل تاریخچه.
    quote_dates = []
    if options_df is not None and not options_df.empty and "quote_date" in options_df.columns:
        quote_dates = sorted({str(d) for d in options_df["quote_date"].dropna().unique()})
    replaced_rows = 0
    for qd in quote_dates:
        replaced_rows += database.delete_snapshot(dataset_name, qd)

    snap_report = save_snapshot(options_df, underlying_df, dataset_name,
                                replace_existing=False)
    snap_report["replaced_rows"] = replaced_rows
    snap_report["quote_dates"] = quote_dates
    finished = dt.datetime.now()

    status = "SUCCESS" if snap_report["records_valid"] > 0 else "PARTIAL"
    database.record_sync(
        provider=provider.name, started_at=started.isoformat(timespec="seconds"),
        finished_at=finished.isoformat(timespec="seconds"), status=status,
        records_received=snap_report["records_received"],
        records_valid=snap_report["records_valid"],
        records_rejected=snap_report["records_rejected"],
        warnings=snap_report["warnings"], error=None,
    )
    return {"status": status, "fetch_report": fetch_report, "snapshot_report": snap_report}
