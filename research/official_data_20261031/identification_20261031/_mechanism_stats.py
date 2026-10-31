
import os, json, collections
proj = r"C:\Projects\停车场充电桩优化方案"
root = os.path.join(proj,"research","collection","taipei_372_polling_20261030","data")
outdir = os.path.join(proj,"research","official_data_20261031","identification_20261031")
occ = {}; total_slots=set(); dups=0; invalid=0; sat=0; missing=0; nrows=0
for day in ["2026-10-30","2026-10-31"]:
    for line in open(os.path.join(root, day, "parking_slots.jsonl"), encoding="utf-8"):
        if not line.strip(): continue
        r=json.loads(line); nrows+=1
        total_slots.add(r["slot_start_utc"])
        if r.get("duplicate_batch"): dups+=1
        if r.get("data_missing"): missing+=1
        d=occ.setdefault(r["parking_id"], {})
        if r.get("duplicate_batch") and r["slot_start_utc"] in d: continue
        if not r.get("availablecar_valid") or r.get("availablecar_raw") is None or r.get("baseline_totalcar") is None:
            invalid+=1; continue
        av=r["availablecar_raw"]; tc=r["baseline_totalcar"]
        if av<=0: sat+=1
        d[r["slot_start_utc"]]=max(0, tc-av)
pos=neg=zero=0; totals=0; lots=0; per={}
for lot,d in occ.items():
    if len(d)<3: continue
    lots+=1; slots=sorted(d); delta=[d[slots[i]]-d[slots[i-1]] for i in range(1,len(slots))]
    totals+=len(delta)
    pd=sum(x for x in delta if x>0); nd=sum(-x for x in delta if x<0)
    pos+=pd; neg+=nd; zero+=sum(1 for x in delta if x==0); per[lot]={"pd":pd,"nd":nd,"slots":len(slots)}
print("SLOTS rows",nrows,"lots",lots,"global_slots",len(total_slots),"dup_rows",dups,"missing_flag_rows",missing,"invalid_avail_rows",invalid,"avail_eq0_rows",sat,
      "deltas",totals,"pos",pos,"neg",neg,"zero",zero)
# connector transitions only across adjacent observed slots
conn={}; crow=0; cdup=0
for day in ["2026-10-30","2026-10-31"]:
    for line in open(os.path.join(root, day, "connector_status_long.jsonl"), encoding="utf-8"):
        if not line.strip(): continue
        r=json.loads(line); crow+=1
        key=(r["parking_id"], r.get("spot_abrv")); d=conn.setdefault(key,{})
        if r.get("duplicate_batch") and r["slot_start_utc"] in d: cdup+=1; continue
        d[r["slot_start_utc"]]=r.get("status_raw")
slots_all=sorted(total_slots); sidx={s:i for i,s in enumerate(slots_all)}
starts=ends=starts_gap=ends_gap=chatter=session_lots=0; start_by_lot=collections.Counter()
for (lot,spot),d in conn.items():
    slots=sorted(d); last_start=None
    for i in range(1,len(slots)):
        a,b=d[slots[i-1]], d[slots[i]]; gap=sidx[slots[i]]-sidx[slots[i-1]]
        if a=="待機中" and b=="充電中":
            if gap==1: starts+=1; start_by_lot[lot]+=1
            else: starts_gap+=1
            if last_start is not None and (sidx[slots[i]]-last_start)<=5: chatter+=1
            last_start=sidx[slots[i]]
        elif a=="充電中" and b=="待機中":
            if gap==1: ends+=1
            else: ends_gap+=1
print("CONN rows",crow,"connectors",len(conn),"dup_skipped",cdup,"starts_adjacent",starts,"starts_across_gap",starts_gap,"ends_adjacent",ends,"ends_across_gap",ends_gap,"restart_within_25min",chatter)
ratio = starts/pos if pos else None
summary={"snapshot_utc":"2026-10-31T03:3xZ read (collector still appending)","parking_rows":nrows,"lots":lots,"global_slot_timestamps":len(total_slots),
 "parking_duplicate_batch_rows":dups,"parking_data_missing_flag_rows":missing,"parking_invalid_available_rows":invalid,
 "availablecar_eq0_rows":sat,"occupancy_deltas_total":totals,"sum_positive_delta":pos,"sum_negative_delta":neg,"zero_delta_count":zero,
 "connector_rows":crow,"connectors":len(conn),"connector_duplicate_skipped":cdup,
 "charging_start_transitions_adjacent":starts,"charging_starts_across_missing_gap":starts_gap,
 "charging_end_transitions_adjacent":ends,"charging_ends_across_missing_gap":ends_gap,
 "restart_within_25min":chatter,"ratio_start_transitions_over_positive_delta":ratio,
 "connector_slot_expected":1888*len(total_slots),"connector_slot_missing_estimate":1888*len(total_slots)-crow}
json.dump(summary, open(os.path.join(outdir,"mechanism_stats.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("Z", ratio)
print("saved mechanism_stats.json")
