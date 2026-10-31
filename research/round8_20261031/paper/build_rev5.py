# -*- coding: utf-8 -*-
"""Build the rev5 working draft and SI skeleton (round 8, C paper track).

Template: paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx
  The template supplies styles, page setup and table style only; its body is
  cleared before the new content is written, so no rev4 paragraph survives in
  the new file.  The rev4 file, the frozen submission and every earlier draft
  are opened read-only and can never be an output path.

Structure (checked): problem - model - methods - data - results - discussion -
reproducibility, i.e. the seven h1 sections listed in
content_rev5.REQUIRED_SECTIONS, in that order.

Modes:
  --skeleton (default) writes the scaffolding: no figure is embedded, every
      empirical number appears as [UNRESOLVED:token], and the document starts
      with an explicit SKELETON warning.  This is a layout/provenance check.
  --real (strict) refuses to save unless every number token resolves to an
      experiment output, every planned figure exists with provenance status
      "real" at >= 300 dpi, and no placeholder string remains.

Every build writes a manifest next to the output with input/output sha256, the
resolved number list (token -> value -> file/row/column/sha256), unresolved
tokens, figure records and word counts.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
ROUND = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(ROUND))
sys.path.insert(0, HERE)

import content_rev5 as C          # noqa: E402
import evidence as EV            # noqa: E402

TEMPLATE = os.path.join(ROOT, "paper", "draft",
                        "Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx")
FROZEN = os.path.join(ROOT, "main_paper",
                      "Electrification tipping point_manuscript 202603submit.docx")
OLD_DRAFTS = [os.path.join(ROOT, "paper", "draft", name) for name in (
    "Electrification_tipping_point_v2_draft_2026-10-29.docx",
    "Electrification_tipping_point_v2_draft_2026-10-30.docx",
    "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx",
    "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx",
    "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx",
    "Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx",
)]
OUT_DEFAULT = {
    "main": os.path.join(HERE, "Electrification_tipping_point_v2_draft_rev5.docx"),
    "si": os.path.join(HERE, "Electrification_tipping_point_v2_supplementary_rev5.docx"),
}
FIGURES_JSON = os.path.join(ROUND, "figures", "FIGURES.json")
PLACEHOLDER_PATTERNS = ("[TBD]", "SKELETON", "UNRESOLVED", "placeholder", "to be drawn")
FIGURES = {}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clone_template():
    doc = Document(TEMPLATE)
    body = doc.element.body
    sect = body.find(qn("w:sectPr"))
    for child in list(body):
        if child is sect:
            continue
        body.remove(child)
    return doc


def _style(doc, name):
    try:
        return doc.styles[name]
    except KeyError:
        return doc.styles["Normal"]


def add_para(doc, text, style="Normal", bold=False, size=None, align=None):
    p = doc.add_paragraph(style=_style(doc, style))
    run = p.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return p


def add_table(doc, spec, evidence):
    caption = evidence.resolve_text(spec["caption"], C.NUMBER_SPECS)
    add_para(doc, caption, style="Caption")
    rows = [spec["header"]] + evidence.resolve_cells(spec["rows"], C.NUMBER_SPECS)
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    try:
        table.style = doc.styles["Table Grid"]
    except KeyError:
        pass
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j, cell_text in enumerate(row):
            cell = table.cell(i, j)
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(cell_text))
            run.font.size = Pt(8)
            run.bold = (i == 0)
    return table


def load_figures():
    if not os.path.exists(FIGURES_JSON):
        return {}
    with open(FIGURES_JSON, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {entry["figure"]: entry for entry in data.get("entries", [])}


def add_figure(doc, figure_id, number, caption, manifest):
    entry = FIGURES.get(figure_id)
    png = os.path.join(ROOT, entry["outputs"]["png"]) if entry else None
    real = bool(entry and entry.get("status") == "real" and png and os.path.exists(png))
    if real:
        doc.add_picture(png, width=Inches(6.3))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        manifest["figures_embedded"].append(figure_id)
    else:
        add_para(doc, "[" + figure_id + " NOT EMBEDDED - no real figure with provenance yet]",
                 align="center")
        manifest["figures_not_embedded"].append(figure_id)
    add_para(doc, "Fig. %d %s" % (number, caption), style="Caption")
    manifest["figure_records"].append({
        "figure": figure_id,
        "embedded": real,
        "status": entry.get("status") if entry else None,
        "png": entry["outputs"]["png"] if entry else None,
        "provenance_record": bool(entry),
    })


def build_main(doc, evidence, manifest):
    add_para(doc, evidence.resolve_text(C.TITLE, C.NUMBER_SPECS), bold=True)
    add_para(doc, "Abstract")
    add_para(doc, evidence.resolve_text(C.ABSTRACT, C.NUMBER_SPECS))
    add_para(doc, evidence.resolve_text(C.KEYWORDS, C.NUMBER_SPECS))
    heads = []
    fig_no = 0
    captions = {f[0]: f[1] for f in C.FIGURE_PLAN}
    for block in C.MAIN:
        kind = block[0]
        if kind == "h1":
            add_para(doc, evidence.resolve_text(block[1], C.NUMBER_SPECS), style="Heading 1")
            heads.append(block[1])
        elif kind == "h2":
            add_para(doc, evidence.resolve_text(block[1], C.NUMBER_SPECS), style="Heading 2")
        elif kind == "p":
            add_para(doc, evidence.resolve_text(block[1], C.NUMBER_SPECS))
        elif kind == "caption":
            add_para(doc, evidence.resolve_text(block[1], C.NUMBER_SPECS), style="Caption")
        elif kind == "figure":
            fig_no += 1
            add_figure(doc, block[1], fig_no, captions.get(block[1], block[1]), manifest)
        elif kind == "table":
            add_table(doc, block[1], evidence)
        else:
            raise SystemExit("unknown block kind: %r" % (kind,))
    manifest["h1_sections"] = heads
    core = [h for h in heads if h in C.REQUIRED_SECTIONS]
    manifest["structure_ok"] = core[:len(C.REQUIRED_SECTIONS)] == C.REQUIRED_SECTIONS


def build_si(doc, evidence, manifest):
    heads = []
    captions = {f[0]: f[1] for f in C.FIGURE_PLAN}
    fig_no = 0
    for block in C.SI:
        if block[0] == "h1":
            add_para(doc, evidence.resolve_text(block[1], C.NUMBER_SPECS), style="Heading 1")
            heads.append(block[1])
        elif block[0] == "h2":
            add_para(doc, evidence.resolve_text(block[1], C.NUMBER_SPECS), style="Heading 2")
        elif block[0] == "figure":
            fig_no += 1
            add_figure(doc, block[1], fig_no, captions.get(block[1], block[1]), manifest)
        elif block[0] == "table":
            add_table(doc, block[1], evidence)
        else:
            add_para(doc, evidence.resolve_text(block[1], C.NUMBER_SPECS))
    manifest["h1_sections"] = heads
    manifest["structure_ok"] = len(heads) == 7 and heads[0].startswith("S1 ")


def count_words(doc):
    text = "\n".join(p.text for p in doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text += "\n" + cell.text
    return len(re.findall(r"[A-Za-z]+", text)), len(text)


def check_path(out):
    out = os.path.abspath(out)
    forbidden = [os.path.abspath(FROZEN)] + [os.path.abspath(p) for p in OLD_DRAFTS]
    if out in forbidden:
        raise SystemExit("refusing to overwrite the frozen submission or an earlier draft: " + out)
    parent = os.path.abspath(os.path.dirname(out))
    allowed = [os.path.abspath(HERE), os.path.join(ROOT, "paper", "draft")]
    if not any(parent == os.path.abspath(a) or parent.startswith(os.path.abspath(a) + os.sep)
               for a in allowed):
        raise SystemExit("output must stay in %s or paper/draft: %s" % (HERE, out))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the round-8 rev5 draft/SI skeleton.")
    ap.add_argument("--doc", choices=("main", "si"), default="main")
    ap.add_argument("--out", default=None)
    ap.add_argument("--real", action="store_true",
                    help="strict build from machine outputs (default: skeleton)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    out = check_path(args.out or OUT_DEFAULT[args.doc])
    if os.path.exists(out) and not args.force:
        raise SystemExit("output exists, pass --force: " + out)
    if not os.path.exists(TEMPLATE):
        raise SystemExit("template draft missing: " + TEMPLATE)

    global FIGURES
    FIGURES = load_figures()
    manifest = {
        "schema": "round8/rev5_build/v1",
        "mode": "real" if args.real else "skeleton",
        "document": args.doc,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "template": {"path": os.path.relpath(TEMPLATE, ROOT), "sha256": sha256(TEMPLATE),
                     "note": "styles and section properties only; body cleared"},
        "output": {"path": os.path.relpath(out, ROOT)},
        "figures_embedded": [],
        "figures_not_embedded": [],
        "figure_records": [],
    }
    if os.path.exists(FIGURES_JSON):
        manifest["figures_json"] = {"path": os.path.relpath(FIGURES_JSON, ROOT),
                                    "sha256": sha256(FIGURES_JSON)}

    doc = clone_template()
    if not args.real:
        add_para(doc, "SKELETON BUILD - no empirical result is contained in this file. "
                      "Every number appears as [UNRESOLVED:token] until the experiments "
                      "outputs exist; run build_rev5.py --real to produce a draft.",
                 bold=True)

    evidence = EV.Evidence(ROUND, strict=args.real)
    if args.doc == "main":
        build_main(doc, evidence, manifest)
    else:
        build_si(doc, evidence, manifest)

    refs_used = []
    for p in doc.paragraphs:
        for key in re.findall(r"\{([A-Z][A-Z0-9]*)\}", p.text):
            if key not in refs_used:
                refs_used.append(key)
    manifest["references_cited"] = refs_used
    manifest["references_defined"] = sorted(C.REFS)

    words, chars = count_words(doc)
    manifest["word_count"] = words
    manifest["char_count"] = chars
    manifest["paragraphs"] = len(doc.paragraphs)
    manifest["tables"] = len(doc.tables)
    manifest["unresolved_numbers"] = evidence.unresolved
    manifest["unresolved_citation_keys"] = [k for k in refs_used if k not in C.REFS]
    manifest["numbers"] = evidence.records

    all_text = "\n".join(p.text for p in doc.paragraphs)
    manifest["placeholder_hits"] = {pat: all_text.count(pat) for pat in PLACEHOLDER_PATTERNS}
    problems = []
    if not manifest["structure_ok"]:
        problems.append("section structure does not match the required order")
    if evidence.unresolved:
        problems.append("%d unresolved number tokens" % len(evidence.unresolved))
    if manifest["unresolved_citation_keys"]:
        problems.append("%d unresolved citation keys"
                        % len(manifest["unresolved_citation_keys"]))
    if args.real:
        if manifest["figures_not_embedded"]:
            problems.append("figures without real provenance: %s"
                            % manifest["figures_not_embedded"])
        bad = {k: v for k, v in manifest["placeholder_hits"].items() if v}
        if bad:
            problems.append("placeholder strings remain: %r" % bad)
    manifest["problems"] = problems

    if args.real and problems:
        manifest["output"]["sha256"] = None
        manifest["output"]["bytes"] = None
        manifest["output"]["written"] = False
        manifest_path = os.path.join(os.path.dirname(out),
                                     "build_rev5_%s_manifest.json" % args.doc)
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=1)
        ev_path = os.path.join(os.path.dirname(out), "evidence_rev5_%s.json" % args.doc)
        with open(ev_path, "w", encoding="utf-8") as fh:
            json.dump(evidence.manifest(), fh, ensure_ascii=False, indent=1)
        print(json.dumps({
            "mode": manifest["mode"], "document": args.doc,
            "written": False, "problems": problems,
            "unresolved_numbers": len(evidence.unresolved),
            "figures_not_embedded": manifest["figures_not_embedded"],
        }, ensure_ascii=False, indent=1))
        print("REAL BUILD REFUSED - no document written")
        return 1

    os.makedirs(os.path.dirname(out), exist_ok=True)
    doc.save(out)
    manifest["output"]["written"] = True
    manifest["output"]["sha256"] = sha256(out)
    manifest["output"]["bytes"] = os.path.getsize(out)
    manifest_path = os.path.join(os.path.dirname(out),
                                 "build_rev5_%s_manifest.json" % args.doc)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    ev_path = os.path.join(os.path.dirname(out), "evidence_rev5_%s.json" % args.doc)
    with open(ev_path, "w", encoding="utf-8") as fh:
        json.dump(evidence.manifest(), fh, ensure_ascii=False, indent=1)

    print(json.dumps({
        "mode": manifest["mode"], "document": args.doc,
        "out": manifest["output"]["path"], "bytes": manifest["output"]["bytes"],
        "paragraphs": manifest["paragraphs"], "tables": manifest["tables"],
        "word_count": manifest["word_count"], "h1": manifest["h1_sections"],
        "unresolved_numbers": len(evidence.unresolved),
        "figures_embedded": manifest["figures_embedded"],
        "figures_not_embedded": manifest["figures_not_embedded"],
        "problems": problems,
    }, ensure_ascii=False, indent=1))
    if problems and args.real:
        print("REAL BUILD FAILED")
        return 1
    if problems and not args.real:
        print("skeleton build: %d open items (expected in skeleton mode)" % len(problems))
    return 0


if __name__ == "__main__":
    sys.exit(main())
