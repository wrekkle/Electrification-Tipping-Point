
# -*- coding: utf-8 -*-
"""Build unified event contract + QA stats from City of Melbourne 2014 parking bay arrivals/departures."""
import zipfile, io, json, os, sys, time, re
import numpy as np
import pandas as pd

ROOT = r"research/round8_20261031/data"
ZIP = os.path.join(ROOT, "raw", "melbourne_parking_bay_arrivals_departures_2014_mq3i-cbxd.zip")
OUT_CSV = os.path.join(ROOT, "processed", "unified_events.csv")
OUT_SITE = os.path.join(ROOT, "processed", "site_index.csv")
OUT_STATS = os.path.join(ROOT, "qa", "stats.json")
os.makedirs(os.path.join(ROOT,"processed"), exist_ok=True)
os.makedirs(os.path.join(ROOT,"qa"), exist_ok=True)

TZ = "Australia/Melbourne"
DS = "melbourne_parking_bay_arrivals_departures_2014"
COLS = ["ParkingEventId","DeviceId","ArrivalTime","DepartureTime","DurationSeconds",
        "StreetId","StreetName","Area","AreaName","SideCode","SideOfStreet","BayID","InViolation"]
USECOLS = ["ParkingEventId","DeviceId","ArrivalTime","DepartureTime","DurationSeconds",
           "StreetId","StreetName","Area","SideCode","BayID","InViolation"]

name = [n for n in zipfile.ZipFile(ZIP).namelist() if n.endswith(".csv")][0]
z = zipfile.ZipFile(ZIP)
tf = io.TextIOWrapper(z.open(name), encoding="utf-8-sig", newline="", errors="replace")

t0=time.time()
acc = {k: [] for k in ["ev","dev","arr_s","dep_s","dur_s","street","site","bay","area","viol","row"]}
nraw = 0; nbad_ev = 0; nbad_dev = 0; nbad_street=0
reader = pd.read_csv(tf, usecols=USECOLS, chunksize=1_000_000,
    dtype={"ParkingEventId":"object","DeviceId":"object","ArrivalTime":"object","DepartureTime":"object",
           "DurationSeconds":"object","StreetId":"object","StreetName":"object","Area":"object",
           "SideCode":"object","BayID":"object","InViolation":"object"})
def num(s):
    return pd.to_numeric(s.astype("string").str.replace(",","",regex=False).str.strip().replace({"":None}), errors="coerce")
def parse_local(s):
    # "04/02/2014 10:56:29 AM +0000" -> dd/mm/yyyy local wall clock (offset field noted separately: see QA)
    t = s.astype("string").str.strip().str.replace(r"\s*[+-]\d{4}$","",regex=True)
    return pd.to_datetime(t, format="%d/%m/%Y %I:%M:%S %p", errors="coerce")

for ci, chunk in enumerate(reader):
    n = len(chunk)
    ev = num(chunk["ParkingEventId"]); dev = num(chunk["DeviceId"])
    arr = parse_local(chunk["ArrivalTime"]); dep = parse_local(chunk["DepartureTime"])
    dur = num(chunk["DurationSeconds"]); bay = num(chunk["BayID"])
    street = num(chunk["StreetId"]); area = num(chunk["Area"])
    side = chunk["SideCode"].astype("string").str.strip()
    viol = chunk["InViolation"].astype("string").str.strip().str.lower().isin(["true","1","yes"])
    rows = np.arange(nraw, nraw+n, dtype=np.int64); nraw += n
    nbad_ev += int(ev.isna().sum()); nbad_dev += int(dev.isna().sum()); nbad_street += int(street.isna().sum())
    acc["ev"].append(ev.to_numpy(dtype="float64")); acc["dev"].append(dev.to_numpy(dtype="float64"))
    acc["arr_s"].append(arr.to_numpy(dtype="datetime64[s]")); acc["dep_s"].append(dep.to_numpy(dtype="datetime64[s]"))
    acc["dur_s"].append(dur.to_numpy(dtype="float64"))
    acc["street"].append(street.to_numpy(dtype="float64")); acc["bay"].append(bay.to_numpy(dtype="float64"))
    acc["area"].append(area.to_numpy(dtype="float64"))
    acc["viol"].append(viol.to_numpy(dtype="bool")); acc["row"].append(rows)
    acc.setdefault("side", []).append(pd.Categorical(side).codes.astype(np.int16))
    acc.setdefault("side_cats", []).append(list(pd.Categorical(side).categories))
    print(f"chunk {ci} n={n} elapsed={time.time()-t0:.0f}s", flush=True)

D = {k: np.concatenate(v) for k,v in acc.items() if k!="side_cats"}
cats = []
for c in acc["side_cats"]:
    for x in c:
        if x not in cats: cats.append(x)
side_idx = np.concatenate([x for x in acc["side"] if False]) if False else None
# rebuild side as string using per-chunk categories order preserved? simpler: store side codes via value mapping below
print("read done rows=", nraw, "secs=", round(time.time()-t0,1), flush=True)

# ---- side string handling: per-chunk categorical codes were built per chunk; rebuild from code arrays
side = np.empty(nraw, dtype=object)
pos=0
for c in acc["side"]:
    m = len(c)
    side[pos:pos+m] = [cats[i] if 0 <= i < len(cats) else "" for i in c[:0]] if False else ""
    pos+=m
# Fallback: recompute side from scratch is not possible; use mapping trick below
print("side placeholder built (will recompute if needed)")
