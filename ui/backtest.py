"""
Backtest — آزمون تاریخی استراتژی (بخش ۵۱ تا ۵۵ Master Prompt).

پرسش اصلی صفحه: «اگر این استراتژی را در گذشته اجرا می‌کردم چه نتیجه‌ای داشت؟»

چهار بخش مفهومی، در یک فضای کار پلکانی (نه ویزارد چندصفحه‌ای):
    ۰۱ استراتژی · ۰۲ بازار و دوره · ۰۳ قواعد · ۰۴ نتایج

بازتولیدپذیری (بخش ۵۴): هر نتیجه، پیکربندی کاملی که با آن ساخته شده را
کنار خودش نگه می‌دارد.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import backtest as engine, database, design
from ui import common
from ui import components as c
from ui.common import JD, _jalali_date_cols

TEMPLATES = {
    "Iron Condor": "فروش Strangle با دو پایه پوششی — سود از آرامش بازار",
    "Short Strangle": "فروش هم‌زمان Call و Put دور از قیمت — بدون پوشش",
    "Long Straddle": "خرید هم‌زمان Call و Put هم‌قیمت — سود از حرکت شدید",
}


def render():
    intent = common.take_intent("dataset") or {}
    if intent.get("dataset"):
        st.session_state["bt_dataset"] = intent["dataset"]
    if intent.get("underlying"):
        st.session_state["bt_underlying"] = intent["underlying"]

    datasets = database.list_datasets()
    if datasets.empty:
        c.page_header("بک‌تست", "آزمون استراتژی روی داده تاریخی",
                      status="err", status_text="داده‌ای موجود نیست")
        c.empty_state("هنوز داده‌ای وارد نشده", "از «مرکز داده» فایل بازار را وارد کنید.")
        return

    c.page_header("بک‌تست", "اجرای استراتژی روی Snapshotهای گذشته همین مجموعه")

    # ---------------- ۰۱ استراتژی ----------------
    c.section("۰۱ · استراتژی", "چه چیزی آزمون شود")
    s1, s2 = st.columns([1.4, 2.6])
    with s1:
        template = st.selectbox("قالب", list(TEMPLATES.keys()), key="bt_template")
    with s2:
        c.spacer(24)
        c.helper(TEMPLATES[template])

    saved = database.list_strategies()
    if not saved.empty:
        c.helper(f"{len(saved)} استراتژی ذخیره‌شده دارید. بک‌تست فعلی بر پایه فاصله درصدی از "
                 "قیمت روز ورود کار می‌کند، نه قیمت‌های اعمال ثابت — پس استراتژی ذخیره‌شده "
                 "مستقیماً قابل اجرا نیست و باید قالب معادلش را اینجا انتخاب کنید.")

    # ---------------- ۰۲ بازار و دوره ----------------
    c.spacer(20)
    c.section("۰۲ · بازار و دوره", "روی چه نمادی و چه بازه‌ای")
    m1, m2, m3 = st.columns(3)
    with m1:
        dataset_name = st.selectbox("Dataset", datasets["dataset"].tolist(), key="bt_dataset")
    underlyings = database.list_underlyings(dataset_name)
    if not underlyings:
        c.empty_state("این مجموعه نماد پایه‌ای ندارد", "مجموعه دیگری انتخاب کنید.")
        return
    with m2:
        underlying = st.selectbox("نماد پایه", underlyings, key="bt_underlying")

    options_df = database.load_data(dataset_name=dataset_name, underlying=underlying)
    underlying_df = database.load_underlying_data(dataset_name=dataset_name, underlying=underlying)

    dates = sorted(options_df["quote_date"].dropna().unique()) if not options_df.empty else []
    n_dates = len(dates)
    covered = sorted(set(dates) & set(underlying_df["quote_date"])) if not underlying_df.empty else []

    with m3:
        st.markdown(f'<div class="kpi-label">Snapshotهای قابل‌استفاده</div>'
                    f'<div class="kpi-value num">{len(covered)}</div>', unsafe_allow_html=True)

    # تاریخچه از سرویس گرفته می‌شود، نه از Snapshotهای دستی کاربر.
    c.spacer(16)
    if not c.history_gate(dataset_name, underlying, need_days=3, have_days=len(covered),
                          purpose="بک‌تست", key="bt_hist"):
        return

    c.helper(f"دوره: {JD(covered[0])} تا {JD(covered[-1])} — {len(covered)} روز معاملاتی")

    # ---------------- ۰۳ قواعد ----------------
    c.spacer(20)
    c.section("۰۳ · قواعد", "ورود، خروج و انتخاب قیمت اعمال")
    r1, r2 = st.columns(2)
    with r1:
        wing = st.slider("فاصله پایه فروخته‌شده از قیمت روز (٪)", 1, 30, 8, key="bt_wing")
        entry_dte = st.number_input("روز تا سررسید هنگام ورود", 1, 365, 30, key="bt_entry_dte")
    with r2:
        protect = st.slider("فاصله پایه پوششی (٪) — فقط Iron Condor",
                            wing + 1, 50, max(15, wing + 2), key="bt_protect",
                            disabled=template != "Iron Condor")
        exit_dte = st.number_input("روز تا سررسید هنگام خروج", 0, 364, 7, key="bt_exit_dte")

    with st.expander("قواعد پیشرفته — سرمایه، کارمزد و شرایط خروج"):
        a1, a2, a3 = st.columns(3)
        target = a1.number_input("هدف سود (نسبت به خالص ورود)", 0.1, 10.0, 0.5, 0.1, key="bt_target")
        stop = a2.number_input("حد ضرر (نسبت به خالص ورود)", 0.1, 10.0, 2.0, 0.1, key="bt_stop")
        tol = a3.number_input("تحمل انحراف DTE ورود (روز)", 1, 60, 10, key="bt_tol")

        b1, b2 = st.columns(2)
        capital = b1.number_input(
            "سرمایه اولیه", 0, value=0, step=1_000_000, key="bt_capital",
            help="مبنای محاسبه بازده درصدی. اگر صفر بماند، Atlas از بزرگ‌ترین زیان "
                 "تجمعی دوره به‌عنوان مبنای محافظه‌کارانه استفاده می‌کند.",
        )
        fee = b2.number_input(
            "کارمزد هر سمت معامله (٪)", 0.0, 5.0, 0.5, 0.05, format="%.2f", key="bt_fee",
            help="درصد از ارزش هر پایه، هم در ورود و هم در خروج. کارمزد رایج "
                 "اختیار معامله در بورس ایران حدود ۰.۱ تا ۰.۵ درصد است — عدد دقیق "
                 "را از کارگزار خود بگیرید.",
        )

    if exit_dte >= entry_dte:
        c.spacer(12)
        c.error_state("قواعد ناسازگار",
                      "روز خروج باید کمتر از روز ورود باشد، وگرنه هیچ معامله‌ای باز نمی‌ماند.")
        return

    w, p = wing / 100, protect / 100
    if template == "Iron Condor":
        legs = [{"option_type": "put", "side": "buy", "offset_pct": -p},
                {"option_type": "put", "side": "sell", "offset_pct": -w},
                {"option_type": "call", "side": "sell", "offset_pct": w},
                {"option_type": "call", "side": "buy", "offset_pct": p}]
    elif template == "Short Strangle":
        legs = [{"option_type": "put", "side": "sell", "offset_pct": -w},
                {"option_type": "call", "side": "sell", "offset_pct": w}]
    else:
        legs = [{"option_type": "call", "side": "buy", "offset_pct": 0.0},
                {"option_type": "put", "side": "buy", "offset_pct": 0.0}]

    c.spacer(16)
    if not st.button("اجرای بک‌تست", type="primary", key="bt_run"):
        return

    with st.spinner("در حال شبیه‌سازی معاملات…"):
        trades, equity, stats = engine.run_backtest(
            options_df, underlying_df, legs,
            entry_dte=int(entry_dte), exit_dte=int(exit_dte),
            profit_target_pct=float(target), stop_loss_pct=float(stop),
            dte_tolerance=int(tol),
            initial_capital=float(capital) if capital else None,
            fee_pct=float(fee),
        )

    # ---------------- ۰۴ نتایج ----------------
    c.spacer(24)
    c.section("۰۴ · نتایج")
    if stats.get("total_trades", 0) == 0:
        c.empty_state(
            "هیچ معامله‌ای شبیه‌سازی نشد",
            f"در هیچ Snapshot، سررسیدی با حدود {entry_dte} روز تا انقضا (±{tol} روز) و "
            "قراردادهای لازم برای همه پایه‌ها پیدا نشد. «روز تا سررسید ورود» یا «تحمل انحراف» "
            "را تغییر دهید، یا قالب ساده‌تری با پایه‌های کمتر انتخاب کنید.",
        )
        return

    _config_card(template, dataset_name, underlying, covered, wing, protect,
                 entry_dte, exit_dte, target, stop, tol, capital, fee, stats)
    c.spacer(20)
    _kpis(stats)
    c.spacer(20)
    _equity_chart(equity, trades)
    c.spacer(20)
    _trades_table(trades)


# ===========================================================================
def _kpis(s):
    c.kpi_strip([
        {"label": "بازده کل", "value": f"{s['total_return_pct']:+.1f}%" if s.get("total_return_pct") is not None else "—",
         "na": s.get("total_return_pct") is None,
         "tone": "pos" if (s.get("total_return_pct") or 0) > 0 else "neg"},
        {"label": "بازده سالانه‌شده",
         "value": f"{s['annualized_return_pct']:+.1f}%" if s.get("annualized_return_pct") is not None else "—",
         "na": s.get("annualized_return_pct") is None},
        {"label": "حداکثر افت",
         "value": f"{s['max_drawdown_pct']:.1f}%" if s.get("max_drawdown_pct") is not None else c.fmt_int(s["max_drawdown"]),
         "na": False},
        {"label": "نرخ برد", "value": f"{s['win_rate_pct']:.0f}%", "na": False},
        {"label": "Profit Factor", "value": c.fmt_ratio(s["profit_factor"]) if s["profit_factor"] else "—",
         "na": not s["profit_factor"]},
        {"label": "تعداد معاملات", "value": c.fmt_int(s["total_trades"]), "na": False},
    ])
    notes = []
    if s.get("capital_basis"):
        notes.append(f"مبنای بازده: {s.get('capital_basis_label')} ({s['capital_basis']:,.0f}).")
    if s.get("total_fees"):
        gross = s["total_pnl"] + s["total_fees"]
        notes.append(f"کارمزد پرداختی: {s['total_fees']:,.0f} — سود/زیان پیش از کارمزد "
                     f"{gross:+,.0f} بوده است.")
    if s.get("annualized_return_pct") is None and s.get("span_days"):
        notes.append(f"بازده سالانه‌شده محاسبه نشد: دوره آزمون فقط {s['span_days']} روز است "
                     "(حداقل ۳۰ روز لازم است).")
    if s["total_trades"] < 10:
        notes.append(f"فقط {s['total_trades']} معامله — نرخ برد و Profit Factor با این تعداد "
                     "از نظر آماری قابل‌اتکا نیستند.")
    for n in notes:
        c.helper("• " + n)
    c.spacer(8)
    c.kpi_strip([
        {"label": "سود/زیان خالص", "value": f"{s['total_pnl']:+,.0f}", "na": False,
         "tone": "pos" if s["total_pnl"] > 0 else "neg"},
        {"label": "معاملات برنده", "value": c.fmt_int(s["winning_trades"]), "na": False},
        {"label": "معاملات بازنده", "value": c.fmt_int(s["losing_trades"]), "na": False},
        {"label": "میانگین برد", "value": f"{s['avg_win']:+,.0f}", "na": False},
        {"label": "میانگین باخت", "value": f"{s['avg_loss']:+,.0f}", "na": False},
        {"label": "میانگین مدت", "value": f"{s['avg_duration_days']:.0f} روز" if s.get("avg_duration_days") else "—",
         "na": not s.get("avg_duration_days")},
    ])


def _config_card(template, dataset, underlying, covered, wing, protect,
                 entry_dte, exit_dte, target, stop, tol, capital, fee, stats):
    """بخش ۵۴: نتیجه بدون پیکربندی، غیرقابل بازتولید و بی‌ارزش است."""
    items = [
        ("استراتژی", template), ("مجموعه داده", dataset), ("نماد پایه", underlying),
        ("دوره", f"{JD(covered[0])} تا {JD(covered[-1])}"),
        ("Snapshotها", f"{len(covered)} روز"),
        ("فاصله پایه فروش", f"{wing}%"),
        ("فاصله پایه پوششی", f"{protect}%" if template == "Iron Condor" else "—"),
        ("DTE ورود / خروج", f"{entry_dte} / {exit_dte} (±{tol})"),
        ("هدف سود / حد ضرر", f"{target}× / {stop}×"),
        ("سرمایه اولیه", f"{capital:,.0f}" if capital else "اعلام نشده"),
        ("کارمزد هر سمت", f"{fee:.2f}%"),
        ("کل کارمزد پرداختی", f"{stats.get('total_fees', 0):,.0f}"),
    ]
    cells = "".join(
        f'<div style="min-width:150px"><div class="kpi-label">{c.esc(k)}</div>'
        f'<div style="font-size:.82rem;color:var(--text-1)">{c.esc(v)}</div></div>'
        for k, v in items
    )
    st.markdown(
        f'<div class="brief"><div class="kpi-label" style="margin-bottom:10px">'
        f'پیکربندی این نتیجه</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:18px 28px">{cells}</div></div>',
        unsafe_allow_html=True)
    c.helper("کارمزد در هر دو سمت ورود و خروج از سود/زیان کسر شده است. "
             "مالیات، لغزش قیمت (Slippage) و اثر نقدشوندگی مدل نشده‌اند.")


def _equity_chart(equity, trades):
    c.section("منحنی سرمایه", "سود/زیان تجمعی در طول دوره")
    T = design.TOKENS
    x = [JD(d) for d in equity["date"]]
    y = equity["cum_pnl"]
    peak = y.cummax()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=peak, mode="lines", name="سقف",
                             line=dict(color=T["border_strong"], width=1, dash="dot"),
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", name="سود/زیان تجمعی",
                             line=dict(color=T["accent"], width=2),
                             marker=dict(size=5,
                                         color=[T["positive"] if v >= 0 else T["negative"]
                                                for v in trades["pnl"]]),
                             hovertemplate="%{x}<br>تجمعی: %{y:,.0f}<extra></extra>"))
    fig.add_hline(y=0, line_width=1, line_color=T["border_strong"])
    layout = dict(design.PLOTLY_LAYOUT)
    layout.update(height=300, margin=dict(l=8, r=8, t=8, b=28))
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    dd = y - peak
    if dd.min() < 0:
        c.section("افت از سقف (Drawdown)")
        fig2 = go.Figure(go.Scatter(x=x, y=dd, mode="lines", fill="tozeroy",
                                    line=dict(color=T["negative"], width=1.5),
                                    fillcolor="rgba(229,72,77,0.12)",
                                    hovertemplate="%{x}<br>افت: %{y:,.0f}<extra></extra>"))
        layout2 = dict(design.PLOTLY_LAYOUT)
        layout2.update(height=180, margin=dict(l=8, r=8, t=8, b=28))
        fig2.update_layout(**layout2)
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})


def _trades_table(trades):
    c.section("تاریخچه معاملات", f"{len(trades)} معامله")
    reasons = {"profit_target": "هدف سود", "stop_loss": "حد ضرر",
               "dte_exit": "خروج زمانی", "expired": "سررسید"}
    headers = ["#", "ورود", "خروج", "مدت", "قیمت پایه ورود", "قیمت پایه خروج",
               "خالص ورود", "کارمزد", "سود/زیان", "بازده", "دلیل خروج"]
    rows = []
    for i, t in trades.iterrows():
        pnl = t["pnl"]
        cls = "pos" if pnl > 0 else ("neg" if pnl < 0 else "muted")
        ret = t.get("return_pct")
        rows.append([
            f'<span class="rank">{i + 1}</span>',
            c.num(JD(t["entry_date"])), c.num(JD(t["exit_date"])),
            c.num(f"{int(t['duration_days'])} روز" if pd.notna(t.get("duration_days")) else c.NA),
            c.num(c.fmt_int(t["entry_spot"])), c.num(c.fmt_int(t["exit_spot"])),
            c.num(f"{t['entry_credit']:+,.0f}"),
            c.num(c.fmt_int(t.get("fees"))),
            f'<span class="num {cls}">{pnl:+,.0f}</span>',
            f'<span class="num {cls}">{ret:+.1f}%</span>' if ret is not None and pd.notna(ret) else f'<span class="muted">{c.NA}</span>',
            c.esc(reasons.get(t["exit_reason"], t["exit_reason"])),
        ])
    c.table(headers, rows, numeric_cols={0, 1, 2, 3, 4, 5, 6, 7, 8, 9})

    csv = trades.to_csv(index=False).encode("utf-8-sig")
    st.download_button("دانلود CSV معاملات", csv, "atlas_backtest_trades.csv",
                       "text/csv", key="bt_csv")
