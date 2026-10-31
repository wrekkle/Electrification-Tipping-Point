
import re, json, os
base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw")
h = open(os.path.join(base,"AFDC_stations_states.html"), encoding="utf-8", errors="replace").read()
print("AFDC has California:", "California" in h, "| numbers sample:", re.findall(r"California[^<]{0,200}", h)[:1])
print("AFDC has ports json:", len(re.findall(r"charging_ports|ev_ports|Electric", h)))
# IOT methodology
p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "source_review", "iot_report_hits.txt")
t = open(p, encoding="utf-8").read()
for kw in ["有效樣本","調查期間","回收","抽樣","份問卷","電動小客車使用者"]:
    idxs = [m.start() for m in re.finditer(kw, t)][:3]
    for i in idxs:
        print("IOT", kw, "|", t[max(0,i-160):i+180].replace("\n"," / ")[:340])
