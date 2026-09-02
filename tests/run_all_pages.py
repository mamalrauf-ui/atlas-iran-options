# -*- coding: utf-8 -*-
"""اجرای هر ۹ صفحه با Stub — بدون شبکه، بدون دیتابیس و با دیتابیس واقعی."""
import os, sys, json, types
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.join(HERE,'..')
sys.path.insert(0,os.path.join(HERE,'stub')); sys.path.insert(0,ROOT)
SAMPLE=os.path.join(HERE,'fixtures','tsetmc_sample.json')
fake=types.ModuleType("requests"); fake.exceptions=types.SimpleNamespace(RequestException=Exception)
class R:
    status_code=200
    def raise_for_status(self): pass
    def json(self): return json.load(open(SAMPLE,encoding='utf-8'))
    content=b""; text=""
fake.get=lambda *a,**k: R(); fake.Session=lambda: R()
sys.modules['requests']=fake
import streamlit as st
from core import database
PAGES=["dashboard","scanner","opportunities","option_chain","strategy_lab",
       "backtest","analytics","data_center","settings"]
def run(label):
    from ui import common
    common.init_session_state()
    fails=[]
    for name in PAGES:
        mod=__import__(f"ui.{name}",fromlist=[name])
        st.LOG.clear()
        try:
            mod.render(); print(f"  ✓ {name}")
        except SystemExit: print(f"  ✓ {name} (stop)")
        except Exception as e:
            fails.append(name); print(f"  ✗ {name}: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc(limit=3)
    return fails
print("=== بدون دیتابیس ===")
database.DB_PATH.unlink(missing_ok=True)
f1=run("empty")
print("\n=== با داده واقعی TSETMC ===")
from core import live_data
from core.data.snapshot import save_snapshot
o,u,_=live_data.fetch_option_chain(); save_snapshot(o,u,'LIVE',replace_existing=False)
from ui import common; common.clear_caches()
f2=run("live")
print("\nخطاها:",(f1+f2) or "هیچ")
sys.exit(1 if (f1+f2) else 0)
