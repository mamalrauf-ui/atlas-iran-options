import sys, re, pandas as pd, numpy as np
sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'stub')); sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'..'))
import streamlit as st
from core import pricing, market_brief
from ui import option_chain as oc, common, components as c
common.init_session_state()

# strikes 900..1100, spot=1000, band 2% -> ATM = [980,1020]
rows=[]
for k in [900,950,980,1000,1020,1050,1100]:
    for t in ["call","put"]:
        if k==1050 and t=="put": continue   # قرارداد ناموجود عمدی
        rows.append(dict(quote_date="2026-08-25",symbol=f"s{t}{k}",underlying="شستا",option_type=t,
        strike=float(k),expiry="2026-09-20",dte=30,close=50.0,bid=48.0,ask=52.0,volume=100,
        open_interest=500,iv=0.5,delta=0.5,gamma=0.01,theta=-1.0,vega=2.0,rho=0.1))
df=pd.DataFrame(rows)
uh=pd.DataFrame([dict(quote_date="2026-08-25",underlying="شستا",close=1000.0)])
ch=market_brief.add_moneyness_bucket(pricing.enrich_full_dataset(df,uh))

st.LOG.clear()
oc._render_chain_table(ch, ["bid","ask","volume","iv"], 1000.0, 2.0)
html=[t for e in st.LOG if e[0]=="md" for t in [e[1]]][0]

rowsh=re.findall(r'<tr.*?</tr>', html, re.S)
print("header rows + body rows:", len(rowsh))
atm=[r for r in rowsh if 'ATM</div>' in r]
print("ATM rows:", len(atm), "-> strikes:", re.findall(r'>([\d,]+)<div', "".join(atm)))
assert len(atm)==3, "۹۸۰، ۱۰۰۰ و ۱۰۲۰ در باند ۲٪ هستند"
assert not [r for r in rowsh if ("900" in r or "1,100" in r) and "ATM</div>" in r], "خارج از باند نباید ATM شود"

# ستون‌های Call باید آینه باشند: IV، حجم، عرضه، تقاضا | STRIKE | تقاضا، عرضه، حجم، IV
hdr=re.findall(r'<th class="num">([^<]*)</th>', rowsh[1])
print("header order:", hdr)
assert hdr[:4]==['IV','حجم','عرضه','تقاضا'], "ستون Call باید آینه شود"
assert hdr[5:]==['تقاضا','عرضه','حجم','IV']

# ردیف 1050 باید سمت Put همه — باشد
r1050=[r for r in rowsh if '1,050' in r][0]
tds=re.findall(r'<td[^>]*>(.*?)</td>', r1050, re.S)
print("strike 1050 cells:", [re.sub(r'<[^>]+>','',x).strip() for x in tds])
assert tds[-1].count('—')==1 and 'muted' in r1050, "Put غایب باید — باشد نه صفر"
# ITM رنگ: put با strike 1100 و spot 1000 -> ITM
r1100=[r for r in rowsh if '1,100' in r][0]
print("ITM coloring present:", 'num pos' in r1100)
print("\nCHAIN TABLE TESTS PASSED")
