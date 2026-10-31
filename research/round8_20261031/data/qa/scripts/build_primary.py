
# -*- coding: utf-8 -*-
"""Build unified event contract + field-level QA for City of Melbourne 2014 parking bay arrivals/departures.

Input : data/raw/melbourne_parking_bay_arrivals_departures_2014_mq3i-cbxd.zip (read streamed, not extracted)
Output: data/processed/unified_events.csv, data/processed/site_index.csv,
        data/qa/stats.json, data/qa/day_counts.csv
"""
import zipfile, io, json, os, time, re, collections
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

TZ = "Australia/Melbourne"
DS = "melbourne_parking_bay_arrivals_departures_2014"
USECOLS = ["ParkingEventId","DeviceId","ArrivalTime","DepartureTime","DurationSeconds",
           "StreetId","StreetName","Area","AreaName","SideCode","BayID","InViolation"]

name = [n for n in zipfile.ZipFile(ZIP).namelist() if n.endswith(".csv")][0]
z = zipfile.ZipFile(ZIP)
arr_size = zipfile.ZipFile(ZIP).getinfo(name).file_size
tf = io.TextIOWrapper(z.open(name), encoding="utf-8-sig", newline="", errors="replace")

t0 = time.time()
def num(s):
    return pd.to_numeric(s.astype("string").str.replace(",", "", regex=False).str.strip().replace({"": None}), errors="coerce")
def parse_local(s):
    t = s.astype("string").str.strip().str.replace(r"\s*[+-]\d{4}\s*$", "", regex=True)
    return pd.to_datetime(t, format="%d/%m/%Y %I:%M:%S %p", errors="coerce")

ev_l, dev_l, arr_l, dep_l, dur_l = [], [], [], [], []
street_l, bay_l, area_l, side_l, viol_l, rownum_l = [], [], [], [], [], []
offset_counter = collections.Counter()
site_meta = {}
nraw = 0
reader = pd.read_csv(tf, usecols=USECOLS, chunksize=1_000_000,
    dtype={c: "object" for c in USECOLS})
for ci, chunk in enumerate(reader):
    n = len(chunk)
    ev_l.append(num(chunk["ParkingEventId"]).to_numpy(dtype="float64"))
    dev_l.append(num(chunk["DeviceId"]).to_numpy(dtype="float64"))
    arr_l.append(parse_local(chunk["ArrivalTime"]).to_numpy(dtype="datetime64[s]"))
    dep_l.append(parse_local(chunk["DepartureTime"]).to_numpy(dtype="datetime64[s]"))
    dur_l.append(num(chunk["DurationSeconds"]).to_numpy(dtype="float64"))
    street_l.append(num(chunk["StreetId"]).to_numpy(dtype="float64"))
    bay_l.append(num(chunk["BayID"]).to_numpy(dtype="float64"))
    area_l.append(num(chunk["Area"]).to_numpy(dtype="float64"))
    side_l.append(chunk["SideCode"].astype("string").fillna("").to_numpy(dtype=object))
    viol_l.append(chunk["InViolation"].astype("string").str.strip().str.lower().isin(["true","1","yes"]).to_numpy(dtype=bool))
    rownum_l.append(np.arange(nraw, nraw + n, dtype=np.int64))
    off = chunk["ArrivalTime"].astype("string").str.extract(r"([+-]\d{4})\s*$", expand=False).fillna("NONE")
    offset_counter.update(off.value_counts().to_dict())
    # site metadata dict: (street, side) -> (street_name, area_name, area)
    if "StreetName" in chunk.columns:
        sm = pd.DataFrame({
            "street": num(chunk["StreetId"]), "side": chunk["SideCode"].astype("string").fillna(""),
            "sname": chunk["StreetName"].astype("string").fillna(""), "aname": chunk["AreaName"].astype("string").fillna(""),
            "area": num(chunk["Area"])}).drop_duplicates(subset=["street","side"])
        for r in sm.itertuples(index=False):
            k = (r.street, r.side)
            if k not in site_meta:
                site_meta[k] = {"street_name": r.sname, "area_name": r.aname, "area": r.area}
    nraw += n
    print(f"chunk {ci} n={n} cum={nraw} elapsed={time.time()-t0:.0f}s", flush=True)

D = dict(ev=np.concatenate(ev_l), dev=np.concatenate(dev_l), arr=np.concatenate(arr_l),
         dep=np.concatenate(dep_l), dur=np.concatenate(dur_l), street=np.concatenate(street_l),
         bay=np.concatenate(bay_l), area=np.concatenate(area_l), side=np.concatenate(side_l),
         viol=np.concatenate(viol_l), row=np.concatenate(rownum_l))
del ev_l, dev_l, arr_l, dep_l, dur_l, street_l, bay_l, area_l, side_l, viol_l, rownum_l
print("read done rows=", nraw, "secs=", round(time.time()-t0,1), flush=True)

# ---------- timezone assumption: raw offset field is a constant label; treat stored values as local wall clock
S = pd.Series(D["arr"]).astype("datetime64[ns]")
loc = S.dt.tz_localize(TZ, ambiguous=np.zeros(len(S), dtype=bool), nonexistent="shift_forward")
utc = loc.dt.tz_convert("UTC")
ambig = int(S.dt.tz_localize(TZ, ambiguous="NaT", nonexistent="NaT").isna().sum())
dep_utc = pd.Series(D["dep"]).astype("datetime64[ns]").dt.tz_localize(TZ, ambiguous=np.zeros(len(S), dtype=bool), nonexistent="shift_forward").dt.tz_convert("UTC")
arr_local = S
arr_utc_i = utc.astype("int64") // 10**9
dep_utc_i = dep_utc.astype("int64") // 10**9
day_local = arr_local.dt.strftime("%Y-%m-%d")
arr_hour = arr_local.dt.hour

# ---------- filters
dur = D["dur"].astype("float64")
arr_ok = S.notna().to_numpy()
dep_ok = pd.Series(D["dep"]).notna().to_numpy()
dur_ok = np.isfinite(dur)
neg = dur_ok & (dur < 0)
zero = dur_ok & (dur == 0)
ts_mismatch = dur_ok & (np.abs((dep_utc_i - arr_utc_i) - dur) > 5) & dep_ok & arr_ok
long24 = dur_ok & (dur > 86400)
ev_ok = np.isfinite(D["ev"])
ev_dup = np.zeros(len(S), dtype=bool)
if ev_ok.any():
    u, cnt = np.unique(D["ev"][ev_ok], return_counts=True)
    dupvals = u[cnt > 1]
    if len(dupvals):
        ev_dup = np.isin(D["ev"], dupvals)
bay_ok = np.isfinite(D["bay"])
valid = arr_ok & dep_ok & dur_ok & (dur > 0) & (dur <= 86400) & (~ev_dup) & bay_ok & (dep_utc_i >= arr_utc_i)
mask_keep = valid
print("valid", int(valid.sum()), "of", nraw, flush=True)

# ---------- site key & capacity
side_clean = pd.Series(D["side"]).astype("string").str.strip().fillna("")
street_int = pd.Series(D["street"])
site_key = np.where(np.isfinite(D["street"]),
                    "MELB-ST-" + pd.Series(D["street"]).fillna(-1).astype("int64").astype(str) + "-" + side_clean,
                    "MELB-AREA-" + pd.Series(D["area"]).fillna(-1).astype("int64").astype(str) + "-" + side_clean)
site_key = pd.Series(site_key)
cap_df = pd.DataFrame({"site_id": site_key[bay_ok], "bay": D["bay"][bay_ok]}).drop_duplicates()
cap_map = cap_df.groupby("site_id")["bay"].nunique()
site_cap = site_key.map(cap_map).fillna(0).astype("int64")

# ---------- duplicates on (bay, arrival)
k2 = pd.DataFrame({"bay": D["bay"], "a": D["arr"]}).drop_duplicates()
dup_bay_arr = int(bay_ok.sum() - (k2.dropna().shape[0] - k2["bay"].isna().sum()))

# ---------- overlaps within bay (capacity conflict; each bay capacity = 1)
order = np.lexsort((arr_utc_i, np.nan_to_num(D["bay"], nan=-1)))
bay_s = D["bay"][order]; arr_s = arr_utc_i[order]; dep_s = dep_utc_i[order]
same = np.zeros(len(order), dtype=bool); same[1:] = bay_s[1:] == bay_s[:-1]
prev_dep = np.full(len(order), -10**18, dtype=np.int64); prev_dep[1:] = dep_s[:-1]
prev_dep[~same] = -10**18
overlap = same & (arr_s < prev_dep) & valid[order]
# chain overlaps per bay (count bays with >=1 overlap)
ob = np.unique(bay_s[overlap])
overlap_cnt = int(overlap.sum())
print("overlaps", overlap_cnt, "bays", len(ob), flush=True)

# ---------- day/date coverage
day_s = pd.Series(day_local)
dates = pd.to_datetime(day_s, errors="coerce")
span_days = int((dates.max() - dates.min()).days) + 1
# per bay observed days
bayday = pd.DataFrame({"bay": D["bay"][valid], "day": dates[valid].to_numpy()}).dropna().drop_duplicates()
bay_day_count = bayday.groupby("bay")["day"].nunique()
active_bays = bay_day_count[bay_day_count >= 30]
all_days = pd.date_range("2014-01-01", "2014-12-31", freq="D")
miss_expected = int(len(active_bays) * len(all_days) - bayday[bayday["bay"].isin(active_bays.index)].shape[0])
glob_counts = dates[valid].value_counts().sort_index()
missing_global_days = [str(d.date()) for d in all_days if d not in set(pd.to_datetime(glob_counts.index))]
# site-day completeness: alive bays per site-day / capacity
sd = pd.DataFrame({"site_id": site_key[valid], "day": dates[valid], "bay": D["bay"][valid]}).dropna(subset=["day"])
sd = sd.drop_duplicates(subset=["site_id","day","bay"])
sd_alive = sd.groupby(["site_id","day"]).size().rename("alive").reset_index()
sd_alive = sd_alive.merge(cap_map.rename("cap").reset_index(), on="site_id", how="left")
sd_alive["frac"] = sd_alive["alive"] / sd_alive["cap"]
COMPLETE_THR = 0.8
complete_sd = sd_alive[sd_alive["frac"] >= COMPLETE_THR]
site_complete = complete_sd.groupby("site_id").size()
sites_ge4 = int((site_complete >= 4).sum())
sites_ge30 = int((site_complete >= 30).sum())

# ---------- dwell stats
dwell_min = (dur / 60.0)
dv = pd.Series(dwell_min[valid])
dwell_stats = {"mean": round(float(dv.mean()),3), "median": round(float(dv.median()),3),
    "p90": round(float(dv.quantile(.90)),3), "p95": round(float(dv.quantile(.95)),3),
    "p99": round(float(dv.quantile(.99)),3), "min": round(float(dv.min()),3), "max": round(float(dv.max()),3)}
hour_hist = pd.Series(arr_hour[valid]).value_counts().sort_index()
wd_hist = arr_local.dt.dayofweek[valid].value_counts().sort_index()

# ---------- write contract CSV
site_valid = site_key[valid]
cap_valid = site_cap[valid]
out = pd.DataFrame({
    "site_id": site_valid.to_numpy(),
    "event_id": D["ev"][valid].astype("int64").astype(str),
    "arrival_ts_utc": pd.Series(utc[valid]).dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(),
    "departure_ts_utc": pd.Series(dep_utc[valid]).dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(),
    "dwell_min": np.round(dwell_min[valid], 2),
    "site_capacity": cap_valid.to_numpy(dtype="int64"),
    "day_local": day_local[valid].to_numpy(),
    "arrival_local_hour": arr_hour[valid].astype("int64").to_numpy(),
    "source_dataset": DS,
    "source_row": D["row"][valid] + 1,
})
out.to_csv(OUT_CSV, index=False, encoding="utf-8")
print("wrote", OUT_CSV, out.shape, round(time.time()-t0,1), flush=True)

# ---------- site index
si = pd.DataFrame({"site_id": site_key[valid], "day": dates[valid], "bay": D["bay"][valid],
                   "dwell": dwell_min[valid], "viol": D["viol"][valid]})
g = si.groupby("site_id")
site_rows = pd.DataFrame({
    "n_events": g.size(),
    "n_days": g["day"].nunique(),
    "first_day": g["day"].min(),
    "last_day": g["day"].max(),
    "mean_dwell_min": g["dwell"].mean().round(2),
    "median_dwell_min": g["dwell"].median().round(2),
    "in_violation_rate": g["viol"].mean().round(4),
}).reset_index()
site_rows["capacity"] = site_rows["site_id"].map(cap_map)
site_rows["complete_days_frac80"] = site_rows["site_id"].map(site_complete).fillna(0).astype(int)
meta_rows = []
for sid in site_rows["site_id"]:
    street = None
    try:
        if sid.startswith("MELB-ST-"):
            parts = sid.split("-"); sid_code = int(parts[2]); side = parts[3] if len(parts)>3 else ""
            patch = dict(zip(list(site_meta.keys()), list(site_meta.values()))) if False else site_meta
            # find meta by (street_code, side)
            hit = None
            for (st, sd_), v in site_meta.items():
                if st is not None and not (isinstance(st,float) and np.isnan(st)) and int(st)==sid_code and sd_==side:
                    hit = v; break
            if hit: meta_rows.append((hit["street_name"], hit["area_name"]))
            else: meta_rows.append(("",""))
        else:
            meta_rows.append(("",""))
    except Exception:
        meta_rows.append(("",""))
site_rows["street_name"] = [m[0] for m in meta_rows]
site_rows["area_name"] = [m[1] for m in meta_rows]
site_rows["mean_events_per_active_day"] = (site_rows["n_events"]/site_rows["n_days"]).round(2)
site_rows = site_rows.sort_values("n_events", ascending=False)
site_rows.to_csv(OUT_SITE, index=False, encoding="utf-8")
print("wrote", OUT_SITE, flush=True)

pd.DataFrame({"day_local": [str(d.date()) for d in glob_counts.index], "n_events": glob_counts.values}).to_csv(OUT_DAY, index=False)

# ---------- stats.json
stats = {
  "generated_at_utc": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
  "source": {"dataset": DS, "zip": os.path.basename(ZIP), "zip_bytes": os.path.getsize(ZIP),
             "csv_entry": name, "csv_uncompressed_bytes": arr_size,
             "license": "CC BY 4.0 (City of Melbourne open data; attribution required)",
             "portal": "https://data.melbourne.vic.gov.au/explore/dataset/parking-bay-arrivals-and-departures-2014/"},
  "contract": {"path": "data/processed/unified_events.csv",
               "columns": ["site_id","event_id","arrival_ts_utc","departure_ts_utc","dwell_min","site_capacity","day_local","arrival_local_hour","source_dataset","source_row"],
               "rows": int(out.shape[0]),
               "definitions": {
                 "site_id": "street-segment x side (StreetId+SideCode); fallback AREA-<area>-<side> when StreetId missing",
                 "site_capacity": "distinct sensor bays (BayID) ever observed on that street-side in the 2014 file",
                 "event_id": "raw ParkingEventId",
                 "source_row": "1-based data row index in the raw CSV (header excluded)"}},
  "raw_rows": nraw,
  "filter_counts": {
    "arrival_unparsable": int((~arr_ok).sum()),
    "departure_missing": int((~dep_ok).sum()),
    "duration_unparsable": int((~dur_ok).sum()),
    "duration_negative": int(neg.sum()),
    "duration_zero": int(zero.sum()),
    "duration_gt_24h_excluded": int(long24.sum()),
    "timestamp_vs_duration_mismatch_gt_5s": int(ts_mismatch.sum()),
    "duplicate_event_id_rows": int(ev_dup.sum()),
    "missing_bay_id": int((~bay_ok).sum()),
    "kept_after_filters": int(valid.sum()),
    "kept_share": round(float(valid.sum())/nraw, 4),
  },
  "timezone": {
    "raw_offset_label_counts": dict(offset_counter),
    "assumption": "stored wall-clock values are local Australia/Melbourne time despite the constant +0000 offset suffix; arrivals peak at local 07:00-18:00 matching published meter restriction hours",
    "dst_ambiguous_local_records": ambig,
    "dst_rule": "zoneinfo Australia/Melbourne, ambiguous=earliest (fold=0), nonexistent=shift_forward",
    "utc_min": pd.Series(utc[valid]).min().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "utc_max": pd.Series(utc[valid]).max().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "local_date_min": str(dates[valid].min().date()), "local_date_max": str(dates[valid].max().date()),
  },
  "scale": {
    "n_sites": int(site_key[valid].nunique()),
    "n_bays": int(np.unique(D["bay"][valid]).size),
    "n_devices": int(np.unique(D["dev"][valid]).size),
    "n_streets": int(np.unique(D["street"][valid & np.isfinite(D["street"])]).size),
    "capacity_per_site": {"min": int(cap_map.min()), "median": float(cap_map.median()), "max": int(cap_map.max()),
                          "sites_cap_ge3": int((cap_map >= 3).sum()), "sites_cap_ge10": int((cap_map >= 10).sum())},
    "valid_events": int(valid.sum()),
    "calendar_days_in_2014": 365,
    "days_with_events": int(len(glob_counts)),
    "missing_calendar_days_2014": missing_global_days,
    "site_days_total": int(len(sd_alive)),
    "site_days_complete_frac80": int(len(complete_sd)),
    "complete_day_definition": "site-day with observed bays / site capacity >= 0.8 (at least one valid arrival per observed bay)",
    "sites_with_ge4_complete_days": sites_ge4,
    "sites_with_ge30_complete_days": sites_ge30,
    "sites_ge30_complete_and_cap_ge3": int(((site_rows.set_index("site_id")["complete_days_frac80"] >= 30) & (site_rows.set_index("site_id")["capacity"] >= 3)).sum()),
    "active_bays_ge30_observed_days": int(len(active_bays)),
    "expected_bay_days_for_active_bays": int(len(active_bays) * len(all_days)),
    "missing_bay_days_estimated": miss_expected,
  },
  "dwell_min_stats": dwell_stats,
  "arrivals_by_local_hour": {str(int(k)): int(v) for k, v in hour_hist.items()},
  "arrivals_by_weekday": {str(int(k)): int(v) for k, v in wd_hist.items()},
  "integrity": {
    "duplicate_event_id_rows": int(ev_dup.sum()),
    "duplicate_bay_arrival_pairs": dup_bay_arr,
    "same_bay_overlapping_stays": overlap_cnt,
    "bays_with_overlap": int(len(ob)),
    "overlap_share_of_valid": round(float(overlap_cnt)/max(1,int(valid.sum())), 5),
    "departure_in_last_24h_possibly_right_censored": int(((dep_utc_i >= int(pd.Timestamp("2014-12-31 00:00", tz="UTC").timestamp())) & valid).sum()),
    "in_violation_rate_valid": round(float(pd.Series(D["viol"][valid]).mean()), 4),
  }
}
with open(OUT_STATS, "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)
print(json.dumps(stats["scale"], ensure_ascii=False, indent=1))
print(json.dumps(stats["filter_counts"], ensure_ascii=False))
print("DONE secs=", round(time.time()-t0,1))
