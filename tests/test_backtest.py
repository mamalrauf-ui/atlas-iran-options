# -*- coding: utf-8 -*-
import sys, numpy as np, pandas as pd
sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'..'))
from core import backtest as bt
F=[]
# بازار مصنوعی: قیمت پایه ثابت 1000، قیمت اختیارها به‌مرور کاهش (سود فروشنده)
rows=[]; und=[]
dates=[f"2026-0{m}-{d:02d}" for m in [6,7] for d in range(1,29,2)]
for i,d in enumerate(dates):
    und.append(dict(quote_date=d,underlying="ت",close=1000.0))
    for exp,dte0 in [("2026-08-20",None)]:
        dte=(pd.to_datetime("2026-08-20")-pd.to_datetime(d)).days
        if dte<0: continue
        for t in ["call","put"]:
            for k in [800,900,1000,1100,1200]:
                rows.append(dict(quote_date=d,symbol=f"{t}{k}",underlying="ت",option_type=t,
                    strike=float(k),expiry=exp,dte=dte,close=max(1.0,100.0-i*3),
                    bid=None,ask=None,volume=100.0,open_interest=500.0,iv=0.4))
opts=pd.DataFrame(rows); undf=pd.DataFrame(und)
legs=[{"option_type":"put","side":"sell","offset_pct":-0.10},
      {"option_type":"call","side":"sell","offset_pct":0.10}]

print("الف) بدون کارمزد")
t0,e0,s0=bt.run_backtest(opts,undf,legs,entry_dte=30,exit_dte=7,fee_pct=0.0)
print(f"  معاملات={s0['total_trades']} سود={s0['total_pnl']:+,.2f} کارمزد={s0['total_fees']:,.2f}")
print(f"  مبنای بازده: {s0['capital_basis_label']} = {s0['capital_basis']} | بازده={s0['total_return_pct']}%")

print("\nب) با کارمزد ۰.۵٪ هر سمت")
t1,e1,s1=bt.run_backtest(opts,undf,legs,entry_dte=30,exit_dte=7,fee_pct=0.5)
print(f"  معاملات={s1['total_trades']} سود={s1['total_pnl']:+,.2f} کارمزد={s1['total_fees']:,.2f}")
ok = s1['total_pnl'] < s0['total_pnl'] and s1['total_fees']>0
print(("  ✓ " if ok else "  ✗ ")+f"کارمزد سود را کاهش داد: {s0['total_pnl']:+.2f} -> {s1['total_pnl']:+.2f}")
if not ok: F.append("fee-effect")
diff=s0['total_pnl']-s1['total_pnl']
print(("  ✓ " if abs(diff-s1['total_fees'])<0.01 else "  ✗ ")+
      f"کاهش سود ({diff:.2f}) دقیقاً برابر کل کارمزد ({s1['total_fees']:.2f})")
if abs(diff-s1['total_fees'])>0.01: F.append("fee-accounting")

# راستی‌آزمایی دستی کارمزد یک معامله
tr=t1.iloc[0]; tr0=t0.iloc[0]
print(f"\n  معامله اول: ورود {tr['entry_date']} خروج {tr['exit_date']}")
print(f"    خالص ورود بدون کارمزد={tr0['entry_credit']:+.2f} | با کارمزد={tr['entry_credit']:+.2f}")
print(f"    کارمزد ثبت‌شده={tr['fees']:.2f} | سود بدون کارمزد={tr0['pnl']:+.2f} با کارمزد={tr['pnl']:+.2f}")
print(("  ✓ " if abs((tr0['pnl']-tr['pnl'])-tr['fees'])<0.01 else "  ✗ ")+"کارمزد هر معامله درست کسر شده")

print("\nج) سرمایه اولیه اعلام‌شده")
CAP=1_000_000
t2,e2,s2=bt.run_backtest(opts,undf,legs,entry_dte=30,exit_dte=7,fee_pct=0.5,initial_capital=CAP)
print(f"  مبنا: {s2['capital_basis_label']} = {s2['capital_basis']:,.0f}")
exp_ret=round(s2['total_pnl']/CAP*100,2)
print(("  ✓ " if s2['total_return_pct']==exp_ret else "  ✗ ")+
      f"بازده={s2['total_return_pct']}% (دستی: {s2['total_pnl']:.2f}/{CAP:,} = {exp_ret}%)")
if s2['total_return_pct']!=exp_ret: F.append("capital-basis")
print(("  ✓ " if s2['capital_basis']==CAP else "  ✗ ")+"مبنا = سرمایه کاربر، نه زیان تجمعی")
print(("  ✓ " if s2['total_pnl']==s1['total_pnl'] else "  ✗ ")+"سرمایه اولیه سود/زیان مطلق را تغییر نمی‌دهد")
if s2['total_pnl']!=s1['total_pnl']: F.append("capital-mutates-pnl")
print(f"  حداکثر افت: {s2['max_drawdown_pct']}% از سرمایه (بدون سرمایه: {s1['max_drawdown_pct']}%)")

print("\nد) کارمزد صفر == رفتار قبلی (سازگاری عقب‌رو)")
print(("  ✓ " if s0['total_fees']==0 else "  ✗ ")+f"fee_pct=0 => کارمزد صفر")

print("\n", "پاس ✓" if not F else f"خطا: {F}")
