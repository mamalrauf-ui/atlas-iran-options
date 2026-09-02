"""
Dashboard — Market Intelligence (بخش‌های ۲۴ تا ۲۹ و ۷۹ Master Prompt).

پرسش اصلی صفحه: «امروز در بازار اختیار ایران چه خبر است؟»

ترتیب اطلاعاتی ثابت:
    Market Snapshot → Market Brief → Market Activity → Market Signals → Top Opportunities

قواعدی که این فایل رعایت می‌کند:
- دقیقاً ۶ KPI ثابت، با ترتیب همیشگی (بخش ۲۵).
- هیچ نمودار تاریخی بزرگی اینجا نیست؛ تاریخ متعلق به Analytics است (بخش ۲۴).
- هیچ نشانه Real-time؛ فقط Snapshot و وضعیت داده (بخش ۶).
- هیچ عدد ساختگی: هر مقدار یا محاسبه‌شده است یا «—» با توضیح.
- همه بخش‌ها Drill-down دارند: داشبورد یک Hub ناوبری است، نه ویترین (بخش ۶۴).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import database, market_brief, opportunity
from ui import common
from ui import components as c

TOP_N_ACTIVITY = 6
TOP_N_OPPORTUNITIES = 5


# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=900)
def _cached_opportunities(chain: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """Opportunity Engine روی کل Snapshot سنگین است — نتیجه Cache می‌شود."""
    return opportunity.detect_contract_opportunities(chain, weights)


def render():
    datasets = database.list_datasets()
    if datasets.empty:
        c.page_header("داشبورد", "نمای وضعیت بازار اختیار در آخرین Snapshot",
                      status="err", status_text="داده‌ای موجود نیست")
        c.empty_state(
            "هنوز هیچ داده‌ای وارد نشده",
            "برای فعال‌شدن داشبورد، از «مرکز داده» فایل اکسل اختیار معامله و قیمت دارایی پایه را وارد کنید.",
        )
        if st.button("رفتن به مرکز داده", type="primary", key="dash_goto_dc"):
            common.go_to("Data Center")
        return

    # ---------------- نوار انتخاب (فشرده، نه فرم بزرگ) ----------------
    f1, f2, _ = st.columns([1.4, 1.4, 3])
    with f1:
        dataset_name = st.selectbox("Dataset", datasets["dataset"].tolist(), key="dash_dataset")

    options_all, underlying_all = common.load_dataset(dataset_name)
    if options_all.empty:
        c.page_header("داشبورد", "نمای وضعیت بازار اختیار در آخرین Snapshot",
                      status="warn", status_text="Dataset خالی است")
        c.empty_state("این Dataset رکوردی ندارد", "یک Dataset دیگر انتخاب کنید یا داده جدید وارد کنید.")
        return

    with f2:
        quote_date, prior_date, quote_dates = common.snapshot_picker(options_all, key="dash_qdate")

    if quote_date is None:
        c.empty_state("Snapshot معتبری یافت نشد", "تاریخ رکوردهای این Dataset نامعتبر است.")
        return

    r = st.session_state.risk_free_rate
    band = st.session_state.atm_band_pct

    chain = common.enrich_snapshot(options_all, underlying_all, quote_date, r, band)
    prior_chain = (
        common.enrich_snapshot(options_all, underlying_all, prior_date, r, band)
        if prior_date else None
    )

    # ---------------- هدر + وضعیت داده ----------------
    is_latest = quote_date == max(quote_dates)
    status, status_text = ("ok", "داده به‌روز است") if is_latest else \
        ("warn", "در حال مشاهده Snapshot تاریخی")

    c.page_header(
        "داشبورد",
        "خلاصه وضعیت بازار اختیار در پایان معاملات",
        snapshot_label=common.JD(quote_date),
        status=status,
        status_text=status_text,
    )

    if chain.empty:
        c.empty_state("این Snapshot قراردادی ندارد", "تاریخ دیگری را انتخاب کنید.")
        return

    # ---------------- ۱) شش KPI ثابت ----------------
    kpis = market_brief.compute_kpis(chain, prior_chain, underlying_all)
    _render_kpis(kpis)
    _render_flow_kpis(chain)

    # ---------------- ۲) Market Brief ----------------
    left, right = st.columns([1.55, 1])
    with left:
        c.section("خلاصه امروز", "تفسیر قاعده‌محور بر پایه داده همین Snapshot")
        brief = market_brief.build_brief(
            kpis, [], chain, prior_chain,
            prior_label=common.JD(prior_date) if prior_date else None,
        )
        _render_brief(brief)

    with right:
        c.section("ترکیب فعالیت", "سهم Call و Put از حجم امروز")
        _render_call_put_split(chain)

    c.spacer(28)

    # ---------------- ۳) Market Activity ----------------
    a_head, a_action = st.columns([4, 1])
    with a_head:
        c.section("فعالیت بازار", "امروز پول و حجم کجا متمرکز بوده است")
    with a_action:
        if st.button("تحلیل کامل ←", key="dash_view_activity", type="tertiary"):
            common.go_to("Analytics", focus="activity", dataset=dataset_name, quote_date=quote_date)

    mode = st.radio("نما", ["نمادهای پایه", "قراردادها"], horizontal=True,
                    label_visibility="collapsed", key="dash_activity_mode")
    if mode == "نمادهای پایه":
        _render_top_underlyings(chain, prior_chain, dataset_name, quote_date)
    else:
        _render_top_contracts(chain, dataset_name, quote_date)

    c.spacer(28)

    # ---------------- ۴) Market Signals ----------------
    c.section("سیگنال‌های بازار", "رویدادهای آماری قابل‌توجه نسبت به Snapshot قبلی")
    signals = market_brief.detect_signals(chain, prior_chain, kpis)
    _render_signals(signals, prior_date, dataset_name, quote_date)

    c.spacer(28)

    # ---------------- ۵) Top Opportunities ----------------
    o_head, o_action = st.columns([4, 1])
    with o_head:
        c.section("فرصت‌های برتر", f"{TOP_N_OPPORTUNITIES} مورد برتر از دید موتور تحلیل ATLAS")
    with o_action:
        if st.button("مشاهده همه ←", key="dash_view_opps", type="tertiary"):
            common.go_to("Opportunities", dataset=dataset_name, quote_date=quote_date)

    _render_top_opportunities(chain, dataset_name, quote_date)


# ===========================================================================
# بخش‌ها
# ===========================================================================
def _render_kpis(k: dict):
    """شش KPI ثابت — ترتیب هرگز تغییر نمی‌کند (بخش ۲۵)."""
    def cell(label, value_str, item, force_neutral=False):
        na = value_str == c.NA
        change = None
        tone = "neu"
        if item.get("change_pct") is not None and not na:
            change = c.fmt_change(item["change_pct"])
            tone = c.change_tone(item["change_pct"],
                                 meaningful=item.get("direction_meaningful", True) and not force_neutral)
        return {"label": label, "value": value_str if not na else "داده موجود نیست",
                "change": change, "tone": tone, "na": na}

    items = [
        cell("حجم کل بازار", c.fmt_compact(k["total_volume"]["value"]), k["total_volume"]),
        cell("موقعیت باز کل", c.fmt_compact(k["total_oi"]["value"]), k["total_oi"]),
        cell("میانه IV بازار", c.fmt_pct(k["avg_iv"]["value"]), k["avg_iv"]),
        cell("قراردادهای فعال", c.fmt_int(k["active_contracts"]["value"]), k["active_contracts"]),
        cell("نسبت Call/Put (حجم)", c.fmt_ratio(k["cp_ratio"]["value"]), k["cp_ratio"]),
        cell("نسبت IV/HV", c.fmt_ratio(k["iv_hv_ratio"]["value"]), k["iv_hv_ratio"]),
    ]
    c.kpi_strip(items)

    notes = [k[key].get("note") for key in ("cp_ratio", "iv_hv_ratio") if k[key].get("note")]
    if notes:
        c.helper(" · ".join(notes))
        c.spacer(10)


def _render_flow_kpis(chain):
    """
    نوار دوم: جریان پول و کیفیت بازار.

    این مقادیر همه از داده‌ای می‌آیند که سرویس می‌دهد ولی تا پیش از این
    هیچ‌جا نمایش داده نمی‌شد — مثل موقعیت باز دیروز که در همان پاسخ API
    هست و تغییر OI را بدون نیاز به Snapshot دیروز ممکن می‌کند.
    """
    def _sum(col):
        if col not in chain.columns or chain[col].dropna().empty:
            return None
        return float(chain[col].dropna().sum())

    def _mean(col):
        if col not in chain.columns or chain[col].dropna().empty:
            return None
        return float(chain[col].dropna().mean())

    oi_net = _sum("oi_change")
    turnover = _sum("turnover")
    trades = _sum("trade_count")

    traded = None
    if "traded_today" in chain.columns and chain["traded_today"].notna().any():
        traded = float(chain["traded_today"].fillna(False).mean() * 100)

    spread = _mean("spread_pct")

    # جهت خالص جریان موقعیت باز: ورود یا خروج پول از بازار اختیار
    tone_oi = "neu"
    if oi_net is not None:
        tone_oi = "pos" if oi_net > 0 else ("neg" if oi_net < 0 else "neu")

    items = [
        {"label": "تغییر خالص موقعیت باز", "na": oi_net is None,
         "value": f"{oi_net:+,.0f}" if oi_net is not None else "داده موجود نیست",
         "change": ("ورود پول" if (oi_net or 0) > 0 else "خروج پول") if oi_net else None,
         "tone": tone_oi},
        {"label": "ارزش معاملات (ریال)", "na": turnover is None,
         "value": c.fmt_compact(turnover) if turnover is not None else "داده موجود نیست"},
        {"label": "تعداد معاملات", "na": trades is None,
         "value": c.fmt_compact(trades) if trades is not None else "داده موجود نیست"},
        {"label": "سهم قراردادهای معامله‌شده", "na": traded is None,
         "value": f"{traded:.0f}%" if traded is not None else "داده موجود نیست"},
        {"label": "میانگین اسپرد", "na": spread is None,
         "value": f"{spread:.1f}%" if spread is not None else "مظنه دوطرفه نیست"},
        {"label": "سررسیدهای فعال", "na": False,
         "value": c.fmt_int(chain["expiry"].nunique())},
    ]
    c.kpi_strip(items)
    if traded is not None and traded < 50:
        c.helper(f"تنها {traded:.0f}٪ قراردادها امروز معامله شده‌اند — این در بازار اختیار "
                 "ایران عادی است، ولی یعنی قیمت پایانی بقیه کهنه است و نوسان ضمنی و "
                 "Greeks استخراج‌شده از آن‌ها با احتیاط استفاده شود.")
    c.spacer(14)


def _render_brief(brief: dict):
    paras = "".join(f"<p>{c.esc(s)}</p>" for s in brief["sentences"])
    chips = ""
    if brief["chips"]:
        chips = '<div class="chips">' + "".join(
            f'<span class="chip {ch.get("tone", "")}">{c.esc(ch["text"])}</span>'
            for ch in brief["chips"]
        ) + "</div>"
    st.markdown(f'<div class="brief">{paras}{chips}</div>', unsafe_allow_html=True)


def _render_call_put_split(chain: pd.DataFrame):
    """نوار سهم Call/Put — کوچک، بدون نمودار سنگین (بخش ۲۴: بدون چارت بزرگ)."""
    if "volume" not in chain.columns or not chain["volume"].notna().any():
        c.empty_state("حجم موجود نیست", "این Snapshot ستون حجم معاملات ندارد.")
        return

    call_v = float(chain[chain["option_type"] == "call"]["volume"].dropna().sum())
    put_v = float(chain[chain["option_type"] == "put"]["volume"].dropna().sum())
    total = call_v + put_v
    if total <= 0:
        c.empty_state("حجم ثبت‌نشده", "مجموع حجم این Snapshot صفر است.")
        return

    call_pct = call_v / total * 100
    put_pct = 100 - call_pct
    st.markdown(
        f"""
        <div style="border:1px solid var(--border);border-radius:8px;
                    background:var(--bg-surface);padding:16px 18px;">
          <div style="display:flex;justify-content:space-between;font-size:.78rem;
                      color:var(--text-2);margin-bottom:10px;">
            <span>Call <span class="num" style="color:var(--pos)">{call_pct:.1f}%</span></span>
            <span>Put <span class="num" style="color:var(--neg)">{put_pct:.1f}%</span></span>
          </div>
          <div style="display:flex;height:8px;border-radius:4px;overflow:hidden;
                      background:var(--bg-elevated);">
            <div style="width:{call_pct:.2f}%;background:var(--pos);opacity:.75"></div>
            <div style="width:{put_pct:.2f}%;background:var(--neg);opacity:.75"></div>
          </div>
          <div style="display:flex;justify-content:space-between;margin-top:12px;
                      font-size:.75rem;color:var(--text-3);">
            <span>حجم Call: <span class="num">{c.fmt_compact(call_v)}</span></span>
            <span>حجم Put: <span class="num">{c.fmt_compact(put_v)}</span></span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_top_underlyings(chain, prior_chain, dataset_name, quote_date):
    df = market_brief.top_underlyings(chain, prior_chain, TOP_N_ACTIVITY)
    if df.empty:
        c.empty_state("داده فعالیت موجود نیست", "برای این Snapshot حجم یا موقعیت باز ثبت نشده است.")
        return

    headers = ["#", "نماد پایه", "حجم", "موقعیت باز", "تغییر OI", "میانگین IV", "قراردادها"]
    rows = []
    for i, row in df.iterrows():
        oi_ch = row.get("oi_change_pct")
        if oi_ch is None or pd.isna(oi_ch):
            oi_cell = f'<span class="muted">{c.NA}</span>'
        else:
            cls = "pos" if oi_ch > 0 else ("neg" if oi_ch < 0 else "muted")
            oi_cell = f'<span class="num {cls}">{c.fmt_change(oi_ch)}</span>'
        rows.append([
            f'<span class="rank">{i + 1}</span>',
            c.esc(row["underlying"]),
            c.num(c.fmt_compact(row.get("volume"))),
            c.num(c.fmt_compact(row.get("open_interest"))),
            oi_cell,
            c.num(c.fmt_pct(row.get("avg_iv"))),
            c.num(c.fmt_int(row.get("contracts"))),
        ])
    c.table(headers, rows, numeric_cols={0, 2, 3, 4, 5, 6})

    st.markdown("")
    cols = st.columns(min(len(df), TOP_N_ACTIVITY))
    for col, (_, row) in zip(cols, df.iterrows()):
        with col:
            if st.button(f"زنجیره {row['underlying']} ←", key=f"dash_u_{row['underlying']}",
                         type="tertiary", use_container_width=True):
                common.go_to("Option Chain", dataset=dataset_name,
                             quote_date=quote_date, underlying=row["underlying"])


def _render_top_contracts(chain, dataset_name, quote_date):
    df = market_brief.top_contracts(chain, TOP_N_ACTIVITY)
    if df.empty:
        c.empty_state("داده فعالیت قرارداد موجود نیست", "حجم و موقعیت باز در این Snapshot ثبت نشده است.")
        return

    headers = ["#", "قرارداد", "نماد پایه", "نوع", "اعمال", "وضعیت", "حجم", "موقعیت باز", "IV"]
    rows = []
    for i, row in df.iterrows():
        rows.append([
            f'<span class="rank">{i + 1}</span>',
            c.num(row.get("symbol") or c.NA),
            c.esc(row.get("underlying")),
            c.type_label(row.get("option_type")),
            c.num(c.fmt_int(row.get("strike"))),
            c.moneyness_badge(row.get("moneyness_bucket")),
            c.num(c.fmt_compact(row.get("volume"))),
            c.num(c.fmt_compact(row.get("open_interest"))),
            c.num(c.fmt_pct(row.get("iv"))),
        ])
    c.table(headers, rows, numeric_cols={0, 4, 6, 7, 8})
    c.helper("برای بررسی جزئیات یک قرارداد، از «زنجیره اختیار» همان نماد وارد شوید.")


def _render_signals(signals, prior_date, dataset_name, quote_date):
    if not signals:
        if prior_date is None:
            c.empty_state(
                "برای تشخیص سیگنال به Snapshot قبلی نیاز است",
                "سیگنال‌هایی مثل IV Expansion و OI Build-up از مقایسه دو Snapshot ساخته می‌شوند. "
                "یک تاریخ دیگر از همین Dataset را وارد کنید.",
            )
        else:
            c.empty_state(
                "سیگنال قابل‌توجهی شناسایی نشد",
                "هیچ‌کدام از قواعد آماری ATLAS در این Snapshot فعال نشدند — بازار آرام بوده است.",
            )
        return

    cols = st.columns(min(len(signals), 4))
    for i, sig in enumerate(signals):
        with cols[i % len(cols)]:
            count_html = (f'<div class="c">{sig["count"]}</div>'
                          if sig["count"] is not None
                          else '<div class="c" style="color:var(--text-2);font-size:.9rem">سطح بازار</div>')
            st.markdown(
                f'<div class="signal"><div class="n">{c.esc(sig["name"])}</div>'
                f'{count_html}<div class="d">{c.esc(sig["description"])}</div></div>',
                unsafe_allow_html=True,
            )
            if sig.get("symbols"):
                if st.button("مشاهده قراردادها ←", key=f"dash_sig_{sig['key']}_{i}",
                             type="tertiary", use_container_width=True):
                    common.go_to("Scanner", dataset=dataset_name, quote_date=quote_date,
                                 signal=sig["key"], symbols=sig["symbols"],
                                 signal_name=sig["name"])
            st.markdown("")


def _render_top_opportunities(chain, dataset_name, quote_date):
    opps = _cached_opportunities(chain, st.session_state.opportunity_weights)
    if opps.empty:
        c.empty_state(
            "فرصتی شناسایی نشد",
            "موتور فرصت‌ها برای مقایسه نسبی به حداقل ۳ قرارداد هم‌گروه (همان نماد، سررسید و نوع) "
            "نیاز دارد. با داده فعلی هیچ گروهی این شرط را برآورده نکرد.",
        )
        return

    top = opps.head(TOP_N_OPPORTUNITIES)
    headers = ["#", "قرارداد", "نماد پایه", "نوع", "سیگنال", "IV", "موقعیت باز", "امتیاز"]
    rows = []
    for i, o in top.iterrows():
        cats = " ".join(c.signal_badge(x) for x in (o["categories"] or [])[:2])
        score = o["score"]
        score_cell = (f'<span class="num" style="color:var(--accent);font-weight:600">{score:.0f}</span>'
                      if score is not None and not pd.isna(score)
                      else f'<span class="muted">{c.NA}</span>')
        rows.append([
            f'<span class="rank">{i + 1}</span>',
            c.num(o.get("symbol") or c.NA),
            c.esc(o.get("underlying")),
            c.type_label(o.get("option_type")),
            cats or f'<span class="muted">{c.NA}</span>',
            c.num(c.fmt_pct(o.get("iv"))),
            c.num(c.fmt_compact(o.get("open_interest"))),
            score_cell,
        ])
    c.table(headers, rows, numeric_cols={0, 5, 6, 7})
    c.helper("امتیاز، ترکیب وزنیِ مؤلفه‌های واقعاً قابل‌محاسبه است؛ مؤلفه‌های بدون داده از فرمول حذف و وزن‌ها بازتوزیع می‌شوند.")
