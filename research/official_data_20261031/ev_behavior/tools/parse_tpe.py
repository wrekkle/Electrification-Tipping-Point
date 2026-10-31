
import re, html, os
base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw")
p = os.path.join(base, "datataipei_parking_dataset.html")
raw = open(p, encoding="utf-8", errors="replace").read()
ids = sorted(set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", raw)))
rids = sorted(set(re.findall(r"/resource/([0-9a-f-]{36})", raw)))
print("DATASET_IDS:", ids)
print("RESOURCE_IDS:", rids)
t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S|re.I)
t = re.sub(r"<[^>]+>", "\n", t); t = html.unescape(t)
lines = [l.strip() for l in t.splitlines() if l.strip()]
print("TITLE_LINES:", " | ".join([l for l in lines if ("停車" in l or "充電" in l or "資料" in l)][:12]))
