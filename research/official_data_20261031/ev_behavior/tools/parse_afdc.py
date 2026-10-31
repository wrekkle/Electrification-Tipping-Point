
import re, html, os, json
base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "source_review")
raw = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw", "AFDC_vehicle_registration_2024.html"), encoding="utf-8", errors="replace").read()
t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S|re.I)
t = re.sub(r"<[^>]+>", "\n", t); t = html.unescape(t)
lines = [l.strip() for l in t.splitlines() if l.strip()]
# print lines around 'California' and 'Total'
for i,l in enumerate(lines):
    if l in ("California","Total","State","Alabama"):
        print(i,"|", " | ".join(lines[i:i+6]))
open(os.path.join(base,"afdc_registration_text.txt"),"w",encoding="utf-8").write("\n".join(lines))
print("wrote afdc text", len(lines))
