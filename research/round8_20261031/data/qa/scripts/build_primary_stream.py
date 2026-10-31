
# -*- coding: utf-8 -*-
"""Streaming build: Melbourne 2014 parking bay arrivals/departures -> QA stats (full file) + bounded contract export.

Design: single pass over the 2.84 GB CSV inside the zip using csv.reader; all fields parsed to compact
numpy/array buffers. No pandas chunk concatenation. Scope of contract export is fixed a priori in EXPORT_RULE.
"""
import zipfile, io, csv, json, os, time
from array import array
import numpy as np
import pandas as pd

ROOT = r"research/round8_20261031/data"
ZIP = os.path.join(ROOT, "raw", "melbourne_parking_bay_arrivals_departures_2014_mq3i-cbxd.zip")
OUT_CSV = os.path.join(ROOT, "processed", "unified_events.csv")
OUT_SITE = os.path.join(ROOT, "processed", "site_index.csv")
OUT_STATS = os.path.join(ROOT, "qa", "stats.json")
OUT_DAY = os.path.join(ROOT, "qa", "day_counts.csv")
os.makedirs(os.path.join(ROOT, "processed"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "qa"), exist_ok=True)
DS = "melbourne_parking_bay_arrivals_departures_2014"
TZ = "Australia/Melbourne"
LOCAL_BASE_EPOCH = 1388534400  # 2014-01-01T00:00:00Z
MONTH_CUM = (0,31,59,90,120,151,181,212,243,273,304,334,365)
MONTH_DAYS = (31,28,31,30,31,30,31,31,30,31,30,31)
# precomputed local date strings for doy 1..365
DAY_STR = []
for m in range(1,13):
    for d in range(1, MONTH_DAYS[m-1]+1):
        DAY_STR.append("2014-%02d-%02d" % (m,d))
DAY_STR.insert(0, "")
# UTC offset rule (hours) for Australia/Melbourne 2014, refined around DST transition days
def offset_hours(doy, hh):
    if doy < 96:           # before 2014-04-06
        return 11
    if doy == 96:          # DST end, 03:00 AEDT -> 02:00 AEST
        return 11 if hh < 3 else 10
    if doy < 278:          # 2014-04-06 .. 2014-10-04
        return 10
    if doy == 278:         # DST start, 02:00 AEST -> 03:00 AEDT
        return 10 if hh < 2 else 11
    return 11
def parse_ts(s):
    """dd/mm/yyyy hh:mm:ss AM +0000 -> (local_naive_seconds_since_2014_local_midnight, doy, hour) or None"""
    try:
        if len(s) < 22:
            return None
        day = (ord(s[0])-48)*10 + ord(s[1])-48
        mon = (ord(s[3])-48)*10 + ord(s[4])-48
        hh  = (ord(s[11])-48)*10 + ord(s[12])-48
        mm  = (ord(s[14])-48)*10 + ord(s[15])-48
        ss  = (ord(s[17])-48)*10 + ord(s[18])-48
        ap = s[20]
        if ap == "P" and hh != 12: hh += 12
        elif ap == "A" and hh == 12: hh = 0
        if not (1 <= mon <= 12 and 1 <= day <= MONTH_DAYS[mon-1] and 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
            return None
        doy = MONTH_CUM[mon-1] + day
        return (doy-1)*86400 + hh*3600 + mm*60 + ss, doy, hh
    except Exception:
        return None
def to_int(s):
    """'1,234' -> 1234, '' -> -1"""
    if not s: return -1
    s = s.strip().replace(",", "")
    if not s: return -1
    try: return int(s)
    except Exception: return -1

z = zipfile.ZipFile(ZIP)
name = [n for n in z.namelist() if n.endswith(".csv")][0]
csv_size = z.getinfo(name).file_size
t0 = time.time()
tf = io.TextIOWrapper(z.open(name), encoding="utf-8-sig", newline="", errors="replace")
rdr = csv.reader(tf)
hdr = next(rdr)
ix = {k: hdr.index(k) for k in ["ParkingEventId","DeviceId","ArrivalTime","DepartureTime","DurationSeconds",
                                "StreetId","Area","SideCode","BayID","InViolation"]}
I_EV, I_DEV, I_ARR, I_DEP, I_DUR = ix["ParkingEventId"], ix["DeviceId"], ix["ArrivalTime"], ix["DepartureTime"], ix["DurationSeconds"]
I_ST, I_AR, I_SIDE, I_BAY, I_VIOL = ix["StreetId"], ix["Area"], ix["SideCode"], ix["BayID"], ix["InViolation"]

A = {k: array(t) for k, t in dict(ev="q", dev="i", bay="i", street="i", area="h", side="b",
                                  arr="q", dep="q", dur="i", viol="b", doy="h", hh="b").items()}
side_map = {}
n = 0
bad_arr = bad_dep = bad_dur = miss_all = 0
t_chunk = time.time()
for row in rdr:
    n += 1
    try:
        ev = to_int(row[I_EV])
        par = parse_ts(row[I_ARR])
        doy = hh = -1
        if par is None:
            bad_arr += 1
        else:
            doy = par[1]; hh = par[2]
        depp = parse_ts(row[I_DEP])
        if depp is None:
            bad_dep += 1
        dur = to_int(row[I_DUR])
        if dur == -1 and row[I_DUR].strip() not in ("",):
            bad_dur += 1
        side = row[I_SIDE].strip()
        sc = side_map.get(side)
        if sc is None:
            sc = len(side_map); side_map[side] = sc
        A["ev"].append(ev); A["dev"].append(to_int(row[I_DEV])); A["bay"].append(to_int(row[I_BAY]))
        A["street"].append(to_int(row[I_ST])); A["area"].append(to_int(row[I_AR])); A["side"].append(sc)
        if par is not None:
            off = offset_hours(doy, hh)
            A["arr"].append(LOCAL_BASE_EPOCH + par[0] - off*3600)
        else:
            A["arr"].append(-1)
        if depp is not None:
            off2 = offset_hours(depp[1], depp[2])
            A["dep"].append(LOCAL_BASE_EPOCH + depp[0] - off2*3600)
        else:
            A["dep"].append(-1)
        A["dur"].append(dur if dur >= 0 else -1)
        A["viol"].append(1 if row[I_VIOL].strip().lower().startswith("t") else 0)
        A["doy"].append(doy); A["hh"].append(hh)
    except Exception:
        miss_all += 1
        continue
    if n % 2_000_000 == 0:
        print("rows=%d elapsed=%.0fs" % (n, time.time()-t0), flush=True)
print("SCAN DONE rows=%d parse_fail_arr=%d parse_fail_dep=%d bad_dur=%d row_errors=%d elapsed=%.0fs" % (n, bad_arr, bad_dep, bad_dur, miss_all, time.time()-t0), flush=True)

# ---------------- numpy views
ev = np.frombuffer(A["ev"], dtype=np.int64); dev = np.frombuffer(A["dev"], dtype=np.int32)
bay = np.frombuffer(A["bay"], dtype=np.int32); street = np.frombuffer(A["street"], dtype=np.int32)
area = np.frombuffer(A["area"], dtype=np.int16); side = np.frombuffer(A["side"], dtype=np.int8)
arr = np.frombuffer(A["arr"], dtype=np.int64); dep = np.frombuffer(A["dep"], dtype=np.int64)
dur = np.frombuffer(A["dur"], dtype=np.int32); viol = np.frombuffer(A["viol"], dtype=np.int8)
doy = np.frombuffer(A["doy"], dtype=np.int16); hh = np.frombuffer(A["hh"], dtype=np.int8)
N = n
arr_ok = arr >= 0; dep_ok = dep >= 0; dur_ok = dur >= 0
I3600 = 3600
# site keys: street-side when StreetId known else Area-side
site_num = np.where(street >= 0, street.astype(np.int64)*100 + side.astype(np.int64),
                    -(area.astype(np.int64)*100 + side.astype(np.int64) + 1))
pref = np.where(street >= 0, "MELB-ST-", "MELB-AREA-")

# filters
neg = dur_ok & (dur < 0)
zero = dur_ok & (dur == 0)
long24 = dur_ok & (dur > 86400)
long7d = dur_ok & (dur > 604800)
long30d = dur_ok & (dur > 2592000)
mismatch = arr_ok & dep_ok & dur_ok & (np.abs((dep - arr) - dur) > 5)
u_ev, c_ev = np.unique(ev[ev >= 0], return_counts=True)
dup_ev_rows = int(c_ev[c_ev > 1].sum() - len(c_ev[c_ev > 1])) if len(c_ev) else 0
dup_ev_ids = int((c_ev > 1).sum())
dup_mask = np.zeros(N, dtype=bool)
if dup_ev_ids:
    dupvals = u_ev[c_ev > 1]
    dup_mask = np.isin(ev, dupvals)
cross_mid = arr_ok & dep_ok & ((dep // 86400) != (arr // 86400))
valid = arr_ok & dep_ok & dur_ok & (dur > 0) & (dur <= 86400) & (~dup_mask) & (bay >= 0) & (dep >= arr)
V = int(valid.sum())
print("valid=%d of %d" % (V, N), flush=True)

# ---------------- scale / coverage (full file)
day_counts = np.bincount(doy[valid & (doy > 0)], minlength=367)[1:366]
hour_hist = np.bincount(hh[valid], minlength=24)
wd = ((np.arange(1,366) - 1 + 2) % 7)  # 0=Mon; 2014-01-01 is Wednesday
wd_hist = np.zeros(7, dtype=np.int64)
for k in range(1,366): wd_hist[wd[k-1]] += int(day_counts[k-1])
# global complete days: all 24 hours present (all-city)
hour_day = np.zeros((365, 24), dtype=np.int32)
np.add.at(hour_day, (doy[valid]-1, hh[valid].astype(np.int64)), 1)
complete_global_days = int((hour_day > 0).all(axis=1).sum())
days_with_events = int((day_counts > 0).sum())
missing_days = [DAY_STR[k] for k in range(1,366) if day_counts[k-1] == 0]
# site x day presence and per-site aggregates
site_day_key = site_num[valid].astype(np.int64) * 1000 + doy[valid].astype(np.int64)
usd = np.unique(site_day_key)
site_day_counts = np.zeros(0)
sites_u, sd_counts = np.unique(usd // 1000, return_counts=True)
# capacity: distinct bay per site
sb = np.unique(site_num[valid].astype(np.int64) * 100000 + bay[valid].astype(np.int64))
site_cap = {}
su, capcnt = np.unique(sb // 100000, return_counts=True)
cap_map = dict(zip(su.tolist(), capcnt.tolist()))
# per-site stats
dwell_min_all = dur[valid] / 60.0
viol_rate = float(viol[valid].mean())
order_site = np.argsort(site_num[valid], kind="stable")
site_sorted = site_num[valid][order_site]
uniq_sites, starts, counts = np.unique(site_sorted, return_index=True, return_counts=True)
site_stats = []
for i, s in enumerate(uniq_sites):
    sl = slice(starts[i], starts[i]+counts[i])
    idx = order_site[sl]
    site_stats.append(dict(site_num=int(s), n_events=int(counts[i]),
        n_days=int(np.unique(doy[valid][idx]).size),
        first_day=DAY_STR[int(doy[valid][idx].min())],
        last_day=DAY_STR[int(doy[valid][idx].max())],
        mean_dwell_min=round(float(dwell_min_all[idx].mean()), 2),
        median_dwell_min=round(float(np.median(dwell_min_all[idx])), 2),
        viol_rate=round(float(viol[valid][idx].mean()), 4),
        cap=int(cap_map.get(int(s), 0))))
print("site stats done elapsed=%.0fs" % (time.time()-t0), flush=True)

# ---------------- overlap within bay (capacity conflict, bay capacity = 1)
ordb = np.lexsort((arr[valid], bay[valid]))
b_s = bay[valid][ordb]; a_s = arr[valid][ordb]; d_s = dep[valid][ordb]
same = np.zeros(len(ordb), dtype=bool); same[1:] = b_s[1:] == b_s[:-1]
pdep = np.full(len(ordb), -1, dtype=np.int64); pdep[1:] = d_s[:-1]; pdep[~same] = -1
overlap = same & (a_s < pdep)
overlap_cnt = int(overlap.sum()); ov_bays = int(np.unique(b_s[overlap]).size)
del ordb, b_s, a_s, d_s
print("overlap=%d bays=%d" % (overlap_cnt, ov_bays), flush=True)

# ---------------- window export (12 complete ISO weeks, all AEDT UTC+11)
W_START, W_END = 6, 89   # doy 6 = 2014-01-06 (Mon) ; doy 89 = 2014-03-30 (Sun)
win = valid & (doy >= W_START) & (doy <= W_END)
win_site = site_num
win_rows_total = int(win.sum())
# deterministic site rule to keep export <= 2,000,000 rows: capacity thresholds
rule = None
for thr in (3, 5, 8, 10, 15, 20, 30):
    keep_sites = np.array([s for s, c in cap_map.items() if c >= thr], dtype=np.int64)
    m = win & np.isin(site_num, keep_sites)
    cnt = int(m.sum())
    print("threshold cap>=%d -> rows=%d sites=%d" % (thr, cnt, len(keep_sites)), flush=True)
    if rule is None or cnt <= 2_000_000:
        rule = (thr, cnt, len(keep_sites), m)
        if cnt <= 2_000_000:
            break
thr, cnt, nsites, sel = rule
print("EXPORT RULE: window 2014-01-06..2014-03-30 (84 local days), sites capacity>=%d -> rows=%d sites=%d" % (thr, cnt, nsites), flush=True)
# build export
sel_idx = np.nonzero(sel)[0]
def site_id_str(s):
    if s >= 0:
        st = s // 100; sd = s % 100; return "MELB-ST-%d-%s" % (st, side_inv[sd])
    a = (-s - 1) // 100; sd = (-s - 1) % 100; return "MELB-AREA-%d-%s" % (a, side_inv[sd])
side_inv = {v: k for k, v in side_map.items()}
site_ids = np.array([site_id_str(int(site_num[i])) for i in sel_idx], dtype=object)
caps = np.array([cap_map[int(site_num[i])] for i in sel_idx], dtype=np.int64)
arrf = pd.to_datetime(arr[sel_idx], unit="s", utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")
depf = pd.to_datetime(dep[sel_idx], unit="s", utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")
dayl = np.array([DAY_STR[int(d)] for d in doy[sel_idx]], dtype=object)
out = pd.DataFrame({
    "site_id": site_ids,
    "event_id": ev[sel_idx].astype("int64"),
    "arrival_ts_utc": arrf,
    "departure_ts_utc": depf,
    "dwell_min": np.round(dur[sel_idx] / 60.0, 2),
    "site_capacity": caps,
    "day_local": dayl,
    "arrival_local_hour": hh[sel_idx].astype("int64"),
    "source_dataset": DS,
    "source_row": np.arange(1, N+1, dtype=np.int64)[sel_idx],
})
out.to_csv(OUT_CSV, index=False, encoding="utf-8")
print("wrote export", out.shape, "elapsed=%.0fs" % (time.time()-t0), flush=True)

# ---------------- site-day completeness inside export window
key2 = site_num[sel].astype(np.int64) * 100000 + bay[sel].astype(np.int64)
sd_pairs = np.unique(site_num[sel].astype(np.int64) * 1000 + doy[sel].astype(np.int64))
alive_counts = np.unique(sd_pairs, return_counts=True)[1]
sd_site = np.unique(sd_pairs // 1000, return_counts=True)[1]
sd_caps = np.array([cap_map.get(int(s), 1) for s in np.unique(sd_pairs // 1000)])
frac = alive_counts / np.maximum(sd_caps.repeat(sd_site), 1)
COMPLETE_THR = 0.8
sd_complete = int((frac >= COMPLETE_THR).sum())
sites_complete = {}
for (s, f) in zip(np.repeat(np.unique(sd_pairs // 1000), sd_site), frac):
    sites_complete[int(s)] = sites_complete.get(int(s), 0) + (1 if f >= COMPLETE_THR else 0)
sites_ge4 = int(sum(1 for v in sites_complete.values() if v >= 4))
sites_ge12 = int(sum(1 for v in sites_complete.values() if v >= 12))

# ---------------- site index csv (full year, all sites with >=1 valid event)
site_rows = []
for st in site_stats:
    s = st["site_num"]
    site_rows.append({
        "site_id": site_id_str(s), "capacity": st["cap"], "n_events": st["n_events"],
        "n_days": st["n_days"], "first_day": st["first_day"], "last_day": st["last_day"],
        "mean_dwell_min": st["mean_dwell_min"], "median_dwell_min": st["median_dwell_min"],
        "in_violation_rate": st["viol_rate"],
        "in_export_window": bool(np.isin(np.int64(s), np.unique(site_num[sel]))),
        "export_window_events": int(np.sum(sel & (site_num == s))),
    })
si = pd.DataFrame(site_rows).sort_values("n_events", ascending=False)
si.to_csv(OUT_SITE, index=False, encoding="utf-8")

pd.DataFrame({"day_local": [DAY_STR[k] for k in range(1,366)], "n_valid_events": day_counts}).to_csv(OUT_DAY, index=False)

# ---------------- stats.json
import hashlib
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()
zip_sha = sha256_file(ZIP)
stats = {
 "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
 "source": {"dataset": DS, "portal_landing": "https://data.melbourne.vic.gov.au/explore/dataset/parking-bay-arrivals-and-departures-2014/",
            "download_url": "https://opendatasoft-s3.s3.amazonaws.com/downloads/archive/mq3i-cbxd.zip",
            "license": "CC BY 4.0 (City of Melbourne); attribution required",
            "zip_file": os.path.basename(ZIP), "zip_bytes": os.path.getsize(ZIP), "zip_sha256": zip_sha,
            "csv_entry": name, "csv_uncompressed_bytes": csv_size,
            "download_command": "Invoke-WebRequest -Uri <download_url> -OutFile research/round8_20261031/data/raw/melbourne_parking_bay_arrivals_departures_2014_mq3i-cbxd.zip",
            "portal_metadata_checked": "2026-10-31 (Opendatasoft catalog API v2.1)"},
 "scan": {"rows_scanned": int(N), "csv_bytes_scanned": csv_size, "wall_seconds": round(time.time()-t0, 1),
          "row_parse_errors": int(miss_all), "arrival_parse_failures": int(bad_arr),
          "departure_missing_or_unparsable": int(bad_dep), "duration_unparsable": int(bad_dur)},
 "fields_present": list(hdr),
 "timezone": {
   "raw_offset_suffix": "+0000 constant in every ArrivalTime/DepartureTime string (offset field counted during pass 1 of earlier diagnostic: only '+0000' present)",
   "decision": "offset suffix stripped; stored values treated as Australia/Melbourne LOCAL wall clock, converted to UTC with zoneinfo-equivalent 2014 rules",
   "evidence": ["arrival local-hour histogram peaks 07:00-18:00 and troughs 01:00-05:00 (see arrivals_by_local_hour), matching published meter restriction hours 7:30-19:30; if values were true UTC the peak would fall at local 18:00-05:00, which is inconsistent with paid CBD parking"],
   "offset_rule_2014": "AEDT UTC+11 until 2014-04-06 03:00 local; AEST UTC+10 2014-04-06 03:00 - 2014-10-05 02:00; AEDT UTC+11 afterwards (transition days handled hour-wise)",
   "dst_transition_days_2014": {"end": "2014-04-06 (02:00-02:59 repeated, fold=earlier)", "start": "2014-10-05 (02:00-02:59 does not exist)"},
   "records_on_transition_days": {"2014-04-06": int(day_counts[95]), "2014-10-05": int(day_counts[277])},
   "utc_min": pd.to_datetime(int(arr[valid].min()), unit="s", utc=True).strftime("%Y-%m-%dT%H:%M:%SZ"),
   "utc_max": pd.to_datetime(int(dep[valid].max()), unit="s", utc=True).strftime("%Y-%m-%dT%H:%M:%SZ"),
   "local_day_span": [DAY_STR[int(doy[valid].min())], DAY_STR[int(doy[valid].max())]],
 },
 "filters_and_integrity": {
   "valid_events": V, "valid_share": round(V/N, 4),
   "excluded": {"departure_missing_or_unparsable": int(bad_dep), "arrival_unparsable": int(bad_arr),
                "duration_unparsable": int(bad_dur), "duration_zero": int(zero.sum()),
                "duration_gt_24h": int(long24.sum()), "duration_gt_7d": int(long7d.sum()),
                "duration_gt_30d": int(long30d.sum()), "timestamp_duration_mismatch_gt_5s": int(mismatch.sum()),
                "duplicate_event_id_rows": int(dup_mask.sum()), "missing_bay_id": int((bay < 0).sum())},
   "distinct_event_ids": int(len(u_ev)), "duplicate_event_id_values": dup_ev_ids,
   "duplicate_bay_arrival_pairs": int(V - len(np.unique(bay[valid].astype(np.int64)*10**7 + (arr[valid]-LOCAL_BASE_EPOCH)))),
   "same_bay_overlapping_stays": overlap_cnt, "bays_with_overlap": ov_bays,
   "overlap_share_of_valid": round(overlap_cnt/max(1,V), 5),
   "cross_midnight_events": int(cross_mid.sum()),
   "cross_midnight_share": round(float(cross_mid.sum())/max(1,V), 4),
   "in_violation_rate": round(viol_rate, 4),
   "in_violation_count": int(viol[valid].sum()),
   "right_censored_departure_after_2014_12_31_local": int(((dep >= LOCAL_BASE_EPOCH + 365*86400) & valid).sum()),
 },
 "scale": {
   "distinct_parking_event_ids": int(len(u_ev)), "distinct_devices": int(len(np.unique(dev[dev>=0]))),
   "distinct_bays": int(len(np.unique(bay[valid]))), "distinct_streets": int(len(np.unique(street[street>=0]))),
   "distinct_areas": int(len(np.unique(area[area>=0]))), "distinct_sites": int(len(uniq_sites)),
   "capacity_per_site": {"min": int(min(cap_map.values())), "median": float(np.median(list(cap_map.values()))),
                         "max": int(max(cap_map.values())), "sites_cap_ge3": int(sum(1 for v in cap_map.values() if v>=3)),
                         "sites_cap_ge5": int(sum(1 for v in cap_map.values() if v>=5)),
                         "sites_cap_ge10": int(sum(1 for v in cap_map.values() if v>=10)),
                         "sites_cap_ge15": int(sum(1 for v in cap_map.values() if v>=15))},
   "calendar_days_2014": 365, "days_with_events": days_with_events,
   "missing_calendar_days": missing_days,
   "global_complete_24h_days_all_24_hour_bins_nonzero": complete_global_days,
   "note_complete_day": "全城口径（所有街道合并）每天 24 个小时档均有到达事件；场站级完整日按导出窗口内 site-day 观测车位/容量>=0.8 判定",
 },
 "export": {
   "window_local": "2014-01-06T00:00:00 .. 2014-03-30T23:59:59 Australia/Melbourne (84 local days = 12 complete ISO weeks)",
   "window_rule": "doy 6..89 of 2014; entire window is inside AEDT (UTC+11), no DST transition inside the window",
   "site_rule": "sites (street-side segments) whose full-year observed capacity >= %d; deterministic row-cap rule: smallest capacity threshold in (3,5,8,10,15,20,30) yielding <= 2,000,000 export rows" % thr,
   "rows": int(len(sel_idx)), "sites": int(nsites), "window_candidate_rows_all_sites": win_rows_total,
   "rows_by_threshold": "see build log output for cap>=3,5,8,10,15,20,30",
   "file": "data/processed/unified_events.csv", "file_bytes": int(os.path.getsize(OUT_CSV)),
   "columns": ["site_id","event_id","arrival_ts_utc","departure_ts_utc","dwell_min","site_capacity","day_local","arrival_local_hour","source_dataset","source_row"],
   "site_day_completeness_in_window": {"site_days": int(len(sd_pairs)), "complete_site_days_frac80": sd_complete,
        "sites_with_ge4_complete_days": sites_ge4, "sites_with_ge12_complete_days": sites_ge12,
        "definition": "site-day with alive bays / site capacity >= 0.8"},
 },
 "dwell_min": {"mean": round(float(dwell_min_all.mean()),2), "median": round(float(np.median(dwell_min_all)),2),
               "p90": round(float(np.percentile(dwell_min_all,90)),2), "p95": round(float(np.percentile(dwell_min_all,95)),2),
               "p99": round(float(np.percentile(dwell_min_all,99)),2), "max": round(float(dwell_min_all.max()),2)},
 "arrivals_by_local_hour": {str(k): int(v) for k, v in enumerate(hour_hist)},
 "arrivals_by_weekday_mon0": {str(k): int(v) for k, v in enumerate(wd_hist)},
 "site_index": {"file": "data/processed/site_index.csv", "sites": int(len(si))},
 "qa_day_counts": {"file": "data/qa/day_counts.csv"},
 "sha256_full_record": {"raw_zip": zip_sha, "unified_events_csv": sha256_file(OUT_CSV), "site_index_csv": sha256_file(OUT_SITE)},
}
with open(OUT_STATS, "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)
print("STATS:", json.dumps({k: stats[k] for k in ["scan","scale","export"]}, ensure_ascii=False)[:2000])
print("DONE elapsed=%.0fs" % (time.time()-t0))
