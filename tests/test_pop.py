import sys, numpy as np, time
sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'..'))
from core.strategy import Leg, probability_of_profit
def ref_pop(legs,S0,sigma,T,r=0.20,n=20000,seed=42):
    if T<=0 or sigma<=0: return None
    rng=np.random.default_rng(seed); Z=rng.standard_normal(n)
    ST=S0*np.exp((r-0.5*sigma**2)*T+sigma*np.sqrt(T)*Z)
    return float((np.array([sum(l.payoff_at_expiry(S) for l in legs) for S in ST])>0).mean())
rng=np.random.default_rng(3); worst=0
for _ in range(40):
    legs=[Leg(rng.choice(["call","put"]),rng.choice(["buy","sell"]),float(rng.uniform(500,2000)),
          float(rng.uniform(1,200)),int(rng.integers(1,3))) for _ in range(rng.integers(1,4))]
    a=ref_pop(legs,1000,0.5,0.08); b=probability_of_profit(legs,1000,0.5,0.08)
    worst=max(worst,abs(a-b))
print("۴۰ استراتژی — حداکثر اختلاف POP:",worst)
assert worst==0.0, "POP باید کاملاً یکسان بماند"
print("✓ POP بیت‌به‌بیت یکسان")
legs=[Leg("call","buy",1000,50),Leg("call","sell",1100,20)]
t=time.perf_counter(); [ref_pop(legs,1000,.5,.08) for _ in range(5)]; o=time.perf_counter()-t
t=time.perf_counter(); [probability_of_profit(legs,1000,.5,.08) for _ in range(5)]; n=time.perf_counter()-t
print(f"POP: {o/5*1000:.0f}ms -> {n/5*1000:.2f}ms ({o/n:.0f}× سریع‌تر)")
