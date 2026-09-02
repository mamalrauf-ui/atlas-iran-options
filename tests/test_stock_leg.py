import sys, numpy as np
sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'..'))
from core.strategy import Leg, payoff_curve, net_premium, max_profit_loss, breakevens, STRATEGY_TEMPLATES
F=[]
def chk(n,g,w,t=1e-9):
    ok=abs(float(g)-float(w))<=t; print(("  ✓ " if ok else "  ✗ ")+f"{n}: {float(g):+,.2f} (انتظار {w:+,.2f})")
    if not ok: F.append(n)

print("Covered Call: خرید سهم در ۱۰۰۰ + فروش Call با اعمال ۱۱۰۰ به قیمت ۴۰")
legs=[Leg("stock","buy",0,1000,1), Leg("call","sell",1100,40,1)]
# دستی: S<=1100 => (S-1000)+40 ; S>1100 => 100+40=140
for S,w in [(0,-960),(800,-160),(1000,40),(1100,140),(1500,140),(3000,140)]:
    chk(f"P&L در قیمت {S}", payoff_curve(legs,[S])[0], w)
m=max_profit_loss(legs,1000.0)
chk("حداکثر سود (100+40)", m["max_profit"], 140.0, 0.5)
print(("  ✓ " if not m["max_profit_is_unbounded"] else "  ✗ ")+"سود کراندار است (نه نامحدود)")
print(("  ✓ " if not m["max_loss_is_unbounded"] else "  ✗ ")+"زیان کراندار است ← باگ «نامحدود» رفع شد")
if m["max_loss_is_unbounded"]: F.append("cc-unbounded-loss")
be=breakevens(legs,1000.0); chk("سربه‌سر (1000-40=960)", be[0], 960.0, 2.0)

print("\nمقایسه با Naked Call (بدون سهم) — باید واقعاً نامحدود باشد")
naked=[Leg("call","sell",1100,40,1)]
mn=max_profit_loss(naked,1000.0)
print(("  ✓ " if mn["max_loss_is_unbounded"] else "  ✗ ")+f"Naked Call زیان نامحدود: {mn['max_loss_is_unbounded']}")
if not mn["max_loss_is_unbounded"]: F.append("naked")

print("\nCollar: سهم ۱۰۰۰ + Put 900 به ۲۰ + فروش Call 1100 به ۴۰")
col=[Leg("stock","buy",0,1000,1),Leg("put","buy",900,20,1),Leg("call","sell",1100,40,1)]
for S,w in [(500,-80),(900,-80),(1000,20),(1100,120),(2000,120)]:
    chk(f"P&L در {S}", payoff_curve(col,[S])[0], w)
mc=max_profit_loss(col,1000.0)
print(("  ✓ " if not mc["max_loss_is_unbounded"] and not mc["max_profit_is_unbounded"] else "  ✗ ")+
      f"Collar از دو طرف کراندار: سود={mc['max_profit']:.0f} زیان={mc['max_loss']:.0f}")

print("\nسازگاری عقب‌رو: استراتژی‌های بدون سهم تغییر نکرده‌اند")
bcs=[Leg("call","buy",1000,60),Leg("call","sell",1100,25)]
chk("Bull Call Spread حداکثر سود", max_profit_loss(bcs,1000.)["max_profit"], 65.0, 0.5)
chk("net_premium", net_premium(bcs), -35.0)

print("\nقالب‌های موجود:")
for k,v in STRATEGY_TEMPLATES.items():
    if v and any(l["option_type"]=="stock" for l in v): print("  · (شامل سهم)",k)
print("\n", "پاس ✓" if not F else f"خطا: {F}")
