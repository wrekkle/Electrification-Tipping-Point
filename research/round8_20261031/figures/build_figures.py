# -*- coding: utf-8 -*-
"""Build all round-8 main figures (F1-F7) and verify resolution + provenance.

Usage:
  python build_figures.py            # demo layout check (writes figures/_demo/)
  python build_figures.py --real     # real build from experiments/ machine outputs

In demo mode every figure carries a visible PLACEHOLDER watermark and provenance
goes to FIGURES_DEMO.json; FIGURES.json is never touched, so a placeholder can
never be read as a result.  In real mode the script refuses to run unless the
experiment outputs exist, and it verifies that every figure was written with
status "real", at >= 300 dpi, with an SVG next to the PNG.
"""

import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import style as S

MODULES = ["f1_data", "f2_curve", "f3_feasible", "f4_rules", "f5_info",
           "f6_energy", "f7_trace"]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    real = "--real" in argv
    if real and not os.path.isdir(S.EXPERIMENTS):
        print("missing experiments directory: %s" % S.EXPERIMENTS)
        return 2
    outdir = S.HERE if real else S.DEMO_DIR
    os.makedirs(outdir, exist_ok=True)
    real_json_before = os.path.getmtime(S.FIGURES_JSON) if os.path.exists(S.FIGURES_JSON) else None
    records = []
    for name in MODULES:
        mod = __import__(name)
        rec = mod.build(mode="real" if real else "demo", outdir=outdir,
                        experiments=S.EXPERIMENTS)
        records.append(rec)
    # ---- verify
    problems = []
    for rec in records:
        png = os.path.join(S.ROOT, rec["outputs"]["png"])
        svg = os.path.join(S.ROOT, rec["outputs"]["svg"])
        if not os.path.exists(png):
            problems.append("missing PNG for %s" % rec["figure"])
            continue
        if not os.path.exists(svg):
            problems.append("missing SVG for %s" % rec["figure"])
        with Image.open(png) as im:
            dpi = im.info.get("dpi")
        if dpi is None or min(dpi) < S.MIN_DPI - 0.5:
            problems.append("%s written below %d dpi: %r" % (rec["figure"], S.MIN_DPI, dpi))
        if rec["status"] != ("real" if real else "demo"):
            problems.append("%s has unexpected status %s" % (rec["figure"], rec["status"]))
    if not real and os.path.exists(S.FIGURES_JSON):
        after = os.path.getmtime(S.FIGURES_JSON)
        if real_json_before is None or after != real_json_before:
            problems.append("demo build touched FIGURES.json")
        if any(r["figure"] == "F1" for r in json.load(open(S.FIGURES_JSON, encoding="utf-8"))["entries"]):
            pass
    print(json.dumps({"mode": "real" if real else "demo", "outdir": S.rel(outdir),
                      "figures": [{"figure": r["figure"], "status": r["status"],
                                   "png": r["outputs"]["png"], "svg": r["outputs"]["svg"],
                                   "px": r["png"]["width_px"], "dpi": r["png"]["dpi"]}
                                  for r in records],
                      "problems": problems}, ensure_ascii=False, indent=1))
    if problems:
        print("VERIFY FAILED:", len(problems))
        return 1
    print("VERIFY OK: %d figures, PNG>=300 dpi + SVG, provenance in %s"
          % (len(records), S.rel(S.FIGURES_JSON if real else S.FIGURES_JSON_DEMO)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
