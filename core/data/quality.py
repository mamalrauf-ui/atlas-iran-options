"""
core/data/quality.py

Data Quality Engine (بخش ۲۹ سند). این ماژول هیچ داده‌ای را تغییر
نمی‌دهد؛ فقط وضعیت کامل‌بودن آن را برای نمایش در UI اندازه می‌گیرد.
"""
from __future__ import annotations

import pandas as pd

# فیلدهایی که کامل‌بودنشان بیشترین اثر را روی قابل‌اعتماد بودن تحلیل دارد
_QUALITY_FIELDS = ["close", "bid", "ask", "volume", "open_interest", "underlying_id"]


def snapshot_quality(options_df: pd.DataFrame) -> dict:
    """
    خروجی: درصد کامل‌بودن هر فیلد + یک Score کلی (میانگین ساده).
    هرگز مقدار غایب را با صفر جایگزین نمی‌کند؛ فقط گزارش می‌دهد.
    """
    if options_df is None or options_df.empty:
        return {"status": "unavailable", "score": None, "fields": {}, "rows": 0}

    n = len(options_df)
    field_completeness = {}
    for f in _QUALITY_FIELDS:
        if f in options_df.columns:
            pct = round(float(options_df[f].notna().sum()) / n * 100, 1)
        else:
            pct = 0.0
        field_completeness[f] = pct

    present = [v for v in field_completeness.values()]
    overall = round(sum(present) / len(present), 1) if present else None

    return {
        "status": "calculated",
        "rows": n,
        "fields": field_completeness,
        "score": overall,
    }
