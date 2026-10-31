
import os, json, collections, statistics
proj = r"C:\Projects\停车场充电桩优化方案"
root = os.path.join(proj,"research","collection","taipei_372_polling_20261030")
out = {}
# cohort static
cs = json.load(open(os.path.join(root,"data","static","cohort_static.json"), encoding="utf-8"))
sites = cs["sites"]
tc = [s["baseline_totalcar"] for s in sites]
cc = [s["baseline_connector_count"] for s in sites]
out["cohort"] = {"sites": len(sites), "totalcar_sum": sum(tc), "totalcar_median": statistics.median(tc),
                 "totalcar_min": min(tc), "totalcar_max": max(tc), "connector_sum": sum(cc),
                 "connector_median": statistics.median(cc), "connector_min": min(cc), "connector_max": max(cc),
                 "sites_with_connectors": sum(1 for x in cc if x>0)}
print("COHORT", json.dumps(out["cohort"], ensure_ascii=False))
# parking slots
p = os.path.join(root,"data","2026-10-31","parking_slots.jsonl")
first = open(p, encoding="utf-8").readline()
print("SLOTS first keys:", list(json.loads(first).keys()), "| sample:", first[:260])
n=0; lots=set(); tmin=None; tmax=None; per=collections.Counter()
for line in open(p, encoding="utf-8"):
    if not line.strip(): continue
    r=json.loads(line); n+=1; lots.add(r.get("parking_id") or r.get("id")); 
    ts=r.get("ts") or r.get("time") or r.get("timestamp") or r.get("update_time")
    if ts is not None:
        tmin = ts if tmin is None or ts<tmin else tmin
        tmax = ts if tmax is None or ts>tmax else tmax
print("SLOTS rows:", n, "lots:", len(lots), "tmin:", tmin, "tmax:", tmax)
# connector status
c = os.path.join(root,"data","2026-10-31","connector_status_long.jsonl")
firstc = open(c, encoding="utf-8").readline()
print("CONN first keys:", list(json.loads(firstc).keys()), "| sample:", firstc[:300])
n2=0; lots2=set(); conns=set(); statuses=collections.Counter(); t2min=None; t2max=None
for line in open(c, encoding="utf-8"):
    if not line.strip(): continue
    r=json.loads(line); n2+=1
    lots2.add(r.get("parking_id")); 
    conns.add(r.get("connector_id") or r.get("connector") or r.get("id"))
    statuses[r.get("status")] += 1
    ts=r.get("ts") or r.get("time") or r.get("timestamp")
    if ts is not None:
        t2min = ts if t2min is None or ts<t2min else t2min
        t2max = ts if t2max is None or ts>t2max else t2max
print("CONN rows:", n2, "lots:", len(lots2), "connector_ids:", len(conns), "statuses:", dict(statuses.most_common(10)), "tmin:", t2min, "tmax:", t2max)
out["polling"] = {"slots_rows": n, "slots_lots": len(lots), "slots_tmin": str(tmin), "slots_tmax": str(tmax),
  "conn_rows": n2, "conn_lots": len(lots2), "connector_ids": len(conns), "status_counts": dict(statuses), "conn_tmin": str(t2min), "conn_tmax": str(t2max)}
# commits sample
cd = os.path.join(root,"data","commits","2026-10-31")
if os.path.isdir(cd):
    f = sorted(os.listdir(cd))[0]
    d = json.load(open(os.path.join(cd,f), encoding="utf-8"))
    print("COMMIT file:", f, "| type:", type(d).__name__, "| keys:", (list(d.keys())[:15] if isinstance(d,dict) else len(d)))
    out["commit_sample"] = {"file": f, "keys": (list(d.keys())[:15] if isinstance(d,dict) else None)}
# raw xml sample
rd = os.path.join(root,"data","raw","2026-10-31")
print("RAW31:", os.listdir(rd)[:6])
for f in os.listdir(rd)[:2]:
    fp=os.path.join(rd,f)
    print("  ", f, os.path.getsize(fp), "head:", open(fp, encoding="utf-8", errors="replace").read(220).replace("\n"," "))
json.dump(out, open(os.path.join(proj,"research","official_data_20261031","traffic_resources","summary_stats.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED summary_stats.json")
