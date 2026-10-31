
import json, re, html, zipfile, io, os, csv
base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw")
# UK CKAN
d = json.load(open(os.path.join(base,"uk_datagov_ckan_search.json"), encoding="utf-8"))
res = d.get("result",{}).get("results",[])
print("UK datasets:", len(res))
for r in res[:5]:
    print(" -", r.get("title"), "|", r.get("name"), "| resources:", len(r.get("resources",[])))
    for x in r.get("resources",[])[:4]:
        print("    *", x.get("format"), x.get("url","")[:120])
# ACN research page
raw = open(os.path.join(base,"ACN_research.html"), encoding="utf-8", errors="replace").read()
t = re.sub(r"<script.*?</script>|<style.*?</style>"," ",raw,flags=re.S|re.I)
t = re.sub(r"<[^>]+>","\n",t); t = html.unescape(t)
lines=[l.strip() for l in t.splitlines() if l.strip()]
keep=[l for l in lines if re.search(r"session|charging|dataset|ACN|workplace|Caltech|Jemez|paper", l, re.I)]
print("ACN lines:", len(keep)); print("\n".join(keep[:18]))
# AFDC stations states
raw2 = open(os.path.join(base,"AFDC_stations_states.html"), encoding="utf-8", errors="replace").read()
t2 = re.sub(r"<[^>]+>","\n",re.sub(r"<script.*?</script>|<style.*?</style>"," ",raw2,flags=re.S|re.I)); t2=html.unescape(t2)
l2=[l.strip() for l in t2.splitlines() if l.strip()]
print("AFDC station-state lines sample:", " | ".join(l2[80:120])[:1200])
# EPA zip
z = zipfile.ZipFile(os.path.join(base,"epa_vehicles.csv.zip"))
print("EPA files:", z.namelist())
name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
with z.open(name) as f:
    txt = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
    rd = csv.DictReader(txt)
    cols = rd.fieldnames
    print("EPA columns:", cols[:40])
    n=0; ev=0; ranges=[]
    for row in rd:
        n+=1
        if row.get("fuelType1","").lower().startswith("electric") or row.get("fuelType2","").lower()=="electricity":
            ev+=1
            try: ranges.append(float(row.get("range","") or 0))
            except: pass
    print("EPA rows:", n, "EV rows:", ev, "range>0:", sum(1 for r in ranges if r>0))
