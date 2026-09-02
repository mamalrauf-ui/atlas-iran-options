"""
ATLAS — Iran Options Intelligence
اجرا: streamlit run app.py

Router سطح‌بالا: دیزاین‌سیستم را اعمال، Sidebar را رندر و صفحه فعال را
صدا می‌زند. هیچ منطق تجاری اینجا نیست (بخش ۷۳ Master Prompt).
"""
import streamlit as st

from core import design
from ui import common
from ui import (dashboard, scanner, opportunities, option_chain,
                strategy_lab, backtest, analytics, data_center, settings)

st.set_page_config(
    page_title="ATLAS — Iran Options Intelligence",
    layout="wide",
    page_icon="◆",
    initial_sidebar_state="expanded",
)

design.apply()
common.init_session_state()

page = common.render_sidebar()

PAGE_RENDERERS = {
    "Dashboard": dashboard.render,
    "Scanner": scanner.render,
    "Opportunities": opportunities.render,
    "Option Chain": option_chain.render,
    "Strategy Lab": strategy_lab.render,
    "Backtest": backtest.render,
    "Analytics": analytics.render,
    "Data Center": data_center.render,
    "Settings": settings.render,
}

PAGE_RENDERERS[page]()
