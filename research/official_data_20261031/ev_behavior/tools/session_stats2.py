
import os, json, csv, statistics, collections
from datetime import datetime
proj = r"C:\Projects\停车场充电桩优化方案"
raw = os.path.join(proj,"research","official_data_20261031","ev_behavior","raw")
der = os.path.join(proj,"research","official_data_20261031","ev_behavior","derived")
os.makedirs(der, exist_ok=True)
# Robust Barnet parse
rows = list(csv.DictReader(open(os.path.join(raw,"barnet_cityev_2021Q2.csv"), encoding="utf-8-sig", errors="replace")))
FMTS = ["%d/%m/%Y %H:%M","%d/%m/%Y %H:%M:%S","%d/%m/%Y","%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M","%m/%d/%Y %H:%M"]
def parse(s):
    s=(s or "").strip()
    if not s: return None
    for f in FMTS:
        try: return datetime.strptime(s,f)
        except ValueError: pass
    return None
conn=[]; chg=[]; dwell=[]; kwh=[]; bad=0; cp_min=collections.Counter()
for r in rows:
    pi,pu,cs,ce = (parse(r.get(k,"")) for k in ["Plug in Date and Time","Unplug Date and Time","Charge start Date and Time","Charge end Date and Time"])
    try:
        if pi and pu and cs and ce:
            c=(pu-pi).total_seconds()/60; g=(ce-cs).total_seconds()/60; d=(pu-ce).total_seconds()/60
            if c>=0 and g>=0:
                conn.append(c); chg.append(g); dwell.append(d)
        kwh.append(float(r["Total kWh"]))
    except Exception:
        bad+=1
def q(v,p):
    v=sorted(v); return v[min(len(v)-1,int(p*(len(v)-1)))]
stats = {"rows": len(rows), "valid_times": len(conn), "bad_rows": bad,
 "conn_min_median": round(statistics.median(conn),1), "conn_min_p90": round(q(conn,0.9),1),
 "chg_min_median": round(statistics.median(chg),1), "chg_min_p90": round(q(chg,0.9),1),
 "post_charge_conn_min_median": round(statistics.median(dwell),1), "post_charge_conn_min_p90": round(q(dwell,0.9),1),
 "share_dwell_gt_30min": round(sum(1 for d in dwell if d>30)/len(dwell),4),
 "share_dwell_gt_60min": round(sum(1 for d in dwell if d>60)/len(dwell),4),
 "kwh_median": round(statistics.median(kwh),2), "kwh_mean": round(statistics.mean(kwh),2),
 "distinct_chargepoints": len(set(r["Chargepoint ID"] for r in rows)),
 "operators": dict(collections.Counter(r["Operator"] for r in rows).most_common(5))}
print("BARNET ROBUST", json.dumps(stats, ensure_ascii=False))
json.dump(stats, open(os.path.join(der,"barnet_session_stats.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
# Taipei slot rows both days + commits coverage
root = os.path.join(proj,"research","collection","taipei_372_polling_20261030")
out = {}
for day in ["2026-10-30","2026-10-31"]:
    p=os.path.join(root,"data",day,"parking_slots.jsonl")
    n=0; dup=0; tmin=None; tmax=None
    for line in open(p, encoding="utf-8"):
        r=json.loads(line); n+=1
        if r.get("duplicate_batch"): dup+=1
        ts=r.get("slot_start_utc")
        tmin = ts if tmin is None or ts<tmin else tmin
        tmax = ts if tmax is None or ts>tmax else tmax
    out[day]={"rows":n,"duplicate_batch":dup,"tmin":tmin,"tmax":tmax}
    print(day, out[day])
cd = os.path.join(root,"data","commits")
for day in os.listdir(cd):
    fs = sorted(os.listdir(os.path.join(cd,day)))
    if fs:
        print("commits", day, len(fs), "first", fs[0], "last", fs[-1])
        out.setdefault("commits",{})[day]={"files":len(fs),"first":fs[0],"last":fs[-1]}
json.dump(out, open(os.path.join(proj,"research","official_data_20261031","traffic_resources","summary_stats_extra2.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved")
