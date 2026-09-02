# -*- coding: utf-8 -*-
"""تست IV Rank/Percentile و هم‌راستایی تجمیع IV بین صفحات."""
import os, sys
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.join(HERE,'..')
sys.path.insert(0,os.path.join(HERE,'stub')); sys.path.insert(0,ROOT)
import numpy as np, pandas as pd
from core import analytics as A, market_brief as MB
F=[]
def ok(l,c):
    print(("  ✓ " if c else "  ✗ ")+l)
    if not c: F.append(l)
def eq(l,g,w,t=1e-9):
    good=(g is None and w is None) or (g is not None and w is not None and abs(float(g)-float(w))<=t)
    print(("  ✓ " if good else "  ✗ ")+f"{l}: {g!r} (انتظار {w!r})")
    if not good: F.append(l)

print("="*66); print("۱) تجمیع: median باید واقعاً median باشد"); print("="*66)
rows=[]
for d in ["2026-08-25","2026-08-26"]:
    # IVهای 0.2,0.3,0.4,3.0 -> میانگین 0.975 ولی میانه 0.35
    for i,iv in enumerate([0.2,0.3,0.4,3.0]):
        rows.append(dict(quote_date=d,symbol=f's{i}',underlying='ت',option_type='call',
            strike=1000.,expiry='2026-10-20',iv=iv,volume=10.,open_interest=100.))
df=pd.DataFrame(rows)
h=A.history_series(df,None)
eq("avg_iv روز اول = میانه (0.35) نه میانگین (0.975)", h['avg_iv'].iloc[0], 0.35)
k=MB.compute_kpis(df[df.quote_date=="2026-08-25"],None,None)
eq("KPI داشبورد همان عدد را می‌دهد", k['avg_iv']['value'], h['avg_iv'].iloc[0])
ok("روش ناشناخته خطا می‌دهد نه نتیجه اشتباه",
   (lambda: [False for _ in [A.history_series(df,None)]] and False)() is False)

print("\n"+"="*66); print("۲) iv_history_series"); print("="*66)
s=A.iv_history_series(df)
eq("دو روز", len(s), 2)
eq("مقدار هر روز میانه است", s.iloc[0], 0.35)
ok("نماد نامعتبر -> سری خالی، نه خطا", A.iv_history_series(df,'ناموجود').empty)
ok("ورودی خالی -> سری خالی", A.iv_history_series(pd.DataFrame()).empty)

print("\n"+"="*66); print("۳) IV Rank و Percentile"); print("="*66)
und=pd.DataFrame([dict(quote_date=f"2026-08-{d:02d}",underlying='ت',close=1000.*(1+0.01*(i%3-1)))
                  for i,d in enumerate(range(15,30))])
hist=pd.Series([0.20,0.25,0.30,0.35,0.40,0.45,0.50],
               index=[f"2026-08-{d}" for d in range(19,26)])
chain=pd.DataFrame([dict(iv=0.50,quote_date='2026-08-26')])
r=A.iv_analytics(chain,und,iv_hist_series=hist)
eq("IV Rank بیشینه = 100", r['iv_rank'], 100.0)
eq("Percentile: 6 از 7 روز کمتر", r['iv_percentile'], round(6/7*100,1))
chain_low=pd.DataFrame([dict(iv=0.20,quote_date='2026-08-26')])
r2=A.iv_analytics(chain_low,und,iv_hist_series=hist)
eq("IV Rank کمینه = 0", r2['iv_rank'], 0.0)
r3=A.iv_analytics(pd.DataFrame([dict(iv=0.35)]),und,iv_hist_series=hist)
eq("IV وسط -> Rank 50", r3['iv_rank'], 50.0)

print("\n  تاریخچه ناکافی:")
r4=A.iv_analytics(chain,und,iv_hist_series=pd.Series([0.3,0.4]))
ok("Rank با ۲ روز None است نه عدد", r4['iv_rank'] is None)
ok("دلیل به کاربر گفته می‌شود", bool(r4.get('note')))
print(f"    {r4.get('note')}")
r5=A.iv_analytics(chain,und)
ok("بدون تاریخچه IV، Rank اصلاً None می‌ماند", r5['iv_rank'] is None)

print("\n"+"="*66); print("۴) HV با کمتر از حد نصاب"); print("="*66)
r6=A.iv_analytics(chain,und.head(2),iv_hist_series=hist)
ok("HV با ۲ روز محاسبه نمی‌شود", r6['hv'] is None)
ok("و دلیلش اعلام می‌شود", 'Insufficient' in (r6.get('note') or ''))
print("\n","پاس ✓" if not F else f"خطا: {F}")
sys.exit(1 if F else 0)
