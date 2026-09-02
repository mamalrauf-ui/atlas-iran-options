# -*- coding: utf-8 -*-
"""تست Provider تاریخچه بومی TSETMC (بدون وابستگی شخص‌ثالث)."""
import os, sys, json, types
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.join(HERE,'..')
sys.path.insert(0,os.path.join(HERE,'stub')); sys.path.insert(0,ROOT)
SAMPLE=os.path.join(HERE,'fixtures','tsetmc_sample.json')

# پاسخ شبیه‌سازی‌شده Endpoint تاریخچه، با ساختار واقعی آن
HISTORY={"closingPriceDaily":[
    {"dEven":20260825,"pClosing":1000,"pDrCotVal":1005,"priceFirst":990,"priceMax":1010,
     "priceMin":985,"priceYesterday":995,"qTotTran5J":50000,"qTotCap":5e10,"zTotTran":300},
    {"dEven":20260826,"pClosing":1020,"pDrCotVal":1018,"priceFirst":1000,"priceMax":1030,
     "priceMin":1000,"priceYesterday":1000,"qTotTran5J":60000,"qTotCap":6e10,"zTotTran":350},
    {"dEven":20260827,"pClosing":0,"pDrCotVal":0,"qTotTran5J":0,"zTotTran":0},   # روز بدون معامله
    {"dEven":20240101,"pClosing":500,"qTotTran5J":100,"zTotTran":5},             # پیش از سقف تاریخی
    {"dEven":"bad","pClosing":900},                                              # تاریخ خراب
]}

class Resp:
    def __init__(s,payload): s.payload=payload
    def raise_for_status(s): pass
    def json(s): return s.payload

fake=types.ModuleType("requests"); fake.exceptions=types.SimpleNamespace(RequestException=Exception)
def _get(url,*a,**k):
    if "GetClosingPriceDailyList" in url:
        if "FAIL" in url: raise Exception("timeout")
        if "EMPTY" in url: return Resp({"closingPriceDaily":[]})
        if "WEIRD" in url: return Resp({"unexpected":[]})
        return Resp(HISTORY)
    return Resp(json.load(open(SAMPLE,encoding='utf-8')))
fake.get=_get; sys.modules['requests']=fake

import pandas as pd
from core.data.providers.tsetmc_history import TSETMCHistoryProvider
from core.data.providers.base import ProviderError
from core import database, live_data
from core.data.snapshot import save_snapshot
from core.data import auto_history

F=[]
def ok(l,c):
    print(("  ✓ " if c else "  ✗ ")+l)
    if not c: F.append(l)

p=TSETMCHistoryProvider()
print("="*66); print("۱) تجزیه پاسخ تاریخچه"); print("="*66)
df=p.get_daily_history("12345")
print(df.to_string())
ok("۲ ردیف معتبر ماند (بدون‌معامله/خارج‌محدوده/خراب حذف شد)", len(df)==2)
ok("تاریخ به ISO تبدیل شد", list(df.quote_date)==["2026-08-25","2026-08-26"])
ok("قیمت پایانی درست", list(df.close)==[1000.0,1020.0])
ok("روز بدون معامله حذف شد (قیمت صفر ≠ قیمت واقعی)", "2026-08-27" not in list(df.quote_date))
ok("سقف تاریخی ۱۴۰۵/۰۱/۰۱ اعمال شد", "2024-01-01" not in list(df.quote_date))
ok("OI تاریخی None است نه صفر", df["open_interest"].isna().all())
ok("منبع برچسب خورده", (df["source"]=="TSETMC_HISTORY").all())
ok("مرتب بر اساس تاریخ", list(df.quote_date)==sorted(df.quote_date))

print("\n"+"="*66); print("۲) حالت‌های خطا — هیچ‌کدام نباید Crash کند"); print("="*66)
for code,label in [("FAIL","خطای شبکه"),("WEIRD","ساختار ناشناخته")]:
    try:
        p.get_daily_history(code); ok(f"{label} خطا داد",False)
    except ProviderError as e:
        ok(f"{label} -> ProviderError تمیز", True); print(f"      {str(e)[:80]}")
ok("پاسخ خالی -> DataFrame خالی", p.get_daily_history("EMPTY").empty)
try:
    p.get_daily_history(None); ok("InsCode خالی خطا داد",False)
except ProviderError: ok("InsCode خالی -> ProviderError", True)

print("\n"+"="*66); print("۳) همگام‌سازی روی دیتابیس واقعی"); print("="*66)
database.DB_PATH.unlink(missing_ok=True)
o,u,_=live_data.fetch_option_chain(); save_snapshot(o,u,'H',replace_existing=False)
und=sorted(database.load_data(dataset_name='H')['underlying'].dropna().unique())[0]
ok("شناسه ابزار دارایی پایه ذخیره شده", auto_history._underlying_ins_code('H',und) is not None)

r=auto_history.sync_underlying_history('H',und)
print(f"    نتیجه: {r}")
ok("تاریخچه دارایی پایه اضافه شد", r["status"]=="SUCCESS" and r["rows_added"]>0)
r2=auto_history.sync_underlying_history('H',und)
ok("اجرای دوم تکرار نمی‌سازد (افزایشی)", r2["status"]=="UP_TO_DATE" and r2["rows_added"]==0)

# قرارداد باید از همان دارایی پایه باشد، وگرنه پوشش مشترک بی‌معنا می‌شود
_d=database.load_data(dataset_name='H')
sym=sorted(_d[_d.underlying==und]['symbol'].dropna().unique())[0]
rc=auto_history.sync_contract_history('H',sym)
print(f"    قرارداد {sym}: {rc}")
ok("تاریخچه قرارداد اضافه شد", rc["status"] in ("SUCCESS","PARTIAL"))
hist=database.load_data(dataset_name='H')
hist=hist[hist.symbol==sym]
ok("چند تاریخ برای قرارداد موجود شد", hist.quote_date.nunique()>1)
ok("DTE هر روز نسبت به همان روز حساب شده (بدون Look-Ahead)",
   hist.sort_values('quote_date')['dte'].is_monotonic_decreasing)
ok("OI تاریخی خالی ماند نه صفر",
   hist[hist.source=="TSETMC_HISTORY"]["open_interest"].isna().all()
   if "source" in hist.columns else True)

cov=auto_history.history_coverage('H',und)
print(f"    پوشش: {cov['covered_days']} روز مشترک")
ok("پوشش تاریخچه افزایش یافت", cov["option_days"]>1 and cov["underlying_days"]>1)

print("\n"+"="*66); print("۴) bootstrap کامل"); print("="*66)
res=auto_history.bootstrap_history('H',underlyings=[und],include_contracts=False)
ok("bootstrap بدون خطا اجرا شد", res["status"] in ("SUCCESS","UP_TO_DATE"))
ok("هیچ نمادی شکست نخورد", not res["failed"])
print("\n","پاس ✓" if not F else f"خطا: {F}")
sys.exit(1 if F else 0)
