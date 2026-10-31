
# -*- coding: utf-8 -*-
import os, shutil, hashlib, json
ROOT = "C:/Projects/停车场充电桩优化方案"
SNAP = os.path.join(ROOT, "research/manuscript_revision_20261031/snapshot")
os.makedirs(SNAP, exist_ok=True)
files = [
    "paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx",
    "paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx",
    "research/manuscript_revision_20261031/REPORT.md",
    "research/manuscript_revision_20261031/evidence_map.md",
    "research/manuscript_revision_20261031/acceptance.json",
    "research/manuscript_revision_20261031/paper_stats_rev3_recheck.md",
    "research/manuscript_revision_20261031/paper_stats_rev4.md",
    "research/manuscript_revision_20261031/render/main_rev4.pdf",
    "research/manuscript_revision_20261031/render/si_round7.pdf",
    "paper/SECTIONS.md",
    "docs/PROGRESS.md",
    "docs/TODO.md",
    "repo-discipline.json",
    "literature/index.json",
    "literature/INDEX.md",
]
manifest = []
for rel in files:
    src = os.path.join(ROOT, rel)
    h = hashlib.sha256(open(src, "rb").read()).hexdigest()
    dst = os.path.join(SNAP, os.path.basename(rel))
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copy2(src, dst)
    manifest.append((rel, h))
# old frozen manuscript hashes for independent check
old = [
    "main_paper/Electrification tipping point_manuscript 202603submit.docx",
    "paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx",
    "paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx",
    "paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6.docx",
    "paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx",
]
for rel in old:
    h = hashlib.sha256(open(os.path.join(ROOT, rel), "rb").read()).hexdigest()
    manifest.append((rel, h))
with open(os.path.join(SNAP, "MANIFEST.sha256"), "w", encoding="utf-8") as f:
    for rel, h in manifest:
        f.write("%s  %s\n" % (h, rel))
print("SNAPSHOT", SNAP)
print("FILES", len(manifest))
print("MANIFEST", os.path.join(SNAP, "MANIFEST.sha256"))
