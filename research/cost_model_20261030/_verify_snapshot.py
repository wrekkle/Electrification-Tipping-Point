
from docx import Document
base = r"C:\Projects\停车场充电桩优化方案"
doc = Document(base + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-30.docx")
out = []
for p in doc.paragraphs:
    t = p.text
    if "snapshot" in t.lower() or "vacancy" in t.lower() or "occupanc" in t.lower():
        out.append(t.strip()[:400])
open(base + r"\research\cost_model_20261030\_verify_snapshot.txt", "w", encoding="utf-8").write("\n\n".join(out))
print(len(out))
