
import os, json, csv, statistics, re, hashlib
from datetime import datetime
proj = r"C:\Projects\停车场充电桩优化方案"
raw = os.path.join(proj,"research","official_data_20261031","ev_behavior","raw")
der = os.path.join(proj,"research","official_data_20261031","ev_behavior","derived")
os.makedirs(der, exist_ok=True)
out = {}
# Barnet post-charge dwell / duration / energy stats
fmt = "%d/%m/%Y %H:%M"
def parse(s):
    s=s.strip()
    return datetime.strptime(s, fmt) if s else None
rows = list(csv.DictReader(open(os.path.join(raw,"barnet_cityev_2021Q2.csv"), encoding="utf-8-sig", errors="replace")))
conn_min=[]; chg_min=[]; dwell=[]; kwh=[]
for r in rows:
    try:
        pi=parse(r["Plug in Date and Time"]); pu=parse(r["Unplug Date and Time"])
        cs=parse(r["Charge start Date and Time"]); ce=parse(r["Charge end Date and Time"])
        if pi and pu and cs and ce:
            conn_min.append((pu-pi).total_seconds()/60)
            chg_min.append((ce-cs).total_seconds()/60)
            dwell.append((pu-ce).total_seconds()/60)
        kwh.append(float(r["Total kWh"]))
    except Exception:
        pass
def q(v,p): 
    v=sorted(v); import math; return v[min(len(v)-1, int(p*(len(v)-1)))]
out["barnet"] = {"sessions": len(rows), "parsed": len(conn_min),
  "conn_min_median": round(statistics.median(conn_min),1), "chg_min_median": round(statistics.median(chg_min),1),
  "post_charge_conn_min_median": round(statistics.median(dwell),1),
  "post_charge_conn_min_p90": round(q(dwell,0.9),1),
  "share_dwell_gt_30min": round(sum(1 for d in dwell if d>30)/len(dwell),4),
  "share_dwell_gt_60min": round(sum(1 for d in dwell if d>60)/len(dwell),4),
  "kwh_median": round(statistics.median(kwh),2), "kwh_mean": round(statistics.mean(kwh),2),
  "charging_min_total": round(sum(chg_min),1)}
print("BARNET", json.dumps(out["barnet"], ensure_ascii=False))
# IOT home charger share / SOC / battery text
t = open(os.path.join(proj,"research","official_data_20261031","ev_behavior","source_review","iot_report_hits.txt"), encoding="utf-8").read()
for kw in ["固定車位設置充電樁","圖4.6.43","使用公共充電樁前剩餘電量","圖4.6.25","電池容量"]:
    for m in list(re.finditer(kw, t))[:2]:
        print("IOT", kw, "|", t[max(0,m.start()-200):m.start()+260].replace("\n"," / ")[:420])
# static.xml kW contexts
s = open(os.path.join(proj,"research","collection","taipei_source_20261030","raw","static.xml"), encoding="utf-8", errors="replace").read()
for m in list(re.finditer(r".{60}kW.{60}", s))[:3]:
    print("STATIC kW ctx:", m.group(0).replace("\n"," "))
json.dump(out, open(os.path.join(der,"session_stats.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved session_stats.json")
