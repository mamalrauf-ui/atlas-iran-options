"""
موتور بک‌تست ساده - روی داده تاریخی وارد شده (چند Snapshot از تاریخ‌های
مختلف) یک استراتژی را به‌صورت Walk-Forward شبیه‌سازی می‌کند:
هر بار در نزدیک‌ترین DTE هدف وارد می‌شود، تا رسیدن به شرط خروج
(DTE هدف، سود هدف یا حد ضرر) نگه می‌دارد و سپس با قیمت بازار آن روز خارج
می‌شود. اگر تا سررسید داده‌ای برای خروج پیدا نشود، معامله به‌صورت "باز مانده"
علامت‌گذاری می‌شود.
"""
import pandas as pd
import numpy as np


def _nearest_strike(available, target):
    if len(available) == 0:
        return None
    arr = np.array(available)
    return float(arr[np.argmin(np.abs(arr - target))])


def run_backtest(
    options_df: pd.DataFrame,
    underlying_df: pd.DataFrame,
    leg_specs: list,
    entry_dte: int = 30,
    exit_dte: int = 7,
    profit_target_pct: float = 0.5,
    stop_loss_pct: float = 2.0,
    dte_tolerance: int = 10,
    initial_capital: float = None,
    fee_pct: float = 0.0,
):
    """
    leg_specs: لیستی از دیکشنری‌ها که ساختار استراتژی را تعریف می‌کند، مثلاً
        Iron Condor:
        [
            {"option_type": "put",  "side": "buy",  "offset_pct": -0.10},
            {"option_type": "put",  "side": "sell", "offset_pct": -0.05},
            {"option_type": "call", "side": "sell",  "offset_pct": 0.05},
            {"option_type": "call", "side": "buy",  "offset_pct": 0.10},
        ]
    offset_pct نسبت به قیمت لحظه ورود دارایی پایه است (مثبت = بالاتر از قیمت).

    initial_capital: سرمایه اولیه برای محاسبه بازده درصدی. اگر None باشد،
        مبنای محافظه‌کارانه (بزرگ‌ترین زیان تجمعی دوره) استفاده می‌شود.
    fee_pct: کارمزد هر سمت معامله به‌صورت درصد از ارزش معامله‌شده
        (مثلاً 0.5 یعنی نیم درصد). هم در ورود و هم در خروج اعمال می‌شود.

    Returns: trades_df, equity_df, stats(dict)
    """
    fee_rate = max(float(fee_pct or 0.0), 0.0) / 100.0
    spot_map = dict(zip(underlying_df["quote_date"], underlying_df["close"]))
    dates = sorted(set(options_df["quote_date"]).intersection(spot_map.keys()))

    trades = []
    position = None  # دیکشنری وضعیت معامله باز

    for d in dates:
        day_options = options_df[options_df["quote_date"] == d]
        spot = spot_map.get(d)
        if spot is None:
            continue

        # ---- مدیریت معامله باز: بررسی شرط خروج ----
        if position is not None:
            leg_rows = []
            all_found = True
            for leg in position["legs"]:
                match = day_options[
                    (day_options["expiry"] == leg["expiry"])
                    & (day_options["option_type"] == leg["option_type"])
                    & (day_options["strike"] == leg["strike"])
                ]
                if match.empty:
                    all_found = False
                    break
                leg_rows.append(match.iloc[0])

            if all_found:
                mark_pnl = 0.0
                exit_turnover = 0.0
                for leg, row in zip(position["legs"], leg_rows):
                    cur_price = row["close"]
                    if leg["side"] == "sell":
                        mark_pnl += (leg["entry_price"] - cur_price)
                    else:
                        mark_pnl += (cur_price - leg["entry_price"])
                    exit_turnover += abs(cur_price)
                # کارمزد ورود قبلاً از entry_credit کسر شده؛ اینجا کارمزد بستن
                # موقعیت هم کسر می‌شود تا سود/زیان گزارش‌شده خالص باشد.
                exit_fee = exit_turnover * fee_rate
                mark_pnl -= (position["entry_fee"] + exit_fee)
                dte_now = int(leg_rows[0]["dte"])

                credit = position["entry_credit"]
                target_hit = False
                stop_hit = False
                if credit > 0:  # معامله Credit
                    target_hit = mark_pnl >= profit_target_pct * credit
                    stop_hit = mark_pnl <= -stop_loss_pct * credit
                else:  # معامله Debit
                    debit = -credit
                    target_hit = mark_pnl >= profit_target_pct * debit
                    stop_hit = mark_pnl <= -stop_loss_pct * debit if debit > 0 else False

                dte_hit = dte_now <= exit_dte

                if target_hit or stop_hit or dte_hit or dte_now <= 0:
                    trades.append({
                        "entry_date": position["entry_date"],
                        "exit_date": d,
                        "expiry": position["legs"][0]["expiry"],
                        "entry_spot": position["entry_spot"],
                        "exit_spot": spot,
                        "entry_credit": credit,
                        "pnl": mark_pnl,
                        "fees": round(position["entry_fee"] + exit_fee, 2),
                        "duration_days": (pd.to_datetime(d) - pd.to_datetime(position["entry_date"])).days,
                        "return_pct": (round(mark_pnl / abs(credit) * 100, 2) if credit else None),
                        "exit_reason": "profit_target" if target_hit else (
                            "stop_loss" if stop_hit else ("dte_exit" if dte_hit else "expired")
                        ),
                        "status": "closed",
                    })
                    position = None

        # ---- جستجوی فرصت ورود جدید (فقط اگر موقعیتی باز نیست) ----
        if position is None:
            candidates = day_options.copy()
            candidates["dte_diff"] = (candidates["dte"] - entry_dte).abs()
            near = candidates[candidates["dte_diff"] <= dte_tolerance]
            if near.empty:
                continue
            best_expiry = near.loc[near["dte_diff"].idxmin(), "expiry"]
            expiry_chain = day_options[day_options["expiry"] == best_expiry]

            legs_built = []
            ok = True
            for spec in leg_specs:
                subset = expiry_chain[expiry_chain["option_type"] == spec["option_type"]]
                if subset.empty:
                    ok = False
                    break
                target_strike = spot * (1 + spec["offset_pct"])
                strike = _nearest_strike(subset["strike"].unique(), target_strike)
                row = subset[subset["strike"] == strike].iloc[0]
                legs_built.append({
                    "option_type": spec["option_type"],
                    "side": spec["side"],
                    "strike": strike,
                    "expiry": best_expiry,
                    "entry_price": float(row["close"]),
                })
            if not ok:
                continue

            entry_credit = 0.0
            entry_turnover = 0.0
            for leg in legs_built:
                entry_credit += leg["entry_price"] if leg["side"] == "sell" else -leg["entry_price"]
                # کارمزد بر ارزش مطلق معامله‌شده اعمال می‌شود، نه بر خالص —
                # چون کارگزار برای هر سمت جداگانه کارمزد می‌گیرد.
                entry_turnover += abs(leg["entry_price"])
            entry_fee = entry_turnover * fee_rate
            entry_credit -= entry_fee

            position = {
                "entry_fee": entry_fee,
                "entry_date": d,
                "entry_spot": spot,
                "entry_credit": entry_credit,
                "legs": legs_built,
            }

    trades_df = pd.DataFrame(trades)

    if trades_df.empty:
        stats = {"total_trades": 0}
        return trades_df, pd.DataFrame(), stats

    trades_df["cum_pnl"] = trades_df["pnl"].cumsum()
    equity_df = trades_df[["exit_date", "cum_pnl"]].rename(columns={"exit_date": "date"})

    wins = trades_df[trades_df["pnl"] > 0]
    losses = trades_df[trades_df["pnl"] <= 0]
    running_max = trades_df["cum_pnl"].cummax()
    drawdown = trades_df["cum_pnl"] - running_max

    # --- معیارهای بازده (بخش ۵۳) ---
    # مبنای سرمایه: بیشترین «در معرض ریسک بودن» تجمعی نیست، بلکه بزرگ‌ترین
    # زیان تجمعی است. این محافظه‌کارانه‌ترین مبنای قابل‌دفاع با داده موجود
    # است؛ سرمایه اسمی دلخواه اختراع نمی‌کنیم.
    peak_loss = float(abs(min(drawdown.min(), trades_df["cum_pnl"].min(), 0.0)))
    total_pnl = float(trades_df["pnl"].sum())

    # مبنای بازده: سرمایه اولیه‌ای که کاربر اعلام کرده، وگرنه بزرگ‌ترین زیان
    # تجمعی دوره (محافظه‌کارانه‌ترین مبنای قابل‌دفاع با داده موجود).
    if initial_capital and initial_capital > 0:
        basis = float(initial_capital)
        basis_label = "سرمایه اولیه اعلام‌شده"
    elif peak_loss > 0:
        basis = peak_loss
        basis_label = "بیشترین زیان تجمعی دوره"
    else:
        basis = None
        basis_label = None
    total_return_pct = round(total_pnl / basis * 100, 2) if basis else None

    # مدت نگهداری و بازده سالانه‌شده
    try:
        span_days = (pd.to_datetime(trades_df["exit_date"].max())
                     - pd.to_datetime(trades_df["entry_date"].min())).days
    except Exception:
        span_days = None
    annualized_pct = None
    if total_return_pct is not None and span_days and span_days >= 30:
        years = span_days / 365.0
        growth = 1 + total_pnl / basis
        if growth > 0:
            annualized_pct = round((growth ** (1 / years) - 1) * 100, 2)

    max_dd = float(drawdown.min())
    max_dd_pct = round(abs(max_dd) / basis * 100, 2) if basis else None

    stats = {
        "total_return_pct": total_return_pct,
        "annualized_return_pct": annualized_pct,
        "max_drawdown_pct": max_dd_pct,
        "capital_basis": round(basis, 2) if basis else None,
        "capital_basis_label": basis_label,
        "total_fees": round(float(trades_df["fees"].sum()), 2) if "fees" in trades_df.columns else 0.0,
        "fee_pct": fee_pct,
        "span_days": span_days,
        "avg_duration_days": (round(float(trades_df["duration_days"].mean()), 1)
                              if "duration_days" in trades_df.columns else None),
        "total_trades": len(trades_df),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(trades_df), 1) if len(trades_df) else 0,
        "total_pnl": round(trades_df["pnl"].sum(), 2),
        "avg_win": round(wins["pnl"].mean(), 2) if not wins.empty else 0,
        "avg_loss": round(losses["pnl"].mean(), 2) if not losses.empty else 0,
        "profit_factor": round(wins["pnl"].sum() / abs(losses["pnl"].sum()), 2) if not losses.empty and losses["pnl"].sum() != 0 else None,
        "max_drawdown": round(drawdown.min(), 2),
    }
    return trades_df, equity_df, stats
