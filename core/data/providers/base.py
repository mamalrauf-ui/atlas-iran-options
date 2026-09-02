"""
core/data/providers/base.py

Interface پایه تمام Providerهای داده ATLAS.

هر Provider باید:
  - هرگز داده جعلی/صفر برای مقدار غایب برنگرداند (Missing != Zero)
  - وضعیت خودش را از طریق health_check() قابل بررسی کند
  - خروجی خودش را در Canonical Schema (core/schema.py) برگرداند، نه
    فرمت خام Provider.

این فایل هیچ منطق شبکه‌ای ندارد — فقط قرارداد (Contract) است.
"""
from __future__ import annotations

from typing import Optional


class ProviderError(Exception):
    """خطای قابل‌فهم Provider - برای نمایش در UI/Log، نه Traceback خام."""


class OptionsDataProvider:
    name: str = "base"
    is_live: bool = False       # آیا این Provider داده لحظه‌ای بازار می‌دهد؟
    is_historical: bool = False  # آیا این Provider داده تاریخی می‌دهد؟

    def get_option_chain(self, underlying: Optional[str] = None):
        """Returns: (options_df, underlying_df, report) در Canonical Schema."""
        raise NotImplementedError

    def get_historical(self, underlying: str, start_date=None, end_date=None):
        """Returns: (options_df, underlying_df, report) در Canonical Schema."""
        raise NotImplementedError

    def health_check(self) -> dict:
        """
        بدون Side Effect سنگین. برای UI بخش Provider Health (بخش ۴۴ سند).
        خروجی همیشه شامل: name, status ('OK'|'UNAVAILABLE'|'NOT_INSTALLED'|'N/A'), error
        """
        raise NotImplementedError
