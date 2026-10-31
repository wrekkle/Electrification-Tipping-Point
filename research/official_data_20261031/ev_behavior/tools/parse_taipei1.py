
import json, os, re, csv, io
proj = r"C:\Projects\停车场充电桩优化方案"
raw = os.path.join(proj, "research", "official_data_20261031", "ev_behavior", "raw")
# 1) Crossref abstracts
for mid in ["M11","M12"]:
    d = json.load(open(os.path.join(raw, f"crossref_{mid}.json"), encoding="utf-8"))
    m = d["message"]
    print(mid, "|", m.get("title"), "|", re.sub("<[^>]+>"," ",m.get("abstract","NO_ABSTRACT"))[:600].replace("\n"," "))
# 2) Barnet CSV
p = os.path.join(raw, "barnet_cityev_2021Q2.csv")
with open(p, encoding="utf-8-sig", errors="replace") as f:
    head = f.readline().strip()
    rows = [l for l in f]
print("BARNET header:", head[:300], "| rows:", len(rows), "| sample:", rows[0][:250] if rows else "")
# 3) AFDC raw: find table numbers
h = open(os.path.join(raw,"AFDC_stations_states.html"), encoding="utf-8", errors="replace").read()
nums = re.findall(r'"?(?:Level 2|DC Fast|charging ports|Electric)"?[^<>{}]{0,120}', h)[:8]
print("AFDC hints:", nums[:4])
# 4) Taipei inventories
for fn in ["parking_charging_inventory.csv","all_parking_inventory.csv"]:
    fp = os.path.join(proj,"research","collection","taipei_source_20261030",fn)
    with open(fp, encoding="utf-8-sig", errors="replace") as f:
        rd = csv.DictReader(f); rows = list(rd)
    print("TPE", fn, "rows:", len(rows), "cols:", rd.fieldnames)
    print("  sample:", {k: rows[0][k] for k in list(rd.fieldnames)[:14]})
# 5) summary.json
s = json.load(open(os.path.join(proj,"research","collection","taipei_source_20261030","summary.json"), encoding="utf-8"))
print("TPE summary keys:", list(s.keys())[:12], "|", json.dumps(s, ensure_ascii=False)[:700])
