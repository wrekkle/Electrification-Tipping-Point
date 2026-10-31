# -*- coding: utf-8 -*-
"""SI tables for the round-6 supplementary file (S1-S6). Machine JSON -> tables_si.json."""
import json, io, os, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CP = os.path.join(ROOT, "research", "round6_20261031", "c_paper")
def load(p):
    with io.open(p, encoding="utf-8") as fh:
        return json.load(fh)
def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

Q1 = os.path.join(ROOT, "research", "round6_20261031", "b_mechanism", "q1_traces.json")
Q2 = os.path.join(ROOT, "research", "round6_20261031", "a_info", "q2_info_regimes.json")
Q3 = os.path.join(ROOT, "research", "round6_20261031", "b_feasible", "q3_feasible_sets.json")
SEM = os.path.join(ROOT, "research", "round6_20261031", "a_semantics", "recompute_59_curves.json")

tables = {}

# ---- S1 semantics
sem = load(SEM)
ju = sem["joint_units"]
rows = [
    ["Three constraints, zero-demand rate skipped (inclusive)", str(ju["three_na_skip"]), "975", "Pre-registered reading of the convention used in the submitted model"],
    ["Three constraints, every rate required valid (strict)", str(ju["three_strict"]), "975", "Same records, zero-demand rate treated as not satisfied"],
    ["Four constraints, five-state reading", str(ju["four_na_skip"]), "975", "Adds the energy shortfall rate at 5% under the five-state definition"],
    ["Four constraints, strict", str(ju["four_strict"]), "975", "Strict reading with the energy rate scored"],
    ["Four constraints, legacy skip of every zero denominator", str(ju["four_legacy_zero_denominator_skip"]), "975", "Earlier convention; the difference from the strict count is a change of convention, not a repair"],
]
tables["S1"] = {
    "id": "S1",
    "title": "Admissible joint units under five rate conventions",
    "header": ["Convention", "Admissible", "Units", "Note"],
    "widths": [2.55, 0.75, 0.5, 2.3],
    "rows": rows,
    "notes": ["Units are the joint group-by-constraint cells of the 60 stored curves; the counts are recomputed from the records, not copied from an earlier report.",
              "Source: " + rel(SEM) + "; per-rate state counts: capacity-only unmet valid 31360 / not-applicable 615, EV failure valid 31975, ICEV failure valid 31975, energy valid 22895 / not-applicable 615 / censored 8465."],
}

# ---- S3a E1 per-event trajectory
q1 = load(Q1)
ex = q1["examples"][0]
tr = ex["trajectories"]
k0, k1 = tr["0"], tr["1"]
rows = []
for a, b in zip(k0, k1):
    rows.append([
        str(a["seq"]), "%.2f" % a["t"], "EV" if a["is_ev"] else "ICEV",
        "yes" if a["needs_charge"] else "no",
        "-" if a["bay"] is None else str(a["bay"]),
        "-" if b["bay"] is None else str(b["bay"]),
        a["outcome"], b["outcome"],
    ])
tables["S3a"] = {
    "id": "S3a",
    "title": "Trace E1, event by event, at k = 0 and k = 1 (n = 6, seed 1)",
    "header": ["Seq", "t", "Class", "Wants charge", "Bay k=0", "Bay k=1", "Outcome k=0", "Outcome k=1"],
    "widths": [0.45, 0.75, 0.75, 0.85, 0.75, 0.75, 0.9, 0.9],
    "rows": rows,
    "cant_split": False,
    "notes": ["Each row is one arrival in the same externally generated stream; the two right-hand columns differ only through the admission rule.",
              "Bay numbering follows the workbench: equipped bays are the lowest indices, so k = 0 -> 1 converts bay 0 from an equipped bay into an ordinary bay.",
              "Source: " + rel(Q1) + ", examples[0]."],
}

# ---- S3b control variants
vari = []
for e in q1["examples"]:
    vari.append(e["variants"])
names = ["strict_pi0_no_fallback", "slot_order_reverse", "dwell_minus20", "dwell_plus20", "initial_occupancy", "simultaneous_reverse"]
label = {
    "strict_pi0_no_fallback": "EV fallback to an ordinary bay removed",
    "slot_order_reverse": "Bays filled in descending order",
    "dwell_minus20": "Dwell times shortened by 20%",
    "dwell_plus20": "Dwell times lengthened by 20%",
    "initial_occupancy": "Initial occupancy imposed",
    "simultaneous_reverse": "Order of simultaneous events reversed",
}
rows = []
for n in names:
    cells = []
    for v in vari:
        d = v.get(n, {})
        p = d.get("violation_persists")
        cells.append("-" if p is None else ("yes" if p else "no"))
    rows.append([label[n]] + cells)
tables["S3b"] = {
    "id": "S3b",
    "title": "Control variants applied to the three minimal traces",
    "header": ["Variant", "E1", "E2", "E3"],
    "widths": [3.4, 0.55, 0.55, 0.55],
    "rows": rows,
    "notes": ["yes = the decrease in ICEV failures survives the variant; no = it disappears; a dash means the variant was not run for that trace.",
              "The traced model here is the mechanism model; counts and rates are not field measurements.",
              "Source: " + rel(Q1) + ", examples[*].variants."],
}

# ---- S4 Q2 units
q2 = load(Q2)
units = q2["delta_k_info"]["units"]
fk = {(r["lot_id"], r["seed"], r["rule"]): r for r in q2["fixed_k_comparison"]}
cat = {(r["lot_id"], r["seed"], r["rule"]): r["category"] for r in q2["four_categories_at_fixed_k"]}
rows = []
for u in units:
    key = (u["lot_id"], u["seed"], u["rule"])
    f = fk[key]
    i0_ice = f["I0"]["ice_parking_failure_rate"]
    i1_ice = f["I1"]["ice_parking_failure_rate"]
    rows.append([
        u["lot_id"], str(u["seed"]), u["rule"], str(u["k_I0"]), str(u["k_I1"]),
        ("%+d" % u["delta_k_info"]), cat[key],
        "%.2f%%" % (100.0 * i0_ice), "%.2f%%" % (100.0 * i1_ice),
    ])
tables["S4"] = {
    "id": "S4",
    "title": "Paired comparison of the two information conditions, one row per unit",
    "header": ["Lot", "Seed", "Rule", "k I0", "k I1", "Delta", "Category at k I0", "ICEV fail I0", "ICEV fail I1"],
    "widths": [0.75, 0.40, 0.40, 0.55, 0.55, 0.55, 1.10, 0.90, 0.90],
    "rows": rows,
    "notes": ["Delta = k(I1) - k(I0); Category is read at the count selected under I0 (both, only I0, only I1, neither).",
              "ICEV failure rates are those of the fixed-k comparison at k(I0); the two units that are admissible only under I0 are the ones whose ICEV rate rises above 5%.",
              "The I1 policy is one heuristic: charging arrivals are offered equipped bays first, non-charging arrivals ordinary bays first, ICEVs keep the rule they had.",
              "Source: " + rel(Q2) + ", delta_k_info.units, fixed_k_comparison, four_categories_at_fixed_k."],
}

# ---- S5 REF A-D sets and the two shared-rule pairs
q3 = load(Q3)
sets = q3["sets"]
base = "REF|%s|TPE1376|10"
rows = []
for r in "ABCD":
    d = sets[base % r]
    K = d["K"]
    rows.append([r, ("%d-%d" % (K[0], K[-1])) if K else "empty", str(len(K)), str(d["min_known_feasible"]),
                 "yes" if d["truncated_at_kmax"] else "no"])
tables["S5a"] = {
    "id": "S5a",
    "title": "Admissible counts for the four rules in scenario REF, lot TPE1376, seed 10",
    "header": ["Rule", "K", "Count", "Min", "Truncated at 40"],
    "widths": [0.6, 1.3, 0.75, 0.6, 1.35],
    "rows": rows,
    "notes": ["A is the dedicated rule, B and C are shared rules, D is the forecast-gated shared rule; all four see the same exogenous stream.",
              "The grids run over k = 0-40; truncation means the set still contains k = 40 and larger counts were not enumerated.",
              "Source: " + rel(Q3) + ", sets['REF|RULE|TPE1376|10']."],
}
KB, KC, KD = sets[base % "B"]["K"], sets[base % "C"]["K"], sets[base % "D"]["K"]
rows = []
for pair, x, y in (("B vs D", KB, KD), ("C vs D", KC, KD)):
    sx, sy = set(x), set(y)
    rows.append([pair, str(len(x)), str(len(y)), str(len(sx & sy)), str(len(sx - sy)), str(len(sy - sx)),
                 "yes" if (x and y and min(x) > min(y)) else "no"])
tables["S5b"] = {
    "id": "S5b",
    "title": "The two pairwise comparisons that produce the smaller counts, on one lot-seed group",
    "header": ["Pair", "|K first|", "|K second|", "Both", "First only", "Second only", "Second smaller"],
    "widths": [0.9, 0.85, 0.95, 0.6, 0.8, 0.85, 0.95],
    "rows": rows,
    "notes": ["Both pairs use the same scenario, lot and seed; they are two comparisons on one group, not two independent groups, and the cells are allocation-order effects between shared rules.",
              "The dedicated-versus-shared rows of the main text never show a smaller count for the shared rule.",
              "Source: " + rel(Q3) + ", sets; derived here by set difference."],
}

# ---- S6 audit
man = load(os.path.join(CP, "build_manifest_rev2.json"))
docx = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx")
rows = [
    ["Manuscript", "paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx", sha(docx)],
    ["Previous working draft (not overwritten)", "paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6.docx", sha(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx"))],
    ["Frozen submission file (not touched)", "main_paper/Electrification tipping point_manuscript 202603submit.docx", sha(os.path.join(ROOT, "main_paper", "Electrification tipping point_manuscript 202603submit.docx"))],
    ["Base draft used by the builder", "paper/draft/Electrification_tipping_point_v2_draft_2026-10-30.docx", sha(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-30.docx"))],
]
for name in ("q1_traces.json", "q2_info_regimes.json", "q3_feasible_sets.json", "recompute_59_curves.json"):
    p = {"q1_traces.json": Q1, "q2_info_regimes.json": Q2, "q3_feasible_sets.json": Q3, "recompute_59_curves.json": SEM}[name]
    rows.append(["Input " + name, rel(p), sha(p)])
tables["S6"] = {
    "id": "S6",
    "title": "Artifacts and input hashes behind this round",
    "header": ["Item", "Path", "SHA-256"],
    "widths": [1.5, 2.6, 2.1],
    "rows": rows,
    "cant_split": False,
    "notes": ["Commands, interpreters and exit codes are recorded in research/round6_20261031/c_paper/RUNLOG.md; the builder writes build_manifest_rev2.json beside it.",
              "The previous working draft and the frozen submission file are read-only here; their bytes are unchanged by this round."],
}

payload = {"schema": "round6_si_tables_v1", "generated_utc": "2026-10-31",
           "inputs": {rel(p): sha(p) for p in (Q1, Q2, Q3, SEM)},
           "tables": tables}
out = os.path.join(CP, "tables_si.json")
with io.open(out, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=1)
print("wrote", out)
for k in sorted(tables):
    print(k, len(tables[k]["rows"]), "rows")
