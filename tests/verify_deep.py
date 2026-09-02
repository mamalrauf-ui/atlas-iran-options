# -*- coding: utf-8 -*-
import sys, math, numpy as np, pandas as pd
sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'stub')); sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'..'))
from scipy.stats import norm
from core import pricing, opportunity, market_brief as mb, strategy as se
FAIL=[]
def chk(n,g,w,tol=1e-6):
    ok = g is not None and abs(float(g)-float(w))<=tol
    print(("  ✓ " if ok else "  ✗ ")+f"{n}: {g!r} vs {w!r}"); 
    if not ok: FAIL.append(n)

print("="*70); print("۱۰) Greeks در برابر فرمول تحلیلی Black-Scholes"); print("="*70)
S,K,T,r,sig=1000.0,1000.0,30/365,0.20,0.40
d1=(math.log(S/K)+(r+sig**2/2)*T)/(sig*math.sqrt(T)); d2=d1-sig*math.sqrt(T)
ref={"call_price":S*norm.cdf(d1)-K*math.exp(-r*T)*norm.cdf(d2),
     "put_price":K*math.exp(-r*T)*norm.cdf(-d2)-S*norm.cdf(-d1),
     "call_delta":norm.cdf(d1),"put_delta":norm.cdf(d1)-1,
     "gamma":norm.pdf(d1)/(S*sig*math.sqrt(T)),
     "vega":S*norm.pdf(d1)*math.sqrt(T)}
print("  مرجع مستقل (scipy):", {k:round(v,6) for k,v in ref.items()})
try:
    chk("قیمت Call", pricing.bs_price(S,K,T,r,sig,"call"), ref["call_price"],1e-6)
    chk("قیمت Put", pricing.bs_price(S,K,T,r,sig,"put"), ref["put_price"],1e-6)
    g=pricing.greeks(S,K,T,r,sig,"call")
    chk("Delta (Call)", g["delta"], ref["call_delta"],1e-6)
    chk("Gamma", g["gamma"], ref["gamma"],1e-8)
    print(f"  · Vega پروژه={g['vega']:.6f} | مرجع خام={ref['vega']:.6f} | نسبت={g['vega']/ref['vega']:.4f}")
    print("    (نسبت ۰.۰۱ یعنی Vega به‌ازای ۱٪ تغییر نوسان مقیاس شده — قرارداد رایج و درست)")
    gp=pricing.greeks(S,K,T,r,sig,"put")
    chk("Delta (Put)", gp["delta"], ref["put_delta"],1e-6)
    chk("Put-Call Parity در Delta", g["delta"]-gp["delta"], 1.0, 1e-9)
except AttributeError as e:
    print("  ! امضای تابع متفاوت:",e)
    print("  توابع موجود:",[x for x in dir(pricing) if not x.startswith('_')])

print("\n  IV معکوس: آیا از قیمت، همان sigma بازیابی می‌شود؟")
try:
    p=pricing.bs_price(S,K,T,r,0.37,"call")
    iv=pricing.implied_volatility(p,S,K,T,r,"call")
    chk("IV بازیابی‌شده", iv, 0.37, 1e-4)
except Exception as e: print("   ",e)

print("\n"+"="*70); print("۱۱) بازتوزیع وزن امتیاز فرصت (نباید مؤلفه غایب = صفر شود)"); print("="*70)
rows=[]
for i,(k,vol,oi,iv) in enumerate([(900,100,1000,0.30),(1000,500,5000,0.50),(1100,900,9000,0.70),(1200,200,2000,0.40)]):
    rows.append(dict(quote_date="2026-08-25",symbol=f"c{i}",underlying="ت",option_type="call",
      strike=float(k),expiry="2026-09-24",dte=30,close=50.0,bid=48.0,ask=52.0,
      volume=float(vol),open_interest=float(oi),iv=iv,underlying_close=1000.0))
full=pd.DataFrame(rows)
o_full=opportunity.detect_contract_opportunities(full,{k:1.0 for k in opportunity.DEFAULT_WEIGHTS})
noiv=full.copy(); noiv["iv"]=np.nan
o_noiv=opportunity.detect_contract_opportunities(noiv,{k:1.0 for k in opportunity.DEFAULT_WEIGHTS})
print(f"  با IV: {len(o_full)} فرصت، امتیازها={sorted(o_full['score'].dropna().round(1).tolist(),reverse=True)}")
print(f"  بدون IV: {len(o_noiv)} فرصت، امتیازها={sorted(o_noiv['score'].dropna().round(1).tolist(),reverse=True)}")
if len(o_noiv):
    mx=o_noiv["score"].dropna().max()
    print(("  ✓ " if mx>50 else "  ✗ ")+f"حذف IV امتیازها را به سمت صفر نمی‌کشد (max={mx:.1f})")
    if mx<=50: FAIL.append("weight-renorm")
print(("  ✓ " if o_full["score"].dropna().between(0,100).all() else "  ✗ ")+"همه امتیازها در بازه ۰..۱۰۰")

print("\n"+"="*70); print("۱۲) Payoff و سربه‌سر — در برابر ریاضیات دستی"); print("="*70)
# Bull Call Spread: خرید 1000 به 60، فروش 1100 به 25 => هزینه خالص 35
legs=[se.Leg("call","buy",1000,60),se.Leg("call","sell",1100,25)]
chk("خالص ورود (باید -35)", se.net_premium(legs), -35.0)
m=se.max_profit_loss(legs,1000.0)
chk("حداکثر سود (100-35=65)", m["max_profit"], 65.0, 0.5)
chk("حداکثر زیان (-35)", m["max_loss"], -35.0, 0.5)
be=se.breakevens(legs,1000.0)
chk("سربه‌سر (1000+35=1035)", be[0] if be else None, 1035.0, 1.0)
p=se.payoff_curve(legs,[900,1000,1035,1100,1200])
print(f"  Payoff در [900,1000,1035,1100,1200] = {[round(x,1) for x in p]}")
for px,want in [(900,-35),(1000,-35),(1035,0),(1100,65),(1200,65)]:
    got=se.payoff_curve(legs,[px])[0]
    print(("  ✓ " if abs(got-want)<1e-9 else "  ✗ ")+f"P&L در قیمت {px} = {got:+.1f} (انتظار {want:+d})")
    if abs(got-want)>1e-9: FAIL.append(f"payoff@{px}")

print("\n"+"="*70)
print("نتیجه:", "پاس ✓" if not FAIL else f"{len(FAIL)} خطا: {FAIL}")
print("="*70)
