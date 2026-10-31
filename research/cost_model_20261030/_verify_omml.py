
import re, zipfile, json
from docx import Document
base = r"C:\Projects\停车场充电桩优化方案"
p = base + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-30.docx"
xml = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8","ignore")
out=[]
def P(*a): out.append(" ".join(str(x) for x in a))
P("oMath:", xml.count("<m:oMath>"), "oMathTagAny:", xml.count("<m:oMath"), "oMathPara:", xml.count("<m:oMathPara"))
doc = Document(p)
paras = doc.paragraphs
# find selection of equation-ish paragraphs
for i,q in enumerate(paras):
    t = q.text.strip()
    if re.fullmatch(r"\((1[0-5])\)", t) or re.search(r"\((1[0-5])\)$", t):
        P("para", i, repr(t[-40:]), "oMath inside:", len(q._p.findall(".//{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath")))
# check plain text leftovers
body = "\n".join(q.text for q in paras)
for kw in ["Delta t_i", "Delta C_energy", "Delta C_occ", "Delta T_i", "released in time", "occupancy allowed"]:
    P("leftover", kw, body.count(kw))
# list all numbers appearing as standalone paragraph text
nums = [q.text.strip() for q in paras if re.fullmatch(r"\(\s*\d{1,2}\s*\)", q.text.strip())]
P("standalone number paras:", nums)
# in-text refs
for q in paras:
    for m in re.finditer(r"[Ee]quation\(?s?\)?\s*\(?\d{1,2}\)?", q.text):
        P("ref:", q.text.strip()[:120])
# OMML subscripts count and math text
mt = re.findall(r"<m:t[^>]*>([^<]*)</m:t>", xml)
P("m:t total:", len(mt))
P("m:t with Delta:", [t for t in mt if "\u0394" in t])
P("m:t last 40:", mt[-40:])
open(base + r"\research\cost_model_20261030\_verify_omml.txt","w",encoding="utf-8").write("\n".join(out))
