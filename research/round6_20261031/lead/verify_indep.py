# -*- coding: utf-8 -*-
"""Lead 独立复核 A/B 关键断言（不导入分析脚本，只读 JSON 与模块 API）。"""
import json, math, os, sys
ROOT = os.getcwd()
sys.path.insert(0, ROOT)
from apps.parking_lab.workbench import service_semantics as S

def dump(tag, v):
    print(tag, json.dumps(v, ensure_ascii=False, default=str)[:600])

# ---- 1 五态手算反例 ----
base_sm = {"rates": {"capacity_only_unmet_rate": None, "ev_parking_failure_rate": 0.0,
                     "ice_parking_failure_rate": 0.0, "departed_shortfall_energy_rate": None},
           "denominators": {"exogenous_ev_visits": 0, "exogenous_ice_visits": 0,
                            "exogenous_charge_requests": 0, "departed_requested_kwh": 0},
           "numerators": {}}
cases = {}
row = {"charge_requests": 0, "capacity_only_unmet_rate": None, "service_metrics": base_sm}
cases["zero_demand"] = S.classify_rate("departed_shortfall_energy_rate", row)["status"]
cases["cap_na"] = S.classify_rate("capacity_only_unmet_rate", row)["status"]
sm = json.loads(json.dumps(base_sm)); sm["denominators"]["exogenous_charge_requests"] = 3
row_c = {"charge_requests": 3, "capacity_only_unmet_rate": 0.0, "service_metrics": sm}
cases["censored"] = S.classify_rate("departed_shortfall_energy_rate", row_c)["status"]
sm2 = json.loads(json.dumps(sm)); sm2["denominators"]["departed_requested_kwh"] = 7.0
row_m = {"charge_requests": 3, "capacity_only_unmet_rate": 0.0, "service_metrics": sm2}
cases["missing"] = S.classify_rate("departed_shortfall_energy_rate", row_m)["status"]
sm3 = json.loads(json.dumps(sm2)); sm3["rates"]["departed_shortfall_energy_rate"] = 1.5
row_i = {"charge_requests": 3, "capacity_only_unmet_rate": 0.0, "service_metrics": sm3}
cases["illegal"] = S.classify_rate("departed_shortfall_energy_rate", row_i)["status"]
dump("FIVE_STATES", cases)
# judge: censored 不得判 achieved；missing/illegal 不得判 achieved
dump("JUDGE_censored", S.judge(row_c, constraints=("departed_shortfall_energy_rate",)))
dump("JUDGE_missing", S.judge(row_m, constraints=("departed_shortfall_energy_rate",)))
dump("JUDGE_illegal", S.judge(row_i, constraints=("departed_shortfall_energy_rate",)))
dump("JUDGE_valid", S.judge({"charge_requests": 3, "capacity_only_unmet_rate": 0.01,
                             "service_metrics": json.loads(json.dumps(sm2))}, constraints=("capacity_only_unmet_rate",)))

# ---- 2 A 的 59 曲线复算计数 ----
d = json.load(open("research/round6_20261031/a_semantics/recompute_59_curves.json", encoding="utf-8"))
print("RECOMPUTE keys:", list(d)[:14])
for k in ("summary", "counts", "totals"):
    if k in d:
        dump("RECOMPUTE_" + k, d[k])

# ---- 3 Q2 元数据与 Mimic 证据 ----
q2 = json.load(open("research/round6_20261031/a_info/q2_info_regimes.json", encoding="utf-8"))
print("Q2 top:", {k: q2.get(k) for k in ("information_regime", "analysis_only", "policy_kind", "can_mimic_I0", "exit_code", "workers")})
print("Q2 rows:", len(q2.get("rows", [])))
print("Q2 auth:", json.dumps(q2.get("authorization"), ensure_ascii=False)[:400])

# ---- 4 Q3 四类独立复算（round3 main ref s10）----
R = "research/round3_20261031/results"

def num(v): return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))

def st(v, den):
    if not num(den): return "missing"
    if float(den) <= 0: return "na"
    if v is None: return "missing"
    if not num(v) or not (-1e-12 <= float(v) <= 1 + 1e-12): return "illegal"
    return "valid"

def feasible(row):
    for val, den in [(row.get("capacity_only_unmet_rate"), row.get("charge_requests")),
                     ((row.get("service_metrics") or {}).get("rates", {}).get("ev_parking_failure_rate"),
                      (row.get("service_metrics") or {}).get("denominators", {}).get("exogenous_ev_visits")),
                     ((row.get("service_metrics") or {}).get("rates", {}).get("ice_parking_failure_rate"),
                      (row.get("service_metrics") or {}).get("denominators", {}).get("exogenous_ice_visits"))]:
        s = st(val, den)
        if s == "valid":
            if float(val) > 0.05 + 1e-12: return False
        elif s == "na": continue
        else: return False
    return True

sets = {}
for tag, rule in [("main_A_pi0_ref_s10","A"),("main_B_pi1_ref_s10","B"),("main_C_quota_ref_s10","C"),("main_D_pi2_ref_s10","D")]:
    doc = json.load(open(R + "/" + tag + ".json", encoding="utf-8"))
    g = {}
    for row in doc["rows"]: g.setdefault((row["lot_id"], row["seed"]), {})[int(row["k"])] = row
    for key, bk in g.items(): sets[(rule, key[0], key[1])] = [k for k in sorted(bk) if feasible(bk[k])]
cats = {"both": 0, "onlyA": 0, "onlyB": 0, "neither": 0}
disjoint = []
for lot in sorted({k[1] for k in sets}):
    for seed in sorted({k[2] for k in sets}):
        ka, kb = sets.get(("A", lot, seed), []), sets.get(("B", lot, seed), [])
        if ka and kb:
            cats["both"] += 1
            if not (set(ka) & set(kb)): disjoint.append((lot, seed))
        elif ka: cats["onlyA"] += 1
        elif kb: cats["onlyB"] += 1
        else: cats["neither"] += 1
dump("Q3_REF_4CAT_INDEP", cats)
dump("Q3_REF_disjoint", disjoint)
# 形状：所有非空集合是否连续
bad = [(k, v) for k, v in sets.items() if v and v != list(range(v[0], v[-1] + 1))]
dump("Q3_noninterval", {"count": len(bad), "examples": bad[:3]})

# ---- 5 机制模型独立计数 ----
scm = None
import importlib.util
spec = importlib.util.spec_from_file_location("scm", "research/round4_20261031/mechanism/shared_capacity_mechanism.py")
scm = importlib.util.module_from_spec(spec); spec.loader.exec_module(scm)
inst = scm.make_instance(seed=1, n=6, ev_share=0.4, q_need=0.1, dwell_ev=5, dwell_ice=5,
                         rate_per_slot=1.6, ev_offset=-1, ice_offset=1)
r0 = scm.simulate(inst, 0, "pi0"); r1 = scm.simulate(inst, 1, "pi0")
dump("Q1_mechanism_k0_k1", {"k0": r0["rates"], "k1": r1["rates"], "counts0": r0.get("counts"), "counts1": r1.get("counts")})
