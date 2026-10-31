
import os, json, hashlib, collections, statistics, re, csv
proj = r"C:\Projects\停车场充电桩优化方案"
root = os.path.join(proj,"research","collection","taipei_372_polling_20261030")
tr = os.path.join(proj,"research","official_data_20261031","traffic_resources")
out = {}
# A) connector status stats both days
for day in ["2026-10-30","2026-10-31"]:
    p = os.path.join(root,"data",day,"connector_status_long.jsonl")
    if not os.path.exists(p): continue
    st=collections.Counter(); conns=set(); lots=set(); n=0
    for line in open(p, encoding="utf-8"):
        r=json.loads(line); n+=1; st[r.get("status_raw")]+=1; conns.add((r["parking_id"], r.get("spot_abrv"))); lots.add(r["parking_id"])
    out["conn_"+day] = {"rows": n, "connectors": len(conns), "lots": len(lots), "status": dict(st)}
    print(day, "conn rows", n, "connectors", len(conns), "status", dict(st))
# B) per-lot observed connector count vs baseline
cs = json.load(open(os.path.join(root,"data","static","cohort_static.json"), encoding="utf-8"))
base = {s["parking_id"]: s for s in cs["sites"]}
obs = collections.Counter()
for line in open(os.path.join(root,"data","2026-10-31","connector_status_long.jsonl"), encoding="utf-8"):
    r=json.loads(line); obs[r["parking_id"]] += 1
# unique connectors per lot
uniq = collections.defaultdict(set)
for line in open(os.path.join(root,"data","2026-10-31","connector_status_long.jsonl"), encoding="utf-8"):
    r=json.loads(line); uniq[r["parking_id"]].add(r.get("spot_abrv"))
diff = [ (pid, len(uniq[pid]), base[pid]["baseline_connector_count"]) for pid in uniq if len(uniq[pid])!=base[pid]["baseline_connector_count"]]
out["connector_count_mismatch_lots"] = len(diff)
out["connector_count_mismatch_sample"] = diff[:8]
print("connector count mismatches:", len(diff), diff[:5])
# C) static xml keywords (official static API saved by prior collection)
sp = os.path.join(proj,"research","collection","taipei_source_20261030","raw","static.xml")
s = open(sp, encoding="utf-8", errors="replace").read()
for kw in ["功率","kW","充電樁","充電站","Charge","charge","插座","槍"]:
    print("STATICXML kw", kw, s.count(kw))
m = re.search(r"<.{0,40}充電.{0,400}", s)
print("STATICXML sample:", (m.group(0)[:500] if m else "none"))
# D) hashes of raw downloads
raw = os.path.join(proj,"research","official_data_20261031","ev_behavior","raw")
files = []
for f in sorted(os.listdir(raw)):
    fp=os.path.join(raw,f); h=hashlib.sha256(open(fp,"rb").read()).hexdigest()
    files.append({"file": f, "bytes": os.path.getsize(fp), "sha256": h})
out["raw_files"] = files
print("RAW files:", len(files), "total MB:", round(sum(f["bytes"] for f in files)/1048576,1))
# E) Barnet sessions
bp = os.path.join(raw,"barnet_cityev_2021Q2.csv")
with open(bp, encoding="utf-8-sig", errors="replace") as f:
    rd=list(csv.DictReader(f))
print("BARNET rows:", len(rd), "cols:", list(rd[0].keys()))
out["barnet"] = {"rows": len(rd), "cols": list(rd[0].keys())}
# F) EPA EV range
import zipfile, io
z = zipfile.ZipFile(os.path.join(raw,"epa_vehicles.csv.zip"))
with z.open("vehicles.csv") as f:
    rd = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
    rng=[]; ev=0
    for row in rd:
        ft=(row.get("fuelType1","") or "")
        if ft.lower().startswith("electric"):
            ev+=1
            try: rng.append(float(row["range"]))
            except: pass
rng=[r for r in rng if r>0]
out["epa"] = {"EV_rows": ev, "range_n": len(rng), "range_median": statistics.median(rng), "range_min": min(rng), "range_max": max(rng)}
print("EPA:", out["epa"])
# G) AFDC registration totals
tp = os.path.join(proj,"research","official_data_20261031","ev_behavior","source_review","afdc_registration_text.txt")
lines = open(tp, encoding="utf-8").read().splitlines()
vals = []
for i,l in enumerate(lines):
    if re.fullmatch(r"[A-Z][a-zA-Z ]+", l) and i+1 < len(lines) and re.fullmatch(r"[\d,]+", lines[i+1]):
        v=int(lines[i+1].replace(",",""))
        vals.append((l,v))
print("AFDC parsed states:", len(vals), "| top:", sorted(vals,key=lambda x:-x[1])[:5], "| CA:", [v for s,v in vals if s=="California"], "| sum:", sum(v for s,v in vals))
out["afdc_registration"] = {"states_parsed": len(vals), "sum": sum(v for s,v in vals), "top": sorted(vals,key=lambda x:-x[1])[:5]}
json.dump(out, open(os.path.join(tr,"summary_stats_extra.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED summary_stats_extra.json")
