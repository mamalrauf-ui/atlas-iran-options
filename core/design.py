"""
ATLAS Design System — توکن‌های مرکزی و CSS سراسری.

این ماژول تنها منبع حقیقت برای رنگ، فاصله، تایپوگرافی و شکل کامپوننت‌هاست.
هیچ فایل صفحه‌ای نباید رنگ یا اندازه را دوباره Hardcode کند؛ به‌جای آن از
TOKENS یا کلاس‌های CSS تعریف‌شده در همین فایل استفاده می‌کند.

مرجع: بخش‌های ۷ تا ۱۷ Master Prompt (Dark-first، Accent محدود، بدون Card اضافی،
بدون Glassmorphism/Neon/Gradient سنگین).
"""
import streamlit as st

# ---------------------------------------------------------------------------
# توکن‌ها (منبع واحد حقیقت)
# ---------------------------------------------------------------------------
TOKENS = {
    # سطوح
    "bg_app": "#0F1115",
    "bg_surface": "#16191F",
    "bg_elevated": "#1C2027",
    "border": "#272C34",
    "border_strong": "#333944",
    # متن
    "text_primary": "#F3F4F6",
    "text_secondary": "#A7AFBA",
    "text_muted": "#707985",
    # تعامل (فقط برای Interaction — نه تزئین)
    "accent": "#38BDF8",
    "accent_soft": "rgba(56, 189, 248, 0.12)",
    "accent_border": "rgba(56, 189, 248, 0.32)",
    # مالی (فقط معنایی)
    "positive": "#3FB950",
    "negative": "#E5484D",
    "warning": "#D29922",
    "neutral": "#8B949E",
    # فونت
    "font_ui": "'Vazirmatn', Tahoma, sans-serif",
    "font_num": "'Roboto Mono', 'Vazirmatn', monospace",
}

# نگاشت رنگ Moneyness — در کل محصول یکسان
MONEYNESS_COLORS = {
    "ITM": TOKENS["positive"],
    "ATM": TOKENS["neutral"],
    "OTM": TOKENS["negative"],
}

# مقیاس فاصله (بخش ۱۴)
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32, "3xl": 48}

# پالت نمودار — حداکثر چند رنگ، بدون رنگین‌کمان
CHART_COLORS = [TOKENS["accent"], "#A78BFA", "#F0883E", "#57B9A6", "#8B949E"]

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Vazirmatn, Tahoma, sans-serif", size=12, color=TOKENS["text_secondary"]),
    margin=dict(l=8, r=8, t=8, b=8),
    hoverlabel=dict(bgcolor=TOKENS["bg_elevated"], bordercolor=TOKENS["border"],
                    font=dict(family="Vazirmatn, Tahoma, sans-serif")),
    xaxis=dict(gridcolor=TOKENS["border"], zerolinecolor=TOKENS["border"], showgrid=False),
    yaxis=dict(gridcolor=TOKENS["border"], zerolinecolor=TOKENS["border"], gridwidth=1),
    showlegend=False,
    bargap=0.45,
)


def _css() -> str:
    t = TOKENS
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;700&family=Roboto+Mono:wght@400;500&display=swap');

:root {{
  --bg-app: {t['bg_app']};
  --bg-surface: {t['bg_surface']};
  --bg-elevated: {t['bg_elevated']};
  --border: {t['border']};
  --border-strong: {t['border_strong']};
  --text-1: {t['text_primary']};
  --text-2: {t['text_secondary']};
  --text-3: {t['text_muted']};
  --accent: {t['accent']};
  --accent-soft: {t['accent_soft']};
  --accent-border: {t['accent_border']};
  --pos: {t['positive']};
  --neg: {t['negative']};
  --warn: {t['warning']};
  --neu: {t['neutral']};
  --font-ui: {t['font_ui']};
  --font-num: {t['font_num']};
}}

/* ---------- پایه ---------- */
html, body, [class*="css"], .stMarkdown, p, span, div, label,
input, textarea, select, button, h1, h2, h3, h4, h5, h6 {{
  font-family: var(--font-ui) !important;
}}
[data-testid="stAppViewContainer"] {{ background-color: var(--bg-app); direction: rtl; }}
[data-testid="stHeader"] {{ background: transparent; }}
footer, #MainMenu {{ visibility: hidden; }}
.block-container {{ padding-top: 2.2rem !important; padding-bottom: 3rem !important; max-width: 1500px; }}

/* اعداد/نمادهای لاتین داخل متن فارسی به‌درستی و LTR رندر شوند (بخش ۱۳) */
p, span, label, .stMarkdown, [data-testid="stMetricValue"] {{ unicode-bidi: plaintext; }}
.num, .atlas-table td.num, .kpi-value {{
  font-family: var(--font-num) !important;
  direction: ltr; unicode-bidi: isolate; font-variant-numeric: tabular-nums;
}}

/* ---------- تایپوگرافی: نقش‌های محدود و سیستماتیک (بخش ۱۲) ---------- */
h1, h2, h3 {{ color: var(--text-1) !important; border: none !important; padding: 0 !important; }}
.page-title {{ font-size: 1.28rem; font-weight: 700; color: var(--text-1); margin: 0; line-height: 1.5; }}
.page-sub  {{ font-size: .82rem; color: var(--text-3); margin: 2px 0 0 0; }}
.section-title {{ font-size: .95rem; font-weight: 600; color: var(--text-1); margin: 0; }}
.section-note  {{ font-size: .76rem; color: var(--text-3); margin: 2px 0 0 0; }}
.helper {{ font-size: .74rem; color: var(--text-3); }}

/* ---------- هدر صفحه: فشرده، بدون Hero (بخش ۱۸) ---------- */
.page-head {{
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 24px; padding-bottom: 14px; margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
}}
.page-head .meta {{ text-align: left; direction: ltr; }}
.snap {{ font-size: .78rem; color: var(--text-2); font-family: var(--font-num); }}

/* ---------- وضعیت داده ---------- */
.status {{ display: inline-flex; align-items: center; gap: 6px; font-size: .76rem; margin-top: 4px; }}
.status .dot {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; }}
.status.ok   {{ color: var(--pos); }} .status.ok .dot   {{ background: var(--pos); }}
.status.warn {{ color: var(--warn); }} .status.warn .dot {{ background: var(--warn); }}
.status.err  {{ color: var(--neg); }} .status.err .dot  {{ background: var(--neg); }}

/* ---------- نوار KPI (بدون Card شناور — بخش ۱۵/۲۵) ---------- */
.kpi-strip {{
  display: grid; grid-template-columns: repeat(6, 1fr);
  border: 1px solid var(--border); border-radius: 10px;
  background: var(--bg-surface); overflow: hidden; margin-bottom: 26px;
}}
.kpi {{ padding: 14px 16px; border-left: 1px solid var(--border); }}
.kpi:last-child {{ border-left: none; }}
.kpi-label {{ font-size: .74rem; color: var(--text-3); margin-bottom: 6px; white-space: nowrap; }}
.kpi-value {{ font-size: 1.12rem; font-weight: 600; color: var(--text-1); line-height: 1.3; }}
.kpi-value.na {{ font-size: .84rem; font-weight: 400; color: var(--text-3); font-family: var(--font-ui) !important; }}
.kpi-change {{ font-size: .74rem; margin-top: 4px; font-family: var(--font-num); direction: ltr; }}
.kpi-change.pos {{ color: var(--pos); }}
.kpi-change.neg {{ color: var(--neg); }}
.kpi-change.neu {{ color: var(--text-3); }}
@media (max-width: 1200px) {{ .kpi-strip {{ grid-template-columns: repeat(3, 1fr); }}
  .kpi:nth-child(3n) {{ border-left: none; }} .kpi:nth-child(n+4) {{ border-top: 1px solid var(--border); }} }}
@media (max-width: 700px) {{ .kpi-strip {{ grid-template-columns: repeat(2, 1fr); }} }}

/* ---------- عنوان بخش + اکشن ---------- */
.sec-head {{ display: flex; align-items: baseline; justify-content: space-between;
  gap: 16px; margin: 0 0 12px 0; }}

/* ---------- Market Brief ---------- */
.brief {{
  border: 1px solid var(--border); border-right: 2px solid var(--accent);
  border-radius: 8px; background: var(--bg-surface); padding: 16px 18px;
}}
.brief p {{ margin: 0 0 10px 0; color: var(--text-1); font-size: .9rem; line-height: 2; }}
.brief p:last-child {{ margin-bottom: 0; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
.chip {{
  font-size: .74rem; padding: 3px 10px; border-radius: 5px;
  border: 1px solid var(--border-strong); color: var(--text-2); background: var(--bg-elevated);
}}
.chip.pos {{ color: var(--pos); border-color: rgba(63,185,80,.35); }}
.chip.neg {{ color: var(--neg); border-color: rgba(229,72,77,.35); }}
.chip.warn {{ color: var(--warn); border-color: rgba(210,153,34,.35); }}

/* ---------- Badge وضعیت (Moneyness / Signal) ---------- */
.badge {{
  display: inline-block; font-size: .7rem; font-weight: 600; padding: 2px 7px;
  border-radius: 4px; border: 1px solid; line-height: 1.6; direction: ltr;
}}
.badge.itm {{ color: var(--pos); border-color: rgba(63,185,80,.4);  background: rgba(63,185,80,.08); }}
.badge.atm {{ color: var(--neu); border-color: rgba(139,148,158,.4); background: rgba(139,148,158,.08); }}
.badge.otm {{ color: var(--neg); border-color: rgba(229,72,77,.4);  background: rgba(229,72,77,.08); }}
.badge.sig {{ color: var(--text-2); border-color: var(--border-strong); background: var(--bg-elevated); }}

/* ---------- جدول (بخش ۲۲: بدون Grid کامل، بدون Zebra قوی) ---------- */
.atlas-table {{ width: 100%; border-collapse: collapse; font-size: .82rem; }}
.atlas-table th {{
  text-align: right; font-weight: 500; font-size: .74rem; color: var(--text-3);
  padding: 8px 10px; border-bottom: 1px solid var(--border-strong); white-space: nowrap;
}}
.atlas-table td {{
  padding: 9px 10px; border-bottom: 1px solid var(--border);
  color: var(--text-1); white-space: nowrap;
}}
.atlas-table tr:hover td {{ background: var(--bg-surface); }}
.atlas-table td.num, .atlas-table th.num {{ text-align: left; }}
.atlas-table .rank {{ color: var(--text-3); font-family: var(--font-num); }}
.pos {{ color: var(--pos); }} .neg {{ color: var(--neg); }} .muted {{ color: var(--text-3); }}
.table-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg-surface); }}
.table-wrap .atlas-table td:first-child, .table-wrap .atlas-table th:first-child {{ padding-right: 14px; }}

/* DataFrame پیش‌فرض Streamlit هم هم‌سطح شود */
[data-testid="stDataFrame"] {{ border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}

/* ---------- سایدبار (بخش ۱۷) ---------- */
[data-testid="stSidebar"] {{
  background: #12151B; border-left: 1px solid var(--border); direction: rtl;
}}
[data-testid="stSidebar"] > div {{ padding-top: 1.1rem; }}
.sb-brand {{ padding: 0 4px 16px 4px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }}
.sb-brand .name {{ font-size: 1.02rem; font-weight: 700; letter-spacing: .08em; color: var(--text-1); direction: ltr; text-align: right; }}
.sb-brand .tag {{ font-size: .68rem; color: var(--text-3); direction: ltr; text-align: right; }}
.sb-group {{ font-size: .64rem; letter-spacing: .12em; color: var(--text-3);
  margin: 14px 6px 6px 6px; direction: ltr; text-align: right; }}
[data-testid="stSidebar"] .stButton > button {{
  width: 100%; text-align: right; justify-content: flex-start;
  background: transparent !important; border: none !important;
  color: var(--text-2) !important; font-weight: 500 !important; font-size: .86rem !important;
  padding: 7px 10px !important; border-radius: 7px !important; box-shadow: none !important;
  transition: background .12s ease, color .12s ease;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
  background: var(--bg-elevated) !important; color: var(--text-1) !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
  background: var(--accent-soft) !important; color: var(--accent) !important;
  font-weight: 600 !important; box-shadow: inset -2px 0 0 var(--accent) !important;
}}
[data-testid="stSidebar"] hr {{ margin: 14px 0; border-color: var(--border) !important; }}

/* ---------- دکمه‌ها: سه سطح (بخش ۲۰) ---------- */
.stButton > button {{
  border-radius: 7px !important; font-weight: 600 !important; font-size: .84rem !important;
  padding: .42rem 1rem !important; transition: all .12s ease; box-shadow: none !important;
}}
.block-container .stButton > button[kind="primary"] {{
  background: var(--accent) !important; color: #06202B !important; border: 1px solid var(--accent) !important;
}}
.block-container .stButton > button[kind="secondary"] {{
  background: transparent !important; color: var(--text-1) !important;
  border: 1px solid var(--border-strong) !important;
}}
.block-container .stButton > button[kind="secondary"]:hover {{
  border-color: var(--accent) !important; color: var(--accent) !important;
}}
.block-container .stButton > button[kind="tertiary"] {{
  background: transparent !important; color: var(--accent) !important;
  border: none !important; padding: .3rem .2rem !important; font-weight: 500 !important;
}}

/* ---------- ورودی‌ها و فیلترها (بخش ۲۱) ---------- */
[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input,
[data-testid="stDateInput"] input {{
  background: var(--bg-surface) !important; border-color: var(--border) !important;
  color: var(--text-1) !important; border-radius: 7px !important; font-size: .84rem !important;
}}
[data-testid="stWidgetLabel"] p {{ font-size: .76rem !important; color: var(--text-3) !important; }}
[data-baseweb="popover"] li {{ font-family: var(--font-ui) !important; font-size: .84rem !important; }}

/* Radio/Segmented به‌شکل Tab فشرده */
[data-testid="stRadio"] > div {{ gap: 4px; }}
[data-testid="stRadio"] label {{ font-size: .8rem !important; }}
[data-testid="stExpander"] {{ border: 1px solid var(--border) !important; border-radius: 8px !important;
  background: var(--bg-surface) !important; }}
[data-testid="stExpander"] summary p {{ font-size: .82rem !important; color: var(--text-2) !important; }}

/* ---------- حالت‌های خالی/خطا (بخش ۶۹/۷۰) ---------- */
.state-box {{
  border: 1px dashed var(--border-strong); border-radius: 8px; padding: 26px 22px;
  text-align: center; background: var(--bg-surface);
}}
.state-box .t {{ font-size: .9rem; font-weight: 600; color: var(--text-1); margin-bottom: 6px; }}
.state-box .d {{ font-size: .8rem; color: var(--text-3); line-height: 1.9; }}
.state-box.err {{ border-style: solid; border-color: rgba(229,72,77,.4); }}
.state-box.err .t {{ color: var(--neg); }}

/* ---------- سیگنال‌ها ---------- */
.signal {{
  border: 1px solid var(--border); border-radius: 8px; background: var(--bg-surface);
  padding: 12px 14px; height: 100%;
}}
.signal .n {{ font-size: .82rem; font-weight: 600; color: var(--text-1); }}
.signal .c {{ font-size: 1.24rem; font-weight: 600; font-family: var(--font-num);
  color: var(--accent); direction: ltr; margin: 6px 0 4px 0; }}
.signal .d {{ font-size: .73rem; color: var(--text-3); line-height: 1.8; min-height: 2.6em; }}

hr {{ border-color: var(--border) !important; margin: 26px 0 !important; }}
[data-testid="stVerticalBlockBorderWrapper"] > div {{ border-radius: 8px; }}
</style>
"""


def apply():
    """اعمال دیزاین‌سیستم — یک‌بار در app.py صدا زده می‌شود."""
    st.markdown(_css(), unsafe_allow_html=True)
