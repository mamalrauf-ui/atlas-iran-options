"""
Contract Detail — تجربه جزئیات قرارداد، قابل‌استفاده مجدد (بخش ۴۱ و ۸۳).

این یک صفحه سطح‌بالا نیست و در سایدبار ظاهر نمی‌شود. هر صفحه‌ای (زنجیره
اختیار، اسکنر، فرصت‌ها) می‌تواند آن را با یک ردیف قرارداد صدا بزند:

    contract_detail.render(row, context={...})

اصل Progressive Disclosure (بخش ۴۱/۸۴): لایه اول همیشه دیده می‌شود
(هویت + قیمت + نقدشوندگی)، Greeks و ارزش ذاتی/زمانی در لایه دوم.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import components as c
from ui.common import JD


def _row(items: list[tuple[str, str]]) -> str:
    """یک ردیف از جفت‌های برچسب/مقدار به‌صورت شبکه فشرده."""
    cells = "".join(
        f'<div><div class="kpi-label">{c.esc(k)}</div>'
        f'<div style="font-size:.88rem;color:var(--text-1)">{v}</div></div>'
        for k, v in items
    )
    return (
        f'<div style="display:grid;grid-template-columns:repeat({len(items)},1fr);'
        f'gap:14px;margin-bottom:14px">{cells}</div>'
    )


def render(row: pd.Series | dict, context: dict | None = None,
           on_add_to_strategy=None, on_view_chain=None, key_prefix: str = "cd"):
    """
    row: یک ردیف قرارداد از زنجیره enrich‌شده.
    context: {"dataset", "underlying", "quote_date", "expiry"} برای انتقال به Strategy Lab.
    on_add_to_strategy / on_view_chain: اگر None باشند، دکمه مربوطه نمایش داده نمی‌شود
                                        (به‌جای دکمه‌ای که کار نمی‌کند).
    """
    if row is None:
        return
    get = row.get if hasattr(row, "get") else (lambda k, d=None: row[k] if k in row else d)
    context = context or {}

    symbol = get("symbol") or c.NA
    otype = get("option_type")

    # --- سرآیند ---
    st.markdown(
        f'<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:14px">'
        f'<span class="num" style="font-size:1rem;font-weight:600;color:var(--text-1)">{c.esc(symbol)}</span>'
        f'<span class="badge sig">{c.type_label(otype)}</span>'
        f'{c.moneyness_badge(get("moneyness_bucket"))}'
        f'<span class="muted" style="font-size:.78rem">{c.esc(get("underlying") or "")}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    # --- لایه ۱: هویت و قیمت ---
    dte = get("dte")
    st.markdown(
        _row([
            ("قیمت اعمال", c.num(c.fmt_int(get("strike")))),
            ("سررسید", c.num(JD(get("expiry")))),
            ("روز تا سررسید", c.num(c.fmt_int(dte))),
            ("قیمت پایانی", c.num(c.fmt_int(get("close")))),
        ])
        + _row([
            ("بهترین تقاضا", c.num(c.fmt_int(get("bid")))),
            ("بهترین عرضه", c.num(c.fmt_int(get("ask")))),
            ("حجم", c.num(c.fmt_compact(get("volume")))),
            ("موقعیت باز", c.num(c.fmt_compact(get("open_interest")))),
        ])
        + _row([
            ("نوسان ضمنی (IV)", c.num(c.fmt_pct(get("iv")))),
            ("ارزش ذاتی", c.num(c.fmt_int(get("intrinsic_value")))),
            ("ارزش زمانی", c.num(c.fmt_int(get("time_value")))),
            ("قیمت دارایی پایه", c.num(c.fmt_int(get("underlying_close")))),
        ]),
        unsafe_allow_html=True,
    )

    # --- هشدارهای مبتنی بر داده واقعی (نه تفسیر ساختگی) ---
    notes = []
    if pd.notna(get("dte")) and get("dte") is not None and float(get("dte")) <= 7:
        notes.append(("warn", "کمتر از یک هفته تا سررسید — فرسایش زمانی شدید است."))
    bid, ask, close = get("bid"), get("ask"), get("close")
    if all(v is not None and pd.notna(v) for v in (bid, ask, close)) and float(close) > 0:
        spread = (float(ask) - float(bid)) / float(close)
        if spread > 0.15:
            notes.append(("warn", f"اسپرد خرید/فروش گسترده است ({spread * 100:.0f}٪ قیمت)."))
    vol = get("volume")
    if vol is not None and pd.notna(vol) and float(vol) == 0:
        notes.append(("warn", "امروز هیچ معامله‌ای روی این قرارداد انجام نشده."))
    if get("iv") is None or pd.isna(get("iv")):
        notes.append(("", "نوسان ضمنی برای این قرارداد محاسبه نشد؛ Greeks هم قابل‌اتکا نیست."))

    if notes:
        st.markdown(
            '<div class="chips">' + "".join(
                f'<span class="chip {tone}">{c.esc(txt)}</span>' for tone, txt in notes
            ) + "</div>",
            unsafe_allow_html=True,
        )
        c.spacer(12)

    # --- لایه ۲: Greeks (ثانویه — بخش ۴۸) ---
    with st.expander("Greeks و جزئیات فنی"):
        greeks = [("Delta", "delta", 3), ("Gamma", "gamma", 4),
                  ("Theta", "theta", 2), ("Vega", "vega", 2), ("Rho", "rho", 2)]
        cells = []
        for label, key, dec in greeks:
            v = get(key)
            txt = c.NA if v is None or pd.isna(v) else f"{float(v):,.{dec}f}"
            cells.append((label, c.num(txt)))
        st.markdown(_row(cells), unsafe_allow_html=True)
        if all(get(k) is None or pd.isna(get(k)) for _, k, _ in greeks):
            c.helper("Greeks محاسبه نشده — معمولاً چون قیمت دارایی پایه برای این تاریخ وارد نشده است.")

    # --- اکشن‌ها ---
    cols = st.columns(2)
    if on_add_to_strategy is not None:
        if cols[0].button("افزودن به استراتژی", key=f"{key_prefix}_add",
                          type="primary", use_container_width=True):
            on_add_to_strategy(row, context)
    if on_view_chain is not None:
        if cols[1].button("مشاهده زنجیره نماد ←", key=f"{key_prefix}_chain",
                          type="secondary", use_container_width=True):
            on_view_chain(row, context)
