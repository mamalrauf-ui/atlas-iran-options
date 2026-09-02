"""
Excel Importer - خواندن فایل اکسل، تشخیص خودکار ستون‌ها، اعتبارسنجی و تبدیل
به فرمت داخلی استاندارد (Canonical Schema).

هدف: کاربر مجبور نیست دقیقاً یک فرمت خاص بسازد؛ ستون‌های رایج فارسی/انگلیسی
به‌صورت خودکار تشخیص داده می‌شوند و در نهایت هم گزارش اعتبارسنجی و هم
داده تمیز برگردانده می‌شود.
"""
import pandas as pd
import numpy as np
import re
from datetime import date

from core.schema import DataQuality, DataSource, ExerciseStyle

try:
    import jdatetime
    HAS_JALALI = True
except ImportError:
    HAS_JALALI = False


def _jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    """
    تبدیل تاریخ شمسی به میلادی بدون وابستگی خارجی (fallback وقتی jdatetime
    نصب نیست). الگوریتم استاندارد تقویم جلالی.
    """
    jy += 1595
    days = (
        -355668
        + (365 * jy)
        + ((jy // 33) * 8)
        + (((jy % 33) + 3) // 4)
        + jd
        + (((jm - 1) * 31) if jm < 7 else (((jm - 7) * 30) + 186))
    )
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        gy += 100 * ((days - 1) // 36524)
        days = (days - 1) % 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    is_leap = (gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0))
    month_days = [0, 31, 29 if is_leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    for i in range(1, 13):
        if gd <= month_days[i]:
            gm = i
            break
        gd -= month_days[i]
    return date(gy, gm, gd)

# نگاشت نام‌های رایج ستون‌ها (فارسی/انگلیسی) به نام کانونیک داخلی
COLUMN_ALIASES = {
    "quote_date": ["date", "quote_date", "quotedate", "تاریخ"],
    "symbol": ["symbol", "ticker", "نماد"],
    "underlying": ["underlying", "underlying_symbol", "نماد پایه", "دارایی پایه", "پایه"],
    "option_type": ["type", "option_type", "نوع"],
    "strike": ["strike", "strike_price", "قیمت اعمال", "اعمال"],
    "expiry": ["expiry", "expiration", "سررسید", "تاریخ سررسید"],
    "close": ["close", "price", "last", "آخرین قیمت", "قیمت پایانی", "قیمت"],
    "bid": ["bid", "قیمت خرید"],
    "ask": ["ask", "قیمت فروش"],
    "volume": ["volume", "حجم"],
    "open_interest": ["oi", "open_interest", "open interest", "موقعیت باز"],
    "iv": ["iv", "implied_volatility", "نوسان ضمنی"],
    # قیمت دارایی پایه وقتی داخل همان فایل اختیار معامله آمده باشد.
    # این فیلد اجباری نیست، ولی اگر باشد نیازی به فایل جداگانه «قیمت دارایی پایه»
    # نیست و Greeks/Moneyness مستقیماً قابل‌محاسبه می‌شوند.
    "underlying_close": [
        "آخرین پایه", "اخرین پایه", "قیمت سهم پایه", "قیمت دارایی پایه",
        "قیمت پایه", "آخرین قیمت پایه", "اخرین قیمت پایه", "پایانی پایه",
        "underlying_close", "underlying price", "spot", "spot price",
    ],
}

REQUIRED_FIELDS = ["quote_date", "underlying", "option_type", "strike", "expiry", "close"]


def _normalize(s: str) -> str:
    return str(s).strip().lower().replace("_", " ").replace("-", " ")


def _clean_number(val):
    """تمیزکاری اعدادی مثل '459,502 (-9.1%)' یا '3M' یا '6,274.91B' یا '--'."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if s in ("--", "-", ""):
        return np.nan
    s = s.split("(")[0].strip()
    s = s.replace(",", "")
    mult = 1
    if s and s[-1] in "Kk":
        mult, s = 1_000, s[:-1]
    elif s and s[-1] in "Mm":
        mult, s = 1_000_000, s[:-1]
    elif s and s[-1] in "Bb":
        mult, s = 1_000_000_000, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return np.nan


def _clean_iv(val):
    """تبدیل نوسان ضمنی؛ مقدار '--' یعنی نامشخص."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if s in ("--", "-", ""):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def auto_map_columns(columns) -> dict:
    """تشخیص خودکار اینکه هر ستون فایل کاربر معادل کدام فیلد کانونیک است."""
    mapping = {}
    norm_cols = {c: _normalize(c) for c in columns}
    for canonical, aliases in COLUMN_ALIASES.items():
        norm_aliases = [_normalize(a) for a in aliases]
        for orig_col, norm_col in norm_cols.items():
            if norm_col in norm_aliases:
                mapping[canonical] = orig_col
                break
    return mapping


def _parse_date_value(val):
    """تبدیل یک مقدار تاریخ (شمسی یا میلادی، رشته یا عدد) به date میلادی."""
    if pd.isna(val):
        return None
    if isinstance(val, (pd.Timestamp,)):
        return val.date()
    if hasattr(val, "year") and hasattr(val, "month") and hasattr(val, "day"):
        try:
            return date(val.year, val.month, val.day)
        except Exception:
            pass

    s = str(val).strip()
    if not s:
        return None
    s = s.replace("-", "/")
    parts = s.split("/")
    if len(parts) == 3:
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            y = m = d = None
        if y is not None:
            # سال کمتر از 1500 یعنی احتمالاً شمسی است
            if y < 1500 and HAS_JALALI:
                try:
                    return jdatetime.date(y, m, d).togregorian()
                except Exception:
                    pass
            elif y < 1500 and not HAS_JALALI:
                try:
                    return _jalali_to_gregorian(y, m, d)
                except Exception:
                    pass
            else:
                try:
                    return date(y, m, d)
                except Exception:
                    pass
    # fallback به pandas
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


def _gregorian_to_jalali(gy: int, gm: int, gd: int):
    """تبدیل میلادی به شمسی (معکوس _jalali_to_gregorian) - برای نمایش تاریخ‌ها."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def to_jalali_str(value) -> str:
    """
    تبدیل یک تاریخ میلادی (رشته ISO مثل '2026-08-19' یا شیء date/Timestamp)
    به رشته شمسی 'YYYY/MM/DD' برای نمایش در رابط کاربری. اگر مقدار قابل
    تبدیل نباشد، همان مقدار اصلی را برمی‌گرداند.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        if isinstance(value, str):
            d = pd.to_datetime(value).date()
        elif hasattr(value, "year"):
            d = value
        else:
            d = pd.to_datetime(str(value)).date()
        jy, jm, jd = _gregorian_to_jalali(d.year, d.month, d.day)
        return f"{jy:04d}/{jm:02d}/{jd:02d}"
    except Exception:
        return str(value)


def parse_date_value(val):
    """نسخه عمومی (Public) تابع تبدیل تاریخ - برای استفاده خارج از این ماژول."""
    return _parse_date_value(val)


def _normalize_option_type(val):
    s = str(val).strip().lower()
    call_tokens = ["call", "c", "خرید", "اختیار خرید"]
    put_tokens = ["put", "p", "فروش", "اختیار فروش"]
    if s in call_tokens or "call" in s or "خرید" in s:
        return "call"
    if s in put_tokens or "put" in s or "فروش" in s:
        return "put"
    return None


def read_excel_preview(file_path, n_rows: int = 20):
    """فقط برای پیش‌نمایش سریع ستون‌ها و چند ردیف اول، بدون اعتبارسنجی کامل."""
    df = pd.read_excel(file_path, nrows=n_rows)
    return df


def import_excel(file_path, manual_mapping: dict = None):
    """
    خواندن کامل فایل و تبدیل به Canonical Schema.

    Returns:
        clean_df: DataFrame آماده ذخیره در دیتابیس
        report: dict حاوی آمار اعتبارسنجی (برای نمایش به کاربر قبل از ثبت نهایی)
    """
    raw = pd.read_excel(file_path)
    total_rows = len(raw)

    mapping = manual_mapping or auto_map_columns(raw.columns)

    missing_required = [f for f in REQUIRED_FIELDS if f not in mapping]
    report = {
        "total_rows": total_rows,
        "detected_mapping": mapping,
        "missing_required_fields": missing_required,
        "warnings": [],
        "kept_rows": 0,
        "dropped_rows": 0,
        "call_count": 0,
        "put_count": 0,
    }
    if missing_required:
        report["warnings"].append(
            "ستون‌های ضروری زیر پیدا نشدند و باید دستی نگاشت شوند: "
            + ", ".join(missing_required)
        )
        return None, report

    out = pd.DataFrame()
    for canonical, orig_col in mapping.items():
        out[canonical] = raw[orig_col]

    # تبدیل تاریخ‌ها
    out["quote_date"] = out["quote_date"].apply(_parse_date_value)
    out["expiry"] = out["expiry"].apply(_parse_date_value)

    bad_dates = out["quote_date"].isna() | out["expiry"].isna()
    if bad_dates.any():
        report["warnings"].append(f"{int(bad_dates.sum())} ردیف با تاریخ نامعتبر حذف شد")

    # نوع اختیار
    out["option_type"] = out["option_type"].apply(_normalize_option_type)
    bad_type = out["option_type"].isna()
    if bad_type.any():
        report["warnings"].append(f"{int(bad_type.sum())} ردیف با نوع نامشخص (نه Call نه Put) حذف شد")

    # اعداد
    for numeric_field in ["strike", "close", "bid", "ask", "volume", "open_interest", "iv",
                          "underlying_close"]:
        if numeric_field in out.columns:
            # _clean_number اعداد فرمت‌دار فارسی/لاتین مثل «۱,۲۳۴ (-۹.۱%)» یا «3M» را هم می‌پذیرد
            out[numeric_field] = out[numeric_field].apply(_clean_number)

    bad_strike = out["strike"].isna() | (out["strike"] <= 0)
    bad_close = out["close"].isna() | (out["close"] < 0)
    if bad_strike.any():
        report["warnings"].append(f"{int(bad_strike.sum())} ردیف با Strike نامعتبر حذف شد")
    if bad_close.any():
        report["warnings"].append(f"{int(bad_close.sum())} ردیف با قیمت نامعتبر حذف شد")

    drop_mask = bad_dates | bad_type | bad_strike | bad_close
    clean = out[~drop_mask].copy()

    clean["dte"] = clean.apply(
        lambda r: (r["expiry"] - r["quote_date"]).days if r["expiry"] and r["quote_date"] else None,
        axis=1,
    )
    bad_dte = clean["dte"].isna() | (clean["dte"] < 0)
    if bad_dte.any():
        report["warnings"].append(f"{int(bad_dte.sum())} ردیف با سررسید قبل از تاریخ قیمت حذف شد")
    clean = clean[~bad_dte].copy()

    # رشته‌سازی تاریخ‌ها برای ذخیره در دیتابیس (ISO میلادی)
    clean["quote_date"] = clean["quote_date"].astype(str)
    clean["expiry"] = clean["expiry"].astype(str)

    if "symbol" not in clean.columns:
        clean["symbol"] = clean["underlying"].astype(str) + "-" + clean["option_type"] + "-" + clean["strike"].astype(str)

    for optional_field in ["bid", "ask", "volume", "open_interest", "iv"]:
        if optional_field not in clean.columns:
            clean[optional_field] = np.nan

    # --- قیمت دارایی پایه از همان فایل (ستون «آخرین پایه» و مترادف‌هایش) ---
    # اگر این ستون موجود باشد، کاربر لازم نیست فایل جداگانه وارد کند.
    underlying_df = None
    if "underlying_close" in clean.columns and clean["underlying_close"].notna().any():
        valid_spot = clean[clean["underlying_close"].notna() & (clean["underlying_close"] > 0)]
        if not valid_spot.empty:
            # یک قیمت به‌ازای هر (نماد پایه، تاریخ). اگر ردیف‌های یک نماد مقادیر
            # متفاوتی داشته باشند، میانه گرفته می‌شود تا یک غلط تایپی تکی
            # کل Moneyness آن نماد را خراب نکند؛ و مورد در گزارش هشدار داده می‌شود.
            grp = valid_spot.groupby(["underlying", "quote_date"])["underlying_close"]
            inconsistent = int((grp.nunique() > 1).sum())
            if inconsistent:
                report["warnings"].append(
                    f"در {inconsistent} مورد (نماد، تاریخ)، ستون قیمت دارایی پایه مقادیر متفاوتی داشت؛ "
                    "میانه استفاده شد."
                )
            underlying_df = grp.median().reset_index().rename(columns={"underlying_close": "close"})
            report["underlying_prices_found"] = len(underlying_df)

        clean = clean.drop(columns=["underlying_close"])
    else:
        report["warnings"].append(
            "ستون قیمت دارایی پایه (مثلاً «آخرین پایه») در این فایل پیدا نشد. "
            "بدون آن، وضعیت ITM/ATM/OTM و Greeks محاسبه نمی‌شود — یا این ستون را به فایل اضافه کنید "
            "یا فایل «قیمت دارایی پایه» را جداگانه وارد کنید."
        )

    report["kept_rows"] = len(clean)
    report["dropped_rows"] = total_rows - len(clean)
    report["call_count"] = int((clean["option_type"] == "call").sum())
    report["put_count"] = int((clean["option_type"] == "put").sum())

    # برچسب منبع/کیفیت داده — بخش ۵۰ سند: شفافیت منبع برای هر Dataset
    clean["source"] = DataSource.EXCEL_IMPORT
    clean["data_quality"] = DataQuality.IMPORTED
    clean["exercise_style"] = ExerciseStyle.EUROPEAN
    if "iv" in clean.columns:
        clean["iv_source"] = clean["iv"].apply(lambda v: "IMPORTED" if pd.notna(v) else None)

    return clean, report, underlying_df


UNDERLYING_ALIASES = {
    "quote_date": COLUMN_ALIASES["quote_date"],
    "underlying": COLUMN_ALIASES["underlying"] + ["symbol", "نماد"],
    "close": COLUMN_ALIASES["close"],
}


def import_underlying_excel(file_path, manual_mapping: dict = None):
    """Import ساده‌تر برای فایل قیمت دارایی پایه (سهام)."""
    raw = pd.read_excel(file_path)
    total_rows = len(raw)

    mapping = manual_mapping
    if mapping is None:
        mapping = {}
        norm_cols = {c: _normalize(c) for c in raw.columns}
        for canonical, aliases in UNDERLYING_ALIASES.items():
            norm_aliases = [_normalize(a) for a in aliases]
            for orig_col, norm_col in norm_cols.items():
                if norm_col in norm_aliases:
                    mapping[canonical] = orig_col
                    break

    required = ["quote_date", "underlying", "close"]
    missing = [f for f in required if f not in mapping]
    report = {"total_rows": total_rows, "detected_mapping": mapping,
              "missing_required_fields": missing, "warnings": [], "kept_rows": 0, "dropped_rows": 0}
    if missing:
        report["warnings"].append("ستون‌های ضروری یافت نشدند: " + ", ".join(missing))
        return None, report

    out = pd.DataFrame()
    for canonical, orig_col in mapping.items():
        out[canonical] = raw[orig_col]

    out["quote_date"] = out["quote_date"].apply(_parse_date_value)
    out["close"] = pd.to_numeric(out["close"], errors="coerce")

    bad = out["quote_date"].isna() | out["close"].isna() | (out["close"] <= 0)
    clean = out[~bad].copy()
    clean["quote_date"] = clean["quote_date"].astype(str)

    report["kept_rows"] = len(clean)
    report["dropped_rows"] = total_rows - len(clean)
    if bad.any():
        report["warnings"].append(f"{int(bad.sum())} ردیف نامعتبر حذف شد")

    clean["source"] = DataSource.UNDERLYING_IMPORT

    return clean, report


# نام ستون‌هایی که این فرمت خاص (خروجی مستقیم سایت‌های آپشن مثل optionschool/TSETMC) را
# از یک فایل دلخواه اکسل تشخیص می‌دهند
TSE_SCREENER_SIGNATURE_COLUMNS = ["نماد", "قیمت اعمال", "تاریخ سررسید", "قیمت پایانی"]

# نام ستون قیمت دارایی پایه بین سایت‌های مختلف فرق می‌کند
# («قیمت سهم پایه» در optionschool، «آخرین پایه» در برخی خروجی‌های دیگر).
TSE_SPOT_COLUMN_CANDIDATES = COLUMN_ALIASES["underlying_close"]


def find_spot_column(columns):
    """اولین ستونی که قیمت دارایی پایه را نگه می‌دارد، یا None."""
    norm = {_normalize(c): c for c in columns}
    for cand in TSE_SPOT_COLUMN_CANDIDATES:
        hit = norm.get(_normalize(cand))
        if hit is not None:
            return hit
    return None


def looks_like_tse_screener(columns) -> bool:
    """تشخیص خودکار اینکه آیا فایل، خروجی خام یک سایت آپشن‌گر ایرانی است."""
    cols = set(columns)
    return (all(c in cols for c in TSE_SCREENER_SIGNATURE_COLUMNS)
            and find_spot_column(columns) is not None)


def import_tse_screener_excel(file_path, quote_date_str: str, r: float = 0.20):
    """
    Import مستقیم خروجی خام سایت‌های آپشن‌گر بورس ایران (مثل optionschool).
    این فایل‌ها فاقد ستون تاریخ Snapshot هستند، پس quote_date_str باید توسط
    کاربر مشخص شود (تاریخی که این خروجی گرفته شده - شمسی یا میلادی).

    نوع Call/Put و نماد پایه از پیشوند نماد استخراج می‌شود:
        ض... => Call   |   ط... => Put

    برخلاف import_excel معمولی، این تابع دو خروجی می‌دهد چون قیمت دارایی پایه
    از قبل داخل خود فایل (ستون «قیمت سهم پایه») موجود است و نیازی به فایل جدا نیست.

    Returns:
        options_df, underlying_df, report
    """
    raw = pd.read_excel(file_path)
    total_rows = len(raw)
    report = {"total_rows": total_rows, "warnings": [], "kept_rows": 0, "dropped_rows": 0,
              "call_count": 0, "put_count": 0, "missing_required_fields": []}

    missing = [c for c in TSE_SCREENER_SIGNATURE_COLUMNS if c not in raw.columns]
    spot_col = find_spot_column(raw.columns)
    if spot_col is None:
        missing = missing + ["قیمت دارایی پایه (مثلاً «آخرین پایه» یا «قیمت سهم پایه»)"]
    if missing:
        report["missing_required_fields"] = missing
        report["warnings"].append("این فایل با فرمت مورد انتظار خروجی سایت آپشن‌گر همخوانی ندارد. ستون‌های یافت نشده: " + ", ".join(missing))
        return None, None, report

    quote_date_parsed = _parse_date_value(quote_date_str)
    if quote_date_parsed is None:
        report["warnings"].append("تاریخ Snapshot معتبر نیست.")
        return None, None, report

    sym = raw["نماد"].astype(str).str.strip()
    parsed = sym.str.extract(r"^([ضط])([^\d]+)(\d.*)$")
    option_type = parsed[0].map({"ض": "call", "ط": "put"})
    underlying = parsed[1].str.strip()

    out = pd.DataFrame()
    out["symbol"] = sym
    out["underlying"] = underlying
    out["option_type"] = option_type
    out["strike"] = pd.to_numeric(raw["قیمت اعمال"], errors="coerce")
    out["expiry"] = raw["تاریخ سررسید"].apply(_parse_date_value)
    out["close"] = pd.to_numeric(raw["قیمت پایانی"], errors="coerce")
    out["underlying_close"] = raw[spot_col].apply(_clean_number)
    out["bid"] = pd.to_numeric(raw["قیمت بهترین تقاضا"], errors="coerce") if "قیمت بهترین تقاضا" in raw.columns else np.nan
    out["ask"] = pd.to_numeric(raw["قیمت بهترین عرضه"], errors="coerce") if "قیمت بهترین عرضه" in raw.columns else np.nan
    out["volume"] = raw["حجم معاملات"].apply(_clean_number) if "حجم معاملات" in raw.columns else np.nan
    out["open_interest"] = raw["موقعیت های باز"].apply(_clean_number) if "موقعیت های باز" in raw.columns else np.nan
    out["iv"] = raw["نوسان ضمنی"].apply(_clean_iv) if "نوسان ضمنی" in raw.columns else np.nan

    for fa_col, en_col in [("دلتا", "delta"), ("تتا", "theta"), ("گاما", "gamma"), ("وگا", "vega"), ("رو", "rho")]:
        out[en_col] = pd.to_numeric(raw[fa_col], errors="coerce") if fa_col in raw.columns else np.nan

    bad_type = out["option_type"].isna()
    bad_strike = out["strike"].isna() | (out["strike"] <= 0)
    bad_close = out["close"].isna() | (out["close"] < 0)
    bad_expiry = out["expiry"].isna()
    drop_mask = bad_type | bad_strike | bad_close | bad_expiry

    if bad_type.any():
        report["warnings"].append(f"{int(bad_type.sum())} ردیف با نماد غیرقابل‌تشخیص (نه با ض نه با ط) حذف شد")
    if bad_expiry.any():
        report["warnings"].append(f"{int(bad_expiry.sum())} ردیف با سررسید نامعتبر حذف شد")

    clean = out[~drop_mask].copy()
    clean["expiry"] = clean["expiry"].astype(str)
    clean["quote_date"] = str(quote_date_parsed)
    clean["dte"] = clean["expiry"].apply(lambda e: (pd.to_datetime(e).date() - quote_date_parsed).days)

    n_missing_iv = clean["iv"].isna().sum()
    if n_missing_iv > 0:
        report["warnings"].append(f"{int(n_missing_iv)} ردیف بدون نوسان ضمنی در فایل اصلی (به‌صورت '--')")

    n_put = int((clean["option_type"] == "put").sum())
    n_call = int((clean["option_type"] == "call").sum())
    if n_put == 0:
        report["warnings"].append("این فایل هیچ اختیار فروش (Put) ندارد؛ فقط شامل Call است.")
    if n_call == 0:
        report["warnings"].append("این فایل هیچ اختیار خرید (Call) ندارد؛ فقط شامل Put است.")

    report["kept_rows"] = len(clean)
    report["dropped_rows"] = total_rows - len(clean)
    report["call_count"] = n_call
    report["put_count"] = n_put
    report["underlyings_found"] = sorted(clean["underlying"].unique().tolist())

    underlying_df = (
        clean.groupby("underlying", as_index=False)["underlying_close"]
        .first()
        .rename(columns={"underlying_close": "close"})
    )
    underlying_df["quote_date"] = str(quote_date_parsed)
    underlying_df["source"] = DataSource.TSE_SCREENER_IMPORT

    options_out = clean.drop(columns=["underlying_close"])
    options_out["source"] = DataSource.TSE_SCREENER_IMPORT
    options_out["data_quality"] = DataQuality.IMPORTED
    options_out["exercise_style"] = ExerciseStyle.EUROPEAN
    options_out["iv_source"] = options_out["iv"].apply(lambda v: "IMPORTED" if pd.notna(v) else None)

    return options_out, underlying_df, report
