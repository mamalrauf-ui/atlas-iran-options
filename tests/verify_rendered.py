# -*- coding: utf-8 -*-
"""بررسی مقادیری که واقعاً در HTML صفحات رندر می‌شوند."""
import os, sys, json, types, re
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.join(HERE,'..')
sys.path.insert(0,os.path.join(HERE,'stub')); sys.path.insert(0,ROOT)
SAMPLE=os.path.join(HERE,'fixtures','tsetmc_sample.json')
fake=types.ModuleType("requests"); fake.exceptions=types.SimpleNamespace(RequestException=Exception)
class R:
    def raise_for_status(self): pass
    def json(self): return json.load(open(SAMPLE,encoding='utf-8'))
fake.get=lambda *a,**k: R(); sys.modules['requests']=fake
import streamlit as st
from core import database, live_data
from core.data.snapshot import save_snapshot
database.DB_PATH.unlink(missing_ok=True)
o,u,_=live_data.fetch_option_chain(); save_snapshot(o,u,'LIVE',replace_existing=False)
from ui import common
common.init_session_state(); common.clear_caches()
F=[]
def ok(l,c):
    print(("  ✓ " if c else "  ✗ ")+l)
    if not c: F.append(l)

def html_of(mod):
    st.LOG.clear(); mod.render()
    return "\n".join(e[1] for e in st.LOG if e[0]=="md")

from ui import dashboard, opportunities, data_center
print("="*70); print("داشبورد"); print("="*70)
h=html_of(dashboard)
vals=re.findall(r'kpi-value[^"]*">([^<]*)<',h); labs=re.findall(r'kpi-label">([^<]*)<',h)
for l,v in list(zip(labs,vals))[:12]: print(f"    {l:32} = {v}")
ok("هیچ nan/NaN/None خام رندر نشده", not re.search(r'>\s*(nan|NaN|None|inf)\s*<',h))
ok("۱۲ KPI رندر شد (۶ ثابت + ۶ جریان)", len([v for v in vals if v])>=12)
empties=[l for l,v in zip(labs,vals) if v.strip()=="" ]
ok(f"هیچ KPI بی‌مقدار نیست ({empties})", not empties)

print("\n"+"="*70); print("فرصت‌ها"); print("="*70)
st.session_state["opp_dataset"]="LIVE"
h2=html_of(opportunities)
ok("هیچ nan خام", not re.search(r'>\s*(nan|NaN|None)\s*<',h2))
ok("ستون پایه امتیاز رندر شد", "پایه امتیاز" in h2)
ok("ستون تغییر OI رندر شد", "تغییر OI" in h2)
scores=[float(x) for x in re.findall(r'font-weight:600">(\d+)</span>',h2)]
if scores:
    print(f"    امتیازهای رندرشده: {sorted(set(scores),reverse=True)[:8]}")
    ok("امتیازها همه ۱۰۰ نیستند", len(set(scores))>1)

print("\n"+"="*70); print("مرکز داده — جدول منبع پارامترها"); print("="*70)
st.session_state["dc_prov_ds"]="LIVE"
h3=html_of(data_center)
for probe in ["منبع هر پارامتر","دریافتی از TSETMC","محاسبه ATLAS","مشتق از محاسبات",
              "oP_C / oP_P","qTotTran5J_C / _P","yesterdayOP_C / _P","contractSize"]:
    ok(f"«{probe}» در صفحه هست", probe in h3)
ok("ورود اضطراری فقط آپشن‌گر", "آپشن‌گر" in h3)
ok("گزینه‌های حذف‌شده دیگر نیستند",
   "اطلاعات اختیار معامله" not in h3 and "فقط قیمت دارایی پایه" not in h3)
print("\n","پاس ✓" if not F else f"خطا: {F}")
sys.exit(1 if F else 0)
