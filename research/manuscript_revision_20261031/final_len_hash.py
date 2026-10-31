# -*- coding: utf-8 -*-
import os,hashlib
ROOT="C:/Projects/停车场充电桩优化方案"
for f in ["paper/SECTIONS.md","docs/PROGRESS.md","docs/TODO.md","repo-discipline.json"]:
    print(f, len(open(os.path.join(ROOT,f),encoding="utf-8").read()))
print("--- REPORT hash lines ---")
for line in open(os.path.join(ROOT,"research/manuscript_revision_20261031/REPORT.md"),encoding="utf-8"):
    if "SHA-256" in line or "2ddff" in line or "3256ab" in line: print(line.strip())
print("--- snapshot manifest head ---")
for line in open(os.path.join(ROOT,"research/manuscript_revision_20261031/snapshot/MANIFEST.sha256"),encoding="utf-8"):
    if "round7_rev4" in line or "supplementary_2026-10-31_round7" in line: print(line.strip())
