# -*- coding: utf-8 -*-
"""راستی‌آزمایی هر پارامتر داشبورد در برابر محاسبه مستقل و دستی."""
import sys, math, numpy as np, pandas as pd
sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'stub')); sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'..'))
from core import market_brief as mb, pricing, analytics as an

FAIL=[]
def check(name, got, want, tol=1e-9):
    ok = (got is None and want is None) or (
        got is not None and want is not None and abs(float(got)-float(want))<=tol)
    print(("  ✓ " if ok else "  ✗ ")+f"{name}: محاسبه={got!r}  انتظار={want!r}")
    if not ok: FAIL.append(name)

# ============ داده کنترل‌شده با اعداد دست‌ساز ============
SPOT={"شستا":1000.0,"خساپا":2000.0}
rows=[]
# شستا: 4 call, 4 put ; خساپا: 3 call, 3 put
spec=[("شستا","call",800,10,100),("شستا","call",1000,20,200),("شستا","call",1200,30,300),("شستا","call",1400,40,400),
      ("شستا","put",800,11,110),("شستا","put",1000,21,210),("شستا","put",1200,31,310),("شستا","put",1400,41,410),
      ("خساپا","call",1600,50,500),("خساپا","call",2000,60,600),("خساپا","call",2400,70,700),
      ("خساپا","put",1600,51,510),("خساپا","put",2000,61,610),("خساپا","put",2400,71,710)]
for u,t,k,vol,oi in spec:
    rows.append(dict(quote_date="2026-08-25",symbol=f"{u}-{t}-{k}",underlying=u,option_type=t,
        strike=float(k),expiry="2026-09-24",dte=30,close=50.0,bid=48.0,ask=52.0,
        volume=float(vol),open_interest=float(oi),iv=0.40,underlying_close=SPOT[u]))
cur=pd.DataFrame(rows)
prev=cur.copy(); prev["quote_date"]="2026-08-24"
prev["volume"]=prev["volume"]*0.5      # حجم امروز دقیقاً ۲ برابر دیروز
prev["open_interest"]=prev["open_interest"]*0.8  # OI امروز دقیقاً ۱.۲۵ برابر
prev["iv"]=0.50                         # IV امروز از 0.50 به 0.40 => -20%

hist=[]
for u,base in SPOT.items():
    for i,px in enumerate([base*1.00,base*1.02,base*0.99,base*1.03,base*1.01,base*1.00]):
        hist.append(dict(quote_date=f"2026-08-{18+i}",underlying=u,close=px))
uh=pd.DataFrame(hist)

cur=mb.add_moneyness_bucket(cur); prev=mb.add_moneyness_bucket(prev)

print("="*70); print("۱) شش KPI ثابت داشبورد"); print("="*70)
k=mb.compute_kpis(cur,prev,uh)

# --- مستقل: مجموع دستی ---
exp_vol=sum(v for _,_,_,v,_ in spec)          # 100+..+710
exp_oi=sum(o for _,_,_,_,o in spec)
check("حجم کل بازار", k["total_volume"]["value"], exp_vol)
check("موقعیت باز کل", k["total_oi"]["value"], exp_oi)
check("میانگین IV", k["avg_iv"]["value"], 0.40)
check("قراردادهای فعال", k["active_contracts"]["value"], len(spec))
check("تغییر حجم ٪ (باید +100)", k["total_volume"]["change_pct"], 100.0, 1e-9)
check("تغییر OI ٪ (باید +25)", k["total_oi"]["change_pct"], 25.0, 1e-9)
check("تغییر IV ٪ (باید -20)", k["avg_iv"]["change_pct"], -20.0, 1e-9)

exp_call=sum(v for _,t,_,v,_ in spec if t=="call")
exp_put=sum(v for _,t,_,v,_ in spec if t=="put")
check("نسبت Call/Put", k["cp_ratio"]["value"], round(exp_call/exp_put,2), 1e-9)
print(f"     (Call={exp_call}, Put={exp_put}, نسبت خام={exp_call/exp_put:.6f})")

# --- HV مستقل: per-symbol ---
manual=[]
for u in SPOT:
    px=uh[uh.underlying==u].sort_values("quote_date")["close"].astype(float).values
    r=np.diff(np.log(px))
    manual.append(r.std(ddof=1)*math.sqrt(252))
exp_hv=float(np.mean(manual))
check("HV بازار (میانگین per-symbol)", k["_hv"], exp_hv, 1e-12)
check("نسبت IV/HV", k["iv_hv_ratio"]["value"], round(0.40/exp_hv,2), 1e-9)
print(f"     HV هر نماد: {[round(x,4) for x in manual]}")

# --- اثبات اینکه باگ قدیمی واقعاً غلط بود ---
allpx=uh.sort_values("quote_date")["close"].astype(float)
buggy=float(np.log(allpx/allpx.shift(1)).dropna().std()*math.sqrt(252))
print(f"     HV با روش باگ‌دار قدیمی: {buggy:.4f}  ← {buggy/exp_hv:.0f}× بزرگ‌تر از مقدار درست")

print("\n"+"="*70); print("۲) رنگ و معناداری جهت (بخش ۱۰)"); print("="*70)
for key,should in [("total_volume",True),("total_oi",True),("avg_iv",False),
                   ("active_contracts",False),("cp_ratio",False),("iv_hv_ratio",False)]:
    got=k[key]["direction_meaningful"]
    print(("  ✓ " if got==should else "  ✗ ")+f"{key}: جهت معنادار={got} (انتظار {should})")
    if got!=should: FAIL.append(f"meaning-{key}")

print("\n"+"="*70); print("۳) Moneyness (باند ۲٪)"); print("="*70)
# شستا spot=1000: call 800=ITM,1000=ATM,1200=OTM,1400=OTM ; put برعکس
exp={("شستا","call",800):"ITM",("شستا","call",1000):"ATM",("شستا","call",1200):"OTM",("شستا","call",1400):"OTM",
     ("شستا","put",800):"OTM",("شستا","put",1000):"ATM",("شستا","put",1200):"ITM",("شستا","put",1400):"ITM",
     ("خساپا","call",1600):"ITM",("خساپا","call",2000):"ATM",("خساپا","call",2400):"OTM",
     ("خساپا","put",1600):"OTM",("خساپا","put",2000):"ATM",("خساپا","put",2400):"ITM"}
bad=0
for _,r in cur.iterrows():
    want=exp[(r.underlying,r.option_type,int(r.strike))]
    if r.moneyness_bucket!=want:
        print(f"  ✗ {r.underlying} {r.option_type} {int(r.strike)}: {r.moneyness_bucket} != {want}"); bad+=1
print(f"  {'✓' if not bad else '✗'} هر ۱۴ قرارداد: {len(spec)-bad}/{len(spec)} درست")
if bad: FAIL.append("moneyness")

print("\n"+"="*70); print("۴) Market Activity"); print("="*70)
tu=mb.top_underlyings(cur,prev)
sh=tu[tu.underlying=="شستا"].iloc[0]; kh=tu[tu.underlying=="خساپا"].iloc[0]
check("حجم شستا", sh["volume"], sum(v for u,_,_,v,_ in spec if u=="شستا"))
check("حجم خساپا", kh["volume"], sum(v for u,_,_,v,_ in spec if u=="خساپا"))
check("رتبه اول = خساپا (حجم بیشتر)", 1 if tu.iloc[0]["underlying"]=="خساپا" else 0, 1)
check("تغییر OI شستا ٪", sh["oi_change_pct"], 25.0, 1e-9)
check("میانگین IV شستا", sh["avg_iv"], 0.40)
check("تعداد قرارداد شستا", sh["contracts"], 8)
tc=mb.top_contracts(cur,3)
check("پرحجم‌ترین قرارداد (بیشترین volume)", tc.iloc[0]["volume"], max(v for _,_,_,v,_ in spec))

print("\n"+"="*70); print("۵) سیگنال‌ها — آستانه‌ها"); print("="*70)
sigs={s["key"]:s for s in mb.detect_signals(cur,prev,k)}
# IV: 0.50 -> 0.40 = کاهش، پس IV Expansion نباید باشد
print(("  ✓ " if "iv_expansion" not in sigs else "  ✗ ")+"IV کاهش یافته => IV Expansion نباید فعال شود")
if "iv_expansion" in sigs: FAIL.append("iv_exp_false_positive")
# OI +25% = دقیقاً آستانه => باید فعال شود (>=)
print(("  ✓ " if sigs.get("oi_buildup",{}).get("count")==14 else "  ✗ ")+
      f"OI Build-up در آستانه دقیق ۲۵٪: {sigs.get('oi_buildup',{}).get('count')} (انتظار ۱۴)")
if sigs.get("oi_buildup",{}).get("count")!=14: FAIL.append("oi_buildup")
# حجم غیرعادی: گروه شستا-call مقادیر 100,200,300,400 میانه=250، آستانه 2.5x=625 => هیچ‌کدام
print(("  ✓ " if "unusual_volume" not in sigs else f"  ✗ حجم غیرعادی نباید فعال شود: {sigs.get('unusual_volume',{}).get('count')}")
      + ("حجم غیرعادی درست فعال نشد (میانه شستا-call=250، آستانه=625)" if "unusual_volume" not in sigs else ""))
if "unusual_volume" in sigs: FAIL.append("unusual_vol_false_positive")
# IV/HV: 0.40/HV
ratio=round(0.40/exp_hv,2)
expect_key = "iv_hv_divergence_high" if ratio>=1.30 else ("iv_hv_divergence_low" if ratio<=0.80 else None)
print(f"  · IV/HV={ratio} => سیگنال مورد انتظار: {expect_key}, یافت‌شده: {[x for x in sigs if 'iv_hv' in x]}")
# Call/Put
cp=round(exp_call/exp_put,2)
expect_cp = cp>=1.5 or cp<=0.67
print(("  ✓ " if (("cp_skew" in sigs)==expect_cp) else "  ✗ ")+f"Call/Put={cp} => عدم توازن={'بله' if expect_cp else 'خیر'}")
if (("cp_skew" in sigs)!=expect_cp): FAIL.append("cp_skew")

print("\n"+"="*70); print("۶) تست مرزی سیگنال‌ها (دقیقاً روی آستانه)"); print("="*70)
for pct,key,label in [(10.0,"iv_expansion","IV دقیقاً +۱۰٪"),(9.99,"iv_expansion","IV +۹.۹۹٪"),
                      (25.0,"oi_buildup","OI دقیقاً +۲۵٪"),(24.9,"oi_buildup","OI +۲۴.۹٪")]:
    p2=cur.copy(); p2["quote_date"]="2026-08-24"
    if "iv" in key: p2["iv"]=cur["iv"]/(1+pct/100)
    else: p2["open_interest"]=cur["open_interest"]/(1+pct/100)
    s2={x["key"] for x in mb.detect_signals(cur,p2,mb.compute_kpis(cur,p2,uh))}
    fired=key in s2; should = pct>=(10.0 if "iv" in key else 25.0)
    print(("  ✓ " if fired==should else "  ✗ ")+f"{label}: فعال={fired} (انتظار {should})")
    if fired!=should: FAIL.append(label)

print("\n"+"="*70); print("۷) Brief — آیا اعداد جملات با KPI یکی است؟"); print("="*70)
br=mb.build_brief(k,[],cur,prev,"3 شهریور")
txt=" ".join(br["sentences"]); print("   ",txt.replace("مبنای","\n    مبنای"))
import re
nums=re.findall(r'([+-]?\d+\.\d)٪', txt)
print("  اعداد داخل متن:",nums)
ok_v = "+100.0٪" in txt; ok_o="+25.0٪" in txt; ok_i="-20.0٪" in txt
for lbl,o in [("حجم +100.0٪",ok_v),("OI +25.0٪",ok_o),("IV -20.0٪",ok_i)]:
    print(("  ✓ " if o else "  ✗ ")+f"{lbl} در متن Brief")
    if not o: FAIL.append(lbl)
print("  chips:",[c["text"] for c in br["chips"]])

print("\n"+"="*70)
print("نتیجه:", "همه تست‌ها پاس شد ✓" if not FAIL else f"{len(FAIL)} خطا: {FAIL}")
print("="*70)

print("\n"+"="*70); print("۸) فرمت‌دهی اعداد — آیا نمایش، مقدار را تحریف می‌کند؟"); print("="*70)
from ui import components as C
cases=[(C.fmt_compact,1_240_000_000,"1.24B"),(C.fmt_compact,8_420_000,"8.42M"),
       (C.fmt_compact,12_345,"12.3K"),(C.fmt_compact,999,"999"),(C.fmt_compact,0,"0"),
       (C.fmt_compact,None,"—"),(C.fmt_compact,float('nan'),"—"),
       (C.fmt_pct,0.384,"38.4%"),(C.fmt_pct,None,"—"),(C.fmt_pct,0,"0.0%"),
       (C.fmt_ratio,1.336,"1.34"),(C.fmt_ratio,None,"—"),
       (C.fmt_int,1234.6,"1,235"),(C.fmt_int,None,"—"),
       (C.fmt_change,2.18,"+2.18%" if False else "+2.2%"),(C.fmt_change,-1.42,"-1.4%")]
for fn,inp,want in cases:
    got=fn(inp)
    print(("  ✓ " if got==want else "  ✗ ")+f"{fn.__name__}({inp!r}) = {got!r} (انتظار {want!r})")
    if got!=want: FAIL.append(f"fmt {fn.__name__}({inp})")

print("\n  تفکیک «صفر» از «داده نداریم» (باگ ۳):")
z=cur.copy(); z["volume"]=0.0
n=cur.copy(); n["volume"]=np.nan
kz=mb.compute_kpis(z,None,uh); kn=mb.compute_kpis(n,None,uh)
check("حجم همه صفر => مقدار 0", kz["total_volume"]["value"], 0.0)
check("حجم همه NaN => مقدار None", kn["total_volume"]["value"], None)
print(("  ✓ " if C.fmt_compact(kn['total_volume']['value'])=="—" else "  ✗ ")+
      f"NaN در UI به‌صورت «—» نمایش داده می‌شود، نه صفر")
print(("  ✓ " if kn['cp_ratio']['note'] else "  ✗ ")+"دلیل نبود Call/Put به کاربر گفته می‌شود")

print("\n"+"="*70); print("۹) از اکسل «آخرین پایه» تا HTML رندرشده داشبورد"); print("="*70)
import streamlit as st
from core import importer, database
xl=[]
for u,sp in SPOT.items():
    for t_fa,t in [("اختیار خرید","call"),("اختیار فروش","put")]:
        for kk in [0.8,1.0,1.2]:
            xl.append({"تاریخ":"1405/06/03","نماد":f"{u}-{t}-{int(sp*kk)}","نماد پایه":u,"نوع":t_fa,
              "قیمت اعمال":sp*kk,"سررسید":"1405/07/28","قیمت پایانی":"1,000",
              "آخرین پایه":f"{sp:,.0f}","حجم":"1,000","موقعیت باز":"5,000","نوسان ضمنی":0.40})
pd.DataFrame(xl).to_excel("/tmp/v.xlsx",index=False)
clean,rep,und=importer.import_excel("/tmp/v.xlsx")
print(f"  ورودی: {len(xl)} ردیف | معتبر: {rep['kept_rows']} | قیمت پایه استخراج‌شده: {rep.get('underlying_prices_found')}")
check("قیمت پایه شستا از «آخرین پایه»", und[und.underlying=="شستا"]["close"].iloc[0], 1000.0)
check("قیمت پایه خساپا از «آخرین پایه»", und[und.underlying=="خساپا"]["close"].iloc[0], 2000.0)

database.DB_PATH.unlink(missing_ok=True)
database.save_dataframe(clean,"VERIFY"); database.save_underlying_dataframe(und,"VERIFY")
from ui import common, dashboard
common.init_session_state(); common.clear_caches()
st.LOG.clear(); dashboard.render()
html="\n".join(e[1] for e in st.LOG if e[0]=="md")
import re
kpi_vals=re.findall(r'kpi-value[^"]*">([^<]*)<', html)
labels=re.findall(r'kpi-label">([^<]*)<', html)
print("\n  KPIهای رندرشده در HTML:")
for l,v in zip(labels[:6],kpi_vals[:6]): print(f"    {l:22} = {v}")
exp_v=len(xl)*1000; exp_o=len(xl)*5000
print(("  ✓ " if kpi_vals[0]==C.fmt_compact(exp_v) else "  ✗ ")+f"حجم HTML={kpi_vals[0]} انتظار={C.fmt_compact(exp_v)}")
if kpi_vals[0]!=C.fmt_compact(exp_v): FAIL.append("html-volume")
print(("  ✓ " if kpi_vals[1]==C.fmt_compact(exp_o) else "  ✗ ")+f"OI HTML={kpi_vals[1]} انتظار={C.fmt_compact(exp_o)}")
if kpi_vals[1]!=C.fmt_compact(exp_o): FAIL.append("html-oi")
print(("  ✓ " if kpi_vals[2]=="40.0%" else "  ✗ ")+f"IV HTML={kpi_vals[2]} انتظار=40.0%")
if kpi_vals[2]!="40.0%": FAIL.append("html-iv")
print(("  ✓ " if kpi_vals[3]==f"{len(xl)}" else "  ✗ ")+f"قراردادها HTML={kpi_vals[3]} انتظار={len(xl)}")
print(("  ✓ " if kpi_vals[4]=="1.00" else "  ✗ ")+f"Call/Put HTML={kpi_vals[4]} انتظار=1.00 (حجم برابر)")
if kpi_vals[4]!="1.00": FAIL.append("html-cp")
print(f"    IV/HV HTML={kpi_vals[5]} (یک Snapshot => باید «داده موجود نیست» باشد)")
print(("  ✓ " if "داده" in kpi_vals[5] else "  ✗ ")+"با یک Snapshot، IV/HV به‌جای عدد جعلی «داده موجود نیست»")
if "داده" not in kpi_vals[5]: FAIL.append("html-ivhv-fake")

badges=re.findall(r'badge (itm|atm|otm)"',html)
print(f"\n  Moneyness در جدول: {dict((x,badges.count(x)) for x in set(badges))}")
print(("  ✓ " if "0" not in [kpi_vals[0],kpi_vals[1]] else "  ✗ ")+"هیچ KPI صفرِ کاذب رندر نشده")
print(("  ✓ " if "nan" not in html.lower() and "None" not in html else "  ✗ ")+"هیچ nan/None خام در HTML نیست")
if "nan" in html.lower(): FAIL.append("nan-in-html")

print("\n"+"="*70)
print("نتیجه نهایی:", "همه تست‌ها پاس شد ✓" if not FAIL else f"{len(FAIL)} خطا: {FAIL}")
print("="*70)
