
# -*- coding: utf-8 -*-
import os, re, json, hashlib
from docx import Document
ROOT = "C:/Projects/停车场充电桩优化方案"
MAIN = os.path.join(ROOT, "paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx")
SI = os.path.join(ROOT, "paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx")
def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()
def cites(doc):
    body = [p for p in doc.paragraphs if p.style.name != "Bibliography"]
    sup = set()
    for p in body:
        seq = [r.text.strip() for r in p.runs if r.font.superscript and r.text.strip()]
        i = 0
        while i < len(seq):
            t = seq[i]
            if t.isdigit():
                n = int(t)
                if i + 2 < len(seq) and seq[i+1] == "-" and seq[i+2].isdigit():
                    m = int(seq[i+2]); sup.update(range(min(n,m), max(n,m)+1)); i += 3
                else:
                    sup.add(n); i += 1
                continue
            if t in ("-", ","): i += 1; continue
            for part in t.replace(";", ",").split(","):
                part = part.strip()
                for dash in ("-", "–", "—"): part = part.replace(dash, "-")
                if "-" in part:
                    a_s, _, b_s = part.partition("-")
                    if a_s.strip().isdigit() and b_s.strip().isdigit():
                        a,b=int(a_s),int(b_s); sup.update(range(min(a,b),max(a,b)+1)); i += 1; continue
                for m in re.finditer(r"\d+", part): sup.add(int(m.group(0)))
            i += 1
    return sup
main = Document(MAIN); si = Document(SI)
sup = cites(main)
bib = [p for p in main.paragraphs if p.style.name == "Bibliography" and p.text.strip()]
pending = ["placeholder", "to be produced", "To be drawn", "to be reassigned", "author list to be completed"]
pending_hits = [s for s in pending if any(s.lower() in p.text.lower() for p in main.paragraphs)]
full = "\n".join(p.text for p in main.paragraphs)
check = {
    "main_sha256": sha(MAIN), "si_sha256": sha(SI),
    "main_paragraphs": len(main.paragraphs), "main_tables": len(main.tables),
    "main_inline_images": len(main.inline_shapes),
    "main_data_tables": len([t for t in main.tables if t.rows and t.rows[0].cells[0].text.strip() in ("Rule","Trace","Lot","Rule pair","Scenario")]),
    "captions": len([p for p in main.paragraphs if p.style.name == "Caption"]),
    "references": len(bib), "citations": len(sup),
    "missing_refs": [i for i in range(1, len(bib)+1) if i not in sup],
    "out_of_range": [i for i in sup if i > len(bib)],
    "pending_strings": pending_hits,
    "table_refs": sorted(set(int(m.group(1)) for m in re.finditer(r"\bTable\s+(\d+)", full))),
    "table_captions": sorted(set(int(m.group(1)) for m in re.finditer(r"\bTable\s+(\d+)", "\n".join(p.text for p in main.paragraphs if p.style.name == "Caption")))),
    "figure_refs": sorted(set(int(m.group(1)) for m in re.finditer(r"\bFig\.?\s+(\d+)", full))),
    "figure_captions": sorted(set(int(m.group(1)) for m in re.finditer(r"\bFig\.?\s+(\d+)", "\n".join(p.text for p in main.paragraphs if p.style.name == "Caption")))),
    "has_table6_caption": "Table 6" in "\n".join(p.text for p in main.paragraphs if p.style.name == "Caption"),
    "si_sections": [p.text.strip() for p in si.paragraphs if p.text.strip().startswith("S") and len(p.text.strip()) < 120][:12],
    "si_has_S7": any("S7" in p.text for p in si.paragraphs),
}
check["citation_ok"] = (check["missing_refs"] == [] and check["out_of_range"] == [])
check["table_number_ok"] = (check["table_refs"] == [1,2,3,4,5] and check["table_captions"] == [1,2,3,4,5])
check["figure_number_ok"] = (check["figure_refs"] == [1] and check["figure_captions"] == [1])
print(json.dumps(check, ensure_ascii=False, indent=1))
open(os.path.join(ROOT, "research/manuscript_revision_20261031/acceptance.json"), "w", encoding="utf-8").write(json.dumps(check, ensure_ascii=False, indent=1))
