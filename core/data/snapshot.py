"""
core/data/snapshot.py

مسیر واحد ورود داده به Database: هیچ داده‌ای مستقیماً وارد
core.database نمی‌شود، همیشه از validate → save عبور می‌کند.
"""
from __future__ import annotations

from core import database
from core.data.validator import validate_options_df


def save_snapshot(options_df, underlying_df, dataset_name: str, replace_existing: bool = False):
    """
    اعتبارسنجی + ذخیره یک Snapshot. رکوردهای نامعتبر ذخیره نمی‌شوند اما
    Silent هم نیستند — در گزارش برگشتی مشخص‌اند (بخش ۴۳ سند).

    Returns: dict گزارش (records_received/valid/rejected/warnings)
    """
    n_received = len(options_df) if options_df is not None else 0
    valid_mask, warnings = validate_options_df(options_df) if n_received else (None, ["ورودی خالی بود."])

    if n_received:
        valid_df = options_df[valid_mask].copy()
    else:
        valid_df = options_df

    n_valid = len(valid_df) if valid_df is not None else 0
    n_saved = database.save_dataframe(valid_df, dataset_name, replace_existing=replace_existing) if n_valid else 0

    n_underlying_saved = 0
    if underlying_df is not None and not underlying_df.empty:
        n_underlying_saved = database.save_underlying_dataframe(
            underlying_df, dataset_name, replace_existing=replace_existing
        )

    return {
        "records_received": n_received,
        "records_valid": n_valid,
        "records_rejected": n_received - n_valid,
        "records_saved": n_saved,
        "underlying_rows_saved": n_underlying_saved,
        "warnings": warnings,
    }
