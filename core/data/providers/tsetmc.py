"""
core/data/providers/tsetmc.py

Provider شماره ۱ (Primary) — بخش ۵ سند.

این فایل منطق دریافت را دوباره پیاده‌سازی نمی‌کند؛ چون core/live_data.py
همین الان با یک نمونه واقعی از Response تست و تأیید شده (Status 200،
نگاشت فیلد به فیلد با نمونه واقعی JSON، نه حدسی). اینجا فقط آن را پشت
Interface مشترک Provider قرار می‌دهیم تا بقیه پروژه به‌جای فراخوانی
مستقیم core.live_data، از این Provider استفاده کند (طبق بخش ۳ سند:
"هیچ بخش بالادستی نباید مستقیماً به API یک Provider وابسته باشد").
"""
from __future__ import annotations

import time
from typing import Optional

from core import live_data
from core.data.providers.base import OptionsDataProvider, ProviderError
from core.schema import DataSource


class TSETMCProvider(OptionsDataProvider):
    name = DataSource.TSETMC_LIVE
    is_live = True
    is_historical = False  # TSETMC Market Watch فقط لحظه‌ای است؛ تاریخچه رسمی OI ندارد.

    def get_option_chain(self, underlying: Optional[str] = None):
        try:
            return live_data.fetch_option_chain(underlying_filter=underlying)
        except live_data.LiveDataError as exc:
            raise ProviderError(str(exc)) from exc

    def get_historical(self, underlying: str, start_date=None, end_date=None):
        # طبق بخش ۴۹ سند (Provider Field Matrix)، TSETMC برای Historical فقط
        # Fallback رتبه ۲ است، نه Primary. پیاده‌سازی این مسیر (از طریق
        # Endpoint عمومی GetClosingPriceDailyList به‌ازای هر InsCode) در
        # فاز بعدی انجام می‌شود — فعلاً صادقانه NotImplemented اعلام می‌کنیم
        # به‌جای برگرداندن داده جعلی یا ناقص.
        raise NotImplementedError(
            "Historical از TSETMC هنوز پیاده‌سازی نشده؛ از FimaProvider استفاده کنید."
        )

    def list_underlyings(self) -> list:
        try:
            return live_data.list_available_underlyings()
        except live_data.LiveDataError as exc:
            raise ProviderError(str(exc)) from exc

    def health_check(self) -> dict:
        started = time.time()
        try:
            records = live_data.fetch_raw_option_chain()
            return {
                "name": self.name, "status": "OK",
                "latency_seconds": round(time.time() - started, 2),
                "rows_received": len(records), "error": None,
            }
        except live_data.LiveDataError as exc:
            return {
                "name": self.name, "status": "UNAVAILABLE",
                "latency_seconds": round(time.time() - started, 2),
                "rows_received": 0, "error": str(exc),
            }
