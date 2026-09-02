"""
Provider تاریخچه — مستقیماً از خود TSETMC، بدون پکیج شخص‌ثالث.

چرا این به‌جای fima؟
    وابستگی به یک پکیج بیرونیِ تست‌نشده برای داده‌ای که مبنای تصمیم مالی
    است، ریسک غیرضروری بود. Endpoint تاریخچه TSETMC عمومی است و همان
    شناسه‌ای را می‌گیرد (InsCode) که Atlas از قبل هنگام دریافت دیده‌بان
    بازار ذخیره کرده. پس هیچ نگاشت نماد، هیچ جست‌وجوی اضافه و هیچ
    وابستگی جدیدی لازم نیست.

Endpoint:
    /api/ClosingPrice/GetClosingPriceDailyList/{insCode}/0

نکته مهم: این Endpoint فقط OHLCV می‌دهد. موقعیت باز تاریخی در آن نیست و
هیچ منبع عمومی دیگری هم آن را ندارد — پس OI تاریخی None می‌ماند، نه صفر.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from core.data.historical import apply_historical_floor
from core.data.providers.base import OptionsDataProvider, ProviderError
from core.schema import DataSource

BASE_URL = "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{ins_code}/0"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/",
}
TIMEOUT = 25

# نگاشت فیلدهای پاسخ. کلید = ستون Atlas، مقدار = نام‌های ممکن در پاسخ.
FIELD_MAP = {
    "close": ["pClosing"],          # قیمت پایانی
    "last": ["pDrCotVal"],          # آخرین معامله
    "open": ["priceFirst"],
    "high": ["priceMax"],
    "low": ["priceMin"],
    "yesterday": ["priceYesterday"],
    "volume": ["qTotTran5J"],
    "turnover": ["qTotCap"],
    "trade_count": ["zTotTran"],
    "date": ["dEven"],              # تاریخ میلادی به شکل YYYYMMDD
}


def _pick(row: dict, keys):
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def _num(v, allow_zero=True):
    """عدد معتبر یا None. ورودی نامعتبر هرگز صفر نمی‌شود."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    if not allow_zero and f == 0:
        return None
    return f


def _parse_deven(v):
    """تبدیل 20260901 به '2026-09-01'."""
    if v is None:
        return None
    s = str(int(float(v))) if not isinstance(v, str) else v.strip()
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:])).isoformat()
    except ValueError:
        return None


class TSETMCHistoryProvider(OptionsDataProvider):
    """تاریخچه روزانه یک ابزار بر اساس InsCode آن."""

    name = "TSETMC_HISTORY"

    def health_check(self) -> dict:
        try:
            import requests  # noqa: F401
        except ImportError:
            return {"name": self.name, "status": "NOT_INSTALLED",
                    "error": "کتابخانه requests نصب نیست: pip install requests"}
        return {"name": self.name, "status": "OK (بدون تست شبکه)", "error": None}

    def get_daily_history(self, ins_code: str) -> pd.DataFrame:
        """
        تاریخچه یک ابزار. خروجی: DataFrame با ستون‌های Canonical.
        خطای شبکه به ProviderError تبدیل می‌شود تا لایه بالاتر بتواند
        نماد بعدی را ادامه دهد بدون اینکه کل عملیات متوقف شود.
        """
        if not ins_code:
            raise ProviderError("شناسه ابزار (InsCode) خالی است.")
        try:
            import requests
        except ImportError as exc:
            raise ProviderError("کتابخانه requests نصب نیست.") from exc

        url = BASE_URL.format(ins_code=str(ins_code).strip())
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"دریافت تاریخچه ناموفق ({ins_code}): {exc}") from exc

        records = None
        if isinstance(payload, dict):
            for key in ("closingPriceDaily", "ClosingPriceDaily", "closingPrices"):
                if key in payload:
                    records = payload[key]
                    break
        if records is None:
            raise ProviderError(
                f"ساختار پاسخ تاریخچه شناخته نشد (کلیدها: "
                f"{list(payload.keys()) if isinstance(payload, dict) else type(payload)})")
        if not records:
            return pd.DataFrame()

        rows = []
        for r in records:
            qd = _parse_deven(_pick(r, FIELD_MAP["date"]))
            if qd is None:
                continue
            # قیمت صفر یعنی آن روز معامله‌ای نشده — نه اینکه قیمت صفر بوده
            close = _num(_pick(r, FIELD_MAP["close"]), allow_zero=False)
            if close is None:
                continue
            rows.append({
                "quote_date": qd,
                "open": _num(_pick(r, FIELD_MAP["open"]), allow_zero=False),
                "high": _num(_pick(r, FIELD_MAP["high"]), allow_zero=False),
                "low": _num(_pick(r, FIELD_MAP["low"]), allow_zero=False),
                "close": close,
                "last": _num(_pick(r, FIELD_MAP["last"]), allow_zero=False),
                "volume": _num(_pick(r, FIELD_MAP["volume"])),
                "turnover": _num(_pick(r, FIELD_MAP["turnover"])),
                "trade_count": _num(_pick(r, FIELD_MAP["trade_count"])),
                "source": DataSource.TSETMC_HISTORY,
                # موقعیت باز تاریخی در این Endpoint وجود ندارد → None می‌ماند
                "open_interest": None,
            })

        out = pd.DataFrame(rows)
        if out.empty:
            return out
        out = out.sort_values("quote_date").reset_index(drop=True)
        return apply_historical_floor(out, "quote_date")
