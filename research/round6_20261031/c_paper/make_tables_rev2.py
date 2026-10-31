# -*- coding: utf-8 -*-
"""Generate the manuscript tables of the round-6 working draft from machine JSON.

Inputs are read-only project evidence; nothing is recomputed here. The script
copies counts and ratios out of the source JSON files, records the SHA-256 of
every input, and writes one JSON file that the docx builder turns into Word
tables. Numeric cells keep the precision of the source; ratios are rounded for
display only and the exact value stays in the source file.
"""
import hashlib
import io
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT_DIR = os.path.join(ROOT, "research", "round6_20261031", "c_paper")

CATALOGUE = os.path.join(ROOT, "research", "round4_20261031", "charge_probability_sources.json")
RATES = os.path.join(ROOT, "research", "calibration", "charging_probability_20261030", "rates.json")
FOUR = os.path.join(ROOT, "research", "round5_20261031", "review", "four_categories.json")
Q1 = os.path.join(ROOT, "research", "round6_20261031", "b_mechanism", "q1_traces.json")
Q2 = os.path.join(ROOT, "research", "round6_20261031", "a_info", "q2_info_regimes.json")
Q3 = os.path.join(ROOT, "research", "round6_20261031", "b_feasible", "q3_feasible_sets.json")
SEM = os.path.join(ROOT, "research", "round6_20261031", "a_semantics", "recompute_59_curves.json")


def load(path):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# Scenario id -> (context substring in rates.json, source label used in the table)
CONTEXT = {
    "M08-NEAR-BEV": "BEV Nissan Leaf",
    "M08-NEAR-PHEV": "PHEV Chevrolet Volt",
    "M08-NEAR-COMBINED": "BEV and PHEV combined",
    "M10-OUT-OF-HOME": "combined observed samples",
    "M08-ALL-AWAY-REF": "all away-from-home parking",
}
BASIS = {
    "M08-NEAR-BEV": "M08, San Diego 2013, parking events within 300 ft of EVSE",
    "M08-NEAR-PHEV": "M08, San Diego 2013, parking events within 300 ft of EVSE",
    "M08-NEAR-COMBINED": "M08, San Diego 2013, BEV and PHEV pooled",
    "M10-OUT-OF-HOME": "M10, pooled observed samples; search-index transcription, provisional",
    "M08-ALL-AWAY-REF": "M08, all away-from-home parking events of the same sample",
}

catalogue = load(CATALOGUE)
rates = load(RATES)["rows"]

rows = []
for scenario in catalogue["scenarios"]:
    sid = scenario["scenario_id"]
    q = scenario["q_need"]
    if sid == "REF":
        rows.append([
            "REF",
            "%.2f" % q,
            "not applicable",
            "scenario input",
            "Historical reference used by the submitted model; no observed count behind it",
            "historical reference, not identified",
        ])
        continue
    needle = CONTEXT[sid]
    match = [r for r in rates if needle.lower() in (r.get("context") or "").lower()]
    if len(match) != 1:
        raise SystemExit("rates.json match for %s: %d" % (sid, len(match)))
    r = match[0]
    provisional = "provisional" in (r.get("transcription_status") or "").lower()
    rows.append([
        sid,
        "%.4f" % q,
        "%d / %d" % (r["charging_events"], r["parking_events"]),
        "%.4f" % r["probability"],
        BASIS[sid],
        "observed use, transferred as assumption" + (" (provisional transcription)" if provisional else ""),
    ])

table13 = {
    "id": "T13",
    "title": "Observed charging-use ratios used as scenario anchors for the charging-want share",
    "header": ["Scenario", "q used", "Charging events / parking events", "Ratio", "Source and basis", "Identification status"],
    "widths": [0.95, 0.45, 1.0, 0.45, 1.6, 1.2],
    "cant_split": False,
    "rows": rows,
    "notes": [
        "q is the share of the charging-want parameter used in the scenario; ratios are computed from the listed counts and rounded to four decimals.",
        "The denominator is a parking event in the source context, not an arrival at the lot studied here; refusals are not recorded in the source either.",
        "REF carries no observed count: 0.36 is a scenario input kept for comparability with the submitted model.",
    ],
    "source": {"catalogue": os.path.relpath(CATALOGUE, ROOT), "rates": os.path.relpath(RATES, ROOT)},
}

four = load(FOUR)
by_rule = four["summary"]["by_rule"]
labels = [
    ("B", "shared rule at a fixed stock"),
    ("D", "shared rule with a different allocation order"),
]
counts = []
for rule, label in labels:
    d = by_rule[rule]
    counts.append([
        rule,
        label,
        str(d["both_feasible"]["n_cells"]),
        str(d["only_dedicated"]["n_cells"]),
        str(d["only_shared"]["n_cells"]),
        str(d["neither_feasible"]["n_cells"]),
    ])

table14 = {
    "id": "T14",
    "title": "Fixed-k paired comparison of the dedicated and shared rules by cell category",
    "header": ["Rule", "Rule description", "Both feasible", "Dedicated only", "Shared only", "Neither"],
    "widths": [0.5, 2.0, 0.8, 0.85, 0.75, 0.65],
    "rows": counts,
    "notes": [
        "Cell counts over 96 fixed-k cells in total, at tolerance 5% on three service rates (capacity-only unmet, EV parking failure, ICEV parking failure).",
        "k is selected on seeds 1-4 under the dedicated rule and evaluated on seeds 5-10; the two seed sets are disjoint.",
        "A cell counts as feasible only when every rate is valid and at or below the tolerance; a rate with a zero denominator is not applicable and does not make a cell feasible on its own.",
        "Only the 'shared only' column would evidence that shared use substitutes for equipment; it is zero in both rows.",
    ],
    "source": {"four_categories": os.path.relpath(FOUR, ROOT)},
}

payload = {
    "schema": "round6/tables/v1",
    "generated_utc": "deterministic-from-inputs",
    "command": "python research/round6_20261031/c_paper/make_tables.py",
    "interpreter": sys.executable + " | " + sys.version.split()[0],
    "inputs": {
        os.path.relpath(p, ROOT): sha256(p) for p in (CATALOGUE, RATES, FOUR, Q1, Q2, Q3, SEM)
    },
    "tables": {},
}

# ---- round-6 results tables -------------------------------------------------
q1 = load(Q1)
t15_rows = []
for ex in q1["examples"]:
    wb = ex["workbench"]
    k0, k1 = str(ex["k"]), str(ex["k"] + 1)
    a, b = wb["k"], wb["k1"]
    v = ex["variants"]
    nocontrol = v.get("slot_order_reverse", {})
    ctrl = v.get("strict_pi0_no_fallback", {})
    t15_rows.append([
        ex["id"].split("_")[0],
        "%s -> %s" % (k0, k1),
        "%d -> %d" % (a["ice_fail"], b["ice_fail"]),
        "%d -> %d" % (a["ev_fail"], b["ev_fail"]),
        "%s -> %s" % (str(ex["base_ev_ordinary"][0]), str(ex["base_ev_ordinary"][1])),
        "%s -> %s" % (str(ctrl.get("k", ["?", "?"])[0]), str(ctrl.get("k", ["?", "?"])[1])),
    ])
table15 = {
    "id": "T15",
    "title": "Three minimal traces in which one extra equipped bay lowers ICEV parking failures",
    "header": ["Trace", "k -> k+1", "ICEV failures", "EV failures", "EVs in ordinary bays", "ICEV failures, no fallback"],
    "widths": [0.55, 0.75, 0.85, 0.85, 0.9, 1.35],
    "rows": t15_rows,
    "cant_split": False,
    "notes": [
        "Counts are failures per trace over the whole operating window; the trace is replayed at every k and the numbers agree with the mechanism model in all k, not only at the two shown.",
        "Column 6 repeats the same trace with the fallback of an EV to an ordinary bay removed; the decrease in column 3 disappears in all three traces, as it does under a reversed bay order and under dwell times shortened by 20%.",
        "Traces are synthetic configurations of the mechanism model, not field measurements of a site.",
    ],
    "source": {"q1_traces": os.path.relpath(Q1, ROOT)},
}

q2 = load(Q2)
units = q2["delta_k_info"]["units"]
cats = {(c["lot_id"], str(c["seed"]), c["rule"]): c["category"] for c in q2["four_categories_at_fixed_k"]}
t16_rows = []
seen = []
for u in units:
    key = (u["lot_id"], str(u["seed"]))
    if key in seen:
        continue
    seen.append(key)
    t16_rows.append([
        u["lot_id"],
        str(u["seed"]),
        str(u["k_I0"]),
        str(u["k_I1"]),
        str(u["delta_k_info"]),
        cats.get((u["lot_id"], str(u["seed"]), "A"), "n/a"),
        cats.get((u["lot_id"], str(u["seed"]), "B"), "n/a"),
    ])
dk = q2["delta_k_info"]["summary"]
fc = q2["four_categories"]["counts"]
table16 = {
    "id": "T16",
    "title": "Smallest admissible integer count under the two information conditions",
    "header": ["Lot", "Seed", "k, I0", "k, I1", "Change", "Category, rule A", "Category, rule B"],
    "widths": [0.8, 0.45, 0.5, 0.5, 0.5, 1.15, 1.15],
    "rows": t16_rows,
    "notes": [
        "k values are the smallest count at which the three service rates are at or below 5% in that unit; k is searched over the complete integer grid 0-40.",
        "Categories are read at the k of the I0 unit: both means feasible under both conditions, only-I0 means feasible under I0 alone.",
        "Across %d paired units the change is negative in %d, zero in %d and positive in %d (median %s, range %s to %s); across %d fixed-k comparisons the categories are both %d, only I0 %d, only I1 %d, neither %d."
        % (dk["n_units"], dk["negative"], dk["zero"], dk["positive"], dk["median"], dk["min"], dk["max"],
           sum(fc.values()), fc["both"], fc["only_I0"], fc["only_I1"], fc["neither"]),
        "The I1 policy is a heuristic, so the table compares two implemented policies and not two optima.",
    ],
    "source": {"q2_info_regimes": os.path.relpath(Q2, ROOT)},
}

q3 = load(Q3)
pairs = {}
for key, v in q3["pairs"].items():
    scenario, a, b = key.split("|")
    d = pairs.setdefault((a, b), dict(scenarios=set(), pairs=0, both=0, only_first=0, only_second=0,
                                      neither=0, restoration=0, device_saving=0, both_disjoint=0))
    d["scenarios"].add(scenario)
    for f in ("pairs", "both", "only_first", "only_second", "neither", "restoration", "device_saving", "both_disjoint"):
        d[f] += v.get(f) or 0
t17_rows = []
for (a, b), d in sorted(pairs.items()):
    t17_rows.append([
        "%s vs %s (%s)" % (a, b, "dedicated vs shared" if "A" in (a, b) else "shared vs shared"),
        str(len(d["scenarios"])),
        str(d["pairs"]),
        str(d["both"]),
        str(d["only_first"]),
        str(d["only_second"]),
        str(d["neither"]),
        str(d["restoration"]),
        str(d["device_saving"]),
        str(d["both_disjoint"]),
    ])
lim = q3["limits"]
table17 = {
    "id": "T17",
    "title": "Feasible sets of the two rules over complete integer grids",
    "header": ["Rule pair", "Scen.", "Pairs", "Both", "First only", "Second only", "Neither", "Restored", "Smaller k", "Disjoint"],
    "widths": [1.30, 0.38, 0.40, 0.40, 0.52, 0.58, 0.44, 0.52, 0.52, 0.57],
    "rows": t17_rows,
    "cant_split": False,
    "notes": [
        "Pairs are lot-seed groups compared at tolerance 5% over the complete grid k = 0-40. Only the A rows compare the dedicated rule with a shared rule; the B/C/D rows compare two shared rules under the same information condition, and their restored and smaller-k cells are allocation-order effects rather than device savings from sharing.",
        "The two smaller counts in B vs D and C vs D come from the same lot-seed group (TPE1376, seed 10), where the forecast-gated shared rule needs 2 equipped bays while the other shared rules need 24; they are two pairwise comparisons on one group, not two independent groups.",
        "Columns: first only = admissible under the first rule only; restored = admissible under the second rule only; smaller k = the second rule attains a strictly smaller minimal count; disjoint = both rules admissible but the sets share no k.",
        "Set shape over %d groups: broken sets %d, empty under the inclusive convention %d, empty under the strict convention %d, groups where the two conventions differ %d, sets truncated at the grid edge %d."
        % (q3["n_groups"], lim["broken_in_range"], lim["empty_in_range"], lim["empty_strict"],
           lim["strict_vs_inclusive_differ"], lim["truncated_at_kmax"]),
        "Aggregated over the same pairs, service at a common k improves under the second rule in %d pairs and worsens in %d."
        % (sum(v.get("same_k_improvement") or 0 for v in q3["pairs"].values()),
           sum(v.get("same_k_worse") or 0 for v in q3["pairs"].values())),
        "A set truncated at the grid edge is not evidence that no larger admissible count exists.",
    ],
    "source": {"q3_feasible_sets": os.path.relpath(Q3, ROOT)},
}

payload_tables = {"T13": table13, "T14": table14, "T15": table15, "T16": table16, "T17": table17}

payload["tables"] = payload_tables

os.makedirs(OUT_DIR, exist_ok=True)
out = os.path.join(OUT_DIR, "tables_rev2.json")
with io.open(out, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=1)
print("wrote", out)
for tname, tspec in payload_tables.items():
    print(tname, len(tspec["rows"]), "rows")
    for row in tspec["rows"]:
        print("   ", row)
