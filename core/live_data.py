"""
دریافت مستقیم داده لحظه‌ای زنجیره اختیار معامله از API رسمی TSETMC.

این ماژول جایگزین Excel Importer نیست؛ کنار آن قرار می‌گیرد و دقیقاً همان
Canonical Schema که core/importer.py تولید می‌کند را برمی‌گرداند، تا از
همان مسیر ذخیره‌سازی (core/database.py) و محاسبات Greeks/IV (core/pricing.py)
عبور کند. هیچ Greek یا IV در این ماژول محاسبه نمی‌شود — طبق اصل پروژه،
این محاسبات فقط بر مبنای داده خام واقعی و توسط core/pricing.py انجام می‌شود.

منبع داده: Endpoint عمومی و بدون‌نیاز‌به‌کلید خود TSETMC:
    https://cdn.tsetmc.com/api/Instrument/GetInstrumentOptionMarketWatch/0
نگاشت فیلدها با یک نمونه واقعی از پاسخ API تأیید شده (نه حدسی/موقعیتی).

نرخ بدون‌ریسک: میانگین YTM اسناد خزانه (اخزا) با آخرین تاریخ معامله،
از صفحه رسمی فرابورس ایران (ifb.ir/YTM.aspx).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd
import requests

from core.schema import DataQuality, DataSource, ExerciseStyle

TSETMC_OPTION_CHAIN_URL = "https://cdn.tsetmc.com/api/Instrument/GetInstrumentOptionMarketWatch/0"
IFB_YTM_URL = "https://ifb.ir/YTM.aspx"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.tsetmc.com/",
}
_TIMEOUT = 20


class LiveDataError(Exception):
    """خطای قابل‌فهم برای نمایش مستقیم در UI، به‌جای Traceback خام."""


# ---------------------------------------------------------------------------
# دریافت خام
# ---------------------------------------------------------------------------
def fetch_raw_option_chain() -> list[dict]:
    """دریافت خام کل بازار اختیار معامله (همه دارایی‌های پایه، همه سررسیدها)."""
    try:
        resp = requests.get(TSETMC_OPTION_CHAIN_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise LiveDataError(f"اتصال به API رسمی TSETMC ممکن نشد: {exc}") from exc

    try:
        data = resp.json()
        records = data["instrumentOptMarketWatch"]
    except (ValueError, KeyError) as exc:
        raise LiveDataError(f"ساختار پاسخ API تغییر کرده و قابل‌تفسیر نیست: {exc}") from exc

    if not records:
        raise LiveDataError("API پاسخ داد ولی هیچ رکوردی برنگرداند.")
    return records


def list_available_underlyings() -> list[str]:
    """لیست نام دارایی‌های پایه موجود در بازار زنده (برای Selectbox در UI)."""
    records = fetch_raw_option_chain()
    names = sorted({(r.get("lval30_UA") or "").strip() for r in records if r.get("lval30_UA")})
    return names


# ---------------------------------------------------------------------------
# کمکی
# ---------------------------------------------------------------------------
def _yyyymmdd_to_date(value) -> Optional[dt.date]:
    s = str(value).strip()
    if not s or s.lower() == "none" or len(s) != 8:
        return None
    try:
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def _num(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN را None می‌کنیم
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# تبدیل به Canonical Schema
# ---------------------------------------------------------------------------
def fetch_option_chain(underlying_filter: Optional[str] = None):
    """
    دریافت زنجیره زنده و تبدیل به همان ساختاری که core/importer.py تولید می‌کند.

    Parameters
    ----------
    underlying_filter: نام دقیق فارسی دارایی پایه (مثل "اهرم"). اگر None باشد
        کل بازار برگردانده می‌شود (ممکن است چند هزار ردیف باشد).

    Returns
    -------
    (options_df, underlying_df, report)
    """
    records = fetch_raw_option_chain()
    today = dt.date.today()
    quote_date_str = str(today)
    snapshot_ts = dt.datetime.now().isoformat(timespec="seconds")

    option_rows = []
    underlying_rows: dict[str, dict] = {}
    skipped = 0

    for r in records:
        underlying_name = (r.get("lval30_UA") or "").strip()
        if not underlying_name:
            skipped += 1
            continue
        if underlying_filter and underlying_name != underlying_filter:
            continue

        expiry_date = _yyyymmdd_to_date(r.get("endDate"))
        strike = _num(r.get("strikePrice"))
        if expiry_date is None or strike is None:
            skipped += 1
            continue

        dte = _num(r.get("remainedDay"))
        if dte is None:
            # Fallback: اگر remainedDay در پاسخ نبود/نامعتبر بود، از تفاضل
            # تاریخ سررسید و امروز محاسبه می‌شود تا dte هرگز رشته/None
            # نامعتبر باقی نماند (که باعث خطا یا صفر‌شدن IV/Greeks در
            # core/pricing.py می‌شد، چون آنجا `max(row["dte"], 0)` روی
            # مقدار محاسبه می‌شود و مقایسه رشته با عدد Exception می‌دهد).
            dte = (expiry_date - today).days
        underlying_close = _num(r.get("pClosing_UA"))
        underlying_prev_close = _num(r.get("priceYesterday_UA"))
        underlying_id = r.get("uaInsCode")
        contract_size = _num(r.get("contractSize"))

        if underlying_name not in underlying_rows and underlying_close:
            underlying_rows[underlying_name] = {
                "quote_date": quote_date_str,
                "underlying": underlying_name,
                "close": underlying_close,
                "previous_close": underlying_prev_close,
                "instrument_id": underlying_id,
                "source": DataSource.TSETMC_LIVE,
                "snapshot_timestamp": snapshot_ts,
            }

        # اطلاعات مشترک بین Call و Put همین رکورد (بخش‌های ۶، ۱۸، ۱۹ سند)
        common = {
            "quote_date": quote_date_str,
            "underlying": underlying_name,
            "underlying_id": underlying_id,
            "strike": strike,
            "expiry": str(expiry_date),
            "dte": dte,
            "contract_size": contract_size,
            "exercise_style": ExerciseStyle.EUROPEAN,
            "source": DataSource.TSETMC_LIVE,
            "data_quality": DataQuality.LIVE,
            "snapshot_timestamp": snapshot_ts,
            # Greeks/IV هرگز اینجا محاسبه نمی‌شوند — طبق اصل پروژه فقط core/pricing.py
            "iv": None, "iv_source": None, "iv_price_source": None, "iv_confidence": None,
            "delta": None, "gamma": None, "theta": None, "vega": None, "rho": None,
            "intrinsic_value": None, "time_value": None, "moneyness": None,
            "oi_change": None,  # نیازمند Snapshot قبلی است؛ اینجا محاسبه نمی‌شود
        }

        call_symbol = r.get("lVal18AFC_C")
        if call_symbol:
            option_rows.append({
                **common,
                "instrument_id": r.get("insCode_C"),
                "symbol": call_symbol, "option_type": "call",
                "close": _num(r.get("pClosing_C")),
                "previous_close": _num(r.get("priceYesterday_C")),
                "bid": _num(r.get("pMeDem_C")), "ask": _num(r.get("pMeOf_C")),
                "bid_size": _num(r.get("qTitMeDem_C")), "ask_size": _num(r.get("qTitMeOf_C")),
                "volume": _num(r.get("qTotTran5J_C")),
                "trade_count": _num(r.get("zTotTran_C")),
                "turnover": _num(r.get("qTotCap_C")),
                "open_interest": _num(r.get("oP_C")),
                "previous_open_interest": _num(r.get("yesterdayOP_C")),
            })

        put_symbol = r.get("lVal18AFC_P")
        if put_symbol:
            option_rows.append({
                **common,
                "instrument_id": r.get("insCode_P"),
                "symbol": put_symbol, "option_type": "put",
                "close": _num(r.get("pClosing_P")),
                "previous_close": _num(r.get("priceYesterday_P")),
                "bid": _num(r.get("pMeDem_P")), "ask": _num(r.get("pMeOf_P")),
                "bid_size": _num(r.get("qTitMeDem_P")), "ask_size": _num(r.get("qTitMeOf_P")),
                "volume": _num(r.get("qTotTran5J_P")),
                "trade_count": _num(r.get("zTotTran_P")),
                "turnover": _num(r.get("qTotCap_P")),
                "open_interest": _num(r.get("oP_P")),
                "previous_open_interest": _num(r.get("yesterdayOP_P")),
            })

    options_df = pd.DataFrame(option_rows)
    underlying_df = pd.DataFrame(list(underlying_rows.values()))

    report = {
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        "quote_date": quote_date_str,
        "total_rows_from_api": len(records),
        "kept_rows": len(options_df),
        "skipped_rows": skipped,
        "underlyings_found": int(underlying_df["underlying"].nunique()) if not underlying_df.empty else 0,
        "call_count": int((options_df["option_type"] == "call").sum()) if not options_df.empty else 0,
        "put_count": int((options_df["option_type"] == "put").sum()) if not options_df.empty else 0,
    }

    # --------------------------------------------------------------
    # Data-Quality Guard (بخش ۴۳ سند «Never Silently Fail»): اگر Volume
    # و Open Interest برای *همه* ردیف‌ها خالی/صفر بود، این تقریباً همیشه
    # یعنی نگاشت فیلد با ساختار فعلی پاسخ API هم‌خوانی ندارد (سایت TSETMC
    # این ساختار را گاهی تغییر می‌دهد) — نه اینکه بازار واقعاً بدون
    # معامله بوده. به‌جای ذخیره خاموش صفرهای گمراه‌کننده، این هشدار در
    # گزارش برمی‌گردد تا مستقیم در پیش‌نمایش «مرکز داده» دیده شود.
    # --------------------------------------------------------------
    if not options_df.empty:
        for field in ("volume", "open_interest"):
            col = options_df[field]
            non_null = col.dropna()
            if non_null.empty or (non_null == 0).all():
                report.setdefault("warnings", []).append(
                    f"هشدار کیفیت داده: ستون «{field}» برای همه ردیف‌ها خالی یا صفر است. "
                    "این معمولاً یعنی نگاشت فیلد در core/live_data.py با ساختار فعلی "
                    "پاسخ API TSETMC هم‌خوانی ندارد؛ لطفاً یک نمونه پاسخ خام API را "
                    "بررسی و کلیدهای مربوطه (oP_C/oP_P برای OI، qTotTran5J_C/_P برای "
                    "حجم) را تطبیق دهید."
                )
    return options_df, underlying_df, report


# ---------------------------------------------------------------------------
# نرخ بدون‌ریسک (اختیاری — Best-Effort، هرگز عدد ساختگی)
# ---------------------------------------------------------------------------
def fetch_risk_free_rate() -> Optional[float]:
    """
    نرخ بدون‌ریسک تقریبی: میانگین YTM اسناد خزانه (اخزا) با آخرین تاریخ
    معامله، از صفحه رسمی فرابورس ایران.

    اگر جدول یافت نشد یا ساختار صفحه تغییر کرده بود، None برمی‌گرداند —
    طبق اصل پروژه، به‌جای تخمین دلبخواهی هیچ عددی نمایش داده نمی‌شود.
    خروجی به‌صورت کسر اعشاری است (مثلاً 0.32 برای ۳۲٪).
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise LiveDataError(
            "پکیج beautifulsoup4 نصب نیست. اجرا کنید: pip install beautifulsoup4 lxml"
        ) from exc

    try:
        resp = requests.get(IFB_YTM_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise LiveDataError(f"اتصال به ifb.ir ممکن نشد: {exc}") from exc

    soup = BeautifulSoup(resp.content, "html.parser")
    table = soup.find("table", {"id": "ContentPlaceHolder1_grdytmforkhazaneh"})
    if table is None:
        return None

    try:
        df = pd.read_html(str(table))[0]
    except (ValueError, ImportError):
        return None

    ytm_col = next((col for col in df.columns if "ytm" in str(col).lower() or "بازده" in str(col)), None)
    date_col = next((col for col in df.columns if "معامله" in str(col) or "trade" in str(col).lower()), None)
    if ytm_col is None:
        return None

    df[ytm_col] = pd.to_numeric(df[ytm_col], errors="coerce")
    if date_col is not None and df[date_col].notna().any():
        latest = df[date_col].max()
        df = df[df[date_col] == latest]

    rf = df[ytm_col].dropna().mean()
    if pd.isna(rf):
        return None
    return float(rf) / 100 if rf > 1 else float(rf)
