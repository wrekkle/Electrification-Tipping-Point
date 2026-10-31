
import os, json, collections
proj = r"C:\Projects\停车场充电桩优化方案"
root = os.path.join(proj,"research","collection","taipei_372_polling_20261030","data")
outdir = os.path.join(proj,"research","official_data_20261031","identification_20261031")
# build occupancy per lot
occ={}
for day in ["2026-10-30","2026-10-31"]:
    for line in open(os.path.join(root,day,"parking_slots.jsonl"),encoding="utf-8"):
        if not line.strip(): continue
        r=json.loads(line); d=occ.setdefault(r["parking_id"],{})
        if r.get("duplicate_batch") and r["slot_start_utc"] in d: continue
        if not r.get("availablecar_valid") or r.get("availablecar_raw") is None: continue
        d[r["slot_start_utc"]]=max(0,r["baseline_totalcar"]-r["availablecar_raw"])
# connector status per (lot, spot)
conn=collections.defaultdict(dict)
for day in ["2026-10-30","2026-10-31"]:
    for line in open(os.path.join(root,day,"connector_status_long.jsonl"),encoding="utf-8"):
        if not line.strip(): continue
        r=json.loads(line); d=conn[(r["parking_id"],r.get("spot_abrv"))]
        if r.get("duplicate_batch") and r["slot_start_utc"] in d: continue
        d[r["slot_start_utc"]]=r.get("status_raw")
# lot -> slots sorted; status change between adjacent slots for any connector
lot_conn=collections.defaultdict(list)
for (lot,spot),d in conn.items(): lot_conn[lot].append(d)
zero_slots=0; zero_with_change=0; zero_with_charge_start=0; pos_slots=0; pos_with_change=0
for lot,d in occ.items():
    if len(d)<3: continue
    slots=sorted(d)
    cds=lot_conn.get(lot,[])
    for i in range(1,len(slots)):
        a=slots[i-1]; b=slots[i]
        if b not in [s for s in []]: pass
        delta=d[b]-d[a]
        changed=False; started=False
        for cd in cds:
            if a in cd and b in cd:
                if cd[a]!=cd[b]: changed=True
                if cd[a]=="待機中" and cd[b]=="充電中": started=True
        if delta==0:
            zero_slots+=1
            if changed: zero_with_change+=1
            if started: zero_with_charge_start+=1
        elif delta>0:
            pos_slots+=1
            if changed: pos_with_change+=1
print(json.dumps({"zero_delta_slots":zero_slots,"zero_delta_with_any_connector_change":zero_with_change,
 "zero_delta_with_charging_start":zero_with_charge_start,"positive_delta_slots":pos_slots,
 "positive_delta_with_connector_change":pos_with_change}, ensure_ascii=False))
json.dump({"zero_delta_slots":zero_slots,"zero_delta_with_any_connector_change":zero_with_change,
 "zero_delta_with_charging_start":zero_with_charge_start,"positive_delta_slots":pos_slots,
 "positive_delta_with_connector_change":pos_with_change},
 open(os.path.join(outdir,"mechanism_crossstats.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
