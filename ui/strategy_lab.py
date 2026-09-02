"""
Strategy Lab — ساخت و تحلیل استراتژی (بخش ۴۲ تا ۵۰ Master Prompt).

پرسش اصلی صفحه: «چه استراتژی‌ای بسازم و ساختار سود/زیان آن چیست؟»

این صفحه کشف بازار نیست (آن کار Scanner/Opportunities است):
    ساخت موقعیت + تحلیل Payoff + تحلیل سناریو

چیدمان: چپ = سازنده پایه‌ها، راست = Payoff و معیارهای اصلی،
پایین = تحلیل سناریو و Greeks (ثانویه، بخش ۴۸).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import database, design, strategy as engine
from ui import common
from ui import components as c
from ui.common import JD

SCENARIO_STEPS = [-20, -10, -5, 0, 5, 10, 20]
MANUAL = "ترکیب دستی (پایه‌ها را خودم انتخاب می‌کنم)"


def render():
    r = st.session_state.risk_free_rate

    hint = st.session_state.pop("strategy_lab_hint", None)
    pending = st.session_state.get("pending_strategy_legs")

    datasets = database.list_datasets()
    if datasets.empty:
        c.page_header("استراتژی لب", "ساخت موقعیت و تحلیل سود/زیان",
                      status="err", status_text="داده‌ای موجود نیست")
        c.empty_state("هنوز داده‌ای وارد نشده", "از «مرکز داده» یک فایل اختیار معامله وارد کنید.")
        return

    # --- انتخاب داده (Context منتقل‌شده اولویت دارد) ---
    ds_list = datasets["dataset"].tolist()
    if pending and pending.get("dataset") in ds_list:
        st.session_state["sl_dataset"] = pending["dataset"]

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        dataset_name = st.selectbox("Dataset", ds_list, key="sl_dataset")
    underlyings = database.list_underlyings(dataset_name)
    if not underlyings:
        c.page_header("استراتژی لب", "ساخت موقعیت و تحلیل سود/زیان")
        c.empty_state("این مجموعه نماد پایه‌ای ندارد", "مجموعه دیگری انتخاب کنید.")
        return
    if pending and pending.get("underlying") in underlyings:
        st.session_state["sl_underlying"] = pending["underlying"]
    with f2:
        underlying = st.selectbox("نماد پایه", underlyings, key="sl_underlying")

    options_all, underlying_all = common.load_dataset(dataset_name)
    sym = options_all[options_all["underlying"] == underlying]
    if sym.empty:
        c.page_header("استراتژی لب", underlying)
        c.empty_state("قراردادی برای این نماد نیست", "نماد دیگری انتخاب کنید.")
        return

    with f3:
        qdates = sorted(sym["quote_date"].dropna().unique(), reverse=True)
        quote_date = st.selectbox("تاریخ Snapshot", qdates, format_func=JD, key="sl_qdate")

    snap = common.enrich_snapshot(options_all, underlying_all, quote_date, r,
                                  st.session_state.atm_band_pct)
    snap = snap[snap["underlying"] == underlying]
    if snap.empty:
        c.page_header("استراتژی لب", underlying, snapshot_label=JD(quote_date))
        c.empty_state("این نماد در Snapshot انتخاب‌شده قرارداد ندارد", "تاریخ دیگری انتخاب کنید.")
        return

    with f4:
        expiries = sorted(snap["expiry"].dropna().unique())
        expiry = st.selectbox("سررسید", expiries, format_func=JD, key="sl_expiry")

    chain = snap[snap["expiry"] == expiry].copy()

    c.page_header("استراتژی لب", f"ساخت و تحلیل موقعیت روی {underlying}",
                  snapshot_label=JD(quote_date), status="ok", status_text="داده به‌روز است")

    if hint:
        st.markdown(f'<div class="chips"><span class="chip">{c.esc(hint)}</span></div>',
                    unsafe_allow_html=True)
        c.spacer(10)

    # --- قیمت مرجع: فقط قیمت واقعی. بدون آن تحلیل بی‌معناست ---
    spot_series = chain["underlying_close"].dropna() if "underlying_close" in chain.columns else pd.Series(dtype=float)
    if spot_series.empty:
        c.error_state(
            "قیمت دارایی پایه برای این تاریخ موجود نیست",
            "Payoff، نقاط سربه‌سر و احتمال سودآوری همگی به قیمت واقعی دارایی پایه وابسته‌اند. "
            "ستون «آخرین پایه» را به فایل اضافه کنید یا فایل قیمت دارایی پایه را جداگانه وارد کنید. "
            "Atlas عمداً از میانه قیمت‌های اعمال به‌عنوان جایگزین استفاده نمی‌کند، چون عددی ساختگی می‌سازد.",
        )
        return
    S_ref = float(spot_series.iloc[0])

    calls = chain[chain["option_type"] == "call"].sort_values("strike").reset_index(drop=True)
    puts = chain[chain["option_type"] == "put"].sort_values("strike").reset_index(drop=True)

    # =================== چیدمان اصلی ===================
    left, right = st.columns([1, 1.25], gap="large")

    with left:
        c.section("سازنده موقعیت", f"قیمت {underlying}: {S_ref:,.0f}")
        template_names = [MANUAL] + [k for k, v in engine.STRATEGY_TEMPLATES.items() if v is not None]
        default_idx = 0 if pending else 1
        template_name = st.selectbox("قالب", template_names,
                                     index=min(default_idx, len(template_names) - 1),
                                     key="sl_template")
        legs, leg_rows = (_manual_builder(calls, puts, S_ref, pending)
                          if template_name == MANUAL
                          else _template_builder(template_name, calls, puts, S_ref))

    if not legs:
        with right:
            c.section("نتیجه")
            c.empty_state("هنوز پایه‌ای ساخته نشده",
                          "برای این سررسید داده Call یا Put کافی نیست، یا هنوز قراردادی انتخاب نکرده‌اید.")
        return

    # محاسبات مرکزی — همه از core
    credit = engine.net_premium(legs)
    mpl = engine.max_profit_loss(legs, S_ref)
    bes = engine.breakevens(legs, S_ref)
    sigma = float(chain["iv"].dropna().mean()) if chain["iv"].notna().any() else None
    dte = int(chain["dte"].dropna().iloc[0]) if chain["dte"].notna().any() else None
    pop = (engine.probability_of_profit(legs, S_ref, sigma, dte / 365, r)
           if sigma and dte and dte > 0 else None)

    with right:
        c.section("سود و زیان در سررسید")
        _payoff_chart(legs, S_ref, bes, mpl)
        _metrics(credit, mpl, bes, pop, sigma, dte)

    # --- پایه‌ها ---
    c.spacer(24)
    c.section("پایه‌های موقعیت")
    _legs_table(leg_rows)

    # --- تحلیل سناریو (بخش ۴۹) ---
    c.spacer(24)
    c.section("تحلیل سناریو", "سود/زیان در سررسید اگر قیمت دارایی پایه تغییر کند")
    _scenarios(legs, S_ref)

    # --- Greeks: ثانویه (بخش ۴۸) ---
    c.spacer(16)
    with st.expander("حساسیت‌های خالص (Net Greeks)"):
        _net_greeks(leg_rows)

    # --- اکشن‌ها (بخش ۵۰) ---
    c.spacer(24)
    c.section("اقدام")
    _actions(legs, leg_rows, template_name, dataset_name, underlying, quote_date, expiry, S_ref)


# ===========================================================================
# سازنده‌ها
# ===========================================================================
def _fmt_contract(row) -> str:
    d = f"  Δ{row['delta']:.2f}" if pd.notna(row.get("delta")) else ""
    mb = row.get("moneyness_bucket") or ""
    return f"{row['strike']:,.0f}  ·  {row['close']:,.0f}{d}  {mb}"


def _leg_record(row, side, qty, s_ref):
    return {
        "symbol": row.get("symbol"), "option_type": row["option_type"], "side": side,
        "strike": float(row["strike"]), "premium": float(row["close"]), "qty": int(qty),
        "moneyness": row.get("moneyness_bucket"),
        **{k: row.get(k) for k in ("delta", "gamma", "theta", "vega")},
    }


def _default_index(book: pd.DataFrame, rank: str, opt_type: str, s_ref: float) -> int:
    """همان منطق پیش‌فرض core/opportunity برای انتخاب Strike."""
    arr = book["strike"].values
    if len(arr) == 0:
        return 0
    atm = int(np.argmin(np.abs(arr - s_ref)))
    if rank == "atm":
        return atm
    step = 1 if rank == "otm" else 3
    idx = atm + step if opt_type == "call" else atm - step
    return max(0, min(len(arr) - 1, idx))


def _template_builder(template_name, calls, puts, s_ref):
    template = engine.STRATEGY_TEMPLATES[template_name]
    legs, rows = [], []
    for i, role in enumerate(template):
        # پایه سهام: قابل انتخاب نیست چون فقط یک دارایی پایه وجود دارد؛
        # قیمت ورودش قیمت واقعی همان روز است.
        if role["option_type"] == "stock":
            side_fa = "خرید" if role["side"] == "buy" else "فروش"
            g1, g2 = st.columns([3, 1])
            g1.markdown(
                f'<div class="kpi-label">پایه {i + 1} — {side_fa} دارایی پایه</div>'
                f'<div style="font-size:.86rem;color:var(--text-1)">قیمت ورود: '
                f'<span class="num">{s_ref:,.0f}</span></div>', unsafe_allow_html=True)
            qty = g2.number_input("تعداد", 1, 100000, role.get("qty", 1),
                                  key=f"sl_tq_{template_name}_{i}")
            legs.append(engine.Leg("stock", role["side"], 0.0, float(s_ref), int(qty)))
            rows.append({"symbol": "دارایی پایه", "option_type": "stock", "side": role["side"],
                         "strike": None, "premium": float(s_ref), "qty": int(qty),
                         "moneyness": None, "delta": 1.0 if role["side"] == "buy" else -1.0,
                         "gamma": 0.0, "theta": 0.0, "vega": 0.0})
            continue
        book = calls if role["option_type"] == "call" else puts
        type_label = c.type_label(role["option_type"])
        side_fa = "خرید" if role["side"] == "buy" else "فروش"
        if book.empty:
            st.markdown(
                f'<div class="chips"><span class="chip warn">پایه {i + 1} ({side_fa} {type_label}) '
                f"ساخته نشد — برای این سررسید قرارداد {type_label} موجود نیست.</span></div>",
                unsafe_allow_html=True)
            continue
        opts = [_fmt_contract(row) for _, row in book.iterrows()]
        g1, g2 = st.columns([3, 1])
        sel = g1.selectbox(f"پایه {i + 1} — {side_fa} {type_label}", opts,
                           index=_default_index(book, role["rank"], role["option_type"], s_ref),
                           key=f"sl_t_{template_name}_{i}")
        qty = g2.number_input("تعداد", 1, 50, role.get("qty", 1), key=f"sl_tq_{template_name}_{i}")
        row = book.iloc[opts.index(sel)]
        legs.append(engine.Leg(role["option_type"], role["side"], float(row["strike"]),
                               float(row["close"]), int(qty)))
        rows.append(_leg_record(row, role["side"], qty, s_ref))
    return legs, rows


def _manual_builder(calls, puts, s_ref, pending):
    book = pd.concat([calls, puts], ignore_index=True)
    if book.empty:
        return [], []
    labels = [f"{c.type_label(row['option_type'])}  {_fmt_contract(row)}" for _, row in book.iterrows()]

    preselect = None
    if pending and pending.get("leg"):
        target = pending["leg"].get("symbol")
        matches = [i for i, (_, row) in enumerate(book.iterrows()) if row.get("symbol") == target]
        preselect = matches[0] if matches else None
        if preselect is not None:
            st.markdown(
                f'<div class="chips"><span class="chip">قرارداد {c.esc(target)} از صفحه قبل منتقل شد '
                f"و به‌عنوان پایه ۱ انتخاب شده.</span></div>", unsafe_allow_html=True)

    n = st.number_input("تعداد پایه‌ها", 1, 6, 2 if preselect is None else 1, key="sl_n_legs")
    legs, rows = [], []
    for i in range(int(n)):
        idx = preselect if (i == 0 and preselect is not None) else 0
        g1, g2, g3 = st.columns([3, 1, 1])
        sel = g1.selectbox(f"پایه {i + 1}", labels, index=idx, key=f"sl_m_sym_{i}")
        side = g2.selectbox("جهت", ["buy", "sell"],
                            format_func=lambda s: "خرید" if s == "buy" else "فروش",
                            key=f"sl_m_side_{i}")
        qty = g3.number_input("تعداد", 1, 50, 1, key=f"sl_m_qty_{i}")
        row = book.iloc[labels.index(sel)]
        legs.append(engine.Leg(row["option_type"], side, float(row["strike"]),
                               float(row["close"]), int(qty)))
        rows.append(_leg_record(row, side, qty, s_ref))

    if pending:
        st.session_state.pending_strategy_legs = None
    return legs, rows


# ===========================================================================
# نمایش
# ===========================================================================
def _payoff_chart(legs, s_ref, bes, mpl):
    prices = np.linspace(s_ref * 0.55, s_ref * 1.45, 400)
    pay = engine.payoff_curve(legs, prices)
    T = design.TOKENS

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices, y=np.where(pay >= 0, pay, 0), mode="lines",
                             line=dict(width=0), fill="tozeroy",
                             fillcolor="rgba(63,185,80,0.12)", hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=prices, y=np.where(pay < 0, pay, 0), mode="lines",
                             line=dict(width=0), fill="tozeroy",
                             fillcolor="rgba(229,72,77,0.12)", hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=prices, y=pay, mode="lines", name="سود/زیان",
                             line=dict(color=T["accent"], width=2),
                             hovertemplate="قیمت %{x:,.0f}<br>سود/زیان %{y:,.0f}<extra></extra>"))
    fig.add_hline(y=0, line_width=1, line_color=T["border_strong"])
    fig.add_vline(x=s_ref, line_dash="dot", line_width=1, line_color=T["warning"])

    # نقاط سربه‌سر — اطلاعات کلیدی، نه پشت Hover (بخش ۸۵)
    for b in (bes or []):
        if prices[0] <= b <= prices[-1]:
            fig.add_vline(x=b, line_dash="dash", line_width=1, line_color=T["text_muted"])

    # مرز Strikeها
    for leg in legs:
        if prices[0] <= leg.strike <= prices[-1]:
            fig.add_trace(go.Scatter(x=[leg.strike], y=[0], mode="markers",
                                     marker=dict(size=6, color=T["text_muted"], symbol="line-ns-open"),
                                     hovertemplate=f"اعمال {leg.strike:,.0f}<extra></extra>",
                                     showlegend=False))

    layout = dict(design.PLOTLY_LAYOUT)
    layout.update(height=340, margin=dict(l=8, r=8, t=8, b=28),
                  xaxis=dict(gridcolor=T["border"], showgrid=False, title=None),
                  yaxis=dict(gridcolor=T["border"], gridwidth=1, zeroline=False, title=None))
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    c.helper("خط نقطه‌چین نارنجی: قیمت فعلی · خط‌چین خاکستری: نقطه سربه‌سر")


def _metrics(credit, mpl, bes, pop, sigma, dte):
    def bound(v, unbounded):
        return ("نامحدود", True) if unbounded else (c.fmt_int(v), False)

    mp, mp_un = bound(mpl["max_profit"], mpl["max_profit_is_unbounded"])
    ml, ml_un = bound(mpl["max_loss"], mpl["max_loss_is_unbounded"])

    c.kpi_strip([
        {"label": "خالص ورود", "value": f"{credit:+,.0f}", "na": False,
         "change": "دریافتی" if credit > 0 else ("پرداختی" if credit < 0 else None),
         "tone": "pos" if credit > 0 else "neg"},
        {"label": "حداکثر سود", "value": mp, "na": mp_un},
        {"label": "حداکثر زیان", "value": ml, "na": ml_un},
        {"label": "سربه‌سر", "value": "، ".join(f"{b:,.0f}" for b in bes[:2]) if bes else "—",
         "na": not bes},
        {"label": "احتمال سود (POP)", "value": f"{pop * 100:.0f}%" if pop is not None else "محاسبه نشد",
         "na": pop is None},
        {"label": "روز تا سررسید", "value": c.fmt_int(dte), "na": dte is None},
    ])
    if pop is None:
        c.helper("POP محاسبه نشد — به نوسان ضمنی و روز تا سررسید معتبر نیاز دارد.")
    elif sigma:
        c.helper(f"POP با شبیه‌سازی Monte Carlo و نوسان ضمنی میانگین این سررسید ({sigma * 100:.0f}٪) برآورد شده.")


def _legs_table(rows):
    headers = ["#", "قرارداد", "نوع", "جهت", "اعمال", "قیمت", "تعداد", "وضعیت"]
    trs = []
    for i, lg in enumerate(rows):
        side_fa = "خرید" if lg["side"] == "buy" else "فروش"
        cls = "pos" if lg["side"] == "buy" else "neg"
        trs.append([
            f'<span class="rank">{i + 1}</span>',
            c.num(lg.get("symbol") or c.NA),
            c.type_label(lg["option_type"]),
            f'<span class="{cls}">{side_fa}</span>',
            c.num(c.fmt_int(lg["strike"])),
            c.num(c.fmt_int(lg["premium"])),
            c.num(str(lg["qty"])),
            c.moneyness_badge(lg.get("moneyness")),
        ])
    c.table(headers, trs, numeric_cols={0, 4, 5, 6})


def _scenarios(legs, s_ref):
    prices = [s_ref * (1 + p / 100) for p in SCENARIO_STEPS]
    pnl = engine.payoff_curve(legs, prices)

    headers = ["تغییر قیمت پایه"] + [f"{p:+d}%" if p else "بدون تغییر" for p in SCENARIO_STEPS]
    price_row = ["قیمت دارایی پایه"] + [c.num(c.fmt_int(p)) for p in prices]
    pnl_row = ["سود / زیان در سررسید"]
    for v in pnl:
        cls = "pos" if v > 0 else ("neg" if v < 0 else "muted")
        pnl_row.append(f'<span class="num {cls}">{v:+,.0f}</span>')
    c.table(headers, [price_row, pnl_row], numeric_cols=set(range(1, len(headers))))
    c.helper("این ارقام سود/زیان در لحظه سررسید است، نه ارزش لحظه‌ای موقعیت پیش از سررسید.")


def _net_greeks(rows):
    def net(key):
        vals = [(1 if lg["side"] == "buy" else -1) * lg[key] * lg["qty"]
                for lg in rows if lg.get(key) is not None and pd.notna(lg.get(key))]
        return sum(vals) if vals else None

    labels = [("Delta", "delta", 2, "حساسیت به تغییر یک واحد قیمت پایه"),
              ("Gamma", "gamma", 4, "نرخ تغییر دلتا"),
              ("Theta", "theta", 1, "اثر روزانه گذر زمان"),
              ("Vega", "vega", 1, "حساسیت به تغییر نوسان ضمنی")]
    items = []
    for label, key, dec, note in labels:
        v = net(key)
        items.append({"label": label, "value": c.NA if v is None else f"{v:,.{dec}f}",
                      "na": v is None, "change": note, "tone": "neu"})
    items.append({"label": "تعداد پایه", "value": str(len(rows)), "na": False})
    items.append({"label": "مجموع قراردادها", "value": str(sum(lg["qty"] for lg in rows)), "na": False})
    c.kpi_strip(items)
    if all(i["na"] for i in items[:4]):
        c.helper("Greeks در دسترس نیست — معمولاً چون نوسان ضمنی یا قیمت دارایی پایه ناقص است.")


# ===========================================================================
def _actions(legs, rows, template_name, dataset, underlying, quote_date, expiry, spot):
    a1, a2, a3 = st.columns([2, 1, 1])
    name = a1.text_input("نام استراتژی", key="sl_save_name",
                         placeholder=f"{template_name.split(' (')[0]} — {underlying}")
    if a1.button("ذخیره استراتژی", type="secondary", key="sl_save"):
        final = (name or "").strip() or f"{template_name.split(' (')[0]} — {underlying}"
        database.save_strategy(
            final,
            [{"option_type": lg.option_type, "side": lg.side, "strike": lg.strike,
              "premium": lg.premium, "qty": lg.qty} for lg in legs],
            template=template_name, dataset=dataset, underlying=underlying,
            quote_date=quote_date, expiry=expiry, spot=spot,
        )
        st.success(f"استراتژی «{final}» ذخیره شد و در بک‌تست قابل انتخاب است.")

    if a2.button("بک‌تست این استراتژی ←", type="primary", use_container_width=True, key="sl_bt"):
        common.go_to("Backtest", dataset=dataset, underlying=underlying,
                     template=template_name, expiry=expiry)

    if a3.button("بهترین فرصت‌های این استراتژی ←", type="secondary",
                 use_container_width=True, key="sl_opp"):
        common.go_to("Opportunities", dataset=dataset, strategy=template_name,
                     quote_date=quote_date)

    saved = database.list_strategies()
    if not saved.empty:
        c.spacer(16)
        with st.expander(f"استراتژی‌های ذخیره‌شده ({len(saved)})"):
            headers = ["نام", "قالب", "نماد پایه", "پایه‌ها", "تاریخ ثبت"]
            import json
            trs = [[
                c.esc(r["name"]),
                c.esc((r["template"] or "—").split(" (")[0]),
                c.esc(r["underlying"] or "—"),
                c.num(str(len(json.loads(r["legs_json"])))),
                c.num(str(r["created_at"])[:10]),
            ] for _, r in saved.iterrows()]
            c.table(headers, trs, numeric_cols={3, 4})
