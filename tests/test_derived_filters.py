# -*- coding: utf-8 -*-
"""تست فیلترها و ستون‌های مشتق روی داده واقعی TSETMC."""
import os, sys, json, types
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.join(HERE,'..')
sys.path.insert(0,os.path.join(HERE,'stub')); sys.path.insert(0,ROOT)
SAMPLE=os.path.join(HERE,'fixtures','tsetmc_sample.json')
fake=types.ModuleType("requests"); fake.exceptions=types.SimpleNamespace(RequestException=Exception)
class R:
    def raise_for_status(self): pass
    def json(self): return json.load(open(SAMPLE,encoding='utf-8'))
fake.get=lambda *a,**k: R(); sys.modules['requests']=fake
import pandas as pd
from core import live_data, database, pricing, scanner
from core.data.snapshot import save_snapshot
from ui import option_chain

F=[]
def ok(l,c):
    print(("  ✓ " if c else "  ✗ ")+l)
    if not c: F.append(l)

database.DB_PATH.unlink(missing_ok=True)
o,u,_=live_data.fetch_option_chain(); save_snapshot(o,u,'T',replace_existing=False)
ch=pricing.enrich_full_dataset(database.load_data(dataset_name='T'),
                               database.load_underlying_data(dataset_name='T'), r=0.30)
print(f"زنجیره: {len(ch)} قرارداد\n")

print("="*66); print("۱) فیلترهای مشتق در دسترس‌اند"); print("="*66)
avail=scanner.available_filters(ch)
for k in ["oi_change","spread_pct","volume_oi_ratio","premium_yield_annual_pct",
          "breakeven_distance_pct","traded_today"]:
    ok(f"فیلتر {k} فعال است", avail.get(k))

print("\n"+"="*66); print("۲) فیلترها واقعاً اعمال می‌شوند"); print("="*66)
base=len(ch)
r1=scanner.apply_filters(ch,{"traded_today":True})
ok(f"فقط معامله‌شده: {len(r1)} از {base}", 0 < len(r1) < base)
ok("همه نتایج حجم مثبت دارند", (r1["volume"]>0).all())

r2=scanner.apply_filters(ch,{"spread_pct_max":15.0})
ok(f"اسپرد زیر ۱۵٪: {len(r2)} از {base}", len(r2)<base)
ok("همه نتایج اسپرد مجاز دارند", r2["spread_pct"].dropna().le(15.0).all())

r3=scanner.apply_filters(ch,{"oi_change_pct_min":5.0})
ok(f"رشد OI بالای ۵٪: {len(r3)}", len(r3)<base)
ok("همه نتایج رشد OI کافی دارند", r3["oi_change_pct"].dropna().ge(5.0).all())

r4=scanner.apply_filters(ch,{"yield_min":50.0})
ok(f"بازده سالانه بالای ۵۰٪: {len(r4)}", len(r4)<=base)
ok("همه نتایج بازده کافی دارند", r4["premium_yield_annual_pct"].dropna().ge(50.0).all())

print("\n  ترکیب فیلترها (سناریوی واقعی: فروش Call پوششی نقدشونده):")
combo=scanner.apply_filters(ch,{"traded_today":True,"spread_pct_max":20.0,
                                "yield_min":30.0,"option_type":["call"]})
print(f"    {len(combo)} قرارداد از {base}")
ok("ترکیب فیلترها نتیجه منطقی می‌دهد", len(combo)<=len(r1))

print("\n"+"="*66); print("۳) ستون‌های مشتق در زنجیره اختیار"); print("="*66)
for col in ["oi_change","oi_change_pct","spread_pct","bid_size","volume_oi_ratio",
            "premium_yield_annual_pct","breakeven","breakeven_distance_pct"]:
    ok(f"ستون {col} در گزینه‌های پیشرفته", col in option_chain.ADVANCED_SIDE_COLUMNS)
    ok(f"فرمت‌کننده {col} تعریف شده", col in option_chain.SIDE_COLUMNS)

print("\n  آزمون فرمت‌کننده‌ها با None و مقدار:")
bad=[]
for k,(label,fn) in option_chain.SIDE_COLUMNS.items():
    try:
        a=fn(None); b=fn(float('nan')); d=fn(123.456)
        if a!="—" or b!="—": bad.append(f"{k}: None->{a}, nan->{b}")
    except Exception as e:
        bad.append(f"{k}: {type(e).__name__}")
ok(f"همه فرمت‌کننده‌ها None/NaN را «—» می‌کنند ({bad})", not bad)

print("\n"+"="*66); print("۴) هیچ فیلتری داده را جعل نمی‌کند"); print("="*66)
ok("فیلتر روی ستون غایب صرفاً نادیده گرفته می‌شود",
   len(scanner.apply_filters(ch.drop(columns=["spread_pct"]),{"spread_pct_max":5.0}))==base)
ok("مقدار None از فیلتر عددی رد می‌شود، نه اینکه صفر فرض شود",
   scanner.apply_filters(ch,{"spread_pct_max":15.0})["spread_pct"].notna().all())
print("\n","پاس ✓" if not F else f"خطا: {F}")
sys.exit(1 if F else 0)
