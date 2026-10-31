
# -*- coding: utf-8 -*-
"""Build the round-7 supplement from the round-6 supplement: add S7, revise S2/S4/S5, add S6 addendum."""
import os, hashlib
from docx import Document

ROOT = r"C:\Projects\停车场充电桩优化方案"
SRC = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx")
DST = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx")
MAIN = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx")

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

doc = Document(SRC)
paras = list(doc.paragraphs)

def find(prefix):
    for p in paras:
        if p.text.strip().startswith(prefix):
            return p
    raise RuntimeError("not found: " + prefix)

# Intro version statement
p = find("Round-6 working supplement")
p.text = "Round-7 working supplement, 2026-10-31. This file is separate from the manuscript; the main text refers to Supplementary Notes S1-S7. Numbers in S1-S6 are recomputed from the stored machine records named in the audit note S6, and no result in this file is a field measurement. S7 is a historical note on the earlier v1 cost/ETP model and is not evidence for the service-standard results."

# S2 scope
p = find("The proposition below is the only general statement")
p.text = p.text.rstrip() + " In particular, it does not apply to the pi0 rule used in the main comparison, where an EV may fall back to an ordinary berth; the main-text traces show why the fallback reverses the direction."

# S4 unit status
p = find("The heuristic reaches a smaller minimal count in all eight paired units")
p.text = p.text.rstrip() + " The eight units are four lot-seed streams under two rule labels, not eight independent replications: A and B give the same minimum on each stream, and no held-out seed block is used, so this is an exploratory comparison of two implemented policies rather than an independently evaluated effect."

# S5 comparison-type breakdown
p = find("Over the 840 rule pairs, the two rules are both admissible")
p.text = ("Over the 840 rule pairs pooled across the five scenarios, the two rules are both admissible in 677, only the first in 7, only the second in 4 and neither in 152. The comparison types must be kept apart. In the dedicated-versus-shared rows (470 pairs: A vs B, A vs C, A vs D), the shared rule restores admissibility in 0 pairs, lowers the minimal count in 0, improves service at a common k in 4 and worsens it in 0, and 5 pairs are admissible under both rules with disjoint sets. In the shared-versus-shared rows (370 pairs: B vs C, B vs D, C vs D), the shared rule restores admissibility in 4 pairs, lowers the minimal count in 2, improves service at a common k in 0 and worsens it in 6, and no pair is disjoint. These rows are not independent draws and are not summed across types. Only the dedicated-versus-shared rows speak to substitution, and there the shared rule never restores admissibility and never lowers the minimal count.")

# New appendices after the existing S6 table.
def add_heading(text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    return p

def add_plain(text):
    return doc.add_paragraph(text)

add_heading("S6 addendum (round 7)")
add_plain("The round-6 audit table above remains the record for the round-6 files. For this version, the main text is paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx with SHA-256 " + sha(MAIN) + "; this supplement is the file named in the revision report. The builder, statistics reports, render checks and version snapshot are in research/manuscript_revision_20261031/. The round-6 main text (SHA-256 06906f34313f2156beebf1b5e1aa3e2d1d4f2a026fd2f2ffa502a0ccb1fe117a) and the round-6 supplement (SHA-256 2ebc9e832123d5e9ff314220bd985803f84a6b880bed1fb6b9a07b1bd75579f5) are not modified.")

add_heading("S7 The earlier v1 cost/ETP model and its status")
add_plain("The submitted v1 model chose a pile ratio by minimizing a social cost V(m, pi; r) = K_H(m) + E_r[J_H(m, pi; xi)] over candidate ratios, where K_H is installation and maintenance over the operating horizon and J_H collects user time, energy, externality and activity costs. It evaluated the cost at simulated demand and dwell scenarios and reported the ratio and an electrification tipping point at which full installation became cheaper than a partial design under that accounting. The model is described in the round-3/round-4 records and in the retained rev3 working draft; the present supplement does not reproduce its equations or tables.")
add_plain("That exercise is not re-estimated here and is not evidence for the service-standard results of the main text. Its parameters (value of time, complaint and cruising costs, externality factors, relocation cost) are not identified for the site, so the social total is not computable; no old ETP value enters the abstract, results or conclusions of this version. Where the historical model is mentioned in the main text, the sentence is labelled as a historical benchmark and points to this note. The old files and the original manuscript are unchanged.")
add_plain("The distinction is one of object, not of numerical agreement. The service-standard results ask which integer counts satisfy three rate constraints and how the admission rule or an information condition changes that set; the v1 model asked which ratio minimizes a cost and where a cost crossing occurs. Neither question is a test of the other, and the old cost parameters cannot be used to rank the configurations that meet the service standard.")

doc.save(DST)
print("SAVED", DST)
print("MAIN_SHA", sha(MAIN))
print("PARAS", len(doc.paragraphs))
