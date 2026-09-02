"""
شفافیت منبع داده — هر پارامتر از کجا می‌آید.

هدف (خواسته صریح کاربر): اگر عددی در داشبورد مشکوک یا متناقض بود، کاربر
بدون خواندن کد بفهمد آن عدد از کدام سرویس آمده یا کدام فرمول آن را ساخته،
تا بداند مشکل را کجا پیگیری کند.

سه دسته:
    FETCHED    — عیناً از یک سرویس بیرونی می‌آید. Atlas آن را تغییر نمی‌دهد.
    CALCULATED — Atlas از روی داده خام می‌سازد. سرویس آن را نمی‌دهد.
    DERIVED    — از روی مقادیر محاسبه‌شده دیگر ساخته می‌شود (لایه دوم).
"""
from __future__ import annotations

FETCHED = "FETCHED"
CALCULATED = "CALCULATED"
DERIVED = "DERIVED"

KIND_LABELS_FA = {
    FETCHED: "دریافتی از سرویس",
    CALCULATED: "محاسبه ATLAS",
    DERIVED: "مشتق از محاسبات",
}

# سرویس‌ها
TSETMC = "TSETMC"
FIMA = "fima (TSETMC)"
EXCEL = "فایل اکسل"
ATLAS = "ATLAS"


def _f(field, label, source, api_field, note=None, unit=None):
    return {"field": field, "label": label, "kind": FETCHED, "source": source,
            "api_field": api_field, "formula": None, "note": note, "unit": unit}


def _c(field, label, formula, inputs, note=None, unit=None, kind=CALCULATED):
    return {"field": field, "label": label, "kind": kind, "source": ATLAS,
            "api_field": None, "formula": formula, "inputs": inputs,
            "note": note, "unit": unit}


# ---------------------------------------------------------------------------
# داده‌ای که مستقیماً از سرویس می‌آید
# ---------------------------------------------------------------------------
FETCHED_FIELDS = [
    _f("symbol", "نماد قرارداد", TSETMC, "lVal18AFC_C / lVal18AFC_P"),
    _f("underlying", "نماد دارایی پایه", TSETMC, "lval30_UA"),
    _f("instrument_id", "شناسه ابزار", TSETMC, "insCode_C / insCode_P",
       "شناسه پایدار قرارداد؛ نماد فارسی به‌تنهایی کلید مطمئنی نیست."),
    _f("strike", "قیمت اعمال", TSETMC, "strikePrice", unit="ریال"),
    _f("expiry", "تاریخ سررسید", TSETMC, "endDate"),
    _f("contract_size", "اندازه قرارداد", TSETMC, "contractSize",
       "معمولاً ۱۰۰۰ سهم، ولی پس از افزایش سرمایه تعدیل می‌شود "
       "(در همین بازار مقادیر ۱۳۷۱ هم دیده می‌شود). عدد واقعی هر قرارداد "
       "استفاده می‌شود، نه فرض ثابت.", unit="سهم"),
    _f("close", "قیمت پایانی قرارداد", TSETMC, "pClosing_C / pClosing_P", unit="ریال"),
    _f("last", "آخرین معامله", TSETMC, "pDrCotVal_C / pDrCotVal_P", unit="ریال"),
    _f("previous_close", "پایانی روز قبل", TSETMC, "priceYesterday_C / _P", unit="ریال"),
    _f("bid", "بهترین تقاضا", TSETMC, "pMeDem_C / pMeDem_P", unit="ریال"),
    _f("ask", "بهترین عرضه", TSETMC, "pMeOf_C / pMeOf_P", unit="ریال"),
    _f("bid_size", "حجم تقاضا", TSETMC, "qTitMeDem_C / _P", unit="قرارداد"),
    _f("ask_size", "حجم عرضه", TSETMC, "qTitMeOf_C / _P", unit="قرارداد"),
    _f("volume", "حجم معاملات", TSETMC, "qTotTran5J_C / _P",
       "صفر یعنی واقعاً امروز معامله نشده — با «نداریم» یکی نیست.", unit="قرارداد"),
    _f("trade_count", "تعداد معاملات", TSETMC, "zTotTran_C / _P", unit="فقره"),
    _f("turnover", "ارزش معاملات", TSETMC, "qTotCap_C / _P", unit="ریال"),
    _f("open_interest", "موقعیت باز", TSETMC, "oP_C / oP_P", unit="قرارداد"),
    _f("previous_open_interest", "موقعیت باز روز قبل", TSETMC, "yesterdayOP_C / _P",
       "به‌همین‌دلیل تغییر OI از همان روز اول قابل محاسبه است و به Snapshot دیروز نیاز ندارد.",
       unit="قرارداد"),
    _f("underlying_close", "قیمت پایانی دارایی پایه", TSETMC, "pClosing_UA", unit="ریال"),
    _f("underlying_previous_close", "پایانی قبلی دارایی پایه", TSETMC,
       "priceYesterday_UA", unit="ریال"),
    _f("remained_day", "روز باقی‌مانده (خام)", TSETMC, "remainedDay",
       "Atlas آن را با تفاضل تاریخ‌ها راستی‌آزمایی می‌کند.", unit="روز"),
]

TSETMC_HIST = "TSETMC (تاریخچه)"

HISTORICAL_FIELDS = [
    _f("history_close", "تاریخچه قیمت پایانی", TSETMC_HIST,
       "GetClosingPriceDailyList → pClosing",
       "تاریخچه روزانه هر ابزار بر اساس InsCode. مبنای HV، IV Rank و بک‌تست است.",
       unit="ریال"),
    _f("history_volume", "تاریخچه حجم", TSETMC_HIST,
       "GetClosingPriceDailyList → qTotTran5J", unit="قرارداد"),
    _f("history_ohlc", "بازه قیمتی روز", TSETMC_HIST,
       "priceFirst / priceMax / priceMin", unit="ریال"),
    _f("history_open_interest", "موقعیت باز تاریخی", TSETMC_HIST, "—",
       "در هیچ منبع عمومی موجود نیست. برای روزهای گذشته None می‌ماند، نه صفر. "
       "از امروز به بعد با هر Snapshot انباشته می‌شود.", unit="قرارداد"),
]

# ---------------------------------------------------------------------------
# آنچه Atlas خودش محاسبه می‌کند
# ---------------------------------------------------------------------------
CALCULATED_FIELDS = [
    _c("dte", "روز تا سررسید", "expiry − quote_date",
       ["expiry", "quote_date"],
       "بر مبنای تاریخ همان Snapshot، نه تاریخ امروز — وگرنه بک‌تست بی‌معنا می‌شود.",
       unit="روز"),
    _c("iv", "نوسان ضمنی (IV)",
       "حل معکوس Black-Scholes اروپایی روی قیمت بازار",
       ["close/bid/ask", "underlying_close", "strike", "dte", "نرخ بدون‌ریسک"],
       "TSETMC نوسان ضمنی نمی‌دهد. اولویت قیمت: میانه مظنه، سپس آخرین معامله، سپس پایانی.",
       unit="٪"),
    _c("iv_price_source", "منبع قیمت IV", "اولویت MID > LAST > CLOSE",
       ["bid", "ask", "last", "close"],
       "برای اینکه معلوم باشد IV از چه قیمتی استخراج شده."),
    _c("delta", "دلتا", "N(d₁) برای Call و N(d₁)−۱ برای Put",
       ["underlying_close", "strike", "dte", "iv", "نرخ بدون‌ریسک"]),
    _c("gamma", "گاما", "φ(d₁) ÷ (S·σ·√T)",
       ["underlying_close", "strike", "dte", "iv", "نرخ بدون‌ریسک"]),
    _c("theta", "تتا", "مشتق قیمت نسبت به زمان",
       ["underlying_close", "strike", "dte", "iv", "نرخ بدون‌ریسک"], unit="ریال/روز"),
    _c("vega", "وگا", "S·φ(d₁)·√T ÷ ۱۰۰",
       ["underlying_close", "strike", "dte", "iv"], "به‌ازای ۱٪ تغییر نوسان.", unit="ریال"),
    _c("rho", "رو", "مشتق قیمت نسبت به نرخ بهره",
       ["underlying_close", "strike", "dte", "iv", "نرخ بدون‌ریسک"]),
    _c("intrinsic_value", "ارزش ذاتی", "max(0, S−K) برای Call و max(0, K−S) برای Put",
       ["underlying_close", "strike"], unit="ریال"),
    _c("time_value", "ارزش زمانی", "قیمت قرارداد − ارزش ذاتی",
       ["close", "intrinsic_value"], unit="ریال"),
    _c("moneyness", "وضعیت (ITM/ATM/OTM)", "مقایسه قیمت اعمال با قیمت پایه",
       ["strike", "underlying_close"]),
]

DERIVED_FIELDS = [
    _c("oi_change", "تغییر موقعیت باز", "OI امروز − OI دیروز",
       ["open_interest", "previous_open_interest"],
       "هر دو مقدار در همان پاسخ API هستند.", unit="قرارداد", kind=DERIVED),
    _c("oi_change_pct", "تغییر OI (٪)", "(OI − OI قبلی) ÷ OI قبلی",
       ["open_interest", "previous_open_interest"],
       "فقط وقتی پایه مثبت باشد؛ رشد از صفر بی‌نهایت است.", unit="٪", kind=DERIVED),
    _c("spread", "اسپرد", "عرضه − تقاضا", ["bid", "ask"], unit="ریال", kind=DERIVED),
    _c("spread_pct", "اسپرد نسبی", "(عرضه − تقاضا) ÷ میانه مظنه",
       ["bid", "ask"], "بالای ۱۵٪ عملاً غیرقابل‌معامله است.", unit="٪", kind=DERIVED),
    _c("depth_imbalance", "توازن عمق مظنه", "(حجم تقاضا − حجم عرضه) ÷ مجموع",
       ["bid_size", "ask_size"],
       "+۱ یعنی همه عمق سمت خرید، −۱ یعنی همه سمت فروش.", kind=DERIVED),
    _c("volume_oi_ratio", "نسبت حجم به موقعیت باز", "volume ÷ open_interest",
       ["volume", "open_interest"],
       "بالا بودن یعنی فعالیت امروز نسبت به موقعیت‌های موجود غیرعادی است.", kind=DERIVED),
    _c("time_value_per_day", "ارزش زمانی روزانه", "ارزش زمانی ÷ روز مانده",
       ["time_value", "dte"], "هزینه/درآمد روزانه نگهداری موقعیت.",
       unit="ریال/روز", kind=DERIVED),
    _c("premium_yield_pct", "بازده دریافتی", "قیمت قرارداد ÷ قیمت دارایی پایه",
       ["close", "underlying_close"], "برای فروشنده Call پوششی.", unit="٪", kind=DERIVED),
    _c("premium_yield_annual_pct", "بازده سالانه‌شده", "بازده × ۳۶۵ ÷ روز مانده",
       ["close", "underlying_close", "dte"],
       "سالانه‌سازی خطی است نه مرکب، تا عدد خوش‌بینانه‌تر از واقع نشود.",
       unit="٪", kind=DERIVED),
    _c("breakeven", "نقطه سربه‌سر", "K + قیمت (Call) یا K − قیمت (Put)",
       ["strike", "close", "option_type"], unit="ریال", kind=DERIVED),
    _c("breakeven_distance_pct", "فاصله تا سربه‌سر", "(سربه‌سر − قیمت پایه) ÷ قیمت پایه",
       ["breakeven", "underlying_close"],
       "دارایی پایه چقدر باید حرکت کند تا خریدار به سر‌به‌سر برسد.", unit="٪", kind=DERIVED),
    _c("moneyness_pct", "فاصله از قیمت پایه", "(K − S) ÷ S",
       ["strike", "underlying_close"],
       "نسخه پیوسته و قابل مرتب‌سازی وضعیت ITM/OTM.", unit="٪", kind=DERIVED),
    _c("hv", "نوسان تحقق‌یافته (HV)",
       "انحراف معیار بازده لگاریتمی روزانه × √۲۴۰",
       ["تاریخچه قیمت دارایی پایه"],
       "برای هر نماد جداگانه محاسبه می‌شود. ۲۴۰ روز معاملاتی بورس تهران است، نه ۲۵۲.",
       unit="٪", kind=DERIVED),
    _c("iv_hv_ratio", "نسبت IV به HV", "میانگین IV ÷ HV",
       ["iv", "hv"], "بالاتر از ۱ یعنی اختیارها نسبت به نوسان تحقق‌یافته گران‌ترند.",
       kind=DERIVED),
    _c("iv_rank", "IV Rank", "(IV امروز − کمینه) ÷ (بیشینه − کمینه)",
       ["تاریخچه IV"], "حداقل ۵ روز تاریخچه لازم دارد.", unit="٪", kind=DERIVED),
    _c("liquidity_score", "امتیاز نقدشوندگی",
       "ترکیب وزنی حجم، موقعیت باز، تعداد معاملات و اسپرد",
       ["volume", "open_interest", "trade_count", "spread_pct"],
       "مؤلفه غایب حذف و وزن‌ها بازتوزیع می‌شوند؛ صفر جایگزین نمی‌شود.", kind=DERIVED),
    _c("score", "امتیاز فرصت",
       "ترکیب وزنی نقدشوندگی، IV، موقعیت باز و انحراف قیمتی",
       ["liquidity_score", "iv", "open_interest", "iv نسبت به هم‌گروه"],
       "مقایسه فقط درون گروه هم‌ارز (همان نماد، سررسید و نوع) انجام می‌شود.",
       kind=DERIVED),
    _c("payoff / max_profit / max_loss", "سود و زیان استراتژی",
       "ارزیابی Payoff اروپایی در سررسید × اندازه قرارداد",
       ["strike", "close", "contract_size", "option_type"],
       "همه ارقام ریالی با ضریب اندازه قرارداد محاسبه می‌شوند.",
       unit="ریال", kind=DERIVED),
    _c("pop", "احتمال سودآوری",
       "شبیه‌سازی مونت‌کارلو با حرکت براونی هندسی",
       ["underlying_close", "iv", "dte", "نرخ بدون‌ریسک"], unit="٪", kind=DERIVED),
]

ALL_FIELDS = FETCHED_FIELDS + HISTORICAL_FIELDS + CALCULATED_FIELDS + DERIVED_FIELDS


def coverage_for(df, field: str) -> dict:
    """
    پوشش واقعی یک فیلد در داده موجود: چند ردیف مقدار دارند و چند ردیف صفرند.

    تفکیک «خالی» از «صفر» عمدی است: صفر بودن حجم یعنی معامله نشده، ولی
    خالی بودنش یعنی سرویس آن را نداده — و این دو مشکل کاملاً متفاوتی‌اند.
    """
    if df is None or len(df) == 0 or field not in df.columns:
        return {"present": 0, "missing": 0, "zero": 0, "total": 0 if df is None else len(df),
                "status": "ستون موجود نیست"}
    import pandas as pd
    s = df[field]
    total = len(s)
    present = int(s.notna().sum())
    try:
        zero = int((pd.to_numeric(s, errors="coerce") == 0).sum())
    except (TypeError, ValueError):
        zero = 0
    return {"present": present, "missing": total - present, "zero": zero,
            "total": total, "status": None}
