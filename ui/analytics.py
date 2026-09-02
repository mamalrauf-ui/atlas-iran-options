"""
Analytics — تحلیل تاریخی و ساختاری (بخش ۵۶ تا ۵۸ Master Prompt).

پرسش اصلی صفحه: «بازار در طول زمان و نسبت به گذشته چگونه رفتار کرده است؟»

تمایز بنیادی با Dashboard:
    Dashboard = Snapshot امروز   |   Analytics = تاریخ + زمینه + مقایسه + ساختار

این صفحه یک گالری نمودار نیست (بخش ۵۸): چهار بخش دارد و هر نما باید به یک
پرسش مشخص پاسخ دهد. اگر داده تاریخی کافی نباشد، به‌جای رسم نمودار گمراه‌کننده
صراحتاً اعلام می‌شود.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import analytics as engine, database, design
from ui import common
from ui import components as c
from ui.common import JD

MIN_HISTORY = 5
SECTIONS = ["نوسان", "موقعیت باز", "فعالیت", "ساختار بازار"]


def render():
    datasets = database.list_datasets()
    if datasets.empty:
        c.page_header("تحلیل تاریخی", "رفتار بازار در طول زمان",
                      status="err", status_text="داده‌ای موجود نیست")
        c.empty_state("هنوز داده‌ای وارد نشده", "از «مرکز داده» فایل بازار را وارد کنید.")
        return

    intent = common.take_intent("focus") or {}
    if intent.get("dataset"):
        st.session_state["an_dataset"] = intent["dataset"]
    if intent.get("focus") == "activity":
        st.session_state["an_section"] = "فعالیت"

    f1, f2, _ = st.columns([1.4, 2, 2])
    with f1:
        dataset_name = st.selectbox("Dataset", datasets["dataset"].tolist(), key="an_dataset")

    options_all, underlying_all = common.load_dataset(dataset_name)
    if options_all.empty:
        c.page_header("تحلیل تاریخی", "رفتار بازار در طول زمان")
        c.empty_state("این مجموعه رکوردی ندارد", "مجموعه دیگری انتخاب کنید.")
        return

    hist = _history(options_all, underlying_all)
    n = len(hist)
    last_date = hist["quote_date"].iloc[-1] if n else None

    c.page_header(
        "تحلیل تاریخی",
        f"روند بازار در {n} Snapshot ثبت‌شده",
        snapshot_label=JD(last_date) if last_date else None,
        status="ok" if n >= MIN_HISTORY else "warn",
        status_text="تاریخچه کافی است" if n >= MIN_HISTORY else f"فقط {n} Snapshot",
    )

    if n < 2:
        # تاریخچه از سرویس فراخوانی می‌شود، نه از Snapshotهای دستی کاربر.
        all_u = sorted(options_all["underlying"].dropna().unique().tolist())
        pick = st.selectbox("نماد پایه برای دریافت تاریخچه", all_u, key="an_hist_u") if all_u else None
        if pick:
            c.history_gate(dataset_name, pick, need_days=2, have_days=n,
                           purpose="تحلیل تاریخی", key="an_hist")
        else:
            c.empty_state("داده‌ای برای تحلیل نیست", "ابتدا یک Snapshot از بازار بگیرید.")
        return

    with f2:
        section = st.radio("بخش", SECTIONS, horizontal=True,
                           label_visibility="collapsed", key="an_section")

    if n < MIN_HISTORY:
        st.markdown(
            f'<div class="chips"><span class="chip warn">فقط {n} روز داده موجود است — '
            f'HV، IV Rank و Percentile حداقل به {MIN_HISTORY} روز نیاز دارند. '
            f'از «مرکز داده ← تاریخچه» می‌توانید تاریخچه را دریافت کنید.</span></div>',
            unsafe_allow_html=True)
        c.spacer(14)

    latest = common.enrich_snapshot(options_all, underlying_all, last_date,
                                    st.session_state.risk_free_rate,
                                    st.session_state.atm_band_pct)

    {"نوسان": _volatility, "موقعیت باز": _open_interest,
     "فعالیت": _activity, "ساختار بازار": _structure}[section](hist, latest, options_all)


@st.cache_data(show_spinner=False, ttl=900)
def _history(options_all: pd.DataFrame, underlying_all: pd.DataFrame) -> pd.DataFrame:
    return engine.history_series(options_all, underlying_all)


# ===========================================================================
# نمودار پایه — مینیمال، بدون گرادیان و افسانه بزرگ (بخش ۲۳)
# ===========================================================================
def _line(hist, cols: list, labels: list, height=280, pct=False, fill_first=False):
    T = design.TOKENS
    x = [JD(d) for d in hist["quote_date"]]
    fig = go.Figure()
    for i, (col, label) in enumerate(zip(cols, labels)):
        if col not in hist.columns:
            continue
        y = hist[col]
        if y.dropna().empty:
            continue
        fig.add_trace(go.Scatter(
            x=x, y=y * (100 if pct else 1), mode="lines", name=label,
            line=dict(color=design.CHART_COLORS[i % len(design.CHART_COLORS)], width=2),
            fill="tozeroy" if (fill_first and i == 0) else None,
            fillcolor="rgba(56,189,248,0.07)",
            connectgaps=False,
            hovertemplate="%{x}<br>" + label + ": %{y:,.2f}<extra></extra>",
        ))
    if not fig.data:
        return None
    layout = dict(design.PLOTLY_LAYOUT)
    layout.update(height=height, showlegend=len(fig.data) > 1,
                  legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11)),
                  margin=dict(l=8, r=8, t=28 if len(fig.data) > 1 else 8, b=28))
    fig.update_layout(**layout)
    return fig


def _show(fig, question: str, fallback: str):
    c.helper(question)
    if fig is None:
        c.empty_state("قابل‌محاسبه نیست", fallback)
    else:
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _bar(labels, values, height=280, pct=False):
    T = design.TOKENS
    fig = go.Figure(go.Bar(
        x=list(values), y=list(labels), orientation="h",
        marker=dict(color=T["accent"], opacity=.75),
        hovertemplate="%{y}: %{x:,.1f}<extra></extra>",
    ))
    layout = dict(design.PLOTLY_LAYOUT)
    layout.update(height=height, margin=dict(l=8, r=8, t=8, b=24),
                  yaxis=dict(autorange="reversed", gridcolor=T["border"], showgrid=False),
                  xaxis=dict(gridcolor=T["border"], gridwidth=1, showgrid=True))
    fig.update_layout(**layout)
    return fig


# ===========================================================================
# ۱) نوسان
# ===========================================================================
def _volatility(hist, latest, options_all):
    cur_iv = hist["avg_iv"].dropna().iloc[-1] if hist["avg_iv"].notna().any() else None
    stat = engine.iv_percentile(hist["avg_iv"], cur_iv)
    cur_hv = hist["hv"].dropna().iloc[-1] if "hv" in hist and hist["hv"].notna().any() else None
    cur_ratio = hist["iv_hv"].dropna().iloc[-1] if "iv_hv" in hist and hist["iv_hv"].notna().any() else None

    c.kpi_strip([
        {"label": "IV امروز", "value": c.fmt_pct(cur_iv), "na": cur_iv is None},
        {"label": "HV بازار", "value": c.fmt_pct(cur_hv), "na": cur_hv is None},
        {"label": "نسبت IV/HV", "value": c.fmt_ratio(cur_ratio), "na": cur_ratio is None},
        {"label": "IV Rank", "value": f"{stat['rank']:.0f}%" if stat["rank"] is not None else "—",
         "na": stat["rank"] is None},
        {"label": "IV Percentile",
         "value": f"{stat['percentile']:.0f}%" if stat["percentile"] is not None else "—",
         "na": stat["percentile"] is None},
        {"label": "دوره مقایسه", "value": f"{stat['n']} روز", "na": False},
    ])
    if stat["note"]:
        c.helper(stat["note"])

    c.spacer(20)
    c.section("روند نوسان ضمنی و تحقق‌یافته")
    _show(_line(hist, ["avg_iv", "hv"], ["IV ضمنی", "HV تحقق‌یافته"], pct=True),
          "آیا IV امروز نسبت به تاریخچه خودش بالاست؟",
          "نوسان ضمنی در داده این مجموعه ثبت نشده است.")

    if stat["percentile"] is not None:
        verdict = ("بالاتر از" if stat["percentile"] >= 70
                   else "پایین‌تر از" if stat["percentile"] <= 30 else "نزدیک")
        st.markdown(
            f'<div class="chips"><span class="chip">IV امروز {verdict} سطح معمول '
            f'{stat["n"]} روز گذشته است — از {stat["percentile"]:.0f}٪ روزها بالاتر بوده.</span></div>',
            unsafe_allow_html=True)

    c.spacer(20)
    c.section("مقایسه نوسان بین نمادها", "میانگین IV هر نماد در آخرین Snapshot")
    if "iv" in latest.columns and latest["iv"].notna().any():
        by_u = latest.groupby("underlying")["iv"].mean().sort_values(ascending=False).head(10)
        st.plotly_chart(_bar(by_u.index.tolist(), (by_u * 100).round(1).tolist()),
                        use_container_width=True, config={"displayModeBar": False})
        c.helper("واحد: درصد")
    else:
        c.empty_state("قابل‌محاسبه نیست", "نوسان ضمنی در آخرین Snapshot موجود نیست.")


# ===========================================================================
# ۲) موقعیت باز
# ===========================================================================
def _open_interest(hist, latest, options_all):
    c.section("روند موقعیت باز کل")
    _show(_line(hist, ["open_interest"], ["موقعیت باز"], fill_first=True),
          "آیا پول جدید وارد بازار اختیار می‌شود یا خارج؟",
          "موقعیت باز در داده این مجموعه ثبت نشده است.")

    c.spacer(20)
    g1, g2 = st.columns(2)
    with g1:
        c.section("تمرکز روی نمادها")
        by_u = engine.oi_by_dimension(latest, "underlying")
        if by_u.empty:
            c.empty_state("قابل‌محاسبه نیست", "موقعیت باز در آخرین Snapshot موجود نیست.")
        else:
            st.plotly_chart(_bar(by_u["underlying"].tolist(), by_u["share_pct"].round(1).tolist()),
                            use_container_width=True, config={"displayModeBar": False})
            c.helper("سهم از کل موقعیت باز بازار (درصد)")
    with g2:
        c.section("توزیع روی سررسیدها")
        by_e = engine.oi_by_dimension(latest, "expiry")
        if by_e.empty:
            c.empty_state("قابل‌محاسبه نیست", "موقعیت باز یا سررسید در آخرین Snapshot ناقص است.")
        else:
            st.plotly_chart(_bar([JD(e) for e in by_e["expiry"]], by_e["share_pct"].round(1).tolist()),
                            use_container_width=True, config={"displayModeBar": False})
            c.helper("سهم از کل موقعیت باز بازار (درصد)")


# ===========================================================================
# ۳) فعالیت
# ===========================================================================
def _activity(hist, latest, options_all):
    c.section("روند حجم معاملات")
    _show(_line(hist, ["volume"], ["حجم"], fill_first=True),
          "فعالیت بازار نسبت به روزهای گذشته در حال افزایش است؟",
          "حجم معاملات در داده این مجموعه ثبت نشده است.")

    c.spacer(20)
    g1, g2 = st.columns(2)
    with g1:
        c.section("نسبت Call/Put در طول زمان")
        fig = _line(hist, ["cp_ratio"], ["Call/Put"], height=240)
        if fig is not None:
            fig.add_hline(y=1, line_dash="dot", line_width=1,
                          line_color=design.TOKENS["text_muted"])
        _show(fig, "تمایل بازار به کدام سمت بوده؟",
              "برای این نسبت، حجم هر دو سمت Call و Put لازم است.")
    with g2:
        c.section("تعداد قراردادهای فعال")
        _show(_line(hist, ["contracts", "underlyings"], ["قراردادها", "نمادها"], height=240),
              "دامنه بازار در حال گسترش است یا جمع‌شدن؟",
              "داده کافی نیست.")

    c.spacer(20)
    c.section("پرحجم‌ترین نمادها", "در آخرین Snapshot")
    if "volume" in latest.columns and latest["volume"].notna().any():
        by_u = latest.groupby("underlying")["volume"].sum().sort_values(ascending=False).head(10)
        st.plotly_chart(_bar(by_u.index.tolist(), by_u.tolist()),
                        use_container_width=True, config={"displayModeBar": False})
    else:
        c.empty_state("قابل‌محاسبه نیست", "حجم در آخرین Snapshot موجود نیست.")


# ===========================================================================
# ۴) ساختار بازار
# ===========================================================================
def _structure(hist, latest, options_all):
    c.section("تمرکز بازار در طول زمان")
    fig = _line(hist, ["top3_share"], ["سهم ۳ نماد برتر"], height=260)
    if fig is not None:
        fig.update_yaxes(range=[0, 100])
    _show(fig, "آیا حجم بازار در چند نماد محدود متمرکز شده است؟",
          "برای محاسبه تمرکز، حجم و حداقل سه نماد پایه لازم است.")

    c.spacer(20)
    g1, g2 = st.columns(2)
    with g1:
        c.section("توزیع وضعیت قراردادها")
        if "moneyness_bucket" in latest.columns and latest["moneyness_bucket"].notna().any():
            dist = latest["moneyness_bucket"].value_counts()
            order = [k for k in ["ITM", "ATM", "OTM"] if k in dist.index]
            total = dist.sum()
            rows = [[c.moneyness_badge(k), c.num(c.fmt_int(dist[k])),
                     c.num(f"{dist[k] / total * 100:.1f}%")] for k in order]
            c.table(["وضعیت", "تعداد", "سهم"], rows, numeric_cols={1, 2})
            c.helper(f"باند ATM: ±{st.session_state.atm_band_pct:g}٪ حول قیمت دارایی پایه")
        else:
            c.empty_state("قابل‌محاسبه نیست",
                          "وضعیت ITM/ATM/OTM به قیمت دارایی پایه نیاز دارد که برای این Snapshot موجود نیست.")
    with g2:
        c.section("توزیع Call و Put")
        dist = latest["option_type"].value_counts()
        total = dist.sum()
        rows = [[c.type_label(k), c.num(c.fmt_int(v)), c.num(f"{v / total * 100:.1f}%")]
                for k, v in dist.items()]
        c.table(["نوع", "تعداد قرارداد", "سهم"], rows, numeric_cols={1, 2})

    c.spacer(20)
    c.section("توزیع روز تا سررسید", "قراردادهای فعال بر اساس فاصله تا سررسید")
    if "dte" in latest.columns and latest["dte"].notna().any():
        bins = [(0, 7, "کمتر از ۷ روز"), (7, 30, "۷ تا ۳۰ روز"),
                (30, 90, "۳۰ تا ۹۰ روز"), (90, 10**6, "بیش از ۹۰ روز")]
        rows = []
        total = latest["dte"].notna().sum()
        for lo, hi, label in bins:
            n = int(((latest["dte"] >= lo) & (latest["dte"] < hi)).sum())
            rows.append([c.esc(label), c.num(c.fmt_int(n)),
                         c.num(f"{n / total * 100:.1f}%" if total else "—")])
        c.table(["بازه", "تعداد قرارداد", "سهم"], rows, numeric_cols={1, 2})
    else:
        c.empty_state("قابل‌محاسبه نیست", "روز تا سررسید در این Snapshot ثبت نشده.")
