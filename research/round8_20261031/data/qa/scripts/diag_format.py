
import zipfile, sys, io, re, collections
import pandas as pd

ZIP = r"research/round8_20261031/data/raw/melbourne_parking_bay_arrivals_departures_2014_mq3i-cbxd.zip"
name = [n for n in zipfile.ZipFile(ZIP).namelist() if n.endswith(".csv")][0]
z = zipfile.ZipFile(ZIP)
f = z.open(name)
# binary stream -> text stream (utf-8-sig)
import codecs
tf = io.TextIOWrapper(f, encoding="utf-8-sig", newline="")

first_day = collections.Counter()
second_day = collections.Counter()
bad = 0
n = 0
dt_min = None; dt_max = None
hours = collections.Counter()
months = collections.Counter()
dur_sum = 0
reader = pd.read_csv(tf, usecols=["ArrivalTime","DepartureTime","DurationSeconds"], chunksize=1_000_000,
                     dtype={"ArrivalTime":"string","DepartureTime":"string","DurationSeconds":"string"})
for chunk in reader:
    n += len(chunk)
    a = chunk["ArrivalTime"].str.strip()
    parts = a.str.split(" ", n=1, expand=True)
    d = parts[0]
    dp = d.str.split("/", expand=True)
    if dp.shape[1] == 3:
        first_day.update(dp[0].value_counts().to_dict())
        second_day.update(dp[1].value_counts().to_dict())
        months.update(dp[2].str.slice(0,4).value_counts().to_dict())
    ts = pd.to_datetime(a, format="%m/%d/%Y %I:%M:%S %p %z", errors="coerce", utc=True)
    if dt_min is None:
        print("SAMPLE first 5 ArrivalTime:", list(a.head(5)))
    good = ts.notna()
    bad += int((~good).sum())
    if good.any():
        hours.update(ts[good].dt.hour.value_counts().to_dict())
        v = ts[good]
        m = v.min(); M = v.max()
        dt_min = m if dt_min is None or m < dt_min else dt_min
        dt_max = M if dt_max is None or M > dt_max else dt_max
    if n >= 4_000_000: break
print("rows_scanned", n)
print("parse_fail", bad)
print("min_ts", dt_min, "max_ts", dt_max)
print("first_component>12 count:", sum(c for k,c in first_day.items() if k.isdigit() and int(k)>12), "dist:", dict(sorted(first_day.items(), key=lambda x:int(x[0]))["[0:20]"] if False else list(sorted(first_day.items(), key=lambda x:int(x[0])))[:15]))
print("second_component>12 count:", sum(c for k,c in second_day.items() if k.isdigit() and int(k)>12), "dist:", list(sorted(second_day.items(), key=lambda x:int(x[0])))[:15])
print("years:", dict(months))
print("hour_hist(raw-labeled):", dict(sorted(hours.items())))
