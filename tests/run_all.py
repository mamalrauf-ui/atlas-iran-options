# -*- coding: utf-8 -*-
"""اجرای همه تست‌های ATLAS."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = [
    ("run_all_pages.py",    "اجرای هر ۹ صفحه (بدون داده و با داده واقعی)"),
    ("verify_rendered.py",  "مقادیر رندرشده در HTML صفحات"),
    ("test_fixes_v3.py",    "باگ‌های رفع‌شده + معیارهای مشتق + شفافیت منبع"),
    ("test_derived_filters.py", "فیلترها و ستون‌های مشتق روی داده واقعی"),
    ("test_iv_rank.py",     "IV Rank/Percentile و هم‌راستایی تجمیع IV"),
    ("test_history_provider.py", "تاریخچه بومی TSETMC و همگام‌سازی افزایشی"),
    ("verify_dashboard.py", "شش KPI و سیگنال‌ها در برابر محاسبه دستی"),
    ("verify_deep.py",      "Greeks در برابر Black-Scholes تحلیلی"),
    ("test_data_pipeline.py", "خط لوله داده"),
    ("test_live_data.py",   "تجزیه پاسخ TSETMC"),
    ("test_stock_leg.py",   "Covered Call و اندازه قرارداد"),
    ("test_backtest.py",    "کارمزد و مبنای بازده"),
    ("test_chain.py",       "چیدمان CALL | STRIKE | PUT"),
    ("test_import.py",      "ورود اکسل آپشن‌گر"),
    ("test_payoff.py",      "برداری‌سازی Payoff"),
    ("test_pop.py",         "برداری‌سازی احتمال سودآوری"),
]
BAD = ("✗", "خطا:", "Traceback", "AssertionError")
SKIP_MARK = "ModuleNotFoundError"

def main():
    failed, skipped = [], []
    for fname, desc in TESTS:
        path = os.path.join(HERE, fname)
        if not os.path.exists(path):
            continue
        p = subprocess.run([sys.executable, path], capture_output=True, text=True,
                           cwd=HERE, timeout=600)
        out = p.stdout + p.stderr
        if SKIP_MARK in out and "jdatetime" in out:
            skipped.append(fname)
            print(f"  –  {fname:24} {desc}  (وابستگی اختیاری نصب نیست)")
            continue
        bad = p.returncode != 0 or any(m in out for m in BAD)
        print(f"  {'✗' if bad else '✓'}  {fname:24} {desc}")
        if bad:
            failed.append(fname)
            for line in out.splitlines():
                if any(m in line for m in BAD):
                    print(f"       {line.strip()[:110]}")
    print()
    if failed:
        print(f"{len(failed)} تست شکست خورد: {', '.join(failed)}")
        return 1
    print(f"همه تست‌ها پاس شدند ✓" + (f" ({len(skipped)} مورد رد شد)" if skipped else ""))
    return 0

if __name__ == "__main__":
    sys.exit(main())
