"""
موتور قیمت‌گذاری - فرمول‌های استاندارد مالی (Black-Scholes)، Greeks و
استخراج نوسان ضمنی (Implied Volatility). این فرمول‌ها عمومی و شناخته‌شده
هستند و نیازی به وابستگی خارجی ندارند.
"""
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

MIN_T = 1e-6  # جلوگیری از تقسیم بر صفر وقتی DTE=0


def _d1_d2(S, K, T, r, sigma):
    T = max(T, MIN_T)
    sigma = max(sigma, 1e-6)
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2


def bs_price(S, K, T, r, sigma, option_type="call"):
    """قیمت تئوریک Black-Scholes. T بر حسب سال (dte/365)."""
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if option_type == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def greeks(S, K, T, r, sigma, option_type="call"):
    """Delta, Gamma, Theta (روزانه), Vega (به ازای 1% تغییر IV), Rho."""
    T = max(T, MIN_T)
    sigma = max(sigma, 1e-6)
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    pdf_d1 = norm.pdf(d1)

    if option_type == "call":
        delta = norm.cdf(d1)
        theta_annual = (
            -(S * pdf_d1 * sigma) / (2 * np.sqrt(T))
            - r * K * np.exp(-r * T) * norm.cdf(d2)
        )
        rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100
    else:
        delta = norm.cdf(d1) - 1
        theta_annual = (
            -(S * pdf_d1 * sigma) / (2 * np.sqrt(T))
            + r * K * np.exp(-r * T) * norm.cdf(-d2)
        )
        rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100

    gamma = pdf_d1 / (S * sigma * np.sqrt(T))
    vega = S * pdf_d1 * np.sqrt(T) / 100  # به ازای هر 1% تغییر sigma
    theta_daily = theta_annual / 365

    return {
        "delta": float(delta),
        "gamma": float(gamma),
        "theta": float(theta_daily),
        "vega": float(vega),
        "rho": float(rho),
    }


def moneyness_status(option_type: str, strike: float, spot):
    """
    وضعیت سود/زیان قرارداد نسبت به قیمت فعلی دارایی پایه:
    "در سود" (ITM)، "در زیان" (OTM)، یا "خنثی" (ATM دقیق).
    """
    if spot is None or (isinstance(spot, float) and np.isnan(spot)):
        return None
    if abs(strike - spot) < 1e-9:
        return "خنثی"
    if option_type == "call":
        return "در سود" if spot > strike else "در زیان"
    else:
        return "در سود" if spot < strike else "در زیان"


def intrinsic_value(option_type: str, strike: float, spot):
    """ارزش ذاتی قرارداد (Intrinsic Value)."""
    if spot is None or (isinstance(spot, float) and np.isnan(spot)):
        return None
    if option_type == "call":
        return max(0.0, spot - strike)
    return max(0.0, strike - spot)


def time_value(price, intrinsic):
    """ارزش زمانی = قیمت بازار منهای ارزش ذاتی."""
    if price is None or intrinsic is None:
        return None
    if isinstance(price, float) and np.isnan(price):
        return None
    return max(0.0, price - intrinsic)


def implied_volatility(market_price, S, K, T, r, option_type="call"):
    """
    استخراج IV از قیمت بازار با روش Brent (bisection ایمن).
    اگر قیمت بازار خارج از محدوده منطقی باشد None برمی‌گرداند.
    """
    T = max(T, MIN_T)
    if market_price <= 0 or S <= 0 or K <= 0:
        return None

    intrinsic = max(0.0, (S - K) if option_type == "call" else (K - S))
    if market_price < intrinsic:
        return None  # قیمت زیر ارزش ذاتی، غیرمنطقی

    def objective(sigma):
        return bs_price(S, K, T, r, sigma, option_type) - market_price

    try:
        return brentq(objective, 1e-4, 5.0, maxiter=200)
    except ValueError:
        return None


def _is_missing(val):
    return val is None or (isinstance(val, float) and np.isnan(val))


def enrich_with_greeks(df, spot_col="underlying_close", r=0.20):
    """
    یک DataFrame از قراردادها را با IV و Greeks کامل می‌کند.
    اگر مقادیر IV/Greeks از قبل در داده موجود باشند (مثلاً از خروجی مستقیم
    سایت‌های آپشن‌گر ایرانی که خودشان این مقادیر را محاسبه کرده‌اند)، آن
    مقادیر حفظ می‌شوند و دوباره محاسبه نمی‌شوند - فقط ردیف‌های ناقص پر می‌شوند.
    r نرخ بدون ریسک فرضی است (فقط برای ردیف‌هایی که خودمان محاسبه می‌کنیم).
    """
    df = df.copy()
    has_existing_greeks = "delta" in df.columns

    ivs, deltas, gammas, thetas, vegas, rhos = [], [], [], [], [], []
    for _, row in df.iterrows():
        S = row.get(spot_col)
        K = row["strike"]
        T = max(row["dte"], 0) / 365.0
        price = row["close"]
        opt_type = row["option_type"]

        iv = row.get("iv")
        existing_delta = row.get("delta") if has_existing_greeks else None

        if not _is_missing(existing_delta):
            # این ردیف از قبل Greeks معتبر دارد (از منبع داده) - دست نمی‌زنیم
            deltas.append(existing_delta)
            gammas.append(row.get("gamma"))
            thetas.append(row.get("theta"))
            vegas.append(row.get("vega"))
            rhos.append(row.get("rho"))
            ivs.append(iv if not _is_missing(iv) else None)
            continue

        if _is_missing(iv):
            iv = implied_volatility(price, S, K, T, r, opt_type) if S else None

        if iv and S:
            g = greeks(S, K, T, r, iv, opt_type)
        else:
            g = {"delta": None, "gamma": None, "theta": None, "vega": None, "rho": None}

        ivs.append(iv)
        deltas.append(g["delta"])
        gammas.append(g["gamma"])
        thetas.append(g["theta"])
        vegas.append(g["vega"])
        rhos.append(g["rho"])

    df["iv"] = ivs
    df["delta"] = deltas
    df["gamma"] = gammas
    df["theta"] = thetas
    df["vega"] = vegas
    df["rho"] = rhos
    return df


def enrich_full_dataset(options_df, underlying_df, r=0.20):
    """
    نسخه چند-نمادی/چند-Snapshot از enrich_with_greeks: قیمت دارایی پایه را از
    underlying_df بر اساس (underlying, quote_date) merge می‌کند، سپس Greeks/IV
    را کامل می‌کند و ستون‌های Moneyness/Intrinsic/Time Value را هم اضافه می‌کند.
    برای Scanner، Opportunities و Analytics که روی کل Dataset (نه فقط یک
    Underlying/Expiry انتخابی) کار می‌کنند استفاده می‌شود.
    """
    if options_df.empty:
        return options_df.copy()

    df = options_df.copy()
    if underlying_df is not None and not underlying_df.empty:
        spot_map = underlying_df[["underlying", "quote_date", "close"]].rename(
            columns={"close": "underlying_close"}
        )
        df = df.merge(spot_map, on=["underlying", "quote_date"], how="left")
    else:
        df["underlying_close"] = np.nan

    df = enrich_with_greeks(df, spot_col="underlying_close", r=r)

    df["moneyness"] = df.apply(
        lambda row: moneyness_status(row["option_type"], row["strike"], row.get("underlying_close")),
        axis=1,
    )
    df["intrinsic_value"] = df.apply(
        lambda row: intrinsic_value(row["option_type"], row["strike"], row.get("underlying_close")),
        axis=1,
    )
    df["time_value"] = df.apply(
        lambda row: time_value(row.get("close"), row.get("intrinsic_value")),
        axis=1,
    )

    # لایه معیارهای مشتق (تغییر OI، اسپرد، بازده، سربه‌سر و ...).
    # عمداً بعد از Greeks اجرا می‌شود چون بعضی ورودی‌هایش مثل ارزش زمانی
    # خودشان محاسبه‌شده‌اند.
    from core.derived import enrich_derived
    df = enrich_derived(df)
    return df
