# -*- coding: utf-8 -*-
"""تست باگ‌ها و قابلیت‌های نسخه جدید — با داده واقعی TSETMC."""
import os, sys, json, types
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.join(HERE,'..')
sys.path.insert(0,os.path.join(HERE,'stub')); sys.path.insert(0,ROOT)
SAMPLE=os.path.join(HERE,'fixtures','tsetmc_sample.json')
fake=types.ModuleType("requests"); fake.exceptions=types.SimpleNamespace(RequestException=Exception)
class R:
    status_code=200
    def raise_for_status(self): pass
    def json(self): return json.load(open(SAMPLE,encoding='utf-8'))
fake.get=lambda *a,**k: R()
sys.modules['requests']=fake

import pandas as pd, numpy as np
from core import live_data, database, pricing, opportunity, derived, provenance
from core.data.snapshot import save_snapshot
from core.data import auto_history

F=[]
def ok(l,c):
    print(("  ✓ " if c else "  ✗ ")+l)
    if not c: F.append(l)

print("="*70); print("۱) باگ امتیاز ۱۰۰ — رتبه صدکی روی سری تباه"); print("="*70)
ok("سری همه‌یکسان -> None نه 100", opportunity._pct_rank(pd.Series([0.,0.,0.,0.]),0.0) is None)
ok("سری دو‌مقداری هم ناکافی است", opportunity._pct_rank(pd.Series([0.,0.,5.,5.]),5.) is None)
ok("سری متنوع کار می‌کند", opportunity._pct_rank(pd.Series([1.,2.,3.,4.]),3.) is not None)

zero=pd.DataFrame([dict(quote_date='2026-09-01',symbol=f's{i}',underlying='ت',option_type='call',
    strike=800.+100*i,expiry='2026-10-20',dte=49,close=50.,volume=0.,open_interest=0.,
    iv=np.nan,underlying_close=1000.) for i in range(6)])
ok("هیچ فرصتی از داده تماماً صفر ساخته نشد",
   opportunity.detect_contract_opportunities(zero).empty)

print("\n"+"="*70); print("۲) باگ نابودی تاریخچه هنگام ذخیره"); print("="*70)
database.DB_PATH.unlink(missing_ok=True)
def mk(qd,n=3):
    return pd.DataFrame([dict(quote_date=qd,symbol=f'x{i}',underlying='اهرم',option_type='call',
        strike=1000.+i,expiry='2026-10-20',close=50.,volume=10.,open_interest=100.) for i in range(n)])
save_snapshot(mk('2026-08-30'),None,'H',replace_existing=False)
save_snapshot(mk('2026-08-31'),None,'H',replace_existing=False)
n_before=database.load_data(dataset_name='H')['quote_date'].nunique()
database.delete_snapshot('H','2026-08-31')
save_snapshot(mk('2026-08-31',4),None,'H',replace_existing=False)
df=database.load_data(dataset_name='H')
ok(f"دو تاریخ حفظ شد ({df['quote_date'].nunique()})", df['quote_date'].nunique()==2)
ok("روز قدیمی دست‌نخورده", (df.quote_date=='2026-08-30').sum()==3)
ok("روز جایگزین‌شده تکرار نشد", (df.quote_date=='2026-08-31').sum()==4)

print("\n"+"="*70); print("۳) خط لوله کامل با داده واقعی TSETMC"); print("="*70)
database.DB_PATH.unlink(missing_ok=True)
opts,und,rep=live_data.fetch_option_chain()
ok(f"تجزیه {rep['kept_rows']} قرارداد از {rep['total_rows_from_api']} رکورد", rep['kept_rows']>0)
ok("هیچ ردیفی رد نشد", rep['skipped_rows']==0)
r=save_snapshot(opts,und,'LIVE',replace_existing=False)
ok("همه ردیف‌ها ذخیره شدند", r['records_saved']==r['records_received'])
back=database.load_data(dataset_name='LIVE')
for col,label in [('open_interest','موقعیت باز'),('volume','حجم'),('bid','تقاضا'),
                  ('bid_size','حجم تقاضا'),('previous_open_interest','OI دیروز'),
                  ('contract_size','اندازه قرارداد'),('turnover','ارزش معاملات')]:
    ok(f"{label} پس از رفت‌وبرگشت دیتابیس حفظ شد", col in back.columns and back[col].notna().any())
ok("اندازه قرارداد ثابت فرض نشده (۱۰۰۰ و ۱۳۷۱ هر دو هست)",
   back['contract_size'].nunique()>1)

print("\n"+"="*70); print("۴) معیارهای مشتق جدید"); print("="*70)
ch=pricing.enrich_full_dataset(back,database.load_underlying_data(dataset_name='LIVE'),r=0.30)
for col in derived.DERIVED_COLUMNS:
    ok(f"ستون {col} ساخته شد", col in ch.columns)
ok("تغییر OI برای اکثر قراردادها محاسبه شد", ch['oi_change'].notna().mean()>0.9)
ok("اسپرد فقط جایی که مظنه دوطرفه هست", ch['spread'].notna().sum()>0)
ok("traded_today تفکیک صفر از خالی", set(ch['traded_today'].dropna().unique())<={True,False})
neg=ch[ch['volume_oi_ratio'].notna()]
ok("نسبت حجم/OI هرگز منفی نیست", (neg['volume_oi_ratio']>=0).all())

print("\n"+"="*70); print("۵) تفکیک صفر از خالی (Missing ≠ Zero)"); print("="*70)
ok("حجم صفر واقعی وجود دارد", (ch['volume']==0).any())
ok("OI صفر واقعی وجود دارد", (ch['open_interest']==0).any())
ok("درصد تغییر OI روی پایه صفر None است نه بی‌نهایت",
   ch.loc[ch['previous_open_interest']==0,'oi_change_pct'].isna().all())
ok("هیچ inf در ستون‌های عددی نیست",
   not np.isinf(ch.select_dtypes('number').fillna(0).values).any())

print("\n"+"="*70); print("۶) فرصت‌ها با داده واقعی"); print("="*70)
o=opportunity.detect_contract_opportunities(ch)
ok(f"فرصت تولید شد ({len(o)})", not o.empty)
ok("هیچ فرصت غیرقابل‌معامله‌ای نیست",
   o.empty or not ((o.volume.fillna(0)==0)&(o.open_interest.fillna(0)==0)).any())
ok("همه امتیازها پایه کافی دارند",
   o.empty or (o['score_coverage_pct']>=opportunity.MIN_SCORE_COVERAGE_PCT).all())
ok("امتیازها متنوع‌اند", o.empty or o['score'].nunique()>10)
if not o.empty:
    print(f"    بازه امتیاز: {o['score'].min():.1f} تا {o['score'].max():.1f} | "
          f"پایه: {o['score_coverage_pct'].min():.0f}% تا {o['score_coverage_pct'].max():.0f}%")

print("\n"+"="*70); print("۷) شفافیت منبع پارامترها"); print("="*70)
ok("فیلدهای دریافتی ثبت شده", len(provenance.FETCHED_FIELDS)>15)
ok("فیلدهای محاسباتی ثبت شده", len(provenance.CALCULATED_FIELDS)>8)
ok("فیلدهای مشتق ثبت شده", len(provenance.DERIVED_FIELDS)>15)
api_fields=set()
for f in provenance.FETCHED_FIELDS:
    for part in (f['api_field'] or '').replace('/',' ').split():
        if part and part!='—': api_fields.add(part.strip())
real=set(json.load(open(SAMPLE,encoding='utf-8'))['instrumentOptMarketWatch'][0].keys())
unknown=[a for a in api_fields if a not in real and '_C' not in a and '_P' not in a and a!='get_history']
ok(f"همه فیلدهای API ادعاشده واقعاً وجود دارند (نامعلوم: {unknown})", not unknown)
cov=provenance.coverage_for(ch,'open_interest')
ok("پوشش صفر را از خالی جدا می‌کند", cov['zero']>0 and cov['present']==len(ch))

print("\n"+"="*70); print("۸) تاریخچه خودکار"); print("="*70)
c1=auto_history.history_coverage('LIVE')
ok("پوشش تاریخچه گزارش می‌شود", c1['option_days']>=1)
# تاریخچه از خود TSETMC می‌آید؛ در این تست شبکه شبیه‌سازی نشده پس همه
# نمادها شکست می‌خورند — نکته مهم این است که برنامه Crash نکند و خطا
# به‌صورت گزارش برگردد، نه استثنا.
res=auto_history.bootstrap_history('LIVE', include_contracts=False)
ok("عدم دسترسی به شبکه Crash نمی‌کند", isinstance(res, dict) and 'status' in res)
ok("هر نماد ناموفق جداگانه گزارش می‌شود",
   all(r.get('status') in ('SUCCESS','FAILED','NO_DATA','UP_TO_DATE') for r in res['underlyings']))
ok("هیچ پکیج شخص‌ثالثی لازم نیست",
   'fima' not in open(os.path.join(ROOT,'requirements.txt'),encoding='utf-8').read())

print("\n"+"="*70)
print("نتیجه:", "همه پاس ✓" if not F else f"{len(F)} خطا: {F}")
print("="*70)
sys.exit(1 if F else 0)
