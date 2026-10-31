
import re, html, os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw", "M13_nature_article.html")
raw = open(p, encoding="utf-8", errors="replace").read()
txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S|re.I)
txt = re.sub(r"<[^>]+>", "\n", txt)
txt = html.unescape(txt)
lines = [l.strip() for l in txt.splitlines() if l.strip()]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "source_review", "m13_nature_text.txt")
open(out, "w", encoding="utf-8").write("\n".join(lines))
print("lines", len(lines))
for i, l in enumerate(lines):
    if re.search(r"parking|Parking|data availability|Data availability|Zenodo|charging event|SOC", l):
        print(i, "|", l[:220])
