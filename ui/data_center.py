"""
Data Center — مدیریت داده (بخش ۵۹ و ۶۰ Master Prompt).

پرسش اصلی صفحه: «داده‌های Atlas چه وضعیتی دارند و چگونه مدیریت می‌شوند؟»

این صفحه مدیریتی است، نه تحلیلی. جریان ورود داده به‌صورت پلکانی است:
    ۱ بارگذاری → ۲ تشخیص → ۳ بررسی → ۴ ثبت
منطق قدرتمند importer دست‌نخورده می‌ماند و فقط پشت یک UI ساده قرار می‌گیرد.
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile

import pandas as pd
import streamlit as st

from core import analytics, database, importer, live_data
from core.data.providers.tsetmc import TSETMCProvider
from core.data.sync import run_manual_sync
from ui import common
from ui import components as c
from ui.common import JD, _jalali_date_cols

# تنها مسیر ورود دستی باقی‌مانده. دو مسیر دیگر («اطلاعات اختیار معامله» و
# «فقط قیمت دارایی پایه») حذف شدند: با دریافت خودکار از TSETMC دیگر لازم
# نیستند و وجودشان باعث می‌شد کاربر داده‌ای وارد کند که با اسکیمای زنده
# ناسازگار است و بی‌صدا ستون‌های کلیدی را خالی می‌گذارد.
KIND_SCREENER = "خروجی مستقیم سایت آپشن‌گر"


def render():
    datasets = database.list_datasets()
    status, text = ("ok", "داده به‌روز است") if not datasets.empty else ("err", "داده‌ای موجود نیست")
    last = JD(datasets["to_date"].max()) if not datasets.empty else None

    c.page_header("مرکز داده", "دریافت، مدیریت و بررسی کیفیت داده‌های بازار",
                  snapshot_label=last, status=status, status_text=text)

    # طبق تصمیم معماری جدید: TSETMC مسیر اصلی و پیش‌فرض است.
    # Excel/ورود دستی همچنان کار می‌کند، اما فقط به‌عنوان مسیر دستی/اضطراری،
    # در آخرین تب — نه اولین قدم کاربر.
    tabs = st.tabs([
        "دریافت بازار (TSETMC)", "تاریخچه", "منبع پارامترها",
        "مجموعه‌ها", "کیفیت داده", "ورود اضطراری (آپشن‌گر)",
    ])
    with tabs[0]:
        _live_flow()
    with tabs[1]:
        _history_flow(datasets)
    with tabs[2]:
        _provenance_flow(datasets)
    with tabs[3]:
        _datasets(datasets)
    with tabs[4]:
        _quality(datasets)
    with tabs[5]:
        _import_flow()


# ===========================================================================
# دریافت زنده از API رسمی TSETMC
# ===========================================================================
def _live_flow():
    c.section(
        "دریافت زنده از TSETMC",
        "یک Snapshot لحظه‌ای از API رسمی بورس گرفته می‌شود و به‌عنوان یک "
        "مجموعه (Dataset) جدید ذخیره می‌گردد. فایل‌های اکسل موجود دست‌نخورده می‌مانند.",
    )
    c.helper(
        "این داده فقط شامل قیمت، حجم، بهترین خرید/فروش و موقعیت باز است. "
        "Greeks و نوسان ضمنی مثل همیشه توسط موتور داخلی ATLAS محاسبه می‌شود، نه توسط این منبع."
    )

    scope = st.radio(
        "دامنه دریافت",
        ["فقط یک دارایی پایه", "کل بازار"],
        key="dc_live_scope",
        horizontal=True,
        captions=["سریع‌تر و پیشنهادی برای شروع", "همه دارایی‌های پایه — ممکن است حجیم باشد"],
    )

    underlying_filter = None
    if scope == "فقط یک دارایی پایه":
        col1, col2 = st.columns([2, 1])
        with col2:
            fetch_list = st.button("بارگذاری لیست نمادها از بازار", key="dc_live_list_btn")
        if fetch_list:
            try:
                with st.spinner("در حال دریافت لیست دارایی‌های پایه از TSETMC..."):
                    st.session_state["dc_live_underlyings"] = live_data.list_available_underlyings()
            except live_data.LiveDataError as exc:
                st.session_state.pop("dc_live_underlyings", None)
                c.error_state("دریافت لیست نمادها ممکن نشد", str(exc))

        options_list = st.session_state.get("dc_live_underlyings", [])
        with col1:
            if options_list:
                underlying_filter = st.selectbox("دارایی پایه", options_list, key="dc_live_ua")
            else:
                underlying_filter = st.text_input(
                    "دارایی پایه (نام دقیق فارسی، مثل «اهرم»)", key="dc_live_ua_text",
                    help="یا روی «بارگذاری لیست نمادها» کلیک کنید تا از یک لیست انتخاب کنید.",
                )

    dataset_name = st.text_input(
        "نام مجموعه (Dataset)", key="dc_live_name",
        placeholder=f"مثلاً: زنده {JD(str(dt.date.today()))}",
    )

    # --------------------------------------------------------------------
    # نکته حیاتی Streamlit: نتیجه دریافت باید در session_state نگه داشته شود.
    #
    # الگوی قبلی «if not st.button(fetch): return» باعث می‌شد دکمه ذخیره
    # هرگز کار نکند: با کلیک روی ذخیره، اسکریپت از نو اجرا می‌شود، این بار
    # دکمه دریافت False است، تابع زودتر return می‌کند و کد ذخیره اصلاً
    # اجرا نمی‌شود. این دقیقاً همان «می‌خواند ولی ذخیره نمی‌شود» بود.
    # --------------------------------------------------------------------
    if st.button("دریافت و پیش‌نمایش", type="primary", key="dc_live_fetch_btn"):
        if scope == "فقط یک دارایی پایه" and not (underlying_filter or "").strip():
            st.session_state["dc_live_preview"] = {"error": "یک دارایی پایه انتخاب یا وارد کنید."}
        elif not dataset_name.strip():
            st.session_state["dc_live_preview"] = {"error": "یک نام برای این Snapshot وارد کنید."}
        else:
            try:
                with st.spinner("در حال دریافت داده زنده از TSETMC..."):
                    options_df, underlying_df, report = TSETMCProvider().get_option_chain(
                        underlying=underlying_filter if scope == "فقط یک دارایی پایه" else None
                    )
                st.session_state["dc_live_preview"] = {
                    "options_df": options_df, "underlying_df": underlying_df,
                    "report": report, "scope": scope,
                    "underlying": underlying_filter, "dataset": dataset_name.strip(),
                }
            except Exception as exc:  # noqa: BLE001
                st.session_state["dc_live_preview"] = {"error": str(exc)}

    preview = st.session_state.get("dc_live_preview")
    if not preview:
        return
    if preview.get("error"):
        c.error_state("دریافت داده زنده ممکن نشد", preview["error"])
        return

    options_df = preview["options_df"]
    underlying_df = preview["underlying_df"]
    report = preview["report"]
    scope = preview["scope"]
    underlying_filter = preview["underlying"]
    dataset_name = preview["dataset"]

    if options_df.empty:
        c.error_state(
            "هیچ قرارداد معتبری یافت نشد",
            "دارایی پایه را بررسی کنید یا «کل بازار» را امتحان کنید.",
        )
        return

    c.spacer(16)
    c.kpi_strip([
        {"label": "دارایی‌های پایه", "value": c.fmt_int(report["underlyings_found"]), "na": False},
        {"label": "Call", "value": c.fmt_int(report["call_count"]), "na": False},
        {"label": "Put", "value": c.fmt_int(report["put_count"]), "na": False},
        {"label": "ردیف نادیده‌گرفته‌شده", "value": c.fmt_int(report["skipped_rows"]), "na": False},
        {"label": "زمان دریافت", "value": report["fetched_at"][11:19], "na": False},
    ])

    for w in report.get("warnings", []):
        st.warning(w)

    with st.expander(f"پیش‌نمایش {min(len(options_df), 20)} ردیف اول"):
        st.dataframe(_jalali_date_cols(options_df.head(20), ["quote_date", "expiry"]),
                     use_container_width=True, hide_index=True)

    c.spacer(16)
    if st.button("تأیید و ذخیره", type="primary", key="dc_live_save_btn"):
        # داده همین پیش‌نمایش ذخیره می‌شود، نه یک دریافت تازه — وگرنه
        # ممکن بود چیزی ذخیره شود که کاربر اصلاً ندیده است.
        result = run_manual_sync(
            TSETMCProvider(), dataset_name=dataset_name,
            underlying=underlying_filter if scope == "فقط یک دارایی پایه" else None,
            prefetched=(options_df, underlying_df, report),
        )
        common.clear_caches()
        snap = result.get("snapshot_report", {})
        if result["status"] == "FAILED":
            c.error_state("Sync ناموفق بود", result.get("error", ""))
        else:
            msg = (f"{snap.get('records_valid', 0):,} ردیف معتبر ذخیره شد "
                   f"({snap.get('records_rejected', 0)} ردیف نامعتبر رد شد). "
                   f"مجموعه: «{dataset_name}»")
            if snap.get("underlying_rows_saved"):
                msg += f" + {snap['underlying_rows_saved']:,} ردیف قیمت دارایی پایه."
            st.success(msg)
            if snap.get("warnings"):
                with st.expander("جزئیات اعتبارسنجی"):
                    for w in snap["warnings"]:
                        st.write("• " + w)
            # --------------------------------------------------------
            # تاریخچه دارایی‌های پایه بلافاصله و خودکار گرفته می‌شود.
            # این سریع است (حدود ۲۰ نماد) ولی مبنای HV، IV Rank و
            # بک‌تست است — بدون آن نیمی از محصول کار نمی‌کند و کاربر
            # هم دلیلش را نمی‌فهمد.
            # تاریخچه تک‌تک قراردادها خودکار گرفته نمی‌شود چون یک
            # درخواست به‌ازای هر نماد لازم دارد؛ آن از تب «تاریخچه»
            # یا از خود صفحه بک‌تست قابل دریافت است.
            # --------------------------------------------------------
            from core.data import auto_history
            targets = ([underlying_filter.strip()]
                       if scope == "فقط یک دارایی پایه" and (underlying_filter or "").strip()
                       else None)
            bar = st.progress(0.0)
            lbl = st.empty()

            def _prog(done, total, text):
                bar.progress(min(done / total, 1.0) if total else 1.0)
                lbl.markdown(f'<div class="helper">{c.esc(text)} ({done}/{total})</div>',
                             unsafe_allow_html=True)

            hist = auto_history.bootstrap_history(
                dataset_name, underlyings=targets,
                include_contracts=False, progress=_prog)
            bar.empty()
            lbl.empty()
            common.clear_caches()

            if hist["status"] == "UNAVAILABLE":
                st.markdown(
                    '<div class="chips"><span class="chip warn">'
                    + c.esc(hist["error"]) +
                    " تا نصب آن، تحلیل تاریخی و بک‌تست غیرفعال می‌مانند.</span></div>",
                    unsafe_allow_html=True)
            elif hist["rows_added"]:
                st.success(f"تاریخچه دارایی پایه به‌روز شد: "
                           f"{hist['rows_added']:,} ردیف جدید.")
            else:
                c.helper("تاریخچه دارایی پایه از قبل به‌روز بود.")

            if scope == "فقط یک دارایی پایه" and (underlying_filter or "").strip():
                st.session_state["dc_history_ready"] = {
                    "dataset": dataset_name, "underlying": underlying_filter.strip(),
                }

    # تاریخچه قراردادها از تب اختصاصی «تاریخچه» یا مستقیماً از صفحه بک‌تست
    # گرفته می‌شود؛ نگه‌داشتن یک دکمه موازی اینجا فقط سردرگمی می‌ساخت.
    ready = st.session_state.get("dc_history_ready")
    if ready:
        c.spacer(8)
        c.helper(
            f"تاریخچه دارایی پایه «{ready['underlying']}» به‌روز شد. برای بک‌تست به "
            "تاریخچه تک‌تک قراردادها هم نیاز است — آن را از تب «تاریخچه» با گزینه "
            "«دارایی پایه + قراردادها» دریافت کنید."
        )

    with st.expander("گزارش آخرین Syncها (Sync Log)"):
        log_df = database.list_sync_log(limit=10)
        if log_df.empty:
            st.caption("هنوز هیچ Syncی ثبت نشده.")
        else:
            st.dataframe(
                log_df[["provider", "started_at", "status", "records_received",
                        "records_valid", "records_rejected"]],
                use_container_width=True, hide_index=True,
            )


# ===========================================================================
# ۱–۴: جریان ورود داده (مسیر دستی/اضطراری — دیگر مسیر پیش‌فرض نیست)
# ===========================================================================
def _import_flow():
    st.warning(
        "این مسیر **دیگر منبع اصلی داده ATLAS نیست**. منبع پیش‌فرض حالا تب "
        "«دریافت بازار (TSETMC)» است. این تب فقط برای مواردی نگه داشته شده "
        "که TSETMC/fima در دسترس نیستند یا داده‌ای خارج از پوشش آن‌ها دارید.",
        icon="⚠️",
    )
    c.section("۱. بارگذاری", "فایل اکسل بازار را انتخاب کنید")

    # تنها قالب پشتیبانی‌شده: خروجی سایت آپشن‌گر
    kind = KIND_SCREENER
    c.helper("قالب پذیرفته‌شده: خروجی خام سایت آپشن‌گر (نمادها با پیشوند ض/ط).")

    g1, g2 = st.columns([1.6, 1.4])
    with g1:
        dataset_name = st.text_input("نام مجموعه (Dataset)", key="dc_name",
                                     placeholder="مثلاً: شهریور ۱۴۰۵")
    with g2:
        quote_date_str = st.text_input(
            "تاریخ این Snapshot", key="dc_qdate", placeholder="۱۴۰۵/۰۶/۰۵",
            help="این قالب تاریخ را داخل خودش ندارد چون خروجی لحظه‌ای است.",
        )

    uploaded = st.file_uploader("فایل اکسل", type=["xlsx", "xls"], key="dc_file")

    if uploaded is None:
        c.spacer(16)
        c.empty_state("منتظر فایل",
                      "یک فایل اکسل انتخاب کنید تا ستون‌هایش تشخیص داده شود و پیش از ثبت، آن را بررسی کنید.")
        return
    if not dataset_name.strip():
        c.spacer(16)
        c.empty_state("نام مجموعه لازم است",
                      "برای افزودن Snapshot جدید به داده‌های قبلی، همان نام مجموعه قبلی را وارد کنید.")
        return
    if not (quote_date_str or "").strip():
        c.spacer(16)
        c.empty_state("تاریخ Snapshot لازم است",
                      "این فرمت تاریخ ندارد؛ تاریخ روزی که خروجی گرفته شده را وارد کنید.")
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name

    try:
        _detect_review_import(tmp_path, kind, dataset_name.strip(), quote_date_str)
    except Exception as exc:  # خطای خواندن فایل نباید صفحه را بشکند (بخش ۷۰)
        c.spacer(16)
        c.error_state(
            "خواندن فایل ممکن نشد",
            f"{type(exc).__name__}: {exc}. مطمئن شوید فایل یک اکسل سالم است و "
            "سطر اول آن عنوان ستون‌هاست (نه سطر توضیحی).",
        )
    finally:
        os.unlink(tmp_path)


def _detect_review_import(path: str, kind: str, dataset_name: str, quote_date_str):
    # ---------------- ۲. تشخیص ----------------
    c.spacer(20)
    c.section("۲. تشخیص", "ستون‌های فایل شما به فیلدهای Atlas نگاشت می‌شوند")

    clean_df, underlying_df, report = importer.import_tse_screener_excel(path, quote_date_str)

    mapping = report.get("detected_mapping") or {}
    if mapping:
        headers = ["فیلد Atlas", "ستون فایل شما"]
        labels = {
            "quote_date": "تاریخ", "symbol": "نماد قرارداد", "underlying": "نماد پایه",
            "option_type": "نوع (Call/Put)", "strike": "قیمت اعمال", "expiry": "سررسید",
            "close": "قیمت پایانی", "bid": "بهترین تقاضا", "ask": "بهترین عرضه",
            "volume": "حجم", "open_interest": "موقعیت باز", "iv": "نوسان ضمنی",
            "underlying_close": "قیمت دارایی پایه",
        }
        rows = [[c.esc(labels.get(k, k)), c.num(v)] for k, v in mapping.items()]
        c.table(headers, rows)
    elif kind == KIND_SCREENER:
        c.helper("این فرمت نگاشت ثابت دارد و ستون‌هایش مستقیماً شناخته می‌شوند.")

    missing = report.get("missing_required_fields") or []
    if missing:
        c.spacer(16)
        c.error_state("ستون‌های ضروری پیدا نشد", "این فیلدها در فایل نبودند: " + "، ".join(missing))
        return
    if clean_df is None or clean_df.empty:
        c.spacer(16)
        c.error_state("هیچ ردیف معتبری در فایل نبود",
                      "همه ردیف‌ها در اعتبارسنجی حذف شدند. هشدارهای زیر را ببینید.")
        for w in report.get("warnings", []):
            c.helper("• " + w)
        return

    # ---------------- ۳. بررسی ----------------
    c.spacer(24)
    c.section("۳. بررسی", "پیش از ثبت، نتیجه اعتبارسنجی را ببینید")

    n_spot = report.get("underlying_prices_found")
    c.kpi_strip([
        {"label": "ردیف‌های فایل", "value": c.fmt_int(report["total_rows"]), "na": False},
        {"label": "ردیف معتبر", "value": c.fmt_int(report.get("kept_rows", 0)), "na": False},
        {"label": "ردیف حذف‌شده", "value": c.fmt_int(report.get("dropped_rows", 0)), "na": False},
        {"label": "Call", "value": c.fmt_int(report.get("call_count")) if "call_count" in report else "—",
         "na": "call_count" not in report},
        {"label": "Put", "value": c.fmt_int(report.get("put_count")) if "put_count" in report else "—",
         "na": "put_count" not in report},
        {"label": "قیمت دارایی پایه",
         "value": f"{n_spot} نماد" if n_spot else "یافت نشد",
         "na": not n_spot},
    ])

    warnings = report.get("warnings", [])
    if warnings:
        st.markdown(
            '<div class="chips">' + "".join(
                f'<span class="chip warn">{c.esc(w)}</span>' for w in warnings
            ) + "</div>",
            unsafe_allow_html=True,
        )
        c.spacer(12)

    if underlying_df is not None and not underlying_df.empty:
        c.helper("قیمت دارایی پایه از همین فایل استخراج شد — نیازی به فایل جداگانه نیست.")
        rows = [[c.esc(r["underlying"]), c.num(JD(r["quote_date"])), c.num(c.fmt_int(r["close"]))]
                for _, r in underlying_df.head(10).iterrows()]
        c.table(["نماد پایه", "تاریخ", "قیمت پایانی"], rows, numeric_cols={1, 2})
        if len(underlying_df) > 10:
            c.helper(f"{len(underlying_df) - 10} ردیف دیگر نمایش داده نشده.")
        c.spacer(16)

    with st.expander(f"پیش‌نمایش {min(len(clean_df), 20)} ردیف اول"):
        st.dataframe(_jalali_date_cols(clean_df.head(20), ["quote_date", "expiry"]),
                     use_container_width=True, hide_index=True)

    # هشدار داده تکراری — پیش از ثبت، نه بعدش
    dup_dates = _existing_dates(dataset_name, clean_df)
    if dup_dates:
        c.spacer(12)
        st.markdown(
            f'<div class="chips"><span class="chip warn">'
            f'برای {"، ".join(JD(d) for d in dup_dates[:3])}'
            f'{" و چند تاریخ دیگر" if len(dup_dates) > 3 else ""} '
            f'از قبل در این مجموعه داده وجود دارد — ثبت دوباره ردیف تکراری می‌سازد.'
            f"</span></div>",
            unsafe_allow_html=True,
        )

    # ---------------- ۴. ثبت ----------------
    c.spacer(24)
    c.section("۴. ثبت")
    if not st.button("تأیید و ذخیره", type="primary", key="dc_save"):
        return

    n1 = database.save_dataframe(clean_df, dataset_name, replace_existing=False)
    msg = f"{n1:,} ردیف اختیار معامله ذخیره شد."
    if underlying_df is not None and not underlying_df.empty:
        n2 = database.save_underlying_dataframe(underlying_df, dataset_name, replace_existing=False)
        msg += f" همراه با {n2:,} ردیف قیمت دارایی پایه."

    common.clear_caches()  # وگرنه صفحات دیگر داده قدیمی Cache‌شده را نشان می‌دهند
    st.success(msg + f" مجموعه: «{dataset_name}»")


def _existing_dates(dataset_name: str, clean_df: pd.DataFrame) -> list:
    """تاریخ‌هایی از این فایل که از قبل در همین مجموعه ثبت شده‌اند."""
    if "quote_date" not in clean_df.columns:
        return []
    existing = database.load_data(dataset_name=dataset_name)
    if existing.empty:
        return []
    have = set(existing["quote_date"].dropna().unique())
    return sorted(set(clean_df["quote_date"].dropna().unique()) & have)


# ===========================================================================
def _datasets(datasets: pd.DataFrame):
    if datasets.empty:
        c.empty_state("هنوز مجموعه‌ای وارد نشده", "از تب «ورود داده» اولین فایل را اضافه کنید.")
        return

    c.section("مجموعه‌ها", f"{len(datasets)} مجموعه ثبت‌شده")
    headers = ["مجموعه", "ردیف‌ها", "نمادهای پایه", "از تاریخ", "تا تاریخ"]
    rows = [[
        c.esc(r["dataset"]),
        c.num(c.fmt_int(r["rows"])),
        c.num(c.fmt_int(r["underlyings"])),
        c.num(JD(r["from_date"])),
        c.num(JD(r["to_date"])),
    ] for _, r in datasets.iterrows()]
    c.table(headers, rows, numeric_cols={1, 2, 3, 4})

    c.spacer(24)
    c.section("حذف مجموعه", "این کار برگشت‌پذیر نیست")
    d1, d2 = st.columns([2, 1])
    target = d1.selectbox("مجموعه", ["—"] + datasets["dataset"].tolist(), key="dc_del")
    if target != "—":
        confirm = d1.checkbox(f"می‌دانم که همه داده‌های «{target}» پاک می‌شود", key="dc_del_ok")
        if d2.button("حذف", type="secondary", use_container_width=True,
                     disabled=not confirm, key="dc_del_btn"):
            database.delete_dataset(target)
            common.clear_caches()
            st.success(f"مجموعه «{target}» حذف شد.")
            st.rerun()


def _quality(datasets: pd.DataFrame):
    if datasets.empty:
        c.empty_state("داده‌ای برای بررسی نیست", "ابتدا یک فایل وارد کنید.")
        return

    dataset_name = st.selectbox("مجموعه", datasets["dataset"].tolist(), key="dc_q_dataset")
    options_df = database.load_data(dataset_name=dataset_name)
    if options_df.empty:
        c.empty_state("این مجموعه رکوردی ندارد", "مجموعه دیگری انتخاب کنید.")
        return

    rep = analytics.data_quality_report(options_df)
    c.kpi_strip([
        {"label": "ردیف‌ها", "value": c.fmt_int(rep["rows"]), "na": False},
        {"label": "نمادهای پایه", "value": c.fmt_int(rep["underlyings"]), "na": False},
        {"label": "قراردادها", "value": c.fmt_int(rep["contracts"]), "na": rep["contracts"] is None},
        {"label": "Snapshotها", "value": c.fmt_int(rep["snapshots"]), "na": False},
        {"label": "Call", "value": c.fmt_int(rep["calls"]), "na": False},
        {"label": "Put", "value": c.fmt_int(rep["puts"]), "na": False},
    ])

    # هشدار مهم: بک‌تست بدون Snapshot کافی بی‌معناست
    if rep["snapshots"] < 5:
        st.markdown(
            f'<div class="chips"><span class="chip warn">فقط {rep["snapshots"]} Snapshot موجود است — '
            f'برای HV، سیگنال‌های تغییر و بک‌تست معنادار، داده روزهای بیشتری لازم است.</span></div>',
            unsafe_allow_html=True)
        c.spacer(12)

    # قیمت دارایی پایه: بدون آن نیمی از محصول کار نمی‌کند
    und = database.load_underlying_data(dataset_name=dataset_name)
    covered = set(zip(und["underlying"], und["quote_date"])) if not und.empty else set()
    needed = set(zip(options_df["underlying"], options_df["quote_date"]))
    missing = len(needed - covered)
    tone = "warn" if missing else ""
    st.markdown(
        f'<div class="chips"><span class="chip {tone}">قیمت دارایی پایه: '
        f'{len(needed) - missing} از {len(needed)} جفت (نماد، تاریخ) پوشش داده شده'
        + (f" — {missing} جفت بدون قیمت پایه، Greeks و ITM/ATM/OTM آن‌ها محاسبه نمی‌شود."
           if missing else "") + "</span></div>",
        unsafe_allow_html=True)

    c.spacer(20)
    c.section("تکمیل بودن فیلدها", "چند درصد ردیف‌ها این فیلد را واقعاً دارند")
    labels = {"iv": "نوسان ضمنی", "open_interest": "موقعیت باز", "volume": "حجم",
              "bid": "بهترین تقاضا", "ask": "بهترین عرضه", "close": "قیمت پایانی"}
    rows = []
    for field, pct in rep["completeness_pct"].items():
        tone = "pos" if pct >= 90 else ("neg" if pct < 50 else "")
        bar = (f'<div style="background:var(--bg-elevated);border-radius:3px;height:6px;width:120px">'
               f'<div style="width:{max(pct, 0):.0f}%;height:6px;border-radius:3px;'
               f'background:var({"--pos" if pct >= 90 else "--neg" if pct < 50 else "--warn"})"></div></div>')
        rows.append([
            c.esc(labels.get(field, field)),
            f'<span class="num {tone}">{pct:.1f}%</span>',
            c.num(c.fmt_int(rep["missing"][field])),
            bar,
        ])
    c.table(["فیلد", "تکمیل‌شده", "مقادیر خالی", ""], rows, numeric_cols={1, 2})


# ===========================================================================
# تاریخچه خودکار — از سرویس، نه از Snapshotهای دستی کاربر
# ===========================================================================
def _history_flow(datasets):
    from core.data import auto_history

    c.section(
        "تاریخچه بازار",
        "تاریخچه هر نماد مستقیماً از سرویس گرفته می‌شود. لازم نیست هر روز "
        "دستی Snapshot ذخیره کنید.",
    )

    if datasets.empty:
        c.empty_state("هنوز مجموعه‌ای وجود ندارد",
                      "ابتدا از تب «دریافت بازار» یک Snapshot بگیرید تا فهرست "
                      "نمادها مشخص شود، سپس تاریخچه‌شان دریافت می‌شود.")
        return

    g1, g2 = st.columns([1.4, 2.6])
    with g1:
        dataset = st.selectbox("مجموعه", datasets["dataset"].tolist(), key="dc_hist_ds")

    cov = auto_history.history_coverage(dataset)
    c.kpi_strip([
        {"label": "روزهای قابل استفاده", "value": c.fmt_int(cov["covered_days"]), "na": False},
        {"label": "روز داده اختیار", "value": c.fmt_int(cov["option_days"]), "na": False},
        {"label": "روز قیمت پایه", "value": c.fmt_int(cov["underlying_days"]), "na": False},
        {"label": "قراردادها", "value": c.fmt_int(cov["symbols"]), "na": False},
        {"label": "از تاریخ", "value": JD(cov["first"]) if cov["first"] else "—",
         "na": not cov["first"]},
        {"label": "تا تاریخ", "value": JD(cov["last"]) if cov["last"] else "—",
         "na": not cov["last"]},
    ])

    if cov["covered_days"] < 5:
        _msg = (f'<div class="chips"><span class="chip warn">فقط {cov["covered_days"]} روز '
                "داده کامل موجود است. نوسان تحقق‌یافته (HV)، IV Rank و بک‌تست تا "
                "دریافت تاریخچه قابل محاسبه نیستند.</span></div>")
        st.markdown(_msg, unsafe_allow_html=True)
    c.spacer(16)

    all_u = sorted(database.load_data(dataset_name=dataset)["underlying"].dropna().unique().tolist()) \
        if not database.load_data(dataset_name=dataset).empty else []

    h1, h2 = st.columns([2, 1.4])
    with h1:
        picked = st.multiselect(
            "نمادهای پایه", all_u, key="dc_hist_u",
            help="خالی بگذارید تا همه نمادهای این مجموعه پردازش شوند.",
        )
    with h2:
        depth = st.radio(
            "عمق", ["فقط دارایی پایه", "دارایی پایه + قراردادها"],
            key="dc_hist_depth",
            captions=["سریع — کافی برای HV و IV Rank",
                      "کندتر — لازم برای بک‌تست"],
        )

    include_contracts = depth != "فقط دارایی پایه"
    if include_contracts:
        c.helper("تاریخچه هر قرارداد یک درخواست جداگانه به TSETMC لازم دارد. برای یک "
                 "نماد پایه معمولاً چند دقیقه طول می‌کشد؛ برای کل بازار بسیار بیشتر. "
                 "پیشنهاد می‌شود نماد موردنظر بک‌تست را انتخاب کنید.")

    if st.button("دریافت / به‌روزرسانی تاریخچه", type="primary", key="dc_hist_run"):
        bar = st.progress(0.0)
        label = st.empty()

        def progress(done, total, text):
            bar.progress(min(done / total, 1.0) if total else 1.0)
            label.markdown(f'<div class="helper">{c.esc(text)} ({done}/{total})</div>',
                           unsafe_allow_html=True)

        result = auto_history.bootstrap_history(
            dataset, underlyings=picked or None,
            include_contracts=include_contracts, progress=progress)
        bar.empty()
        label.empty()
        common.clear_caches()
        st.session_state["dc_hist_result"] = result

    result = st.session_state.get("dc_hist_result")
    if not result:
        return

    c.spacer(14)
    if result["status"] == "UNAVAILABLE":
        c.error_state("منبع تاریخچه در دسترس نیست", result["error"])
        return
    if result["status"] == "NO_DATA":
        c.error_state("داده‌ای برای پردازش نبود", result.get("error", ""))
        return

    st.success(f"{result['rows_added']:,} ردیف تاریخی جدید اضافه شد "
               f"({result['underlyings_attempted']} دارایی پایه، "
               f"{result['symbols_attempted']} قرارداد بررسی شد).")

    if result.get("truncated"):
        st.markdown('<div class="chips"><span class="chip warn">تعداد قراردادها از سقف '
                    "یک اجرا بیشتر بود؛ برای بقیه دوباره اجرا کنید یا نماد را محدود کنید."
                    "</span></div>", unsafe_allow_html=True)

    rows = []
    for r in result["underlyings"]:
        rows.append([c.esc(r["underlying"]), "دارایی پایه", c.esc(r["status"]),
                     c.num(c.fmt_int(r.get("rows_added"))), c.esc(r.get("error") or "—")])
    for r in result["contracts"][:60]:
        rows.append([c.num(r["symbol"]), "قرارداد", c.esc(r["status"]),
                     c.num(c.fmt_int(r.get("rows_added"))), c.esc(r.get("error") or "—")])
    if rows:
        with st.expander(f"جزئیات ({len(result['underlyings']) + len(result['contracts'])} نماد)"):
            c.table(["نماد", "نوع", "وضعیت", "ردیف جدید", "خطا"], rows, numeric_cols={3})


# ===========================================================================
# منبع پارامترها — چه چیزی دریافتی است و چه چیزی محاسبه ATLAS
# ===========================================================================
def _provenance_flow(datasets):
    from core import provenance as prov

    c.section(
        "منبع هر پارامتر",
        "اگر عددی در داشبورد مشکوک یا متناقض بود، اینجا مشخص است که از کدام "
        "سرویس آمده یا با چه فرمولی ساخته شده.",
    )

    # پوشش واقعی روی داده موجود، در کنار تعریف نظری
    chain = pd.DataFrame()
    if not datasets.empty:
        p1, _ = st.columns([1.4, 2.6])
        with p1:
            ds = st.selectbox("بررسی پوشش روی مجموعه", datasets["dataset"].tolist(),
                              key="dc_prov_ds")
        chain = database.load_data(dataset_name=ds)
        if not chain.empty:
            last_date = chain["quote_date"].max()
            chain = chain[chain["quote_date"] == last_date]
            c.helper(f"پوشش بر مبنای آخرین Snapshot ({JD(last_date)}) با "
                     f"{len(chain):,} قرارداد محاسبه شده است.")
    c.spacer(14)

    groups = [
        ("دریافتی از TSETMC", prov.FETCHED_FIELDS,
         "این مقادیر عیناً از سرویس می‌آیند و ATLAS تغییرشان نمی‌دهد."),
        ("دریافتی از سرویس تاریخچه", prov.HISTORICAL_FIELDS,
         "تاریخچه روزانه؛ مبنای HV، IV Rank و بک‌تست."),
        ("محاسبه ATLAS", prov.CALCULATED_FIELDS,
         "سرویس این مقادیر را نمی‌دهد؛ ATLAS آن‌ها را از داده خام می‌سازد."),
        ("مشتق از محاسبات", prov.DERIVED_FIELDS,
         "لایه دوم: از روی مقادیر محاسبه‌شده ساخته می‌شوند."),
    ]

    for title, fields, note in groups:
        c.section(title, note)
        rows = []
        for f in fields:
            if f["kind"] == prov.FETCHED:
                origin = f'<span class="pos">{c.esc(f["source"])}</span>'
                detail = c.num(f["api_field"] or "—")
            else:
                origin = f'<span style="color:var(--accent)">{c.esc(prov.KIND_LABELS_FA[f["kind"]])}</span>'
                detail = c.esc(f.get("formula") or "—")

            cov = prov.coverage_for(chain, f["field"])
            if cov["status"] or cov["total"] == 0:
                cov_cell = f'<span class="muted">—</span>'
            else:
                pct = cov["present"] / cov["total"] * 100
                cls = "pos" if pct >= 90 else ("neg" if pct < 40 else "warn")
                extra = f" (صفر: {cov['zero']:,})" if cov["zero"] else ""
                cov_cell = (f'<span class="num {cls}">{pct:.0f}%</span>'
                            f'<span class="muted" style="font-size:.7rem">{c.esc(extra)}</span>')

            rows.append([
                c.esc(f["label"]),
                c.num(f["field"]),
                origin,
                detail,
                c.esc(f.get("unit") or "—"),
                cov_cell,
                c.esc(f.get("note") or "—"),
            ])
        c.table(["پارامتر", "نام فنی", "منبع", "فیلد API / فرمول", "واحد",
                 "پوشش", "توضیح"], rows, numeric_cols={5})
        c.spacer(20)

    c.helper("«پوشش» یعنی چند درصد قراردادهای آخرین Snapshot این مقدار را دارند. "
             "عدد داخل پرانتز تعداد مقادیر صفر است — صفر با «نداریم» فرق دارد: "
             "حجم صفر یعنی واقعاً معامله نشده، ولی خالی بودن یعنی سرویس آن را نداده.")
