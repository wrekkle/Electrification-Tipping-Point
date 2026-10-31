# -*- coding: utf-8 -*-
"""R8 Phase3 independent verification (R8-D): analysis artifacts, scenario ledger, statistics.

Writes only under research/round8_20261031/acceptance/evidence/.
Every number printed here is recomputed from the contract / window export / experiment CSVs.
"""
import csv, json, math, os, random, statistics, sys
from collections import Counter, defaultdict
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.getcwd()
R = os.path.join("research", "round8_20261031")
A = os.path.join(R, "analysis")
C = os.path.join(R, "experiments_condshare")
EV = os.path.join(R, "acceptance", "evidence")
res = {"checks": {}, "notes": []}

def jload(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)

def rload(p):
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))

def pct(values, q):
    o = sorted(values); n = len(o); idx = q * (n - 1)
    lo = int(math.floor(idx)); hi = int(math.ceil(idx))
    return float(o[lo]) if lo == hi else float(o[lo] + (o[hi] - o[lo]) * (idx - lo))

def boot_ci(values, n_boot=1000, seed=20261031):
    rng = random.Random(seed); n = len(values); samples = []
    for _ in range(n_boot):
        samples.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    return {"point": sum(values) / n, "low": pct(samples, 0.025), "high": pct(samples, 0.975),
            "n": n, "n_boot": n_boot}

def cluster_boot(group_values, n_boot=1000, seed=20261031):
    rng = random.Random(seed); keys = list(group_values); means = []
    for _ in range(n_boot):
        pool = []
        for _ in range(len(keys)):
            pool.extend(group_values[keys[rng.randrange(len(keys))]])
        means.append(sum(pool) / len(pool))
    allv = [v for g in group_values.values() for v in g]
    return {"point": sum(allv) / len(allv), "low": pct(means, 0.025), "high": pct(means, 0.975),
            "n_clusters": len(keys), "n_obs": len(allv)}

contract = jload(os.path.join(R, "data", "processed", "public_parking_events.json"))
sites = {s["site_id"]: s for s in contract["sites"]}
events = contract["events"]
sel = set(sites)
wrows = rload(os.path.join(R, "data", "processed", "_window_events.csv"))

# ---------------- A. window export -> contract reconciliation ----------------
areas = Counter(r["area"] for r in wrows)
rows_sel = [r for r in wrows if r["area"] in sel]
bad = [r for r in rows_sel if (not r["dep_local"]) or r["dep_local"].startswith("1900") or
       (r["dwell_min"] and float(r["dwell_min"]) <= 0)]
allbad = [r for r in wrows if (not r["dep_local"]) or r["dep_local"].startswith("1900")]
kept = len(rows_sel) - len(bad)
contract_ids = {e["event_id"] for e in events}
wc = Counter(r["area"] for r in rows_sel); cc = Counter(e["site_id"] for e in events)
per_site_diff = {s: {"window_in_area": wc[s], "contract": cc[s], "dropped": wc[s] - cc[s]} for s in sorted(sel)}
site_audit = {r["site_id"]: r for r in rload(os.path.join(A, "site_audit.csv"))}
a = {
    "window_rows": len(wrows), "distinct_areas": len(areas), "selected_areas": len(sel),
    "window_rows_selected": len(rows_sel), "bad_selected": len(bad),
    "bad_all_areas": len(allbad), "kept_selected": kept,
    "contract_events": len(events), "contract_unique_event_ids": len(contract_ids),
    "non_selected_rows": len(wrows) - len(rows_sel),
    "per_site_diff": per_site_diff,
    "bad_rows_detail": [{"area": r["area"], "arr": r["arr_local"], "dep": r["dep_local"],
                          "dwell_min": r["dwell_min"], "bay": r["bay_id"]} for r in bad],
    "site_audit_events_sum": sum(int(r["events"]) for r in site_audit.values()),
    "verdict": None,
}
a["verdict"] = "PASS" if (a["window_rows"] == 236819 and a["distinct_areas"] == 24 and
                          a["window_rows_selected"] == 185552 and a["bad_selected"] == 2 and
                          kept == 185550 == a["contract_events"] == a["contract_unique_event_ids"] and
                          all(v["dropped"] in (0, 1) for v in per_site_diff.values()) and
                          sum(v["dropped"] for v in per_site_diff.values()) == 2 and
                          a["non_selected_rows"] == 51267) else "FAIL"
res["checks"]["A_reconcile"] = a
print("A window", a["window_rows"], "areas", a["distinct_areas"], "selected", a["window_rows_selected"],
      "bad", a["bad_selected"], "kept", kept, "contract", a["contract_events"], "verdict", a["verdict"])
for s, v in per_site_diff.items():
    if v["dropped"]:
        print("  dropped at", s, v)
print("  bad rows:", a["bad_rows_detail"])

# ---------------- B. max concurrency / minutes above capacity ----------------
def sweep(rows, nsp, key_arr="arr_local", key_dep="dep_local"):
    groups = defaultdict(lambda: [0, 0])
    for r in rows:
        if not r[key_dep] or r[key_dep].startswith("1900"):
            continue
        groups[r[key_arr]][0] += 1
        groups[r[key_dep]][1] += 1
    times = sorted(groups)
    occ = 0; mx = 0; over = 0.0; prev = None
    for t in times:
        dt = (datetime.fromisoformat(t) - datetime.fromisoformat(prev)).total_seconds() / 60.0 if prev else 0.0
        if prev is not None and occ > nsp:
            over += dt
        occ += groups[t][0] - groups[t][1]
        mx = max(mx, occ); prev = t
    return mx, over

def sweep_transient(rows, nsp):
    """Reproduce per-event ordering used by fit_for_model.py: arrivals before departures at equal ts."""
    pts = []
    for r in rows:
        if not r["dep_local"] or r["dep_local"].startswith("1900"):
            continue
        pts.append((r["arr_local"], 1)); pts.append((r["dep_local"], -1))
    pts.sort(key=lambda p: (p[0], -p[1]))
    cur = mx = 0; over = 0.0; prev = None
    for t, d in pts:
        if prev is not None:
            dt = (datetime.fromisoformat(t) - datetime.fromisoformat(prev)).total_seconds() / 60.0
            if cur > nsp:
                over += dt
        cur += d; mx = max(mx, cur); prev = t
    return mx, over

b_sites = {}
for s in sorted(sel):
    nsp = sites[s]["n_spaces"]
    rows = [r for r in rows_sel if r["area"] == s]
    mx, over = sweep(rows, nsp)
    mxt, overt = sweep_transient(rows, nsp)
    b_sites[s] = {"n_spaces": nsp, "sweep_max": mx, "sweep_over_min": round(over, 3),
                  "transient_max": mxt, "transient_over_min": round(overt, 3),
                  "csv_max_concurrency": int(site_audit[s]["max_concurrency"]),
                  "csv_peak_over_capacity": int(site_audit[s]["peak_over_capacity"]),
                  "csv_minutes_above_capacity": float(site_audit[s]["minutes_above_capacity"]),
                  "csv_events": int(site_audit[s]["events"])}
b = {"sites": b_sites,
     "sites_sweep_over_nspaces": sorted(s for s, v in b_sites.items() if v["sweep_max"] > v["n_spaces"]),
     "sites_transient_over_nspaces": sorted(s for s, v in b_sites.items() if v["transient_max"] > v["n_spaces"]),
     "sites_csv_positive_peak": sorted(s for s, v in b_sites.items() if v["csv_peak_over_capacity"] > 0),
     "sites_csv_events_mismatch": sorted(s for s in b_sites if b_sites[s]["csv_events"] != cc[s]),
     "fit_md_claim": "FIT_FOR_MODEL.md §2: 任一时刻同时占用数 <= n_spaces，超容量分钟数 0.0，例子 'Victoria Market 35/35'",
     "verdict": None, "verdict_site_audit_consistency": None}
b["verdict"] = "PASS" if (not b["sites_sweep_over_nspaces"] and all(v["sweep_over_min"] == 0.0 for v in b_sites.values())) else "FAIL"
b["verdict_site_audit_consistency"] = "PASS" if (not b["sites_csv_positive_peak"] and not b["sites_csv_events_mismatch"]) else "FAIL"
res["checks"]["B_occupancy"] = b
print("\nB occupancy: my clean sweep max>nspaces sites:", b["sites_sweep_over_nspaces"],
      "| transient-repro >nspaces:", b["sites_transient_over_nspaces"],
      "| csv positive peak:", b["sites_csv_positive_peak"], "verdict", b["verdict"])
for s, v in b_sites.items():
    print(" ", s, v)

# ---------------- C. ideal bound at P=22 over E4 held-out streams ----------------
e4 = rload(os.path.join(R, "experiments_main22", "E4", "test_E4.csv"))
streams = sorted({(r["site_id"], r["day_key"]) for r in e4})
by_key = defaultdict(list)
for e in events:
    by_key[(e["site_id"], e["arrival_ts"][:10])].append(e)
per_stream = []
for s, d in streams:
    evs = by_key[(s, d)]
    n = 0; dem = 0.0; dlv = 0.0; fail = 0
    for e in evs:
        if not (e.get("is_ev") and e.get("needs_charge")):
            continue
        E = float(e["energy_kwh"]); T = float(e["dwell_min"]) / 60.0
        n += 1; dem += E; dlv += min(E, 22.0 * T); fail += 1 if E > 22.0 * T + 1e-9 else 0
    n_events = len(evs)
    per_stream.append({"site_id": s, "day_key": d, "n_events": n_events, "n_requests": n,
                       "demand_kwh": dem, "delivered_kwh": dlv, "fail": fail})
tot_n = sum(x["n_requests"] for x in per_stream)
tot_dem = sum(x["demand_kwh"] for x in per_stream)
tot_dlv = sum(x["delivered_kwh"] for x in per_stream)
tot_fail = sum(x["fail"] for x in per_stream)
ib = rload(os.path.join(A, "ideal_bound_streams.csv"))
ib_by = {(r["site_id"], r["day_key"]): r for r in ib}
ev = rload(os.path.join(C, "evidence_at_n_spaces.csv"))
ev_by = {(r["site_id"], r["day_key"]): r for r in ev if r["policy"] == "A"}
evj = jload(os.path.join(C, "evidence_at_n_spaces.json"))["aggregate"]["A"]
mism_ib = []; mism_ev = []
for x in per_stream:
    k = (x["site_id"], x["day_key"])
    r = ib_by.get(k)
    if r is None or abs(float(r["ideal_delivered_kwh"]) - round(x["delivered_kwh"], 3)) > 1e-6 or \
       abs(float(r["demand_kwh"]) - round(x["demand_kwh"], 3)) > 1e-6 or \
       int(r["session_failure"]) != x["fail"] or int(r["n_requests"]) != x["n_requests"]:
        mism_ib.append((k, r, x))
    r2 = ev_by.get(k)
    if r2 is None or abs(float(r2["delivered_kwh"]) - round(x["delivered_kwh"], 3)) > 1e-6 or \
       int(r2["shortfall_sessions"]) != x["fail"] or int(r2["charge_requests"]) != x["n_requests"] or \
       int(r2["sessions_dwell_lt_required"]) != x["fail"]:
        mism_ev.append((k, r2, x))
e4_seen = {(r["site_id"], r["day_key"]): int(r["n_events"]) for r in e4}
n_events_mism = [(k, v, next(x["n_events"] for x in per_stream if (x["site_id"], x["day_key"]) == k))
                 for k, v in e4_seen.items()
                 if v != next(x["n_events"] for x in per_stream if (x["site_id"], x["day_key"]) == k)]
c = {"n_streams": len(streams), "n_requests": tot_n, "demand_kwh": round(tot_dem, 3),
     "delivered_kwh": round(tot_dlv, 3), "session_failures": tot_fail,
     "csv_delivered_sum": round(sum(float(r["ideal_delivered_kwh"]) for r in ib), 3),
     "json_delivered": evj["delivered_kwh"], "json_demand": evj["demand_kwh"],
     "json_shortfall": evj["shortfall_sessions"], "json_charge_requests": evj["charge_requests"],
     "mismatch_ideal_bound_streams": mism_ib[:5], "n_mismatch_ib": len(mism_ib),
     "n_mismatch_evidence": len(mism_ev), "n_events_mismatch_vs_e4": len(n_events_mism),
     "all_evidence_rows_gate0": all(int(r["rejected_at_gate"]) == 0 for r in ev),
     "evidence_policies": sorted({r["policy"] for r in ev}),
     "verdict": None}
c["verdict"] = "PASS" if (c["n_streams"] == 20 and tot_n == 137 and tot_fail == 80 and
                          abs(tot_dlv - 991.891) < 0.02 and abs(tot_dem - 1891.0) < 0.5 and
                          abs(c["json_delivered"] - 991.9) < 0.06 and len(mism_ib) == 0 and
                          len(mism_ev) == 0 and len(n_events_mism) == 0 and
                          c["all_evidence_rows_gate0"]) else "FAIL"
res["checks"]["C_ideal_bound"] = c
print("\nC ideal bound P=22:", {k: c[k] for k in ("n_streams", "n_requests", "demand_kwh", "delivered_kwh",
      "session_failures", "json_delivered", "json_demand", "json_shortfall", "n_mismatch_ib", "n_mismatch_evidence")},
      "verdict", c["verdict"])

# ---------------- D. demand-dwell matching table ----------------
dd = rload(os.path.join(A, "demand_dwell_matching.csv"))
ddm = []
for E0 in (2.0, 4.0, 6.0, 8.0, 10.0, 14.0, 20.0):
    n = 0; dem = 0.0; dlv = 0.0; fail = 0
    for e in events:
        if not (e.get("is_ev") and e.get("needs_charge")):
            continue
        T = float(e["dwell_min"]) / 60.0
        n += 1; dem += E0; dlv += min(E0, 22.0 * T); fail += 1 if E0 > 22.0 * T + 1e-9 else 0
    ddm.append((E0, n, round(dem, 1), round(dlv, 3), fail))
d_mism = []
for r in dd:
    E0 = float(r["declared_energy_kwh"])
    rec = next(x for x in ddm if x[0] == E0)
    if int(r["n_requests"]) != rec[1] or abs(float(r["demand_kwh"]) - rec[2]) > 1e-6 or \
       abs(float(r["ideal_delivered_kwh"]) - round(rec[3], 1)) > 0.051 or int(r["session_failure"]) != rec[4]:
        d_mism.append((r, rec))
d = {"rows": len(dd), "recomputed": ddm, "mismatches": d_mism,
     "verdict": "PASS" if not d_mism and all(x[1] == 6588 for x in ddm) else "FAIL"}
res["checks"]["D_demand_dwell"] = d
print("\nD demand-dwell rows", len(dd), "n per level", sorted({x[1] for x in ddm}),
      "mismatches", len(d_mism), "verdict", d["verdict"])

# ---------------- E. area selection rule ----------------
areas_rank = rload(os.path.join(A, "area_ranking.csv"))
areas_from_window = {}
for area, n in areas.items():
    areas_from_window[area] = {"events": n, "bays": len({r["bay_id"] for r in wrows if r["area"] == area})}
rank_mism = []
for r in areas_rank:
    rec = areas_from_window[r["area"]]
    if int(r["events"]) != rec["events"] or int(r["bays"]) != rec["bays"]:
        rank_mism.append((r["area"], r["events"], rec["events"], r["bays"], rec["bays"]))
rule = sorted(area for area, v in areas_from_window.items() if v["bays"] >= 12 and v["events"] >= 4000)
rule_alt = sorted(area for area, v in areas_from_window.items() if v["bays"] >= 8 and v["events"] >= 1500)
top10 = sorted(rule_alt, key=lambda x: -areas_from_window[x]["events"])[:10]
prov = jload(os.path.join(R, "data", "PROVENANCE.json"))
sel_rule = prov.get("contract", {}).get("site_selection_rule") or prov.get("site_selection_rule")
e = {"selected": sorted(sel), "rule_bays12_events4000": rule, "rule_yields_selected": sorted(sel) == rule,
     "rule_count": len(rule), "alt_rule_bays8_events1500": rule_alt,
     "alt_top10_by_events": top10, "alt_yields_selected": set(top10) == sel,
     "area_ranking_count": len(areas_rank), "rank_mismatches": rank_mism,
     "provenance_selection_rule": sel_rule,
     "event_share_selected": round(len(rows_sel) / len(wrows), 4),
     "verdict": None}
e["verdict"] = "PASS" if (e["rule_yields_selected"] and len(rule) == 10 and not rank_mism and
                          len(areas_rank) == 24) else "FAIL"
res["checks"]["E_area_selection"] = e
print("\nE area selection: rule bays>=12 & events>=4000 ->", len(rule), "areas; equals selected:",
      e["rule_yields_selected"], "; alt top10 equals selected:", e["alt_yields_selected"])
print("  provenance rule:", sel_rule)
print("  alt rule (bays>=8 & events>=1500):", len(rule_alt), rule_alt, "top10:", top10)
print("  event share selected:", e["event_share_selected"], "rank mismatches:", rank_mism)

# ---------------- F. scenario ledger vs actual application ----------------
rm7 = jload(os.path.join(R, "experiments", "run_meta.json"))
rm22 = jload(os.path.join(R, "experiments_main22", "run_meta.json"))
contract_hw = {s: {"n_spaces": v["n_spaces"], "charging_bays": v["charging_bays"],
                   "connectors": v["connectors"], "connector_kw": v["connector_kw"],
                   "feeder_kw": v["feeder_kw"]} for s, v in sites.items()}
f = {"run_meta_7kw_parameters": rm7["scenario_layer"]["parameters"],
     "run_meta_main22_parameters": rm22["scenario_layer"]["parameters"],
     "run_meta_main22_forced": rm22["scenario_layer"].get("forced_overrides"),
     "contract_declared": contract_hw,
     "contract_hardware_source": sites["Queensberry"]["hardware_source"],
     "verdict_claim": None, "verdict_paper": None}
# capability check without importing the runner (recompute rule from code): if site dict has fields,
# defaults are unused. Import runner to prove effective values.
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "apps", "parking_lab"))
sys.path.insert(0, os.path.join(ROOT, "research", "round8_20261031", "engine"))
from apps.parking_lab.workbench import publicdata as pd
import runner
norm = pd.normalise_contract(contract)
blocks = pd.site_day_blocks(norm)
bq = next(b for b in blocks if b["site_id"] == "Queensberry")
cap = runner.site_capability(bq["site"])
cap_defaults_override = None
runner.SCENARIO_FORCE.clear()
runner.set_scenario(connector_kw=7.0, charging_bay_share=0.1, max_connectors_per_site=4, feeder_share=0.5)
cap2 = runner.site_capability(bq["site"])
stripped = dict(bq["site"])
for kk in ("charging_bays", "connectors", "connector_kw", "feeder_kw"):
    stripped.pop(kk)
cap3 = runner.site_capability(stripped)
runner.SCENARIO_FORCE.clear()
f["effective_capability_contract_site"] = {k: cap[k] for k in ("n_spaces", "charging_bays", "connectors", "connector_kw", "feeder_kw", "derived_fields")}
f["effective_with_share_override"] = {k: cap2[k] for k in ("charging_bays", "connectors", "connector_kw", "feeder_kw", "derived_fields")}
f["effective_if_fields_absent"] = {k: cap3[k] for k in ("charging_bays", "connectors", "connector_kw", "feeder_kw", "derived_fields")}
# output-side evidence: E3 physical bounds and E2 k=8 rows
cls = jload(os.path.join(R, "experiments", "E3", "classes.json"))
f["e3_physical_bounds"] = {i["instance_id"]: {"physical_bound": i["physical_bound"], "k_max_searched": i["k_max_searched"]} for i in cls["instances"]}
e2 = rload(os.path.join(R, "experiments_main22", "E2", "curve_E2.csv"))
f["e2_university_rows_at_k8"] = sum(1 for r in e2 if int(r["k"]) == 8 and r["site_id"] == "University" and r["policy"] == "A")
d22 = os.path.join(R, "experiments_declared22")
if os.path.isdir(d22):
    ha = jload(os.path.join(d22, "hardware_audit.json"))
    f["declared22_hardware_audit_conclusion"] = ha.get("conclusion")
    f["declared22_resolved_hardware"] = ha.get("resolved_hardware")
f["verdict_claim"] = "FAIL" if (cap["charging_bays"] != 8 and cap3["charging_bays"] == 8 and
                                cap["connectors"] == cap["charging_bays"] and
                                cap3["connectors"] == 4) else "PASS"
# paper text
paper_py = open(os.path.join(R, "paper", "content_rev5.py"), encoding="utf-8").read()
paper_20 = [(i, l.strip()[:180]) for i, l in enumerate(paper_py.splitlines(), 1)
            if "20%" in l]
paper_50_4 = [(i, l.strip()[:180]) for i, l in enumerate(paper_py.splitlines(), 1)
              if ("50% feeder" in l or "four connectors" in l)]
import zipfile, re
docx_path = os.path.join(R, "paper", "Electrification_tipping_point_v2_draft_rev5.docx")
docx_text = ""
if os.path.exists(docx_path):
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    docx_text = re.sub(r"<[^>]+>", "", xml)
def snippets(text, needle, n=3):
    out = []
    for m in re.finditer(re.escape(needle), text):
        out.append(text[max(0, m.start() - 90):m.start() + 110].replace("\n", " "))
        if len(out) >= n:
            break
    return out
f["paper_content_rev5_20pct_hits"] = paper_20
f["paper_content_rev5_50pct_or_4conn_hits"] = paper_50_4
f["docx_20pct_count"] = docx_text.count("20%")
f["docx_50pct_snippets"] = snippets(docx_text, "50% feeder")
f["docx_four_connector_snippets"] = snippets(docx_text, "four connectors")
f["docx_01_share_snippets"] = snippets(docx_text, "0.1 ")
f["verdict_paper"] = "FAIL" if (paper_50_4 or f["docx_50pct_snippets"] or f["docx_four_connector_snippets"]) else "PASS"
res["checks"]["F_scenario_ledger"] = f
print("\nF scenario: effective contract site capability", f["effective_capability_contract_site"])
print("  with share override", f["effective_with_share_override"])
print("  if fields absent", f["effective_if_fields_absent"])
print("  E3 physical bounds", f["e3_physical_bounds"])
print("  E2 University rows at k=8:", f["e2_university_rows_at_k8"])
print("  declared22 audit conclusion:", f.get("declared22_hardware_audit_conclusion"))
print("  paper 20% hits:", [i for i, _ in paper_20], "| 50%feeder/4connector hits:", paper_50_4)

# ---------------- G. statistics ----------------
def m2_diffs(rows, base):
    by_stream = {}
    for row in rows:
        by_stream.setdefault(row["stream_id"], {})[row["policy"]] = row
    diffs = []
    for pair in by_stream.values():
        if "A" in pair and base in pair:
            first = pair["A"].get("energy_service_rate_incl_rejected")
            second = pair[base].get("energy_service_rate_incl_rejected")
            if first is not None and second is not None:
                diffs.append(float(second) - float(first))
    return diffs, by_stream

g = {}
for label, rows, meta in (
        ("7kW", rload(os.path.join(R, "experiments", "E4", "test_E4.csv")),
         jload(os.path.join(R, "experiments", "M", "m_summaries.json"))),
        ("main22", e4, jload(os.path.join(R, "experiments_main22", "M", "m_summaries.json")))):
    stored = {x["pair"]: x for x in meta["comparisons"] if x.get("comparison") == "M2"}
    if not stored:
        stored = {x["pair"]: x for x in meta["comparisons"] if x.get("comparison") == "M2"}
    per = {}
    for base in ("B0_FCFS", "B1_QUOTA", "B2_LITERATURE"):
        diffs, by_stream = m2_diffs(rows, base)
        ci = boot_ci(diffs)
        key = base + " - A"
        st = stored.get(key)
        per[base] = {"n": ci["n"], "point": ci["point"], "low": ci["low"], "high": ci["high"],
                     "stored_point": st.get("point") if st else None,
                     "stored_low": st.get("low") if st else None,
                     "stored_high": st.get("high") if st else None,
                     "match": bool(st) and abs(ci["point"] - st["point"]) < 1e-12 and
                              abs(ci["low"] - st["low"]) < 1e-12 and abs(ci["high"] - st["high"]) < 1e-12}
    g[label] = per
# site-cluster bootstrap for B0-A (main22 and 7kW)
g["cluster"] = {}
for label, rows in (("7kW", rload(os.path.join(R, "experiments", "E4", "test_E4.csv"))),
                    ("main22", e4)):
    diffs, by_stream = m2_diffs(rows, "B0_FCFS")
    site_of = {r["stream_id"]: r["site_id"] for r in rows}
    stream_ids = [sid for sid in by_stream]
    groups = defaultdict(list)
    for sid, d in zip(stream_ids, diffs):
        groups[site_of[sid]].append(d)
    cl = cluster_boot(groups)
    cl["excludes_zero"] = cl["low"] > 0 or cl["high"] < 0
    cl["streams"] = len(stream_ids); cl["sites"] = sorted(groups)
    g["cluster"][label] = cl
# B1/B2 identity
energy_fields = ["energy_service_rate_incl_rejected", "delivered_kwh", "demand_kwh",
                 "delivered_kwh_incl_rejected", "demand_kwh_incl_rejected", "gap_kwh", "energy_service_rate"]
capacity_fields = ["capacity_only_unmet_rate", "capacity_unmet_rate", "num_capacity_unmet_requests",
                   "service_capacity_unmet_rate", "feasible_3constraints", "feasible_raw"]
g["b1b2"] = {}
for label, rows in (("7kW", rload(os.path.join(R, "experiments", "E4", "test_E4.csv"))),
                    ("main22", e4)):
    by_stream = {}
    for row in rows:
        by_stream.setdefault(row["stream_id"], {})[row["policy"]] = row
    n = len(by_stream)
    eq_energy = sum(1 for p in by_stream.values() if all(p["B1_QUOTA"].get(f) == p["B2_LITERATURE"].get(f) for f in energy_fields))
    eq_cap = sum(1 for p in by_stream.values() if all(p["B1_QUOTA"].get(f) == p["B2_LITERATURE"].get(f) for f in capacity_fields))
    diff_cols = Counter()
    diff_streams = []
    for sid, p in by_stream.items():
        dcols = [k for k in p["B1_QUOTA"] if p["B1_QUOTA"].get(k) != p["B2_LITERATURE"].get(k)]
        if dcols:
            diff_streams.append({"stream_id": sid, "columns": dcols})
            for k in dcols:
                diff_cols[k] += 1
    g["b1b2"][label] = {"streams": n, "energy_identical": eq_energy, "capacity_identical": eq_cap,
                        "diff_columns": dict(diff_cols), "diff_streams": diff_streams}
g["verdict"] = "PASS" if (all(v["match"] for label in ("7kW", "main22") for v in g[label].values()) and
                          all(g["cluster"][label]["excludes_zero"] for label in ("7kW", "main22")) and
                          g["b1b2"]["main22"]["energy_identical"] == g["b1b2"]["main22"]["streams"] and
                          g["b1b2"]["main22"]["capacity_identical"] == g["b1b2"]["main22"]["streams"]) else "FAIL"
res["checks"]["G_statistics"] = g
print("\nG M2 reproduce:", {lab: {b: (v["match"], round(v["point"], 6), round(v["stored_point"] or 0, 6)) for b, v in g[lab].items()} for lab in ("7kW", "main22")})
print("G site-cluster:", {lab: {k: g["cluster"][lab][k] for k in ("point", "low", "high", "n_clusters", "n_obs", "excludes_zero")} for lab in ("7kW", "main22")})
print("G B1/B2:", {lab: {k: g["b1b2"][lab][k] for k in ("streams", "energy_identical", "capacity_identical", "diff_columns")} for lab in ("7kW", "main22")})

# ---------------- compile scripts in memory (no writes) ----------------
comp = {}
for fn in ("fit_for_model.py", "audit2.py", "audit3.py"):
    src = open(os.path.join(A, fn), encoding="utf-8").read()
    try:
        compile(src, fn, "exec"); comp[fn] = "ok"
    except SyntaxError as exc:
        comp[fn] = "syntax error: %s" % exc
res["checks"]["H_scripts_compile"] = comp
print("\nH scripts compile:", comp)

# snapshot: hashes of verified artifacts
import hashlib
def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
snap = []
for d in (A, C, EV):
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.isfile(p) and name.endswith((".py", ".csv", ".json", ".md", ".out")):
            snap.append({"path": os.path.relpath(p, ROOT).replace(os.sep, "/"), "bytes": os.path.getsize(p),
                         "sha256": sha(p), "mtime": datetime.fromtimestamp(os.path.getmtime(p)).isoformat()})
res["snapshot"] = {"captured_local": datetime.now().isoformat(timespec="seconds"),
                   "contract_sha256": sha(os.path.join(R, "data", "processed", "public_parking_events.json")),
                   "window_export_sha256": sha(os.path.join(R, "data", "processed", "_window_events.csv")),
                   "files": snap}
res["summary"] = {k: v.get("verdict", "see details") for k, v in res["checks"].items() if isinstance(v, dict) and "verdict" in v}
with open(os.path.join(EV, "phase3_results.json"), "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, indent=1, default=str)
print("\nWROTE phase3_results.json", os.path.getsize(os.path.join(EV, "phase3_results.json")))
