# -*- coding: utf-8 -*-
"""R8-G Phase4 independent verification (R8-D). Read-only; writes only acceptance/evidence."""
import csv, json, math, os, random, re, statistics, sys, zipfile
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.getcwd(); R = os.path.join("research", "round8_20261031")
EV = os.path.join(R, "acceptance", "evidence")
res = {"checks": {}, "snapshot": {}}
def jload(p):
    with open(p, encoding="utf-8") as f: return json.load(f)
def rload(p):
    with open(p, encoding="utf-8", newline="") as f: return list(csv.DictReader(f))
def num(r, k): return float(r[k] or 0)
def docx_text(docx):
    p = os.path.join(R, "paper", docx)
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    return re.sub(r"<[^>]+>", "", xml)
rev7_draft_text = docx_text("Electrification_tipping_point_v2_draft_rev7.docx")
rev7_si_text = docx_text("Electrification_tipping_point_v2_supplementary_rev7.docx")
contract = jload(os.path.join(R, "data", "processed", "public_parking_events.json"))
ev = contract["events"]
ps = rload(os.path.join(R, "experiments_declared22", "per_stream_declared22.csv"))
e4 = rload(os.path.join(R, "experiments_declared22", "E4", "test_E4.csv"))
mv = rload(os.path.join(R, "analysis", "metrics_v2_decomposition.csv"))
dc = rload(os.path.join(R, "analysis", "demand_coupling.csv"))
ds = rload(os.path.join(R, "analysis", "dwell_scaling.csv"))
psmap = {r["stream_id"]: r for r in ps}

# ================= 1. metric identity at declared max k =================
cr = sum(num(r, "charge_requests") for r in ps)
gate = sum(num(r, "gate_rejections") for r in ps)
noco = sum(num(r, "no_connector") for r in ps)
short = sum(num(r, "shortfall_sessions") for r in ps)
dlv = sum(num(r, "delivered_kwh") for r in ps)
dem = sum(num(r, "demand_kwh") for r in ps)
ratios = [num(r, "capacity_only_unmet_at_eval") for r in ps]
capmean = sum(ratios) / len(ratios)
pooled = (gate + noco + short) / cr
row_bad = []
for r in ps:
    c = num(r, "charge_requests"); ident = (num(r, "gate_rejections") + num(r, "no_connector") + num(r, "shortfall_sessions")) / c
    if abs(ident - num(r, "capacity_only_unmet_at_eval")) > 1e-9:
        row_bad.append({"stream": r["stream_id"], "identity": ident, "stored": num(r, "capacity_only_unmet_at_eval")})
one_stream = [r["stream_id"] for r in ps if abs(num(r, "gate_rejections") + num(r, "no_connector") - 1) < 1e-9]
# E4 declared22 policy A at max k
e4amax = [r for r in e4 if r["policy"] == "A" and r["k"] == psmap[r["stream_id"]]["k_max_declared"]]
e4sum = {"rows": len(e4amax), "charge": sum(num(r, "charge_requests") for r in e4amax),
         "capacity_unmet": sum(num(r, "num_capacity_unmet_requests") for r in e4amax),
         "delivered": sum(num(r, "delivered_kwh_incl_rejected") for r in e4amax),
         "demand": sum(num(r, "demand_kwh_incl_rejected") for r in e4amax),
         "capmean": sum(num(r, "capacity_only_unmet_rate") for r in e4amax) / len(e4amax),
         "ev_fail": sum(num(r, "num_ev_parking_failures") for r in e4amax),
         "ev_visits": sum(num(r, "den_exogenous_ev_visits") for r in e4amax),
         "ice_fail": sum(num(r, "num_ice_parking_failures") for r in e4amax),
         "ice_visits": sum(num(r, "den_exogenous_ice_visits") for r in e4amax)}
# metrics_v2 A max-k rows
mvamax = [r for r in mv if r["policy"] == "A" and r["k"] == psmap[r["stream"]]["k_max_declared"]]
mv_cap = [num(r, "capacity_only_unmet_rate") for r in mvamax]
mv_neg = [r for r in mvamax if num(r, "never_connected_rate") < 0]
mv_nc_formula = [1 - num(r, "admitted") / num(r, "charge_requests") for r in mvamax]
identity = {
  "charge_requests": cr, "gate": gate, "no_connector": noco, "gate_plus_noconnector": gate + noco,
  "shortfall_sessions": short, "delivered_kwh": round(dlv, 3), "demand_kwh": round(dem, 3),
  "capacity_mean_of_stream_ratios": round(capmean, 6), "capacity_pooled": round(pooled, 6),
  "identity_count_failures": len(row_bad), "identity_failures": row_bad[:5],
  "stream_with_single_never_connected": one_stream,
  "e4_a_max": e4sum,
  "metrics_v2_rows": len(mv), "metrics_v2_a_max_rows": len(mvamax),
  "metrics_v2_capmean": round(sum(mv_cap) / len(mv_cap), 6),
  "metrics_v2_never_connected_negative": len(mv_neg),
  "metrics_v2_never_connected_formula": "1 - admitted/total charge_requests (nonsense: uses all parking admissions)",
  "metrics_v2_nc_recompute_matches_column": all(abs(a - num(r, "never_connected_rate")) < 1e-6 for a, r in zip(mv_nc_formula, mvamax)),
  "delivered_plus_shortfall": round(dlv + sum(num(r, "gap_kwh") for r in ps), 3),
}
identity["verdict"] = "PASS" if (cr == 137 and gate + noco == 1 and short == 80 and abs(dlv - 984.221) < 1e-6 and
  abs(dem - 1891.028) < 1e-6 and abs(capmean - 0.583521) < 1e-9 and abs(pooled - 81/137) < 1e-12 and
  not row_bad and len(mvamax) == 20 and abs(sum(mv_cap)/len(mv_cap) - capmean) < 1e-9 and len(e4amax) == 20) else "FAIL"
res["checks"]["M1_metric_identity"] = identity
print("M1 identity", {k: identity[k] for k in ("charge_requests","gate_plus_noconnector","shortfall_sessions","delivered_kwh","demand_kwh","capacity_mean_of_stream_ratios","capacity_pooled","identity_count_failures")}, "verdict", identity["verdict"])
print("   E4 A max", e4sum)
# service_metrics.py:188/200-201: capacity_unmet = gate refusal + shortfall session; no_connector is access, excluded
row_bad2 = []
for r in ps:
    c = num(r, "charge_requests")
    ident = (num(r, "gate_rejections") + num(r, "shortfall_sessions")) / c
    if abs(ident - num(r, "capacity_only_unmet_at_eval")) > 1e-9:
        row_bad2.append({"stream": r["stream_id"], "identity": ident, "stored": num(r, "capacity_only_unmet_at_eval")})
pooled_capacity = (gate + short) / cr
pooled_with_nc = (gate + noco + short) / cr
identity["pooled_capacity_correct"] = round(pooled_capacity, 6)
identity["pooled_with_never_connected"] = round(pooled_with_nc, 6)
identity["identity_count_failures_correct"] = len(row_bad2)
identity["verdict"] = "PASS" if (cr == 137 and gate + noco == 1 and short == 80 and abs(dlv - 984.221) < 1e-6 and
  abs(dem - 1891.028) < 1e-6 and abs(capmean - 0.583521) < 1e-6 and not row_bad2 and len(mvamax) == 20) else "FAIL"
res["checks"]["M1_metric_identity"] = identity
res["checks"]["M1b_pooled_claim"] = {"claimed_pooled_pct": 59.12, "correct_capacity_only_pooled_pct": round(100 * pooled_capacity, 2),
  "computed_with_never_connected_pct": round(100 * pooled_with_nc, 2),
  "rev7_draft_59_12_count": rev7_draft_text.count("59.12"), "rev7_draft_58_39_count": rev7_draft_text.count("58.39"),
  "rev7_si_58_4_count": rev7_si_text.count("58.4"),
  "verdict": "FAIL" if abs(100 * pooled_capacity - 59.12) > 0.01 else "PASS"}
print("M1 correct pooled capacity-only", round(100 * pooled_capacity, 2), "| pooled with never-connected", round(100 * pooled_with_nc, 2),
      "| identity failures", len(row_bad2), "| verdict", identity["verdict"], "| M1b", res["checks"]["M1b_pooled_claim"]["verdict"])
print("   metrics_v2 neg never_connected rows", len(mv_neg), "sample", [(r["stream"], r["never_connected_rate"], r["admitted"], r["charge_requests"]) for r in mv_neg[:3]])

# ================= 2. demand coupling =================
req = [e for e in ev if e.get("is_ev") and e.get("needs_charge")]
evalls = [e for e in ev if e.get("is_ev")]
E = [float(e["energy_kwh"]) for e in req]; T = [float(e["dwell_min"]) / 60.0 for e in req]
P = 22.0
def ideal(EE, TT, frac):
    n = len(EE); dem = sum(EE); dlv = sum(min(frac * e, P * t) for e, t in zip(EE, TT))
    ok = sum(1 for e, t in zip(EE, TT) if frac * e <= P * t + 1e-9)
    return {"n": n, "demand_kwh": round(dem, 3), "delivered_kwh": round(dlv, 3),
            "energy_rate": dlv / dem, "session_success": ok / n, "session_failure": 1 - ok / n}
A = {frac: ideal(E, T, frac) for frac in (1.0, 0.75, 0.5, 0.25)}
# reimplement script B exactly
rng = random.Random(20261031)
Tmed = statistics.median(T); Tsd = statistics.pstdev(T); b = 1.0
def propensity(t): return 1.0 / (1.0 + math.exp(-b * (t - Tmed) / (Tsd if Tsd else 1.0)))
w = [propensity(float(e["dwell_min"]) / 60.0) for e in evalls]
order = sorted(range(len(evalls)), key=lambda i: -w[i] * rng.random())
chosen = set(order[:len(req)]); reqB = [evalls[i] for i in sorted(chosen)]
EB = sorted(E); TB = [float(e["dwell_min"]) / 60.0 for e in reqB]
B = {frac: ideal(EB, TB, frac) for frac in (1.0, 0.75, 0.5, 0.25)}
csvA = {float(r["target"]): r for r in dc if r["scenario"] == "A_independent"}
csvB = {float(r["target"]): r for r in dc if r["scenario"] == "B_dwell_conditioned"}
mismA = [f for f in A if abs(A[f]["delivered_kwh"] - float(csvA[f]["delivered_kwh"])) > 1e-6 or abs(A[f]["energy_rate"] - float(csvA[f]["energy_rate"])) > 1e-12 or abs(A[f]["session_failure"] - float(csvA[f]["session_failure"])) > 1e-12]
mismB = [f for f in B if abs(B[f]["delivered_kwh"] - float(csvB[f]["delivered_kwh"])) > 1e-6 or abs(B[f]["energy_rate"] - float(csvB[f]["energy_rate"])) > 1e-12 or abs(B[f]["session_failure"] - float(csvB[f]["session_failure"])) > 1e-12]
preserve = {"n_A": len(req), "n_B": len(reqB), "n_equal": len(req) == len(reqB) == 6588,
            "ev_count_contract": len(evalls), "ev_count_A": len(req), "ev_count_B": len(reqB),
            "demand_equal": abs(sum(E) - sum(EB)) < 1e-9,
            "energy_multiset_equal": sorted(E) == sorted(EB),
            "request_ids_A_subset_EV": all(e in evalls for e in req),
            "request_ids_B_subset_EV": all(e in evalls for e in reqB),
            "B_is_different_request_set": reqB != req,
            "A_targets": {str(f): {k: A[f][k] for k in ("n","demand_kwh","delivered_kwh","energy_rate","session_failure")} for f in A},
            "B_targets": {str(f): {k: B[f][k] for k in ("n","demand_kwh","delivered_kwh","energy_rate","session_failure")} for f in B},
            "csv_A_mismatches": mismA, "csv_B_mismatches": mismB}
src_dc = open(os.path.join(R, "analysis", "demand_coupling.py"), encoding="utf-8").read()
preserve["no_crop_in_generation"] = ("E=min(E" not in src_dc.replace(" ", "") and "E = min(E" not in src_dc and "del = min(E" not in src_dc)
preserve["demand_kwh_raw_sum_contract"] = round(sum(E), 3)
preserve["verdict_preserve"] = "PASS" if (preserve["n_equal"] and preserve["energy_multiset_equal"] and preserve["demand_equal"] and not mismA and not mismB) else "FAIL"
res["checks"]["D1_demand_coupling"] = preserve
print("D1 A/B", {f: (round(A[f]["energy_rate"],4), round(A[f]["session_failure"],4), round(B[f]["energy_rate"],4), round(B[f]["session_failure"],4)) for f in A}, "verdict", preserve["verdict_preserve"])
# post-hoc documentation
plan = open(os.path.join(R, "analysis", "DEMAND_COUPLING_PLAN.md"), encoding="utf-8").read()
doc = {"plan_header_posthoc": "在看到 R8 结果后制定的后续分析（不是原始预登记）" in plan,
       "plan_comments_not_identified": ("不可识别" in plan or "未启用" in plan),
       "plan_forbid_crop_delete": ("不得用 E=min(E,P*T) 生成需求" in plan and "不得删除难服务请求" in plan),
       "plan_stress_not_ci": "停留整体缩放 ±12% 作为压力诊断（不是自动成立的置信区间）" in plan,
       "plan_has_b": "负担" in plan or "停留条件分配" in plan}
res["checks"]["D2_doc"] = doc
print("D2 doc", doc)
res["checks"]["D2_doc"]["verdict"] = "PASS" if doc["plan_header_posthoc"] and doc["plan_stress_not_ci"] and doc["plan_forbid_crop_delete"] else "FAIL"

# ================= 3. dwell scaling =================
scale_rows = []
for s in (0.88, 1.0, 1.12):
    for frac in (1.0, 0.5):
        for label, EE, TT in (("A", E, T), ("B", EB, TB)):
            r = ideal(EE, [t * s for t in TT], frac)
            scale_rows.append({"scale": s, "scenario": label, "target": frac,
                               "energy_rate": round(r["energy_rate"], 4), "session_failure": round(r["session_failure"], 4)})
sc_mism = []
for r in ds:
    rec = next(x for x in scale_rows if abs(float(r["scale"]) - x["scale"]) < 1e-9 and r["scenario"] == x["scenario"] and abs(float(r["target"]) - x["target"]) < 1e-9)
    if abs(float(r["energy_rate"]) - rec["energy_rate"]) > 1e-6 or abs(float(r["session_failure"]) - rec["session_failure"]) > 1e-6:
        sc_mism.append((r, rec))
sc = {"rows": len(ds), "recomputed": scale_rows, "mismatches": sc_mism,
      "stress_label_script": "# dwell scaling sensitivity (stress test, not CI)" in src_dc,
      "stress_label_plan": "压力诊断（不是自动成立的置信区间）" in plan,
      "stress_label_content_rev7": "stress test" in open(os.path.join(R,"paper/content_rev7.py"),encoding="utf-8").read() and "not a confidence interval" in open(os.path.join(R,"paper/content_rev7.py"),encoding="utf-8").read(),
      "verdict": "PASS" if not sc_mism else "FAIL"}
res["checks"]["S1_dwell_scaling"] = sc
print("S1 scaling rows", len(ds), "mismatches", len(sc_mism), "labels", sc["stress_label_script"], sc["stress_label_plan"], sc["stress_label_content_rev7"], "verdict", sc["verdict"])

# ================= 4. 11.96% display =================
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "apps", "parking_lab")); sys.path.insert(0, os.path.join(ROOT, R, "engine"))
from apps.parking_lab.workbench import publicdata as pd
import runner
norm = pd.normalise_contract(contract); blocks = pd.site_day_blocks(norm)
split = runner.build_dataset(blocks, seed=20261031)
def dwell_mean(bs):
    vals = [float(e["dwell_min"]) for b in bs for e in b["events"]]
    return sum(vals) / len(vals), len(vals)
cal_mean, cal_n = dwell_mean(split["calibration"]); test_mean, test_n = dwell_mean(split["test"])
rel = (cal_mean - test_mean) / cal_mean
fitrows = rload(os.path.join(R, "experiments", "E1", "fit_metrics.csv"))
dwell_all = next(r for r in fitrows if r["row_kind"] == "dwell_fit" and r["category"] == "all")
c7 = open(os.path.join(R, "paper", "content_rev7.py"), encoding="utf-8").read()
rev7_docx = [f for f in os.listdir(os.path.join(R, "paper")) if "rev7" in f.lower() and f.endswith((".docx", ".pdf", ".json"))]
r6_doc_texts = {}
for docx in ("Electrification_tipping_point_v2_draft_rev6.docx", "Electrification_tipping_point_v2_supplementary_rev6.docx"):
    p = os.path.join(R, "paper", docx)
    if os.path.exists(p):
        with zipfile.ZipFile(p) as z: xml = z.read("word/document.xml").decode("utf-8", "replace")
        r6_doc_texts[docx] = re.sub(r"<[^>]+>", "", xml)
p4 = {"cal_mean": cal_mean, "test_mean": test_mean, "n_cal": cal_n, "n_test": test_n,
      "rel_error": rel, "rel_error_display": "%.2f%%" % (100 * rel),
      "fit_metrics_holdout_mean_rel_error": float(dwell_all["holdout_mean_rel_error"]),
      "fit_metrics_mean_cal": float(dwell_all["mean_calibration"]), "fit_metrics_mean_test": float(dwell_all["mean_test"]),
      "fit_metrics_ks": float(dwell_all["ks_statistic"]),
      "rel_all_spec_scale": "scale = 100.0; fmt = {:.2f}" in c7 and '"rel_all"' in c7,
      "rev7_build_artifacts": rev7_docx,
      "rev6_draft_0_12_count": r6_doc_texts.get("Electrification_tipping_point_v2_draft_rev6.docx", "").count("0.12%"),
      "rev6_draft_11_96_count": r6_doc_texts.get("Electrification_tipping_point_v2_draft_rev6.docx", "").count("11.96%"),
      "rev6_si_0_12_count": r6_doc_texts.get("Electrification_tipping_point_v2_supplementary_rev6.docx", "").count("0.12%"),
      "rev6_si_11_96_count": r6_doc_texts.get("Electrification_tipping_point_v2_supplementary_rev6.docx", "").count("11.96%"),
      "rev7_source_0_12": "0.12" in c7,
      "semantics_level_diff_not_prediction": "level difference between blocks, not a prediction error" in c7,
      "semantics_ks_not_mean_equality": "distributional difference rather than an equality of means" in c7,
      "verdict_value": None, "verdict_rev7_docx": "UNVERIFIED"}
p4["verdict_value"] = "PASS" if (abs(rel - 0.11955213710752803) < 1e-12 and abs(cal_mean - 51.06311806920595) < 1e-6 and abs(test_mean - 44.95841317665835) < 1e-6 and p4["semantics_level_diff_not_prediction"] and p4["semantics_ks_not_mean_equality"]) else "FAIL"
p4["rev7_draft_0_12pct_count"] = rev7_draft_text.count("0.12%")
p4["rev7_si_0_12pct_count"] = rev7_si_text.count("0.12%")
p4["rev7_draft_11_96_count2"] = rev7_draft_text.count("11.96%")
p4["rev7_si_11_96_count2"] = rev7_si_text.count("11.96%")
p4["rev7_draft_unresolved_or_token"] = rev7_draft_text.count("{{") + rev7_draft_text.count("UNRESOLVED") + rev7_draft_text.count("SKELETON")
p4["rev7_draft_semantics_level_diff"] = ("hold-out-to-calibration mean dwell difference" in rev7_draft_text and
                                         "not as an error of a predictive model" in rev7_draft_text)
p4["rev7_si_semantics_version_note"] = ("it is not an access measure" in rev7_si_text and "printed 0.12 where the value is 11.96%" in rev7_si_text)
p4["rev7_draft_ks_clause_present"] = "distributional difference rather than an equality of means" in rev7_draft_text
p4["verdict_rev7_docx"] = "PASS" if (p4["rev7_draft_0_12pct_count"] == 0 and p4["rev7_si_0_12pct_count"] == 0 and
                                     p4["rev7_draft_11_96_count2"] >= 1 and p4["rev7_draft_unresolved_or_token"] == 0) else "FAIL"
res["checks"]["P1_rel_all"] = p4
print("P1 rel", cal_mean, test_mean, rel, "->", p4["rel_error_display"], "verdict", p4["verdict_value"], "| rev7 docx/artifacts", rev7_docx)

# ================= 5. naming / metric formula consistency =================
import sys as _sys
_sys.path.insert(0, os.path.join(ROOT, R, "paper"))
import content_rev7 as c7mod
c7all = json.dumps({"MAIN": c7mod.MAIN, "SI": c7mod.SI}, ensure_ascii=False)
facts = {"never_connected_pct": 100 * (gate + noco) / cr,
         "shortfall_session_pct": 100 * short / cr,
         "energy_shortfall_pct": 100 * (1 - dlv / dem),
         "capmean_pct": 100 * capmean, "pooled_pct": 100 * pooled,
         "ev_fail_rate": e4sum["ev_fail"] / max(1, e4sum["ev_visits"]) * 100,
         "ice_fail_rate": e4sum["ice_fail"] / max(1, e4sum["ice_visits"]) * 100,
         "capacity_formula": "admission refusals + departed shortfall sessions over charge requests"}
# connector-only bound
sessions = defaultdict(list)
for e in req:
    sessions[(e["site_id"], e["arrival_ts"][:10])].append((e["arrival_ts"][11:19], float(e["dwell_min"])))
conc = []
for key, lst in sessions.items():
    pts = []
    for t, d in lst:
        h, m, s = [int(x) for x in t.split(":")]
        start = h * 60 + m + s / 60.0
        pts.append((start, 1)); pts.append((start + d, -1))
    pts.sort(key=lambda x: (x[0], x[1]))
    cur = mx = 0
    for _, dl in pts:
        cur += dl; mx = max(mx, cur)
    conc.append(mx)
facts["conc_n"] = len(conc); facts["conc_median"] = statistics.median(conc)
facts["conc_p90"] = sorted(conc)[int(0.9 * len(conc))]; facts["conc_max"] = max(conc)
naming = {"facts": facts,
          "text_has_capacity_access_claim": any(("not access" not in m.group(0).lower() and "not an access" not in m.group(0).lower()) for m in re.finditer(r"capacity[- ]only unmet[^.]{0,120}(access|charging success)", c7all, re.I)),
          "text_access_denial_phrases": len(re.findall(r"not access|not an access measure", c7all, re.I)),
          "text_says_not_access_measure": "it is not an access measure" in c7all,
          "text_capacity_formula_ok": "refused at admission or depart with less than their requested energy" in c7all,
          "text_table_metrics": [m for m in ("never-connected rate","EV parking failure rate","ICEV parking failure rate","departed shortfall session rate","energy shortfall ratio","capacity-only unmet share (mean over streams)") if m in c7all],
          "text_charging_success_phrase": "charging success" in c7all.lower(),
          "metrics_v2_never_connected_formula_bug": (len(mv_neg) > 0),
          "verdict_source": None, "verdict_rev7_docx": "UNVERIFIED"}
naming["verdict_source"] = "PASS" if (not naming["text_has_capacity_access_claim"] and naming["text_says_not_access_measure"] and not naming["text_charging_success_phrase"] and len(naming["text_table_metrics"]) == 6) else "FAIL"
res["checks"]["N1_naming"] = naming
print("N1 naming", {k: naming[k] for k in ("text_has_capacity_access_claim","text_says_not_access_measure","text_charging_success_phrase","text_table_metrics","verdict_source")}, "facts", {k: round(v,4) if isinstance(v,float) else v for k,v in facts.items()})
# hardcoded facts vs data
hard = {"cr": 137, "gate_noco": 1, "short": 80, "dlv": 984.221, "dem": 1891.028, "capmean": 0.583521,
        "ev": 0, "evvis": 452, "ice": 34, "icevis": 4643, "conc_n": 792, "conc_med": 2, "conc_p90": 4, "conc_max": 9}
hard_mismatch = {k: (hard[k], facts.get(k, e4sum.get(k))) for k in hard if k in hard and abs(float(hard[k]) - float(facts.get(k, e4sum.get(k, float("nan"))))) > 1e-6}
res["checks"]["N2_hardcoded_facts"] = {"expected": hard, "computed": {**e4sum, **facts}, "mismatches": hard_mismatch,
                                       "verdict": "PASS" if not hard_mismatch else "FAIL"}
print("N2 hardcoded mismatches", hard_mismatch)
res["checks"]["N3_pooled_and_table"] = {
  "draft_table_departed_shortfall_58_39": "58.39%" in rev7_draft_text,
  "draft_table_capacity_mean_58_35": "58.35%" in rev7_draft_text,
  "draft_text_pooled_59_12": "59.12" in rev7_draft_text,
  "si_capacity_80_137_58_4": "80/137 = 58.4%" in rev7_si_text,
  "text_no_charging_success": "charging success" not in rev7_draft_text.lower(),
  "verdict_capacity_pooled": "FAIL"}
print("N3 pooled/table", res["checks"]["N3_pooled_and_table"])

# snapshot
import hashlib
def sha(p):
    with open(p, "rb") as f: return hashlib.sha256(f.read()).hexdigest()
snapfiles = []
for rel in ("analysis/metrics_v2.py","analysis/metrics_v2_decomposition.csv","analysis/demand_coupling.py",
            "analysis/demand_coupling.csv","analysis/DEMAND_COUPLING_PLAN.md","analysis/dwell_scaling.csv",
            "experiments_declared22/per_stream_declared22.csv","experiments_declared22/E4/test_E4.csv",
            "experiments/E1/fit_metrics.csv","paper/content_rev7.py","paper/build_rev7.py",
            "paper/content_rev6.py","paper/evidence_rev6_main.json"):
    p = os.path.join(R, rel)
    if os.path.exists(p): snapfiles.append({"path": "research/round8_20261031/" + rel, "bytes": os.path.getsize(p), "sha256": sha(p), "mtime": __import__("datetime").datetime.fromtimestamp(os.path.getmtime(p)).isoformat()})
res["snapshot"] = {"captured_local": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                   "contract_sha256": sha(os.path.join(R, "data", "processed", "public_parking_events.json")),
                   "files": snapfiles}
res["summary"] = {k: v.get("verdict", "see details") for k, v in res["checks"].items()}
with open(os.path.join(EV, "phase4_results.json"), "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1, default=str)
print("\nWROTE phase4_results.json", os.path.getsize(os.path.join(EV, "phase4_results.json")))
print("summary", json.dumps(res["summary"], ensure_ascii=False))
