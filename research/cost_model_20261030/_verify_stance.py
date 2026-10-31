
from docx import Document
base = r"C:\Projects\停车场充电桩优化方案"
d = base + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-30.docx"
doc = Document(d)
body = "\n".join(p.text for p in doc.paragraphs)
out = []
def P(*a): out.append(" ".join(str(x) for x in a))
for kw in ["no_ordinary_bay", "power_released", "connector_released", "charged_bay_released",
           "ordinary_bay_released", "ev_activity_loss", "maintenance_per_bay_day",
           "relocation_cost", "relocation_count", "relocation_blocked", "projected block",
           "at 1x", "not implemented", "idealised intervention", "not computable",
           "unknown rather than zero", "planned dwell time", "finite-window"]:
    P("%-24s count=%d" % (kw, body.count(kw)))
P("--- removed/kept checks ---")
for kw in ["when the capacity of the ordinary zone or the cost of a move is unknown",
           "energy still undelivered when the record ends is not a failure until the vehicle leaves"]:
    P("%-40s count=%d" % (kw[:38], body.count(kw)))
P("paragraphs:", len(doc.paragraphs), "tables:", len(doc.tables))
P("--- matching paragraphs ---")
for p in doc.paragraphs:
    if any(k in p.text for k in ["no_ordinary_bay", "ev_activity_loss", "at 1x"]):
        P(p.text[:300])
open(base + r"\research\cost_model_20261030\_verify_stance.txt", "w", encoding="utf-8").write("\n".join(out))
