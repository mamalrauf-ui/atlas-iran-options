"""
core/data/normalizer.py

تضمین می‌کند خروجی هر Provider، صرف‌نظر از نام فیلدهای خامش
(oP_C، OpenInterest، OI، ...)، در نهایت روی همان ستون‌های Canonical
(core/schema.py) بنشیند. منطق نگاشت واقعی هر Provider داخل خودش است
(چون فقط Provider می‌داند فیلد خامش چه معنایی دارد)؛ این فایل فقط
تضمین می‌کند خروجی نهایی کامل و یکدست است.
"""
from __future__ import annotations

import pandas as pd


def ensure_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """هر ستون Canonical که در df نیست را با None اضافه می‌کند (Missing != Zero)."""
    if df is None:
        return df
    df = df.copy()
    for c in columns:
        if c not in df.columns:
            df[c] = None
    return df[columns + [c for c in df.columns if c not in columns]]


def deduplicate(df: pd.DataFrame, key_columns: list) -> pd.DataFrame:
    """
    حذف رکوردهای تکراری بر اساس یک Identity پایدار (مثلاً instrument_id +
    quote_date) — بخش ۵۴ سند اول / بخش ۹ سند دوم (Duplicate Contract).
    رکورد اول نگه داشته می‌شود.
    """
    if df is None or df.empty:
        return df
    present_keys = [k for k in key_columns if k in df.columns]
    if not present_keys:
        return df
    return df.drop_duplicates(subset=present_keys, keep="first").copy()
