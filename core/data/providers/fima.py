"""
core/data/providers/fima.py

Provider شماره ۲ (Historical) — بخش ۶ سند.

طبق بخش ۶۴ سند اول (که هنوز به‌عنوان اصل احتیاطی معتبر است): اگر fima
نصب نبود، Atlas نباید خراب شود؛ فقط این Provider را Unavailable اعلام
می‌کند.

نکته فنی مهم (که در Audit کد داخلی fima کشف شد، نه حدسی):
  - `fima.Options.download_historical_data(ticker, start_date, end_date)`
    مستقیماً همان Endpoint عمومی TSETMC را صدا می‌زند:
    `GetClosingPriceDailyList/{InsCode}`
  - این Endpoint هیچ Open Interest ندارد — یعنی OI تاریخی از این مسیر
    هم قابل‌دریافت نیست (نتیجه Audit قبلی ما دوباره تأیید شد).
  - `start_date`/`end_date` با فرمت رشته 'YYYY-MM-DD' داده می‌شوند اما
    **به‌صورت تاریخ شمسی تفسیر می‌شوند** (نه میلادی) — این Wrapper این
    ریزه‌کاری را از بقیه Atlas پنهان می‌کند و همیشه تاریخ میلادی می‌گیرد.

⚠️ هشدار صادقانه (چون امکان تست شبکه در این محیط توسعه وجود ندارد):
  منطق نگاشت با خواندن دقیق کد fima نوشته شده، اما به‌صورت Live تست
  نشده. پیش از اعتماد کامل، حتماً یک‌بار روی داده واقعی امتحان شود.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from core.data.historical import apply_historical_floor
from core.data.providers.base import OptionsDataProvider, ProviderError
from core.schema import DataSource

try:
    import fima.Options as fima_options
    import jdatetime
    HAS_FIMA = True
except ImportError:
    HAS_FIMA = False


def _gregorian_to_jalali_str(d: dt.date) -> str:
    j = jdatetime.date.fromgregorian(date=d)
    return f"{j.year:04d}-{j.month:02d}-{j.day:02d}"


def _jalali_col_to_gregorian_str(series: pd.Series) -> pd.Series:
    """ستون Date خروجی fima از نوع jdatetime.date است؛ به رشته میلادی ISO تبدیل می‌شود."""
    return series.apply(lambda jd: str(jd.togregorian()) if jd is not None else None)


class FimaProvider(OptionsDataProvider):
    name = DataSource.FIMA_HISTORICAL
    is_live = False
    is_historical = True

    def _require_fima(self):
        if not HAS_FIMA:
            raise ProviderError(
                "پکیج fima نصب نیست. اجرا کنید: pip install fima"
            )

    def get_option_chain(self, underlying: Optional[str] = None):
        raise NotImplementedError(
            "FimaProvider فقط برای داده تاریخی است؛ برای بازار لحظه‌ای از TSETMCProvider استفاده کنید."
        )

    def get_historical(self, underlying_or_option_symbol: str,
                        start_date: Optional[dt.date] = None,
                        end_date: Optional[dt.date] = None):
        """
        دریافت تاریخچه یک نماد (اختیار معامله یا سهم پایه) از TSETMC از طریق fima.

        Parameters
        ----------
        underlying_or_option_symbol: نماد دقیق فارسی (مثل «ضهرم6040» یا «اهرم»)
        start_date/end_date: تاریخ میلادی (date). اگر None باشد، fima کل
            تاریخچه موجود را برمی‌گرداند و سپس سقف ۱۴۰۵/۰۱/۰۱ اعمال می‌شود.

        Returns
        -------
        (option_history_df, underlying_history_df, report) در Canonical Schema
        """
        self._require_fima()

        kwargs = {}
        if start_date is not None and end_date is not None:
            kwargs["start_date"] = _gregorian_to_jalali_str(start_date)
            kwargs["end_date"] = _gregorian_to_jalali_str(end_date)

        try:
            opt_raw, ua_raw = fima_options.download_historical_data(
                underlying_or_option_symbol, **kwargs
            )
        except Exception as exc:  # noqa: BLE001 - خطای شبکه/Parsing از پکیج شخص‌ثالث
            raise ProviderError(f"دریافت تاریخچه از fima ممکن نشد: {exc}") from exc

        if opt_raw is None or ua_raw is None:
            raise ProviderError(f"fima هیچ داده تاریخی برای «{underlying_or_option_symbol}» برنگرداند.")

        option_df = self._map_history(opt_raw, symbol=underlying_or_option_symbol)
        underlying_df = self._map_history(ua_raw, symbol=None, is_underlying=True)

        option_df = apply_historical_floor(option_df, "quote_date")
        underlying_df = apply_historical_floor(underlying_df, "quote_date")

        report = {
            "provider": self.name,
            "symbol": underlying_or_option_symbol,
            "rows_option": len(option_df),
            "rows_underlying": len(underlying_df),
            "note": "Open Interest تاریخی در این منبع موجود نیست (Missing، نه صفر).",
        }
        return option_df, underlying_df, report

    @staticmethod
    def _map_history(raw: pd.DataFrame, symbol: Optional[str], is_underlying: bool = False) -> pd.DataFrame:
        """نگاشت ستون‌های خروجی fima (Date/Quantity/Volume/Value/...) به Canonical Schema."""
        out = pd.DataFrame()
        out["quote_date"] = _jalali_col_to_gregorian_str(raw["Date"])
        out["open"] = pd.to_numeric(raw.get("FirstPrice"), errors="coerce")
        out["high"] = pd.to_numeric(raw.get("MaxPrice"), errors="coerce")
        out["low"] = pd.to_numeric(raw.get("MinPrice"), errors="coerce")
        out["close"] = pd.to_numeric(raw.get("ClosePrice"), errors="coerce")
        out["volume"] = pd.to_numeric(raw.get("Volume"), errors="coerce")
        out["trade_count"] = pd.to_numeric(raw.get("Quantity"), errors="coerce")
        out["turnover"] = pd.to_numeric(raw.get("Value"), errors="coerce")
        out["source"] = DataSource.FIMA_HISTORICAL
        # OI عمداً ست نمی‌شود -> None/NaN می‌ماند (Missing != Zero)
        if not is_underlying and symbol is not None:
            out["symbol"] = symbol
        return out

    def health_check(self) -> dict:
        if not HAS_FIMA:
            return {"name": self.name, "status": "NOT_INSTALLED",
                    "error": "pip install fima"}
        return {"name": self.name, "status": "OK (نصب شده - Health واقعی نیازمند تست شبکه است)",
                "error": None}
