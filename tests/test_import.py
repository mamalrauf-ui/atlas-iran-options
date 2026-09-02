import sys, pandas as pd, numpy as np
sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'stub')); sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'..'))
from core import importer, pricing, market_brief

rows=[]
for u,spot in [("شستا",1000),("خساپا",2000)]:
    for k in [0.9,0.95,1.0,1.05,1.1]:
        for t in ["اختیار خرید","اختیار فروش"]:
            rows.append({"تاریخ":"1405/06/05","نماد":f"ض{u}{int(k*100)}","نماد پایه":u,"نوع":t,
              "قیمت اعمال":spot*k,"سررسید":"1405/07/28","قیمت پایانی":"1,250",
              "آخرین پایه":f"{spot:,}",          # <<< ستون شما
              "حجم":"3,400","موقعیت باز":"12,500","نوسان ضمنی":0.45})
df=pd.DataFrame(rows); df.to_excel("/tmp/market.xlsx",index=False)
print("ستون‌های فایل:",list(df.columns))

m=importer.auto_map_columns(df.columns)
print("\nنگاشت خودکار:",m)
assert m.get("underlying_close")=="آخرین پایه", "«آخرین پایه» باید شناسایی شود"
print("✓ «آخرین پایه» شناسایی شد")

clean, rep, und = importer.import_excel("/tmp/market.xlsx")
print(f"\nردیف معتبر: {rep['kept_rows']} | حذف: {rep['dropped_rows']} | Call {rep['call_count']} / Put {rep['put_count']}")
print("قیمت‌های پایه استخراج‌شده:", rep.get("underlying_prices_found"))
print(und.to_string())
assert und is not None and len(und)==2
assert "underlying_close" not in clean.columns, "نباید در جدول اختیارها بماند"
print("هشدارها:", rep["warnings"])

# آیا Moneyness واقعاً کار می‌کند؟
en = pricing.enrich_full_dataset(clean, und)
en = market_brief.add_moneyness_bucket(en)
print("\nMoneyness:", en.moneyness_bucket.value_counts().to_dict())
assert en.moneyness_bucket.notna().all(), "همه ردیف‌ها باید وضعیت داشته باشند"
print("Greeks محاسبه شد:", en.delta.notna().sum(), "از", len(en))
print("✓ بدون فایل جداگانه، Moneyness و Greeks کامل شد")

# --- فایل بدون ستون پایه: باید هشدار صریح بدهد نه سکوت ---
df2=df.drop(columns=["آخرین پایه"]); df2.to_excel("/tmp/nospot.xlsx",index=False)
c2,r2,u2=importer.import_excel("/tmp/nospot.xlsx")
print("\nبدون ستون پایه -> underlying_df:",u2,"| هشدار:",[w for w in r2["warnings"] if "پایه" in w][:1])
assert u2 is None and any("آخرین پایه" in w for w in r2["warnings"])

# --- مقادیر ناسازگار برای یک نماد ---
df3=df.copy(); df3.loc[0,"آخرین پایه"]="9,999"; df3.to_excel("/tmp/incons.xlsx",index=False)
c3,r3,u3=importer.import_excel("/tmp/incons.xlsx")
print("\nناسازگاری:",[w for w in r3["warnings"] if "متفاوت" in w])
print("قیمت شستا (میانه، مقاوم به غلط تایپی):", u3[u3.underlying=="شستا"]["close"].iloc[0])
assert u3[u3.underlying=="شستا"]["close"].iloc[0]==1000.0
print("\nIMPORT TESTS PASSED")
