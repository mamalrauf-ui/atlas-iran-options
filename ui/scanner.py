"""
Scanner — موتور کشف قرارداد (بخش ۳۰، ۳۱ و ۸۰ Master Prompt).

پرسش اصلی صفحه: «با شرایطی که خودم تعیین می‌کنم، چه قراردادهایی مناسب‌اند؟»

تفاوت بنیادی با Opportunities (بخش ۸۰):
    اینجا **کاربر** شرط می‌گذارد. آنجا **Atlas** رتبه‌بندی می‌کند.
این تفاوت باید در متن، چیدمان و کنترل‌ها آشکار بماند — به همین دلیل این صفحه
هیچ Score تولید نمی‌کند و هیچ چیزی را «پیشنهاد» نمی‌دهد.

Scanner یک موتور استراتژی هم نیست: خروجی آن به Strategy Lab منتقل می‌شود.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import database, scanner as engine
from ui import common, contract_detail
from ui import components as c
from ui.common import JD

RESULT_LIMIT = 200


def render():
    datasets = database.list_datasets()
    if datasets.empty:
        c.page_header("اسکنر", "جست‌وجوی قرارداد با معیارهای خودت",
                      status="err", status_text="داده‌ای موجود نیست")
        c.empty_state("هنوز داده‌ای وارد نشده", "از «مرکز داده» یک فایل اختیار معامله وارد کنید.")
        return

    # --- Context ورودی از داشبورد (Drill-down سیگنال) ---
    intent = common.take_intent("dataset") or {}
    if intent.get("symbols"):
        st.session_state["scan_focus_symbols"] = intent["symbols"]
        st.session_state["scan_focus_name"] = intent.get("signal_name", "سیگنال")
        if intent.get("dataset"):
            st.session_state["scan_dataset"] = intent["dataset"]
    focus_symbols = st.session_state.get("scan_focus_symbols")

    c.page_header("اسکنر", "قراردادها را با شرط‌های خودت فیلتر کن — اینجا Atlas پیشنهادی نمی‌دهد")

    if focus_symbols:
        fc1, fc2 = st.columns([4, 1])
        with fc1:
            st.markdown(
                f'<div class="chips"><span class="chip">آمده از داشبورد: '
                f'{c.esc(st.session_state.get("scan_focus_name", "سیگنال"))} — '
                f'{len(focus_symbols)} قرارداد</span></div>',
                unsafe_allow_html=True)
        with fc2:
            if st.button("حذف این فیلتر", key="scan_clear_focus", type="secondary",
                         use_container_width=True):
                st.session_state.pop("scan_focus_symbols", None)
                st.session_state.pop("scan_focus_name", None)
                st.rerun()
        c.spacer(10)

    # --- انتخاب داده ---
    f1, f2, _ = st.columns([1.4, 1.4, 3])
    with f1:
        dataset_name = st.selectbox("Dataset", datasets["dataset"].tolist(), key="scan_dataset")
    options_all, underlying_all = common.load_dataset(dataset_name)
    if options_all.empty:
        c.empty_state("این Dataset رکوردی ندارد", "Dataset دیگری انتخاب کنید.")
        return
    with f2:
        quote_date, _prior, _all = common.snapshot_picker(options_all, key="scan_qdate")
    if quote_date is None:
        c.empty_state("Snapshot معتبری یافت نشد", "تاریخ رکوردهای این Dataset نامعتبر است.")
        return

    chain = common.enrich_snapshot(options_all, underlying_all, quote_date,
                                   st.session_state.risk_free_rate,
                                   st.session_state.atm_band_pct)
    if focus_symbols and "symbol" in chain.columns:
        chain = chain[chain["symbol"].isin(focus_symbols)].copy()
        if chain.empty:
            c.empty_state(
                "این قراردادها در Snapshot انتخاب‌شده نیستند",
                "فیلتر سیگنال را حذف کنید، یا تاریخ Snapshot را به همان روزی که در داشبورد دیدید برگردانید.",
            )
            return

    if chain.empty:
        c.empty_state("این Snapshot قراردادی ندارد", "تاریخ دیگری انتخاب کنید.")
        return

    avail = engine.available_filters(chain)

    # --- Quick Scans (بخش ۳۰) ---
    c.section("اسکن سریع", "شروع از یک شرط آماده — بعد در صورت نیاز دقیق‌ترش کن")
    preset = st.selectbox("Preset", ["بدون Preset"] + list(engine.PRESETS.keys()),
                          key="scan_preset", label_visibility="collapsed")

    # --- فیلترهای اصلی (بخش ۲۱: نوار فشرده) ---
    c.spacer(14)
    c.section("فیلترهای اصلی")
    filters: dict = {}
    e1, e2, e3, e4 = st.columns(4)
    if avail["underlying"]:
        filters["underlying"] = e1.multiselect("نماد پایه", sorted(chain["underlying"].dropna().unique()),
                                               key="scan_u")
    if avail["expiry"]:
        filters["expiry"] = e2.multiselect("سررسید", sorted(chain["expiry"].dropna().unique()),
                                           format_func=JD, key="scan_exp")
    if avail["option_type"]:
        type_sel = e3.selectbox("نوع", ["همه", "Call", "Put"], key="scan_type")
        if type_sel != "همه":
            filters["option_type"] = [type_sel.lower()]
    moneyness_sel = e4.selectbox("وضعیت", ["همه", "ITM", "ATM", "OTM"], key="scan_moneyness")

    # --- فیلترهای پیشرفته (Progressive Disclosure) ---
    with st.expander("فیلترهای بیشتر"):
        a1, a2, a3, a4 = st.columns(4)
        if avail["dte"]:
            lo, hi = int(chain["dte"].min()), int(chain["dte"].max())
            if lo < hi:
                rng = a1.slider("روز تا سررسید", lo, hi, (lo, hi), key="scan_dte")
                filters["dte_min"], filters["dte_max"] = rng
        if avail["iv"]:
            iv_min = a2.number_input("حداقل IV (%)", 0.0, 500.0, 0.0, 5.0, key="scan_ivmin")
            if iv_min > 0:
                filters["iv_min"] = iv_min / 100
        if avail["volume"]:
            v = a3.number_input("حداقل حجم", 0, value=0, step=100, key="scan_volmin")
            if v:
                filters["volume_min"] = v
        if avail["open_interest"]:
            o = a4.number_input("حداقل موقعیت باز", 0, value=0, step=100, key="scan_oimin")
            if o:
                filters["oi_min"] = o

        # --- معیارهای مشتق ATLAS ---
        d1, d2, d3, d4 = st.columns(4)
        if avail.get("traded_today"):
            if d1.checkbox("فقط معامله‌شده امروز", key="scan_traded",
                           help="قرارداد بی‌معامله قیمت پایانی کهنه دارد و IV و "
                                "Greeks آن قابل اتکا نیست."):
                filters["traded_today"] = True
        if avail.get("oi_change_pct" if "oi_change_pct" in chain.columns else "oi_change"):
            oi_ch = d2.number_input("حداقل رشد موقعیت باز (٪)", -100.0, 1000.0, -100.0, 5.0,
                                    key="scan_oichg",
                                    help="ورود پول جدید به قرارداد.")
            if oi_ch > -100.0:
                filters["oi_change_pct_min"] = oi_ch
        if avail.get("spread_pct"):
            sp = d3.number_input("حداکثر اسپرد (٪)", 0.0, 200.0, 0.0, 1.0, key="scan_spread",
                                 help="۰ یعنی بدون محدودیت. اسپرد بالای ۱۵٪ عملاً غیرقابل‌معامله است.")
            if sp > 0:
                filters["spread_pct_max"] = sp
        if avail.get("premium_yield_annual_pct"):
            yld = d4.number_input("حداقل بازده سالانه (٪)", 0.0, 100000.0, 0.0, 10.0,
                                  key="scan_yield",
                                  help="برای فروشنده Call پوششی: قیمت قرارداد نسبت به قیمت پایه، سالانه‌شده.")
            if yld > 0:
                filters["yield_min"] = yld

        b1, b2 = st.columns(4)[:2]
        if avail["delta"]:
            d = b1.slider("محدوده Delta", -1.0, 1.0, (-1.0, 1.0), 0.05, key="scan_delta")
            if d != (-1.0, 1.0):
                filters["delta_min"], filters["delta_max"] = d
        if avail["close"]:
            p = b2.number_input("حداکثر قیمت قرارداد", 0, value=0, step=100, key="scan_pmax")
            if p:
                filters["price_max"] = p

    # --- اجرا ---
    c.spacer(14)
    run_col, reset_col, _ = st.columns([1, 1, 4])
    run = run_col.button("اجرای اسکن", type="primary", use_container_width=True, key="scan_run")
    if reset_col.button("پاک‌کردن فیلترها", type="secondary", use_container_width=True, key="scan_reset"):
        for k in list(st.session_state.keys()):
            if k.startswith("scan_") and k not in ("scan_dataset", "scan_qdate"):
                del st.session_state[k]
        st.rerun()

    if not run and not st.session_state.get("scan_has_run"):
        c.spacer(20)
        c.empty_state("آماده اسکن",
                      "شرط‌ها را تعیین کنید و «اجرای اسکن» را بزنید. "
                      f"در حال حاضر {len(chain):,} قرارداد در این Snapshot موجود است.")
        return
    st.session_state["scan_has_run"] = True

    # --- اعمال: Preset اول، سپس فیلترهای کاربر ---
    result = chain
    if preset != "بدون Preset":
        result, reason = engine.apply_preset(result, preset)
        if result is None:
            c.spacer(20)
            c.error_state("این Preset روی داده فعلی قابل‌اجرا نیست", reason)
            return
    result = engine.apply_filters(result, filters)
    if moneyness_sel != "همه" and "moneyness_bucket" in result.columns:
        result = result[result["moneyness_bucket"] == moneyness_sel]

    # --- نتایج ---
    c.spacer(24)
    c.section("نتایج", f"{len(result):,} قرارداد از {len(chain):,} قرارداد این Snapshot")

    if result.empty:
        c.empty_state("هیچ قراردادی با این شرط‌ها پیدا نشد",
                      "یک یا چند فیلتر را شل‌تر کنید — مثلاً حداقل حجم یا محدوده Delta.")
        return

    sort_options = [k for k in ["volume", "open_interest", "iv", "dte", "close", "strike"]
                    if k in result.columns and result[k].notna().any()]
    labels = {"volume": "حجم", "open_interest": "موقعیت باز", "iv": "IV",
              "dte": "روز تا سررسید", "close": "قیمت", "strike": "قیمت اعمال"}
    s1, s2, _ = st.columns([1.2, 1, 3])
    sort_by = s1.selectbox("مرتب‌سازی", sort_options, format_func=lambda k: labels[k], key="scan_sort")
    ascending = s2.selectbox("ترتیب", ["نزولی", "صعودی"], key="scan_order") == "صعودی"
    view = result.sort_values(sort_by, ascending=ascending, na_position="last").head(RESULT_LIMIT)

    _render_results(view)
    if len(result) > RESULT_LIMIT:
        c.helper(f"فقط {RESULT_LIMIT} ردیف اول نمایش داده شده — برای دیدن بقیه، فیلترها را دقیق‌تر کنید.")

    # --- جزئیات قرارداد ---
    c.spacer(28)
    c.section("جزئیات قرارداد", "یک قرارداد را برای بررسی یا افزودن به استراتژی انتخاب کنید")
    symbols = view["symbol"].dropna().tolist()
    if not symbols:
        c.empty_state("قرارداد قابل‌انتخابی نیست", "ردیف‌های نتیجه نماد ثبت‌شده ندارند.")
        return
    if st.session_state.get("scan_detail_symbol") not in symbols:
        st.session_state["scan_detail_symbol"] = symbols[0]
    sel = st.selectbox("قرارداد", symbols, key="scan_detail_symbol")
    row = view[view["symbol"] == sel].iloc[0]

    contract_detail.render(
        row,
        context={"dataset": dataset_name, "underlying": row["underlying"],
                 "quote_date": quote_date, "expiry": row["expiry"]},
        on_add_to_strategy=_add_to_strategy,
        on_view_chain=_view_chain,
        key_prefix="scan",
    )


# ===========================================================================
def _render_results(view: pd.DataFrame):
    headers = ["قرارداد", "نماد پایه", "نوع", "اعمال", "وضعیت", "سررسید",
               "DTE", "قیمت", "حجم", "موقعیت باز", "IV", "Delta"]
    rows = []
    for _, o in view.iterrows():
        delta = o.get("delta")
        rows.append([
            c.num(o.get("symbol") or c.NA),
            c.esc(o.get("underlying")),
            c.type_label(o.get("option_type")),
            c.num(c.fmt_int(o.get("strike"))),
            c.moneyness_badge(o.get("moneyness_bucket")),
            c.num(JD(o.get("expiry"))),
            c.num(c.fmt_int(o.get("dte"))),
            c.num(c.fmt_int(o.get("close"))),
            c.num(c.fmt_compact(o.get("volume"))),
            c.num(c.fmt_compact(o.get("open_interest"))),
            c.num(c.fmt_pct(o.get("iv"))),
            c.num(c.NA if delta is None or pd.isna(delta) else f"{float(delta):.2f}"),
        ])
    c.table(headers, rows, numeric_cols={3, 5, 6, 7, 8, 9, 10, 11})


def _add_to_strategy(row, ctx):
    st.session_state.pending_strategy_legs = {
        "dataset": ctx.get("dataset"), "underlying": ctx.get("underlying"),
        "quote_date": ctx.get("quote_date"), "expiry": ctx.get("expiry"),
        "leg": {"option_type": row["option_type"], "strike": float(row["strike"]),
                "close": float(row["close"]) if pd.notna(row.get("close")) else 0.0,
                "symbol": row.get("symbol")},
    }
    common.go_to("Strategy Lab")


def _view_chain(row, ctx):
    common.go_to("Option Chain", dataset=ctx.get("dataset"), underlying=row["underlying"],
                 quote_date=ctx.get("quote_date"), expiry=row.get("expiry"),
                 symbol=row.get("symbol"))
