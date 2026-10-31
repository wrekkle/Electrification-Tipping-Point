# -*- coding: utf-8 -*-
"""Build the round-6 working draft on top of the registered working draft.

Base : paper/draft/Electrification_tipping_point_v2_draft_2026-10-30.docx
       (registered in paper/SECTIONS.md; the submitted manuscript it was built
       from stays frozen and is never opened for writing here)
Out  : paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx

The script applies an explicit list of operations from paper_v3_round6_rev3_content.py
(in-place paragraph rewrites, heading renames, one appended sentence, and
inserted blocks), converts {KEY} tokens into superscript numbers, appends the
new reference entries in order of first use, and then verifies the result:
no unresolved token, every reference cited, every citation number within range,
and a manifest with input and output hashes. Nothing is overwritten unless
--force is given, and the frozen submission is refused as an output path.
"""
import argparse
import copy
import hashlib
import io
import json
import os
import re
import sys
import datetime

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from paper_v3_round6_rev3_content import OPS, REFS, NOTES  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-30.docx")
OUT_DEFAULT = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx")
REV_PREV = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx")
REV1 = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx")
FROZEN = os.path.join(ROOT, "main_paper", "Electrification tipping point_manuscript 202603submit.docx")
TABLES = os.path.join(ROOT, "research", "round6_20261031", "c_paper", "tables_rev2.json")
MANIFEST = os.path.join(ROOT, "research", "round6_20261031", "c_paper", "build_manifest_rev3.json")

CIT = re.compile(r"\{([A-Z0-9][A-Z0-9,]*(?:\s*,\s*[A-Z0-9]+)*)\}")
LIT = re.compile(r"\[\[([0-9][0-9,\-\u2013 ]*)\]\]")
NUM = re.compile(r"\d+")
TB = re.compile(r"Table (\d+)")
TBC = re.compile(r"^Table (\d+) ")
FG = re.compile(r"Fig\. (\d+)")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_para(doc, kind, text):
    for p in doc.paragraphs:
        st = p.style.name
        if kind == "h1" and st != "Heading 1":
            continue
        if kind == "h2" and st != "Heading 2":
            continue
        if kind == "p" and st not in ("Normal",):
            continue
        if kind == "any":
            pass
        if p.text.strip().startswith(text):
            return p
    raise SystemExit("anchor not found: %s %s" % (kind, text))


def make_table(doc, spec):
    header, rows = spec["header"], spec["rows"]
    widths = spec.get("widths") or [1.0] * len(header)
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False

    def put(cell, text, bold=False):
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(text)
        run.font.size = Pt(8)
        run.bold = bold

    for j, txt in enumerate(header):
        put(t.cell(0, j), txt, True)
    for i, row in enumerate(rows, start=1):
        for j, txt in enumerate(row):
            put(t.cell(i, j), txt)
    for j, w in enumerate(widths):
        t.columns[j].width = Inches(w)
        for cell in t.columns[j].cells:
            cell.width = Inches(w)
    t.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    if spec.get("cant_split", True):
        for row in t.rows:
            row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    return t._tbl


def main():
    ap = argparse.ArgumentParser(description="Build the round-6 working draft.")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    if out in (os.path.abspath(SRC), os.path.abspath(FROZEN), os.path.abspath(REV_PREV), os.path.abspath(REV1)):
        raise SystemExit("refuse to overwrite the source draft or the frozen submission")
    if os.path.basename(out) != "draft" and os.path.basename(os.path.dirname(out)) != "draft":
        raise SystemExit("output must stay in paper/draft: " + out)
    if os.path.exists(out) and not args.force:
        raise SystemExit("output exists, pass --force: " + out)
    if not os.path.exists(SRC):
        raise SystemExit("base draft missing: " + SRC)

    tables = json.load(io.open(TABLES, encoding="utf-8"))["tables"]
    doc = Document(SRC)

    body_t = find_para(doc, "p", "Our findings indicate that charging pile planning")
    h2_t = find_para(doc, "h2", "Sensitivity analysis")
    bib_t = None
    for p in doc.paragraphs:
        if p.style.name == "Bibliography" and p.text.strip():
            bib_t = p
            break
    cap_t = None
    for p in doc.paragraphs:
        if p.style.name == "Caption" and p.text.strip():
            cap_t = p
            break

    def rpr_of(p):
        for r in p.runs:
            if r._r.find(qn("w:rPr")) is not None:
                return copy.deepcopy(r._r.find(qn("w:rPr")))
        return None

    body_rpr = rpr_of(body_t)
    h2_rpr = rpr_of(h2_t)
    bib_rpr = rpr_of(bib_t)
    cap_rpr = rpr_of(cap_t) if cap_t is not None else None

    def note_rpr():
        rp = copy.deepcopy(body_rpr) if body_rpr is not None else OxmlElement("w:rPr")
        for tag in ("w:sz", "w:szCs"):
            for el in rp.findall(qn(tag)):
                rp.remove(el)
        sz = OxmlElement("w:sz"); sz.set(qn("w:val"), "16"); rp.append(sz)
        szcs = OxmlElement("w:szCs"); szcs.set(qn("w:val"), "16"); rp.append(szcs)
        return rp

    def make_el(tmpl_p, tmpl_rpr, segments):
        el = copy.deepcopy(tmpl_p._p)
        for ch in list(el):
            if ch.tag != qn("w:pPr"):
                el.remove(ch)
        for text, sup in segments:
            r = OxmlElement("w:r")
            if tmpl_rpr is not None:
                r.append(copy.deepcopy(tmpl_rpr))
            if sup:
                rp = r.find(qn("w:rPr"))
                if rp is None:
                    rp = OxmlElement("w:rPr"); r.insert(0, rp)
                for va in rp.findall(qn("w:vertAlign")):
                    rp.remove(va)
                va = OxmlElement("w:vertAlign"); va.set(qn("w:val"), "superscript"); rp.append(va)
            t = OxmlElement("w:t"); t.text = text
            t.set(qn("xml:space"), "preserve")
            r.append(t)
            el.append(r)
        return el

    refs_existing = [p for p in doc.paragraphs if p.style.name == "Bibliography" and p.text.strip()]
    BASE = len(refs_existing) + 1
    order, num = [], {}

    def cite_segments(text):
        """Tokens: {KEY} -> superscript number of a new reference entry,
        [[34-36]] -> literal superscript numbers reused from the base list."""
        segs, pos = [], 0
        pattern = re.compile(CIT.pattern + "|" + LIT.pattern)
        for m in pattern.finditer(text):
            if m.start() > pos:
                segs.append((text[pos:m.start()], False))
            if m.group(1) is not None:
                toks = [x.strip() for x in m.group(1).split(",")]
                for tok in toks:
                    if tok not in REFS:
                        raise SystemExit("no reference entry for token {%s}" % tok)
                    if tok not in num:
                        num[tok] = BASE + len(order)
                        order.append(tok)
                segs.append((", ".join(str(num[t]) for t in toks), True))
            else:
                segs.append((m.group(2).strip(), True))
            pos = m.end()
        if pos < len(text):
            segs.append((text[pos:], False))
        return segs

    def keep_with_next(el):
        pPr = el.find(qn("w:pPr"))
        if pPr is None:
            pPr = OxmlElement("w:pPr")
            el.insert(0, pPr)
        kn = OxmlElement("w:keepNext")
        pStyle = pPr.find(qn("w:pStyle"))
        if pStyle is not None:
            pStyle.addnext(kn)
        else:
            pPr.insert(0, kn)

    applied = []
    for op in OPS:
        kind = op["kind"]
        anchor = find_para(doc, op["anchor"][0], op["anchor"][1])
        if kind == "rename":
            runs = anchor.runs
            if not runs:
                raise SystemExit("rename target has no run: " + op["anchor"][1])
            runs[0].text = op["text"]
            for r in runs[1:]:
                r._r.getparent().remove(r._r)
            applied.append({"op": "rename", "anchor": op["anchor"], "text": op["text"]})
            continue
        if kind == "append":
            segs = cite_segments(op["text"])
            plain = [r for r in anchor.runs if not r.font.superscript]
            if not plain:
                raise SystemExit("append target has no plain run: " + op["anchor"][1])
            last = plain[-1]
            for text, sup in segs:
                new_r = copy.deepcopy(last._r)
                for t in new_r.findall(qn("w:t")):
                    new_r.remove(t)
                if sup:
                    rp = new_r.find(qn("w:rPr"))
                    if rp is None:
                        rp = OxmlElement("w:rPr"); new_r.insert(0, rp)
                    for va in rp.findall(qn("w:vertAlign")):
                        rp.remove(va)
                    va = OxmlElement("w:vertAlign"); va.set(qn("w:val"), "superscript"); rp.append(va)
                t = OxmlElement("w:t"); t.text = text
                t.set(qn("xml:space"), "preserve"); new_r.append(t)
                last._r.addnext(new_r)
                last = anchor.runs[-1] if False else last
            # rebuild anchor reference to the newly appended el
            applied.append({"op": "append", "anchor": op["anchor"], "chars": len(op["text"])})
            continue
        if kind == "pagebreak":
            pPr = anchor._p.find(qn("w:pPr"))
            if pPr is None:
                pPr = OxmlElement("w:pPr")
                anchor._p.insert(0, pPr)
            pbb = OxmlElement("w:pageBreakBefore")
            anchor_after = None
            for tag in ("w:pStyle", "w:keepNext", "w:keepLines"):
                el = pPr.find(qn(tag))
                if el is not None:
                    anchor_after = el
            if anchor_after is not None:
                anchor_after.addnext(pbb)
            else:
                pPr.insert(0, pbb)
            applied.append({"op": "pagebreak", "anchor": op["anchor"]})
            continue
        if kind == "style":
            anchor.style = doc.styles[op["style"]]
            applied.append({"op": "style", "anchor": op["anchor"], "style": op["style"]})
            continue
        if kind == "delete":
            el = anchor._p
            el.getparent().remove(el)
            applied.append({"op": "delete", "anchor": op["anchor"]})
            continue
        if kind == "subtext":
            old_s, new_s = op["old"], op["new"]
            want = anchor.text.count(old_s)
            for r in anchor.runs:
                if old_s in r.text:
                    r.text = r.text.replace(old_s, new_s)
            run_level = anchor.text.count(old_s) == 0
            if anchor.text.count(old_s) != 0:
                full = anchor.text.replace(old_s, new_s)
                new_el = make_el(body_t, body_rpr, [(full, False)])
                anchor._p.addprevious(new_el)
                anchor._p.getparent().remove(anchor._p)
            applied.append({"op": "subtext", "anchor": op["anchor"], "old": old_s,
                            "new": new_s, "occurrences": want, "run_level": run_level})
            continue
        if kind == "replace":
            tmpl_p = anchor if op.get("tmpl") == "self" else body_t
            tmpl_rpr = rpr_of(anchor) if op.get("tmpl") == "self" else body_rpr
            new_el = make_el(tmpl_p, tmpl_rpr, cite_segments(op["nodes"][0][1]))
            anchor._p.addprevious(new_el)
            anchor._p.getparent().remove(anchor._p)
            applied.append({"op": "replace", "anchor": op["anchor"]})
            continue
        if kind == "insert":
            cursor = anchor._p
            prev_el = None
            count = 0
            for node_kind, payload in op["nodes"]:
                if node_kind == "table":
                    if prev_el is not None and prev_el.tag == qn("w:p"):
                        keep_with_next(prev_el)
                    el = make_table(doc, tables[payload])
                elif node_kind == "h2":
                    el = make_el(h2_t, h2_rpr, [(payload, False)])
                elif node_kind == "caption":
                    el = make_el(cap_t if cap_t is not None else body_t,
                                 cap_rpr if cap_rpr is not None else body_rpr,
                                 [(payload, False)])
                elif node_kind == "note":
                    el = make_el(body_t, note_rpr(), [(NOTES[payload], False)])
                elif node_kind == "eq":
                    el = make_el(body_t, body_rpr, [(payload, False)])
                else:
                    el = make_el(body_t, body_rpr, cite_segments(payload))
                if op["pos"] == "before":
                    cursor.addprevious(el)
                else:
                    cursor.addnext(el)
                    cursor = el
                prev_el = el
                count += 1
            applied.append({"op": "insert", "anchor": op["anchor"], "pos": op["pos"], "nodes": count})
            continue
        raise SystemExit("unknown op: " + kind)

    # append new reference entries in order of first use, after the last one
    bib_all = [p for p in doc.paragraphs if p.style.name == "Bibliography"]
    target = [p for p in bib_all if p.text.strip()][-1]._p
    for tok in order:
        el = make_el(bib_t, bib_rpr, [(REFS[tok], False)])
        target.addnext(el)
        target = el

    dropped_bib = 0
    for p in list(doc.paragraphs):
        if p.style.name == "Bibliography" and not p.text.strip():
            p._p.getparent().remove(p._p)
            dropped_bib += 1
    print("empty bibliography paragraphs removed:", dropped_bib)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    doc.save(out)

    # ---------------------------------------------------------------- verify
    v = Document(out)
    paras = v.paragraphs
    bib = [p for p in paras if p.style.name == "Bibliography" and p.text.strip()]
    body_paras = [p for p in paras if p.style.name != "Bibliography"]
    left = [p.text for p in paras if CIT.search(p.text)]
    # Citations were written by Word as many short superscript runs with empty
    # runs interleaved ("2", "", "-", "", "4"), so a plain text match would
    # either lose the range or concatenate neighbouring marks. The tokenizer
    # below walks the non-empty superscript runs in document order: a digit run
    # followed by a dash run is read as a range, otherwise each digit run is one
    # citation number.
    sup_tokens = set()
    for p in body_paras:
        seq = [r.text.strip() for r in p.runs if r.font.superscript and r.text.strip()]
        i = 0
        while i < len(seq):
            t = seq[i]
            if t.isdigit():
                n = int(t)
                if i + 2 < len(seq) and seq[i + 1] == "-" and seq[i + 2].isdigit():
                    m = int(seq[i + 2])
                    sup_tokens.update(range(min(n, m), max(n, m) + 1))
                    i += 3
                else:
                    sup_tokens.add(n)
                    i += 1
                continue
            if t in ("-", ","):
                i += 1
                continue
            for part in t.replace(";", ",").split(","):
                part = part.strip()
                for dash in ("-", "–", "—"):
                    part = part.replace(dash, "-")
                if "-" in part:
                    a_s, _, b_s = part.partition("-")
                    if a_s.strip().isdigit() and b_s.strip().isdigit():
                        a, b = int(a_s), int(b_s)
                        sup_tokens.update(range(min(a, b), max(a, b) + 1))
                        i += 1
                        continue
                for m in NUM.finditer(part):
                    sup_tokens.add(int(m.group(0)))
            i += 1
    total_refs = len(bib)
    over = sorted(t for t in sup_tokens if t > total_refs)
    missing_refs = [i for i in range(1, total_refs + 1) if i not in sup_tokens]
    words = lambda s: len(re.findall(r"[A-Za-z]+", s))
    checks = {
        "unresolved_citation_tokens": left,
        "references_total": total_refs,
        "new_reference_numbers": {k: v for k, v in num.items()},
        "citation_numbers_out_of_range": over,
        "reference_numbers_never_cited_in_body": missing_refs,
        "paragraphs": len(paras),
        "tables": len(v.tables),
        "headings_h1": [p.text for p in paras if p.style.name == "Heading 1"],
        "headings_h2": [p.text for p in paras if p.style.name == "Heading 2"],
        "word_count_all_paragraphs": sum(words(p.text) for p in paras),
        "pending_production_strings": {
            "placeholder": sum(p.text.count("placeholder") for p in paras),
            "to be produced": sum(p.text.count("to be produced") for p in paras),
            "To be drawn": sum(p.text.count("To be drawn") for p in paras),
            "to be reassigned": sum(p.text.count("to be reassigned") for p in paras),
        },
        "table_numbers_referenced": sorted({int(m.group(1)) for p in paras for m in TB.finditer(p.text)}),
        "table_caption_numbers": sorted({int(m.group(1)) for p in paras for m in TBC.finditer(p.text)}),
        "figure_numbers_referenced": sorted({int(m.group(1)) for p in paras for m in FG.finditer(p.text)}),
        "bibliography_total_paragraphs": len([p for p in paras if p.style.name == "Bibliography"]),
        "bibliography_nonempty": total_refs,
    }
    manifest = {
        "schema": "round6/paper_build/v1",
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": "python paper/draft/build_paper_v3_round6_rev3.py",
        "interpreter": sys.executable + " | " + sys.version.split()[0],
        "base": {"path": os.path.relpath(SRC, ROOT), "sha256": sha256(SRC)},
        "output": {"path": os.path.relpath(out, ROOT), "sha256": sha256(out),
                   "bytes": os.path.getsize(out)},
        "tables_json": {"path": os.path.relpath(TABLES, ROOT), "sha256": sha256(TABLES)},
        "ops_applied": applied,
        "checks": checks,
    }
    with io.open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: checks[k] for k in ("references_total", "citation_numbers_out_of_range",
                                            "reference_numbers_never_cited_in_body", "paragraphs", "tables",
                                            "word_count_all_paragraphs")}, ensure_ascii=False))
    print("unresolved tokens:", left[:5])
    print("new refs:", json.dumps(num))
    print("saved:", out, os.path.getsize(out))
    print("manifest:", MANIFEST)
    pend = checks["pending_production_strings"]
    pend_total = sum(pend.values())
    if left or over or missing_refs or pend_total:
        print("CHECK FAILED: token/range/reference/pending mismatch", pend)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
