"""
Option Chain — فضای کار تحلیل یک نماد (بخش ۳۸ تا ۴۱ Master Prompt).

پرسش اصلی صفحه: «قراردادهای اختیار این نماد چه وضعیتی دارند؟»

ساختار:
    سرآیند نماد → انتخاب سررسید → فیلتر فشرده → زنجیره CALL | STRIKE | PUT → Contract Detail

قواعد رعایت‌شده:
- Strike ستون مرکزی است و ATM با نوار افقی و برچسب مشخص می‌شود (بخش ۳۹).
- ستون‌های پیش‌فرض محدودند؛ Greeks پشت «ستون‌های پیشرفته» (بخش ۳۹).
- Contract Detail یک کامپوننت مشترک است، نه صفحه دهم (بخش ۴۱).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import database, market_brief
from ui import common, contract_detail
from ui import components as c
from ui.common import JD

# ستون‌های هر سمت زنجیره: (کلید، عنوان، فرمت‌کننده)
SIDE_COLUMNS = {
    "bid": ("تقاضا", lambda v: c.fmt_int(v)),
    "ask": ("عرضه", lambda v: c.fmt_int(v)),
    "close": ("پایانی", lambda v: c.fmt_int(v)),
    "volume": ("حجم", lambda v: c.fmt_compact(v)),
    "open_interest": ("موقعیت باز", lambda v: c.fmt_compact(v)),
    "iv": ("IV", lambda v: c.fmt_pct(v)),
    "delta": ("Delta", lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):.2f}"),
    "gamma": ("Gamma", lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):.4f}"),
    "theta": ("Theta", lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):.2f}"),
    "vega": ("Vega", lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):.2f}"),
    "intrinsic_value": ("ارزش ذاتی", lambda v: c.fmt_int(v)),
    "time_value": ("ارزش زمانی", lambda v: c.fmt_int(v)),
    # --- معیارهای مشتق ATLAS ---
    "oi_change": ("تغییر OI", lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):+,.0f}"),
    "oi_change_pct": ("تغییر OI ٪", lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):+.1f}%"),
    "spread_pct": ("اسپرد ٪", lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):.1f}%"),
    "bid_size": ("حجم تقاضا", lambda v: c.fmt_compact(v)),
    "ask_size": ("حجم عرضه", lambda v: c.fmt_compact(v)),
    "trade_count": ("تعداد معامله", lambda v: c.fmt_compact(v)),
    "volume_oi_ratio": ("حجم/OI", lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):.2f}"),
    "time_value_per_day": ("ارزش زمانی/روز", lambda v: c.fmt_int(v)),
    "premium_yield_annual_pct": ("بازده سالانه ٪",
                                 lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):,.0f}%"),
    "breakeven": ("سربه‌سر", lambda v: c.fmt_int(v)),
    "breakeven_distance_pct": ("فاصله سربه‌سر ٪",
                               lambda v: c.NA if v is None or pd.isna(v) else f"{float(v):+.1f}%"),
}
DEFAULT_SIDE_COLUMNS = ["bid", "ask", "volume", "open_interest", "iv", "delta"]
ADVANCED_SIDE_COLUMNS = [
    "close", "gamma", "theta", "vega", "intrinsic_value", "time_value",
    "oi_change", "oi_change_pct", "spread_pct", "bid_size", "ask_size",
    "trade_count", "volume_oi_ratio", "time_value_per_day",
    "premium_yield_annual_pct", "breakeven", "breakeven_distance_pct",
]


def render():
    # --- Context ورودی از داشبورد / اسکنر (بخش ۸۳) ---
    intent = common.take_intent("underlying")
    if intent:
        if intent.get("dataset"):
            st.session_state["chain_dataset"] = intent["dataset"]
        st.session_state["chain_underlying"] = intent["underlying"]
        if intent.get("expiry"):
            st.session_state["chain_expiry"] = intent["expiry"]
        if intent.get("symbol"):
            st.session_state["chain_detail_symbol"] = intent["symbol"]

    datasets = database.list_datasets()
    if datasets.empty:
        c.page_header("زنجیره اختیار", "وضعیت قراردادهای اختیار یک نماد پایه",
                      status="err", status_text="داده‌ای موجود نیست")
        c.empty_state("هنوز داده‌ای وارد نشده", "از «مرکز داده» یک فایل اختیار معامله وارد کنید.")
        return

    # --- نوار انتخاب فشرده ---
    f1, f2, f3 = st.columns([1.3, 1.3, 1.3])
    with f1:
        ds_list = datasets["dataset"].tolist()
        dataset_name = st.selectbox("Dataset", ds_list, key="chain_dataset")

    underlyings = database.list_underlyings(dataset_name)
    if not underlyings:
        c.page_header("زنجیره اختیار", "وضعیت قراردادهای اختیار یک نماد پایه")
        c.empty_state("این Dataset نماد پایه‌ای ندارد", "Dataset دیگری انتخاب کنید.")
        return
    with f2:
        underlying = st.selectbox("نماد پایه", underlyings, key="chain_underlying")

    options_all, underlying_all = common.load_dataset(dataset_name)
    sym_opts = options_all[options_all["underlying"] == underlying]
    if sym_opts.empty:
        c.page_header("زنجیره اختیار", underlying)
        c.empty_state("قراردادی برای این نماد نیست", "نماد دیگری انتخاب کنید.")
        return

    with f3:
        quote_dates = sorted(sym_opts["quote_date"].dropna().unique(), reverse=True)
        quote_date = st.selectbox("تاریخ Snapshot", quote_dates, format_func=JD, key="chain_qdate")

    r = st.session_state.risk_free_rate
    band = st.session_state.atm_band_pct
    snap = common.enrich_snapshot(options_all, underlying_all, quote_date, r, band)
    snap = snap[snap["underlying"] == underlying]

    if snap.empty:
        c.page_header("زنجیره اختیار", underlying, snapshot_label=JD(quote_date))
        c.empty_state("این نماد در Snapshot انتخاب‌شده قرارداد ندارد", "تاریخ دیگری انتخاب کنید.")
        return

    spot = _first_valid(snap.get("underlying_close"))
    is_latest = quote_date == max(quote_dates)

    # --- سرآیند نماد (بخش ۳۸) ---
    c.page_header(
        f"زنجیره اختیار — {underlying}",
        "وضعیت قراردادهای اختیار این نماد در پایان معاملات",
        snapshot_label=JD(quote_date),
        status="ok" if is_latest else "warn",
        status_text="داده به‌روز است" if is_latest else "Snapshot تاریخی",
    )
    _underlying_header(snap, underlying, spot)

    if spot is None:
        c.helper("قیمت دارایی پایه برای این تاریخ وارد نشده — وضعیت ITM/ATM/OTM و Greeks محاسبه نمی‌شود. "
                 "فایل «قیمت دارایی پایه» را در مرکز داده وارد کنید.")
        c.spacer(12)

    # --- سررسید + فیلترهای فشرده (بخش ۴۰) ---
    expiries = sorted(snap["expiry"].dropna().unique())
    g1, g2, g3 = st.columns([1.3, 1.3, 2])
    with g1:
        expiry = st.selectbox("سررسید", expiries, format_func=JD, key="chain_expiry")
    with g2:
        moneyness_filter = st.selectbox("وضعیت", ["همه", "ITM", "ATM", "OTM"], key="chain_moneyness")
    with g3:
        extra_cols = st.multiselect(
            "ستون‌های پیشرفته",
            [k for k in ADVANCED_SIDE_COLUMNS if k in snap.columns],
            format_func=lambda k: SIDE_COLUMNS[k][0],
            key="chain_extra_cols",
        )

    chain = snap[snap["expiry"] == expiry].copy()
    if moneyness_filter != "همه":
        chain = chain[chain["moneyness_bucket"] == moneyness_filter]

    if chain.empty:
        c.empty_state("هیچ قراردادی با این فیلترها یافت نشد",
                      "فیلتر وضعیت را روی «همه» بگذارید یا سررسید دیگری انتخاب کنید.")
        return

    side_cols = [k for k in DEFAULT_SIDE_COLUMNS if k in chain.columns] + \
                [k for k in extra_cols if k in chain.columns]

    c.spacer(8)
    c.section("زنجیره", f"سررسید {JD(expiry)} — {len(chain)} قرارداد"
                        + (f" · باند ATM: ±{band:g}٪" if spot else ""))
    _render_chain_table(chain, side_cols, spot, band)

    # --- Contract Detail (بخش ۴۱) ---
    c.spacer(28)
    c.section("جزئیات قرارداد", "یک قرارداد را انتخاب کنید تا تحلیل کامل آن باز شود")

    symbols = chain["symbol"].dropna().tolist()
    if not symbols:
        c.empty_state("قرارداد قابل‌انتخابی نیست", "ردیف‌های این زنجیره نماد ثبت‌شده ندارند.")
        return

    if st.session_state.get("chain_detail_symbol") not in symbols:
        st.session_state["chain_detail_symbol"] = symbols[0]
    sel = st.selectbox("قرارداد", symbols, key="chain_detail_symbol",
                       format_func=lambda s: _symbol_label(chain, s))

    row = chain[chain["symbol"] == sel].iloc[0]
    ctx = {"dataset": dataset_name, "underlying": underlying,
           "quote_date": quote_date, "expiry": expiry}

    contract_detail.render(
        row, context=ctx,
        on_add_to_strategy=_add_to_strategy,
        key_prefix="chain",
    )


# ===========================================================================
def _first_valid(series):
    if series is None:
        return None
    s = pd.Series(series).dropna()
    return float(s.iloc[0]) if not s.empty else None


def _symbol_label(chain: pd.DataFrame, symbol: str) -> str:
    row = chain[chain["symbol"] == symbol]
    if row.empty:
        return symbol
    row = row.iloc[0]
    return f"{symbol} — {c.type_label(row['option_type'])} {c.fmt_int(row['strike'])}"


def _underlying_header(snap: pd.DataFrame, underlying: str, spot):
    """نوار وضعیت نماد پایه — فقط مقادیری که واقعاً موجودند (بخش ۳۸)."""
    iv = snap["iv"].dropna().mean() if "iv" in snap.columns and snap["iv"].notna().any() else None
    vol = snap["volume"].dropna().sum() if "volume" in snap.columns and snap["volume"].notna().any() else None
    oi = (snap["open_interest"].dropna().sum()
          if "open_interest" in snap.columns and snap["open_interest"].notna().any() else None)
    n_exp = snap["expiry"].nunique()

    items = [
        {"label": f"قیمت پایانی {underlying}", "value": c.fmt_int(spot) if spot else "داده موجود نیست",
         "na": spot is None},
        {"label": "میانگین IV نماد", "value": c.fmt_pct(iv) if iv is not None else "داده موجود نیست",
         "na": iv is None},
        {"label": "حجم کل نماد", "value": c.fmt_compact(vol) if vol is not None else "داده موجود نیست",
         "na": vol is None},
        {"label": "موقعیت باز کل", "value": c.fmt_compact(oi) if oi is not None else "داده موجود نیست",
         "na": oi is None},
        {"label": "سررسیدهای فعال", "value": c.fmt_int(n_exp), "na": False},
        {"label": "قراردادهای فعال", "value": c.fmt_int(len(snap)), "na": False},
    ]
    c.kpi_strip(items)


def _render_chain_table(chain: pd.DataFrame, side_cols: list[str], spot, band: float):
    """
    زنجیره حرفه‌ای: CALL | STRIKE | PUT با Strike مرکزی و مرز ATM.
    ستون‌های Call از راست به چپ آینه می‌شوند تا Strike در وسط بماند.
    """
    calls = chain[chain["option_type"] == "call"].set_index("strike", drop=False)
    puts = chain[chain["option_type"] == "put"].set_index("strike", drop=False)
    strikes = sorted(chain["strike"].dropna().unique())

    call_headers = [SIDE_COLUMNS[k][0] for k in reversed(side_cols)]
    put_headers = [SIDE_COLUMNS[k][0] for k in side_cols]
    n_side = len(side_cols)

    head = (
        f'<tr><th class="num" colspan="{n_side}" style="text-align:center;color:var(--text-2)">CALL</th>'
        f'<th class="num" style="text-align:center;color:var(--accent)">STRIKE</th>'
        f'<th class="num" colspan="{n_side}" style="text-align:center;color:var(--text-2)">PUT</th></tr>'
        "<tr>"
        + "".join(f'<th class="num">{c.esc(h)}</th>' for h in call_headers)
        + '<th class="num"></th>'
        + "".join(f'<th class="num">{c.esc(h)}</th>' for h in put_headers)
        + "</tr>"
    )

    body = []
    for k in strikes:
        call = calls.loc[[k]].iloc[0] if k in calls.index else None
        put = puts.loc[[k]].iloc[0] if k in puts.index else None

        # ATM از روی همان باند مرکزیِ market_brief — یک منبع حقیقت
        is_atm = bool(spot) and abs(k - spot) / spot <= band / 100.0
        style = (' style="background:rgba(56,189,248,.06);'
                 'box-shadow:inset 0 1px 0 var(--accent-border),inset 0 -1px 0 var(--accent-border)"'
                 if is_atm else "")

        def cells(row, keys):
            out = []
            for key in keys:
                if row is None:
                    out.append(f'<td class="num muted">{c.NA}</td>')
                    continue
                val = SIDE_COLUMNS[key][1](row.get(key))
                # وضعیت ITM با رنگ متن ملایم، نه پس‌زمینه پررنگ (بخش ۱۱)
                cls = "num"
                if key in ("bid", "ask", "close") and row.get("moneyness_bucket") == "ITM":
                    cls = "num pos"
                out.append(f'<td class="{cls}">{c.esc(val)}</td>')
            return "".join(out)

        strike_cell = (
            f'<td class="num" style="font-weight:600;color:var(--text-1);'
            f'border-inline:1px solid var(--border-strong)">{c.esc(c.fmt_int(k))}'
            + ('<div style="font-size:.62rem;color:var(--accent);font-family:var(--font-ui)">ATM</div>'
               if is_atm else "")
            + "</td>"
        )

        body.append(
            f"<tr{style}>"
            + cells(call, list(reversed(side_cols)))
            + strike_cell
            + cells(put, side_cols)
            + "</tr>"
        )

    st.markdown(
        f'<div class="table-wrap"><table class="atlas-table">'
        f"<thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    legend = "سطر پررنگ = نزدیک‌ترین قراردادها به قیمت دارایی پایه (ATM). "
    legend += "قیمت‌های سبز = قرارداد در سود (ITM). «—» یعنی قرارداد یا داده آن موجود نیست."
    c.helper(legend)


def _add_to_strategy(row, ctx):
    """انتقال قرارداد انتخاب‌شده به Strategy Lab با حفظ Context (بخش ۸۳)."""
    st.session_state.pending_strategy_legs = {
        "dataset": ctx.get("dataset"),
        "underlying": ctx.get("underlying"),
        "quote_date": ctx.get("quote_date"),
        "expiry": ctx.get("expiry"),
        "leg": {
            "option_type": row["option_type"],
            "strike": float(row["strike"]),
            "close": float(row["close"]) if pd.notna(row.get("close")) else 0.0,
            "symbol": row.get("symbol"),
        },
    }
    common.go_to("Strategy Lab")
