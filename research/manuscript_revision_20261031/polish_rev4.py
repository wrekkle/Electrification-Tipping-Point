
# -*- coding: utf-8 -*-
"""Round-7 rev4 polish: complete M06/M07/M10/M18 reference metadata; fix table headers/widths."""
import os
from docx import Document
from docx.shared import Pt, Inches

ROOT = r"C:\Projects\停车场充电桩优化方案"
PATH = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx")
doc = Document(PATH)
ps = list(doc.paragraphs)

def find(prefix):
    for p in ps:
        if p.text.strip().startswith(prefix):
            return p
    raise RuntimeError("not found: " + prefix)

refs = {
    "Hou et al.": ("Hou, J., Guo, Z. & Li, T. An augmented Lagrangian relaxation algorithm for allocation optimization of shared private parking spaces considering EV charging. Expert Systems with Applications 308, 131133 (2026). doi:10.1016/j.eswa.2026.131133"),
    "Zhang et al.": ("Zhang, H., Gong, J., Tang, W., Mei, Z. & Feng, C. Electric vehicles shared charging and parking: a reservation-based dynamic rolling allocation framework considering unpunctuality. Transportation Research Part C 179, 105259 (2025). doi:10.1016/j.trc.2025.105259"),
    "Chen, Pavlov, Zhao, Feng & Xu.": ("Chen, F., Pavlov, V., Zhao, S., Feng, J. & Xu, S. X. Joint operation strategy of parking and charging infrastructure. Transportation Research Part D 144, 104773 (2025). doi:10.1016/j.trd.2025.104773"),
    "A scenario-based stochastic programming approach": ("Kim, S., Rasouli, S., Timmermans, H. J. P. & Yang, D. A scenario-based stochastic programming approach for the public charging station location problem. Transportmetrica B 10, 340-367 (2022). doi:10.1080/21680566.2021.1997672"),
}
for pref, new in refs.items():
    p = find(pref)
    p.text = new

# Table 3 headers and widths
for table in doc.tables:
    hdr = [c.text.strip() for c in table.rows[0].cells]
    if hdr and hdr[0] == "Lot":
        cells = table.rows[0].cells
        cells[4].text = "Delta k"
        cells[5].text = "Cat. A"
        cells[6].text = "Cat. B"
        widths = [Inches(0.7), Inches(0.45), Inches(0.55), Inches(0.55), Inches(0.65), Inches(1.0), Inches(1.0)]
        for row in table.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = w
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(9)
    if hdr and hdr[0] == "Rule pair":
        widths = [Inches(1.35)] + [Inches(0.45)] * 9
        for row in table.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = w
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(8)

doc.save(PATH)
print("SAVED", PATH)
print("PARAS", len(doc.paragraphs))
# pending-string check
bad = ["to be completed", "placeholder", "to be produced", "To be drawn"]
for p in doc.paragraphs:
    for b in bad:
        if b.lower() in p.text.lower():
            print("PENDING", repr(b), p.text[:200])
