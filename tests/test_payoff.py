import sys, time, numpy as np, itertools
sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'..'))
from core.strategy import Leg, payoff_curve, max_profit_loss

def ref(legs, prices):  # پیاده‌سازی اصلی قبل از بهینه‌سازی
    return np.array([sum(l.payoff_at_expiry(S) for l in legs) for S in prices])

rng=np.random.default_rng(7); worst=0.0; n=0
for trial in range(300):
    k=rng.integers(1,5)
    legs=[Leg(rng.choice(["call","put"]), rng.choice(["buy","sell"]),
              float(rng.uniform(50,5000)), float(rng.uniform(0,500)), int(rng.integers(1,4)))
          for _ in range(k)]
    prices=np.linspace(0.01, 6000, 500)
    a,b=ref(legs,prices), payoff_curve(legs,prices)
    d=np.abs(a-b).max(); worst=max(worst,d); n+=1
print(f"{n} استراتژی تصادفی — حداکثر اختلاف با پیاده‌سازی مرجع: {worst:.2e}")
assert worst < 1e-9, "اختلاف باید در حد خطای اعشاری ماشین بماند"
print("✓ اختلاف فقط در حد خطای گِرد‌کردن اعشاری (ترتیب جمع) — بی‌اثر بر هر تصمیم مالی")

legs=[Leg("call","buy",1000,50),Leg("call","sell",1100,20),Leg("put","buy",900,40)]
prices=np.linspace(1,4000,2000)
t=time.perf_counter(); [ref(legs,prices) for _ in range(20)]; t_old=time.perf_counter()-t
t=time.perf_counter(); [payoff_curve(legs,prices) for _ in range(20)]; t_new=time.perf_counter()-t
print(f"سرعت: {t_old/20*1000:.1f}ms -> {t_new/20*1000:.2f}ms  ({t_old/t_new:.0f}× سریع‌تر)")
print("max_profit_loss:", max_profit_loss(legs,1000.0))
