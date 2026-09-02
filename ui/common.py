"""
زیرساخت مشترک UI: Sidebar گروه‌بندی‌شده، Session State، Navigation Intent
(برای Drill-down بین صفحات)، و لایه Cache روی محاسبات سنگین.

طبق بخش ۷۳: هیچ منطق مالی اینجا نیست؛ فقط Routing و Rendering.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import database, importer, market_brief, pricing
from ui import components as c

JD = importer.to_jalali_str

APP_NAME = "ATLAS"
APP_TAGLINE = "Iran Options Intelligence"

# دقیقاً ۹ صفحه سطح‌بالا، گروه‌بندی‌شده (بخش ۴). Contract Detail عمداً اینجا نیست.
NAV_GROUPS = [
    ("MARKET", [("Dashboard", "داشبورد"), ("Option Chain", "زنجیره اختیار")]),
    ("DISCOVER", [("Scanner", "اسکنر"), ("Opportunities", "فرصت‌ها")]),
    ("BUILD & TEST", [("Strategy Lab", "استراتژی لب"), ("Backtest", "بک‌تست")]),
    ("ANALYZE", [("Analytics", "تحلیل تاریخی")]),
    ("SYSTEM", [("Data Center", "مرکز داده"), ("Settings", "تنظیمات")]),
]
NAV_PAGES = [p for _, items in NAV_GROUPS for p, _ in items]
NAV_LABELS_FA = {p: fa for _, items in NAV_GROUPS for p, fa in items}

RISK_FREE_RATE_DEFAULT = 0.20


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------
def init_session_state():
    ss = st.session_state
    ss.setdefault("risk_free_rate", RISK_FREE_RATE_DEFAULT)
    ss.setdefault("active_page", "Dashboard")
    ss.setdefault("pending_strategy_legs", None)
    ss.setdefault("nav_intent", None)         # payload انتقالی بین صفحات
    ss.setdefault("selected_contract", None)  # برای Contract Detail (Drawer)
    ss.setdefault("atm_band_pct", market_brief.THRESHOLDS["atm_band_pct"])
    if "opportunity_weights" not in ss:
        from core.opportunity import DEFAULT_WEIGHTS
        ss.opportunity_weights = dict(DEFAULT_WEIGHTS)


def go_to(page: str, **intent):
    """
    ناوبری با حفظ Context (بخش ۵ و ۸۳).
    مثال: go_to("Scanner", signal="iv_expansion", symbols=[...])
    """
    if page not in NAV_PAGES:
        return
    payload = {"source": st.session_state.get("active_page"), **intent} if intent else None
    st.session_state.active_page = page
    st.session_state.nav_intent = payload
    st.rerun()


def take_intent(key: str | None = None):
    """Intent را می‌خواند و مصرف می‌کند (یک‌بارمصرف تا در Rerun بعدی گیر نکند)."""
    intent = st.session_state.get("nav_intent")
    if not intent:
        return None
    if key and key not in intent:
        return None
    st.session_state.nav_intent = None
    return intent


def open_contract(contract: dict):
    """باز کردن Contract Detail به‌صورت Drawer درون‌صفحه‌ای (نه منوی دهم)."""
    st.session_state.selected_contract = contract


# ---------------------------------------------------------------------------
# لایه Cache — enrich پرهزینه است (iterrows روی کل Snapshot)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=900)
def load_dataset(dataset_name: str):
    """داده خام یک Dataset. Cache چون در هر Rerun صفحه دوباره خوانده می‌شود."""
    return (
        database.load_data(dataset_name=dataset_name),
        database.load_underlying_data(dataset_name=dataset_name),
    )


@st.cache_data(show_spinner="در حال محاسبه Greeks و Moneyness…", ttl=900)
def enrich_snapshot(options_df: pd.DataFrame, underlying_df: pd.DataFrame,
                    quote_date: str, r: float, atm_band: float) -> pd.DataFrame:
    """
    یک Snapshot را enrich و ستون moneyness_bucket را اضافه می‌کند.
    quote_date در امضا هست تا کلید Cache به تاریخ حساس باشد.
    """
    snap = options_df[options_df["quote_date"] == quote_date].copy()
    if snap.empty:
        return snap
    snap = pricing.enrich_full_dataset(snap, underlying_df, r=r)
    return market_brief.add_moneyness_bucket(snap, atm_band)


def clear_caches():
    load_dataset.clear()
    enrich_snapshot.clear()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def _data_status():
    """(status, text, last_snapshot_label)"""
    datasets = database.list_datasets()
    if datasets.empty:
        return "err", "داده‌ای وارد نشده", None
    last = datasets["to_date"].max()
    return "ok", "داده به‌روز است", JD(last)


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            f'<div class="sb-brand"><div class="name">{APP_NAME}</div>'
            f'<div class="tag">{APP_TAGLINE}</div></div>',
            unsafe_allow_html=True,
        )

        active = st.session_state.active_page
        for group, items in NAV_GROUPS:
            st.markdown(f'<div class="sb-group">{group}</div>', unsafe_allow_html=True)
            for page, label in items:
                if st.button(
                    label,
                    key=f"nav_{page}",
                    use_container_width=True,
                    type="primary" if page == active else "secondary",
                ):
                    if page != active:
                        st.session_state.active_page = page
                        st.session_state.nav_intent = None
                        st.rerun()

        st.divider()
        status, text, last = _data_status()
        st.markdown(
            f'<div class="status {status}"><span class="dot"></span>{text}</div>'
            + (f'<div class="snap" style="margin-top:4px">آخرین Snapshot: {last}</div>' if last else ""),
            unsafe_allow_html=True,
        )

    return st.session_state.active_page


# ---------------------------------------------------------------------------
# انتخاب Dataset / Snapshot — الگوی مشترک صفحات
# ---------------------------------------------------------------------------
def dataset_picker(key_prefix: str, with_underlying: bool = True):
    datasets = database.list_datasets()
    if datasets.empty:
        c.empty_state("هنوز داده‌ای وارد نشده",
                      "برای شروع، از «مرکز داده» یک فایل اکسل اختیار معامله وارد کنید.")
        return None, None

    dataset_name = st.selectbox("Dataset", datasets["dataset"].tolist(), key=f"{key_prefix}_dataset")
    if not with_underlying:
        return dataset_name, None

    underlyings = database.list_underlyings(dataset_name)
    if not underlyings:
        c.empty_state("این Dataset نماد پایه‌ای ندارد", "یک فایل معتبر دیگر وارد کنید.")
        return dataset_name, None
    return dataset_name, st.selectbox("نماد پایه", underlyings, key=f"{key_prefix}_underlying")


def snapshot_picker(options_all: pd.DataFrame, key: str):
    """
    انتخاب Snapshot + Snapshot قبلی برای مقایسه.
    خروجی: (quote_date, prior_date | None, quote_dates)
    """
    quote_dates = sorted(options_all["quote_date"].dropna().unique(), reverse=True)
    if not quote_dates:
        return None, None, []
    qd = st.selectbox("تاریخ Snapshot", quote_dates, format_func=JD, key=key)
    priors = [d for d in quote_dates if d < qd]
    return qd, (max(priors) if priors else None), quote_dates


def _jalali_date_cols(df: pd.DataFrame, cols) -> pd.DataFrame:
    """نسخه‌ای از DataFrame با ستون‌های تاریخ تبدیل‌شده به شمسی — فقط برای نمایش."""
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = out[col].apply(JD)
    return out


# سازگاری با صفحاتی که هنوز Refactor نشده‌اند
def fmt_num(v, decimals=1, suffix=""):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:,.{decimals}f}{suffix}"


def render_header(title: str, subtitle: str = "", badge: str = ""):
    c.page_header(title, subtitle, snapshot_label=badge or None)
