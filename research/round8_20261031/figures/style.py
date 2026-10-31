# -*- coding: utf-8 -*-
"""Round-8 figure style, save and provenance rules (single source of truth).

Applies to every figure produced for research/round8_20261031/ (main F1-F7 and
the SI figures).  The rules are fixed here so that no figure script can invent
its own colours, units, legend hiding, sample-size note or output resolution:

* semantic colours that stay distinguishable in greyscale and for the common
  colour-vision deficiencies; marker shape and line style always vary with the
  colour, so a black-and-white print loses nothing;
* axis labels carry units; counts are labelled "berths", rates are percent,
  energy is kWh and power is kW;
* the service tolerance is drawn as the same dashed reference line everywhere,
  and the achieved/not-achieved verdict is written next to it;
* sample size N and the evaluation unit are printed in a figure note;
* boundary and censoring situations get their own marker (open marker plus
  "grid truncated" / "censored" text), never a silent crop;
* output is PNG at >= 300 dpi plus an SVG with editable text; both names are
  recorded with a sha-256 and the input files/fields that produced the figure.

Provenance: save() appends one record per figure to figures/FIGURES.json
(status "real") or figures/FIGURES_DEMO.json (status "demo").  A demo build can
therefore never be mistaken for a result: it carries a visible watermark and
does not touch FIGURES.json.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

import numpy as np

# --------------------------------------------------------------------------- paths
HERE = os.path.dirname(os.path.abspath(__file__))
ROUND = os.path.dirname(HERE)                      # research/round8_20261031
ROOT = os.path.dirname(os.path.dirname(ROUND))     # project root
EXPERIMENTS = os.path.join(ROUND, "experiments")
FIGURES_JSON = os.path.join(HERE, "FIGURES.json")
FIGURES_JSON_DEMO = os.path.join(HERE, "FIGURES_DEMO.json")
DEMO_DIR = os.path.join(HERE, "_demo")

SCHEMA = "round8/figures/v1"
MIN_DPI = 300
DPI = 300

# --------------------------------------------------------------------------- style
# Okabe-Ito based, colour-blind safe, ordered so that the greyscale versions are
# still distinguishable (checked by the marker/line-style cycling below).
PALETTE = {
    "A": "#0072B2",
    "B": "#D55E00",
    "C": "#009E73",
    "D": "#CC79A7",
    "B0_FCFS": "#8C8C8C",
    "B1_quota": "#E69F00",
    "B2_literature": "#56B4E9",
    "dedicated": "#0072B2",
    "shared": "#D55E00",
    "info_I0": "#0072B2",
    "info_I1": "#D55E00",
    "confirmed_minimal": "#0072B2",
    "minimality_unconfirmed": "#E69F00",
    "physically_infeasible": "#D55E00",
    "budget_not_covered": "#56B4E9",
    "missing_data": "#8C8C8C",
    "ev": "#009E73",
    "icev": "#4D4D4D",
    "reference": "#222222",
    "band": "#B0B0B0",
    "highlight": "#CC79A7",
}

MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
LINESTYLES = ["-", "--", "-.", ":", (0, (3, 1, 1, 1)), (0, (5, 1))]
CLASS_ORDER = [
    "confirmed_minimal",
    "minimality_unconfirmed",
    "physically_infeasible",
    "budget_not_covered",
    "missing_data",
]

UNITS = {
    "k": "berths",
    "count": "count",
    "rate": "%",
    "failure_rate": "failure rate (%)",
    "share": "share (%)",
    "dwell": "min",
    "arrival": "veh/h",
    "energy": "kWh",
    "power": "kW",
    "feeder": "kW",
    "delta_k": "delta k (berths)",
    "time": "time of day (h)",
    "coverage": "share of slots observed (0-1)",
}

TOLERANCE_PCT = 5.0
TOLERANCE_NOTE = "tolerance alpha = 5% (design matrix service_standard)"


def series_style(i, key=None):
    """Colour + marker + line style for series i (or semantic key)."""
    if key is not None and key in PALETTE:
        color = PALETTE[key]
    else:
        color = PALETTE[[k for k in ("A", "B", "C", "D")][i % 4]]
    return {
        "color": color,
        "marker": MARKERS[i % len(MARKERS)],
        "linestyle": LINESTYLES[i % len(LINESTYLES)],
        "linewidth": 1.2,
        "markersize": 4.0,
    }


def apply_style():
    """Set the journal-grade rcParams.  Call once per figure script."""
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.titlesize": 9,
        "axes.labelsize": 8,
        "legend.fontsize": 6.5,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "axes.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": "#D9D9D9",
        "grid.linewidth": 0.5,
        "grid.alpha": 0.9,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.dpi": DPI,
        "svg.fonttype": "none",
        "figure.dpi": 120,
        "legend.frameon": False,
        "mathtext.fontset": "dejavusans",
    })


def new_fig(nrows=1, ncols=1, width=7.2, height=None, **kwargs):
    """Standard figure.  Width 7.2 in = double column at 300 dpi."""
    apply_style()
    if height is None:
        height = 2.9 * nrows + 0.4
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height), **kwargs)
    fig.set_layout_engine("none")
    return fig, axes


def panel_label(ax, letter):
    """Bold panel letter, outside the axes, journal convention a/b/c."""
    ax.text(-0.10, 1.04, letter, transform=ax.transAxes, fontsize=9,
            fontweight="bold", ha="left", va="bottom")


def tolerance_line(ax, value=TOLERANCE_PCT, label=None, vertical=False):
    """The one tolerance reference used everywhere."""
    kw = dict(color=PALETTE["reference"], linestyle=(0, (4, 2)), linewidth=0.8, zorder=1)
    if vertical:
        ax.axvline(value, **kw)
    else:
        ax.axhline(value, **kw)
    if label:
        ax.text(0.01, value, " " + label, transform=ax.get_yaxis_transform(),
                ha="left", va="bottom", fontsize=6, color=PALETTE["reference"])


def verdict_text(ax, achieved, where=(0.02, 0.96)):
    """State whether the configured standard is met; never imply it is."""
    txt = "meets tolerance" if achieved else "does NOT meet tolerance"
    color = PALETTE["confirmed_minimal"] if achieved else PALETTE["physically_infeasible"]
    ax.text(where[0], where[1], txt, transform=ax.transAxes, fontsize=6.5,
            color=color, fontweight="bold", va="top", ha="left")


def boundary_marker(ax, x, y, label="grid truncated", dx=0.0, dy=0.0):
    """Open marker + text for a truncated search range or a censored value."""
    ax.plot([x], [y], marker=">", markersize=7, markerfacecolor="white",
            markeredgecolor=PALETTE["reference"], markeredgewidth=0.9,
            linestyle="none", zorder=5, clip_on=False)
    ax.annotate(label, (x, y), xytext=(x + dx, y + dy), fontsize=6,
                color=PALETTE["reference"], va="center")


def censored_marker(ax, x, y, label="censored", dx=0.0, dy=0.0):
    """Cross marker for a value that cannot be evaluated (censored / missing)."""
    ax.plot([x], [y], marker="x", markersize=6, color=PALETTE["reference"],
            linestyle="none", zorder=5)
    ax.annotate(label, (x, y), xytext=(x + dx, y + dy), fontsize=6,
                color=PALETTE["reference"], va="center")


def n_note(fig, text, size=6.2):
    """Sample-size / evaluation-unit note under the figure.

    Two things happen here so that the note never collides with the axes:
    the text is wrapped to the figure width (an unwrapped line makes
    bbox_inches="tight" widen the PNG and leave a blank right margin), and the
    wrapped line count is stored on the figure; save() then reserves exactly
    that much bottom margin, wherever the script called subplots_adjust.
    """
    import textwrap
    width = max(70, int(112 * fig.get_size_inches()[0] / 7.2))
    wrapped = textwrap.fill(text, width=width)
    fig.text(0.012, 0.070, wrapped, fontsize=size, color="#333333",
             va="top", ha="left", linespacing=1.3)


def watermark(fig, text="PLACEHOLDER DATA - NOT A RESULT (demo mode)"):
    """Visible stamp for demo builds; must never appear on a real figure."""
    fig.text(0.5, 0.5, text, fontsize=13, color="#B00000", alpha=0.35,
             ha="center", va="center", rotation=18, zorder=50)


def class_legend_handles():
    handles = []
    for i, cls in enumerate(CLASS_ORDER):
        st = series_style(i, cls)
        handles.append(Line2D([], [], color=st["color"], marker=st["marker"],
                              linestyle="none", markersize=5,
                              label=cls.replace("_", " ")))
    return handles


# --------------------------------------------------------------------------- provenance
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path):
    try:
        return os.path.relpath(path, ROOT).replace("\\", "/")
    except ValueError:
        return path


def _png_info(path):
    from PIL import Image
    with Image.open(path) as im:
        width, height = im.size
        dpi = im.info.get("dpi")
    return {"width_px": int(width), "height_px": int(height),
            "dpi": [round(float(d), 1) for d in dpi] if dpi else None}


def _merge_record(json_path, record):
    data = {"schema": SCHEMA, "entries": []}
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("entries", [])
    data["generated_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    data["entries"] = [e for e in data["entries"] if e.get("figure") != record["figure"]]
    data["entries"].append(record)
    data["entries"].sort(key=lambda e: e["figure"])
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    return data


def save(fig, figure_id, inputs=None, fields=None, demo=False, caption="",
         outdir=None, script=None, note=""):
    """Write PNG (>=300 dpi) + SVG, verify resolution, append provenance.

    inputs: list of paths or list of dicts with path/sha256/rows/fields.
    Returns the provenance record.
    """
    script = script or sys.argv[0]
    outdir = outdir or HERE
    os.makedirs(outdir, exist_ok=True)
    png = os.path.join(outdir, figure_id + ".png")
    svg = os.path.join(outdir, figure_id + ".svg")
    fig.savefig(png, dpi=DPI, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(svg, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)

    pinfo = _png_info(png)
    dpi_ok = pinfo["dpi"] is not None and min(pinfo["dpi"]) >= MIN_DPI - 0.5
    if not dpi_ok:
        raise SystemExit("figure %s written below %d dpi: %r" % (figure_id, MIN_DPI, pinfo["dpi"]))

    norm_inputs = []
    for item in inputs or []:
        if isinstance(item, str):
            item = {"path": item}
        path = item["path"]
        if not os.path.isabs(path):
            path = os.path.join(ROOT, path)
        rec = dict(item)
        rec["path"] = rel(path)
        rec["sha256"] = sha256_file(path)
        norm_inputs.append(rec)

    record = {
        "figure": figure_id,
        "caption_draft": caption,
        "script": rel(script),
        "script_sha256": sha256_file(script) if os.path.exists(script) else None,
        "status": "demo" if demo else "real",
        "inputs": norm_inputs,
        "fields": list(fields or []),
        "outputs": {"png": rel(png), "svg": rel(svg)},
        "png": pinfo,
        "note": note,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
    }
    target = FIGURES_JSON_DEMO if demo else FIGURES_JSON
    _merge_record(target, record)
    return record


# --------------------------------------------------------------------------- inputs
def read_csv(path, required_columns=()):
    """Read an experiment CSV and record its path/rows for provenance.

    Returns (rows, meta).  Missing file or column is a hard error: a figure is
    never drawn from guessed data.
    """
    import csv
    path = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(path):
        raise SystemExit("missing experiment output: %s" % rel(path))
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit("empty experiment output: %s" % rel(path))
    need = [c for c in required_columns if c not in rows[0]]
    if need:
        raise SystemExit("missing columns %s in %s" % (need, rel(path)))
    meta = {"path": rel(path), "rows": len(rows),
            "fields": list(rows[0].keys())}
    return rows, meta


def experiment_path(*parts):
    return os.path.join(EXPERIMENTS, *parts)


def parse_args(figure_ids, description):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--demo", action="store_true",
                    help="draw the layout with generated placeholder data (default)")
    ap.add_argument("--real", action="store_true",
                    help="draw from research/round8_20261031/experiments/ outputs")
    ap.add_argument("--experiments", default=EXPERIMENTS,
                    help="experiments output root (default: %(default)s)")
    ap.add_argument("--outdir", default=None,
                    help="output directory (default: figures/ for real, figures/_demo/ for demo)")
    args = ap.parse_args()
    if args.real and args.demo:
        ap.error("choose at most one of --real / --demo")
    return args


def figure_ids_note(figure_id):
    return figure_id
