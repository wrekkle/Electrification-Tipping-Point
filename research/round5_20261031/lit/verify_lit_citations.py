# -*- coding: utf-8 -*-
"""Build and verify the M18/M06/M07 citation registry against the local PDFs."""
import json, os, re, sys, unicodedata
import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PDF = {
 "M18": os.path.join(ROOT, "papers", "electrification-math", "M18_joint-operation-parking-charging_TRD2025.pdf"),
 "M06": os.path.join(ROOT, "papers", "electrification-math", "M06_shared-private-parking-EV_ALR_ESWA2026.pdf"),
 "M07": os.path.join(ROOT, "papers", "electrification-math", "M07_dynamic-rolling-parking-charging-unpunctuality_TRC2025.pdf"),
}
# (paper, page, needle, axis, tier): tier A=full text directly checkable, B=author-reported number, C=UNVERIFIED
ENTRIES = [
 ("M18",2,"proofs are presented in the Appendix","information","A"),
 ("M18",4,"monopolized by two differentiated operators","decision","A"),
 ("M18",4,"There are three stages","information","A"),
 ("M18",5,"The quantity of charging piles constructed by operator i","decision","A"),
 ("M18",5,"The cost coefficient of constructing unit charging pile","capacity_power","A"),
 ("M18",6,"we solve the following GNB","objective","A"),
 ("M18",10,"Consumer surplus (CS) can be expressed as","objective","A"),
 ("M18",10,"constitute social welfare","objective","A"),
 ("M18",13,"social welfare is SW","objective","A"),
 ("M18",13,"When the government subsidizes parking space operator","objective","A"),
 ("M18",14,"Operator H consistently chooses to construct charging piles","decision","A"),
 ("M18",14,"commissioning piles enables the company to invest less","decision","A"),
 ("M18",15,"No data was used for the research described in the article","validation","A"),
 ("M18",15,"Future studies could further explore charging services for EVs","validation","A"),
 ("M06",1,"An augmented Lagrangian relaxation algorithm for allocation optimization","method","A"),
 ("M06",1,"reduces computation time by 80.31%","validation","B"),
 ("M06",2,"minimal walking distance","positioning","A"),
 ("M06",7,"Rule 1: Parking users who do not require charging","capacity_power","A"),
 ("M06",7,"Rule 2","information","A"),
 ("M06",7,"Assumption 1","information","A"),
 ("M06",9,"objective function","objective","A"),
 ("M06",10,"Lagrangian relaxation","method","A"),
 ("M06",16,"data","validation","A"),
 ("M06",18,"Table 9","validation","B"),
 ("M06",24,"without incorporating factors such as charging power and grid load","capacity_power","A"),
 ("M06",24,"future research will focus on integrating","validation","A"),
 ("M07",1,"Electric vehicles shared charging and parking","identity","A"),
 ("M07",1,"maximize revenue in hybrid parking lots","objective","A"),
 ("M07",4,"actual arrival and departure","information","A"),
 ("M07",8,"deterministic dynamic rolling allocation model (D-DRA)","decision","A"),
 ("M07",8,"charging power required by request m","capacity_power","A"),
 ("M07",10,"robust dynamic rolling allocation model (R-DRA)","decision","A"),
 ("M07",11,"probability","information","A"),
 ("M07",15,"Hangzhou","validation","A"),
 ("M07",15,"36 RMB","validation","B"),
 ("M07",22,"Table 8","validation","B"),
 ("M07",25,"proportion","validation","A"),
 ("M07",26,"future","validation","A"),
]

def norm(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    return re.sub(r"\s+", " ", text).strip().lower()

def main():
    docs = {k: pymupdf.open(v) for k, v in PDF.items()}
    pages = {k: [norm(pg.get_text()) for pg in doc] for k, doc in docs.items()}
    out, failures = [], []
    for paper, page, needle, axis, tier in ENTRIES:
        if not (1 <= page <= len(pages[paper])):
            failures.append((paper, page, needle, "page out of range")); continue
        if norm(needle) not in pages[paper][page - 1]:
            failures.append((paper, page, needle, "needle not on page")); continue
        out.append({"paper": paper, "page": page, "needle": needle, "axis": axis, "tier": tier,
                    "pdf": os.path.relpath(PDF[paper], ROOT).replace(os.sep, "/")})
    targets = os.path.join(ROOT, "research", "round5_20261031", "lit", "citations_m18_m06_m07.json")
    with open(targets, "w", encoding="utf-8") as h:
        json.dump({"schema": "lit_citations/v1", "entries": out}, h, ensure_ascii=False, indent=1)
    print(json.dumps({"verified": len(out), "failed": len(failures),
                      "by_paper": {p: sum(1 for e in out if e["paper"] == p) for p in PDF},
                      "failures": [{"paper": f[0], "page": f[1], "needle": f[2], "why": f[3]} for f in failures]},
                     ensure_ascii=False, indent=1))
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
