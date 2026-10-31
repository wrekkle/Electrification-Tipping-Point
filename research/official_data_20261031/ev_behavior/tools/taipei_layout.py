
import os, json, collections, itertools
proj = r"C:\Projects\停车场充电桩优化方案"
root = os.path.join(proj,"research","collection","taipei_372_polling_20261030")
outdir = os.path.join(proj,"research","official_data_20261031","traffic_resources")
os.makedirs(outdir, exist_ok=True)
# 0) layout
for sub in ["", "data", "data/static", "data/raw", "legacy", "ops", "polling"]:
    p = os.path.join(root, sub)
    if os.path.isdir(p):
        fs = os.listdir(p)[:15]
        print("DIR", sub or ".", "->", fs)
# 1) static snapshot file
sp = os.path.join(root,"data","static")
for f in os.listdir(sp):
    fp = os.path.join(sp,f)
    if os.path.isfile(fp):
        print("STATIC FILE:", f, os.path.getsize(fp))
        try:
            d = json.load(open(fp, encoding="utf-8"))
            print("  nodes type:", type(d).__name__, "| keys/len:", (list(d.keys())[:20] if isinstance(d,dict) else len(d)))
            s = json.dumps(d, ensure_ascii=False)
            for kw in ["充電","功率","kW","connector","status","type"]:
                print("  kw", kw, s.count(kw))
            print("  snippet:", s[:1200])
        except Exception as e:
            print("  parse err", e)
        break
# 2) raw static xml structure
xp = os.path.join(root,"data","raw")
if os.path.isdir(xp):
    print("RAW dir:", os.listdir(xp)[:5])
