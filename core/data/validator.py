"""
core/data/validator.py

اعتبارسنجی Context-Aware (بخش ۹ سند): یک مقدار صفر که واقعاً صفر
اقتصادی است (مثلاً OI=0 وقتی هیچ‌کس موقعیت باز ندارد) نباید Invalid
اعلام شود؛ فقط مقادیر واقعاً غیرممکن رد می‌شوند.

هرگز رکورد را «تعمیر» نمی‌کند (هرگز مقدار را با صفر/میانگین جایگزین
نمی‌کند) — طبق بخش ۴۳ سند («Never Silently Fail»)، فقط رد یا هشدار
می‌دهد؛ تصمیم درباره حذف با فراخواننده (Provider/Snapshot layer) است.
"""
from __future__ import annotations

import pandas as pd

REQUIRED_FIELDS = ["quote_date", "underlying", "option_type", "strike", "expiry", "close"]


def validate_options_df(df: pd.DataFrame) -> tuple:
    """
    Returns
    -------
    (valid_mask: pd.Series[bool], warnings: list[str])
    valid_mask == True یعنی ردیف قابل ذخیره‌سازی است.
    """
    if df is None or df.empty:
        return pd.Series([], dtype=bool), ["DataFrame خالی است."]

    warnings = []
    n = len(df)
    invalid = pd.Series(False, index=df.index)

    for field in REQUIRED_FIELDS:
        if field not in df.columns:
            warnings.append(f"فیلد ضروری «{field}» اصلاً در داده وجود ندارد.")
            return pd.Series(False, index=df.index), warnings
        missing = df[field].isna()
        if missing.any():
            warnings.append(f"{int(missing.sum())} ردیف بدون «{field}» رد شد.")
            invalid |= missing

    if "strike" in df.columns:
        bad_strike = pd.to_numeric(df["strike"], errors="coerce") <= 0
        if bad_strike.any():
            warnings.append(f"{int(bad_strike.sum())} ردیف با Strike نامعتبر (<=۰) رد شد.")
            invalid |= bad_strike

    if "option_type" in df.columns:
        bad_type = ~df["option_type"].isin(["call", "put"])
        if bad_type.any():
            warnings.append(f"{int(bad_type.sum())} ردیف با نوع اختیار نامعتبر رد شد.")
            invalid |= bad_type

    # صفر اقتصادی مجاز است؛ فقط منفی بودن غیرممکن است.
    for field in ["volume", "open_interest", "trade_count", "turnover"]:
        if field in df.columns:
            neg = pd.to_numeric(df[field], errors="coerce") < 0
            if neg.any():
                warnings.append(f"{int(neg.sum())} ردیف با «{field}» منفی (غیرممکن) رد شد.")
                invalid |= neg.fillna(False)

    if "expiry" in df.columns and "quote_date" in df.columns:
        try:
            bad_expiry = pd.to_datetime(df["expiry"], errors="coerce") < pd.to_datetime(
                df["quote_date"], errors="coerce"
            )
            if bad_expiry.any():
                warnings.append(f"{int(bad_expiry.sum())} ردیف با سررسید قبل از تاریخ Quote (غیرممکن) رد شد.")
                invalid |= bad_expiry.fillna(False)
        except Exception:
            pass

    # Duplicate Contract (بخش ۹): همان قرارداد در همان Snapshot دو بار
    if "instrument_id" in df.columns and "quote_date" in df.columns:
        dup_key = df["instrument_id"].astype(str) + "|" + df["quote_date"].astype(str)
        dup = dup_key.duplicated(keep="first") & df["instrument_id"].notna()
        if dup.any():
            warnings.append(f"{int(dup.sum())} ردیف تکراری (همان instrument_id در همان quote_date) رد شد.")
            invalid |= dup

    valid_mask = ~invalid
    if not warnings:
        warnings.append(f"همه {n} ردیف معتبر تشخیص داده شدند.")
    return valid_mask, warnings
