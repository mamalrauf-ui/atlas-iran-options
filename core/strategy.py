"""
موتور استراتژی - محاسبه Payoff، سود/زیان حداکثر، نقاط سربه‌سر و
احتمال سودآوری (POP) برای یک استراتژی چندپایه (Multi-leg).
"""
from dataclasses import dataclass
import numpy as np


@dataclass
class Leg:
    """
    یک پایه از استراتژی.

    option_type:
        'call' / 'put' — قرارداد اختیار.
        'stock'        — خودِ دارایی پایه. برای Covered Call و Collar لازم است،
                         چون بدون آن «فروش Call» یک موقعیت برهنه با زیان
                         نامحدود به نظر می‌رسد، در حالی که با مالکیت سهم،
                         زیان کراندار است.
    برای پایه سهام:
        premium = قیمت خرید/فروش هر سهم
        strike  = بی‌معناست و نادیده گرفته می‌شود (برای سازگاری، همان premium)
    """
    option_type: str   # 'call' | 'put' | 'stock'
    side: str           # 'buy' یا 'sell'
    strike: float
    premium: float       # قیمت هر واحد قرارداد (یا هر سهم برای پایه سهام)
    qty: int = 1

    @property
    def is_stock(self) -> bool:
        return self.option_type == "stock"

    def payoff_at_expiry(self, S):
        if self.is_stock:
            # سود/زیان مالکیت سهم: قیمت سررسید منهای قیمت ورود
            pnl_per_unit = S - self.premium
        else:
            intrinsic = (max(0.0, S - self.strike) if self.option_type == "call"
                         else max(0.0, self.strike - S))
            pnl_per_unit = intrinsic - self.premium
        sign = 1 if self.side == "buy" else -1
        return sign * pnl_per_unit * self.qty


def net_premium(legs):
    """خالص دریافتی/پرداختی هنگام ورود (Credit مثبت، Debit منفی)."""
    total = 0.0
    for leg in legs:
        sign = -1 if leg.side == "buy" else 1  # buy = پرداخت، sell = دریافت
        total += sign * leg.premium * leg.qty
    return total


def payoff_curve(legs, price_range):
    """
    Payoff کل استراتژی روی یک بازه از قیمت‌های دارایی پایه در سررسید.

    نسخه برداری‌شده (Vectorized): ریاضیات دقیقاً همان Leg.payoff_at_expiry است،
    فقط به‌جای حلقه پایتون روی هزاران قیمت، یک‌بار روی هر پایه با numpy محاسبه
    می‌شود. این برای اسکن استراتژی روی کل بازار حیاتی است (۲۰۰۰ قیمت × چند پایه
    × ده‌ها قالب × ده‌ها نماد).
    """
    S = np.asarray(price_range, dtype=float)
    total = np.zeros_like(S)
    for leg in legs:
        if getattr(leg, "option_type", None) == "stock":
            pnl = S - leg.premium
        elif leg.option_type == "call":
            pnl = np.maximum(0.0, S - leg.strike) - leg.premium
        else:
            pnl = np.maximum(0.0, leg.strike - S) - leg.premium
        sign = 1 if leg.side == "buy" else -1
        total += sign * pnl * leg.qty
    return total


def max_profit_loss(legs, S_ref, width_factor=3.0, steps=2000):
    """
    برآورد سود/زیان حداکثر با اسکن یک بازه وسیع قیمتی حول قیمت فعلی.
    برای استراتژی‌های با ریسک نامحدود (مثل Naked Call فروخته‌شده)، سود/زیان
    در انتهای بازه به‌عنوان تقریبی از "نامحدود" گزارش می‌شود.
    """
    low = max(0.01, S_ref * (1 - width_factor))
    high = S_ref * (1 + width_factor)
    prices = np.linspace(low, high, steps)
    payoffs = payoff_curve(legs, prices)

    max_p = payoffs.max()
    min_p = payoffs.min()

    # اگر Payoff در انتهای بازه (بالاترین قیمت) همچنان رو به افزایش/کاهش باشد،
    # یعنی سود یا زیان عملاً نامحدود است (مثلاً Call فروخته‌شده بدون پوشش)
    unbounded_profit = payoffs[-1] > payoffs[-2]
    unbounded_loss = payoffs[-1] < payoffs[-2]

    return {
        "max_profit": float(max_p) if not unbounded_profit else None,
        "max_loss": float(min_p) if not unbounded_loss else None,
        "max_profit_is_unbounded": bool(unbounded_profit),
        "max_loss_is_unbounded": bool(unbounded_loss),
    }


def breakevens(legs, S_ref, width_factor=3.0, steps=5000):
    """پیدا کردن نقاط سربه‌سر با جستجوی تغییر علامت روی منحنی Payoff."""
    low = max(0.01, S_ref * (1 - width_factor))
    high = S_ref * (1 + width_factor)
    prices = np.linspace(low, high, steps)
    payoffs = payoff_curve(legs, prices)

    points = []
    for i in range(len(prices) - 1):
        p1, p2 = payoffs[i], payoffs[i + 1]
        if p1 == 0:
            points.append(prices[i])
        elif p1 * p2 < 0:
            # درون‌یابی خطی برای تقریب دقیق‌تر نقطه صفر
            frac = -p1 / (p2 - p1)
            points.append(prices[i] + frac * (prices[i + 1] - prices[i]))
    return sorted(set(round(p, 2) for p in points))


def probability_of_profit(legs, S0, sigma, T_years, r=0.20, n_sims=20000, seed=42):
    """
    برآورد POP با شبیه‌سازی Monte Carlo تحت حرکت هندسی براونی (GBM) —
    همان رویکردی که در ابزارهایی مثل poptions استفاده می‌شود، اما پیاده‌سازی
    ساده و مستقل با numpy.
    """
    if T_years <= 0 or sigma <= 0:
        return None
    rng = np.random.default_rng(seed)
    Z = rng.standard_normal(n_sims)
    ST = S0 * np.exp((r - 0.5 * sigma ** 2) * T_years + sigma * np.sqrt(T_years) * Z)
    # از همان payoff_curve برداری‌شده استفاده می‌شود: مسیرهای Monte Carlo هم
    # فقط یک بردار قیمت‌اند. نتیجه با حلقه قبلی یکسان است (همان seed، همان فرمول)
    # ولی به‌جای n_sims بار فراخوانی پایتونی، یک عملیات numpy انجام می‌شود.
    payoffs = payoff_curve(legs, ST)
    return float((payoffs > 0).mean())


PRESET_STRATEGIES = {
    "Long Call": lambda K, prem: [Leg("call", "buy", K, prem)],
    "Long Put": lambda K, prem: [Leg("put", "buy", K, prem)],
    "Covered Call (فرض تصاحب دارایی پایه جدا)": lambda K, prem: [Leg("call", "sell", K, prem)],
    "Bull Call Spread": lambda K1, p1, K2, p2: [Leg("call", "buy", K1, p1), Leg("call", "sell", K2, p2)],
    "Bear Put Spread": lambda K1, p1, K2, p2: [Leg("put", "buy", K1, p1), Leg("put", "sell", K2, p2)],
    "Straddle": lambda K, pc, pp: [Leg("call", "buy", K, pc), Leg("put", "buy", K, pp)],
    "Strangle": lambda Kc, pc, Kp, pp: [Leg("call", "buy", Kc, pc), Leg("put", "buy", Kp, pp)],
    "Iron Condor": lambda Kp1, pp1, Kp2, pp2, Kc1, pc1, Kc2, pc2: [
        Leg("put", "buy", Kp1, pp1),
        Leg("put", "sell", Kp2, pp2),
        Leg("call", "sell", Kc1, pc1),
        Leg("call", "buy", Kc2, pc2),
    ],
}


# ---------------------------------------------------------------------------
# قالب‌های استراتژی برای صفحه «ساخت استراتژی» - هر قالب لیستی از "نقش" پایه‌هاست:
# نوع (call/put)، جهت (buy/sell)، تعداد پیش‌فرض، و ترجیح انتخاب پیش‌فرض Strike
# (rank): "atm" نزدیک‌ترین به قیمت فعلی، "otm" اولین Strike خارج از سود بعد از
# ATM، "far_otm" یک پله دورتر از آن (برای پایه‌های پوششی در Iron Condor/Butterfly).
# کاربر همیشه می‌تواند این پیشنهاد پیش‌فرض را از یک لیست کشویی از قراردادهای
# واقعی موجود در داده تغییر دهد.
# ---------------------------------------------------------------------------
STRATEGY_TEMPLATES = {
    "Long Call (خرید اختیار خرید)": [
        {"option_type": "call", "side": "buy", "qty": 1, "rank": "atm"},
    ],
    "Long Put (خرید اختیار فروش)": [
        {"option_type": "put", "side": "buy", "qty": 1, "rank": "atm"},
    ],
    # Covered Call واقعی: مالکیت سهم + فروش Call. بدون پایه سهام، این موقعیت
    # یک Naked Call با زیان نامحدود است که تصویر ریسک را کاملاً غلط نشان می‌دهد.
    "Covered Call (خرید سهم + فروش Call)": [
        {"option_type": "stock", "side": "buy", "qty": 1},
        {"option_type": "call", "side": "sell", "qty": 1, "rank": "otm"},
    ],
    "Naked Call (فروش Call بدون پوشش)": [
        {"option_type": "call", "side": "sell", "qty": 1, "rank": "otm"},
    ],
    "Protective Put (خرید Put برای پوشش - با فرض مالکیت جدا از دارایی پایه)": [
        {"option_type": "put", "side": "buy", "qty": 1, "rank": "otm"},
    ],
    "Bull Call Spread (اسپرد صعودی با Call)": [
        {"option_type": "call", "side": "buy", "qty": 1, "rank": "atm"},
        {"option_type": "call", "side": "sell", "qty": 1, "rank": "otm"},
    ],
    "Bear Call Spread (اسپرد نزولی اعتباری با Call)": [
        {"option_type": "call", "side": "sell", "qty": 1, "rank": "atm"},
        {"option_type": "call", "side": "buy", "qty": 1, "rank": "otm"},
    ],
    "Bull Put Spread (اسپرد صعودی اعتباری با Put)": [
        {"option_type": "put", "side": "sell", "qty": 1, "rank": "atm"},
        {"option_type": "put", "side": "buy", "qty": 1, "rank": "otm"},
    ],
    "Bear Put Spread (اسپرد نزولی با Put)": [
        {"option_type": "put", "side": "buy", "qty": 1, "rank": "atm"},
        {"option_type": "put", "side": "sell", "qty": 1, "rank": "otm"},
    ],
    "Long Straddle (خرید هم‌زمان Call و Put هم‌قیمت)": [
        {"option_type": "call", "side": "buy", "qty": 1, "rank": "atm"},
        {"option_type": "put", "side": "buy", "qty": 1, "rank": "atm"},
    ],
    "Long Strangle (خرید Call و Put با Strike متفاوت)": [
        {"option_type": "call", "side": "buy", "qty": 1, "rank": "otm"},
        {"option_type": "put", "side": "buy", "qty": 1, "rank": "otm"},
    ],
    "Iron Condor": [
        {"option_type": "put", "side": "buy", "qty": 1, "rank": "far_otm"},
        {"option_type": "put", "side": "sell", "qty": 1, "rank": "otm"},
        {"option_type": "call", "side": "sell", "qty": 1, "rank": "otm"},
        {"option_type": "call", "side": "buy", "qty": 1, "rank": "far_otm"},
    ],
    "Iron Butterfly": [
        {"option_type": "put", "side": "buy", "qty": 1, "rank": "far_otm"},
        {"option_type": "put", "side": "sell", "qty": 1, "rank": "atm"},
        {"option_type": "call", "side": "sell", "qty": 1, "rank": "atm"},
        {"option_type": "call", "side": "buy", "qty": 1, "rank": "far_otm"},
    ],
    "Collar (خرید سهم + Put حمایتی + فروش Call)": [
        {"option_type": "stock", "side": "buy", "qty": 1},
        {"option_type": "put", "side": "buy", "qty": 1, "rank": "otm"},
        {"option_type": "call", "side": "sell", "qty": 1, "rank": "otm"},
    ],
    "ترکیب سفارشی (خودم قرارداد اضافه می‌کنم)": None,
}
