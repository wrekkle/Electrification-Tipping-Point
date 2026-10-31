import json, os
base = "C:/Projects/停车场充电桩优化方案/research/collection/taipei_372_polling_20261030/data"
with open(os.path.join(base, "static", "cohort_static.json"), encoding="utf-8") as handle:
    static = json.load(handle)
sites = static.get("sites")
print("sites type:", type(sites).__name__, "n=", len(sites) if sites is not None else None)
if isinstance(sites, dict):
    items = list(sites.items())
    print("first key:", items[0][0])
    print("first value keys:", list(items[0][1].keys()) if isinstance(items[0][1], dict) else type(items[0][1]))
    rows = [v for _, v in items if isinstance(v, dict)]
elif isinstance(sites, list):
    rows = sites
    print("first row keys:", list(rows[0].keys()) if rows else None)
else:
    rows = []
caps = []
for row in rows:
    for key in ("baseline_totalcar", "totalcar", "capacity", "total_car", "spaces"):
        v = row.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            caps.append(float(v)); break
if caps:
    caps.sort()
    def q(p): return caps[min(len(caps)-1, int(p*(len(caps)-1)))]
    print("capacity n=%d min=%g p10=%g p25=%g p50=%g p75=%g p90=%g max=%g sum=%g" % (len(caps), caps[0], q(.1), q(.25), q(.5), q(.75), q(.9), caps[-1], sum(caps)))
    bands = [(0,50),(50,100),(100,200),(200,400),(400,10000)]
    for lo,hi in bands:
        print("  band %g-%g: %d" % (lo, hi, sum(1 for c in caps if lo <= c < hi)))
