# -*- coding: utf-8 -*-
"""审查核查 2/3：alpha 与第四约束重分析（只读曲线，不重跑仿真、不扩网格）。

alpha in {0.02, 0.05, 0.10}；约束集 A=原三条，B=原三条+departed_shortfall_energy_rate<=0.05（固定）。
对每条曲线每个 (lot, seed) 求联合最小 k；Delta k = k_A(专用) - k_rule(共享)。
零分母按预登记标 not_applicable 跳过；真实缺失（分母>0）记 not achieved。

命令：python research/round5_20261031/review/reanalysis_alpha_constraints.py
输出：research/round5_20261031/review/reanalysis_alpha_constraints.json
"""
from __future__ import annotations

import glob
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R3DIR = ROOT / "research/round3_20261031"
sys.path.insert(0, str(R3DIR))
import analyze_round3 as A3  # noqa: E402

OUT = HERE / "reanalysis_alpha_constraints.json"
COMMAND = "python research/round5_20261031/review/reanalysis_alpha_constraints.py"
ALPHAS = (0.02, 0.05, 0.10)
FOURTH = 0.05
EPS = 1e-12
SETS = {"A": tuple(A3.CONSTRAINTS),
        "B": tuple(A3.CONSTRAINTS) + ("departed_shortfall_energy_rate",)}
RATE_TAGS = {"A": "A", "B": "B", "C": "C", "D": "D"}
TAG_BY_FILE = {"A_pi0": "A", "B_pi1": "B", "C_quota": "C", "D_pi2": "D"}


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def rate_cell(row, name):
    if name == "capacity_only_unmet_rate":
        value, den = row.get(name), row.get("charge_requests")
    else:
        sm = row.get("service_metrics")
        if not isinstance(sm, dict):
            return {"value": None, "den": None, "category": "true_missing"}
        rates = sm.get("rates") if isinstance(sm.get("rates"), dict) else {}
        dens = sm.get("denominators") if isinstance(sm.get("denominators"), dict) else {}
        den_key = {"ev_parking_failure_rate": "exogenous_ev_visits",
                   "ice_parking_failure_rate": "exogenous_ice_visits",
                   "departed_shortfall_energy_rate": "departed_requested_kwh"}[name]
        value, den = rates.get(name), dens.get(den_key)
    if value is None:
        if _num(den) and math.isfinite(float(den)) and float(den) > 0.0:
            return {"value": None, "den": den, "category": "true_missing"}
        if _num(den) and math.isfinite(float(den)) and float(den) <= 0.0:
            return {"value": None, "den": den, "category": "zero_denominator"}
        return {"value": None, "den": den, "category": "true_missing"}
    if not _num(value) or not math.isfinite(float(value)) or float(value) < -EPS or float(value) > 1 + EPS:
        return {"value": value, "den": den, "category": "illegal"}
    return {"value": float(value), "den": den, "category": "valid"}


def joint_variant(by_k, alpha, set_name):
    ks = sorted(int(k) for k in by_k)
    for k in ks:
        row = by_k[k]
        ok = True
        for name in SETS[set_name]:
            limit = FOURTH if (set_name == "B" and name == "departed_shortfall_energy_rate") else alpha
            cell = rate_cell(row, name)
            if cell["category"] == "valid":
                if cell["value"] > limit + EPS:
                    ok = False
                    break
            elif cell["category"] == "zero_denominator":
                continue
            else:
                ok = False
                break
        if ok:
            return {"k": int(k), "status": "achieved", "k_max": ks[-1]}
    return {"k": None, "status": "not_achieved_within_kmax", "k_max": ks[-1] if ks else None}


def load_blocks():
    blocks = []
    rule_rows = {}
    meta_first = None
    for tag, rule in TAG_BY_FILE.items():
        document = A3.load_curve(tag, 10)
        rows = document["rows"]
        meta_first = meta_first or document.get("meta", {})
        grouped = {}
        for row in rows:
            grouped.setdefault((row["lot_id"], int(row["seed"])), {})[int(row["k"])] = row
        rule_rows[rule] = grouped
    blocks.append({"id": "round3_REF", "kind": "round3_main_plus_expand",
                   "paths": ["research/round3_20261031/results/main_{A_pi0,B_pi1,C_quota,D_pi2}_ref_s10.json",
                             "research/round3_20261031/results/expand_A_pi0_TPE0330_s10.json"],
                   "rules": sorted(rule_rows),
                   "k_max_by_rule": {r: max(max(v) for v in g.values()) for r, g in rule_rows.items()},
                   "meta": {k: meta_first.get(k) for k in ("p_ev_override", "q_need_override",
                                                           "scenario_model", "charger_kw", "feeder_kw",
                                                           "horizon_min", "rule")},
                   "rows": rule_rows})
    scenario_files = {}
    for path in sorted(glob.glob(str(ROOT / "research/round4_20261031/results/scenario_*_s5.json"))):
        name = Path(path).name
        rest = name[len("scenario_"):-len("_s5.json")]
        scenario, rule_tag = rest.rsplit("_", 1)
        if rule_tag not in RATE_TAGS:
            continue
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        scenario_files.setdefault(scenario, {"rules": {}, "meta": doc.get("meta", {}),
                                             "paths": []})["rules"][rule_tag] = doc["rows"]
        scenario_files[scenario]["paths"].append("research/round4_20261031/results/" + name)
    for scenario, payload in sorted(scenario_files.items()):
        rule_rows = {}
        for rule_tag, rows in payload["rules"].items():
            grouped = {}
            for row in rows:
                grouped.setdefault((row["lot_id"], int(row["seed"])), {})[int(row["k"])] = row
            rule_rows[rule_tag] = grouped
        meta = payload["meta"]
        blocks.append({"id": "round4_" + scenario, "kind": "round4_source_scenario",
                       "paths": payload["paths"], "rules": sorted(rule_rows),
                       "k_max_by_rule": {r: max(max(v) for v in g.values())
                                         for r, g in rule_rows.items()},
                       "meta": {k: meta.get(k) for k in ("p_ev_override", "q_need_override",
                                                         "charge_scenario", "scenario_model",
                                                         "charger_kw", "feeder_kw", "horizon_min")},
                       "rows": rule_rows})
    return blocks


def quartiles(values):
    if not values:
        return None, None, None
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        return ordered[0], ordered[0], ordered[0]

    def q(p):
        pos = (n - 1) * p
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)
    return q(0.25), q(0.5), q(0.75)


def main():
    blocks = load_blocks()
    unit_k = {}
    for block in blocks:
        for rule, grouped in block["rows"].items():
            for key, by_k in grouped.items():
                for set_name in SETS:
                    for alpha in ALPHAS:
                        unit_k[(block["id"], rule, key, set_name, alpha)] = joint_variant(
                            by_k, alpha, set_name)

    aggregates = []
    per_block = []
    baseline_changes = []
    stratified = []
    for block in blocks:
        block_rules = block["rules"]
        shared_rules = [r for r in block_rules if r != "A"]
        for rule in shared_rules:
            for set_name in SETS:
                for alpha in ALPHAS:
                    deltas, cats = [], {"both_achieved": 0, "only_dedicated": 0,
                                        "only_shared": 0, "neither_achieved": 0}
                    excluded = 0
                    pairs_total = 0
                    for key in block["rows"][rule]:
                        if key not in block["rows"]["A"]:
                            continue
                        pairs_total += 1
                        ka = unit_k[(block["id"], "A", key, set_name, alpha)]["k"]
                        ks = unit_k[(block["id"], rule, key, set_name, alpha)]["k"]
                        k_a_max = block["k_max_by_rule"]["A"]
                        k_s_max = block["k_max_by_rule"][rule]
                        if ka is not None and ks is not None:
                            cats["both_achieved"] += 1
                        elif ka is not None:
                            cats["only_dedicated"] += 1
                        elif ks is not None:
                            cats["only_shared"] += 1
                        else:
                            cats["neither_achieved"] += 1
                        if ka is not None and ks is not None:
                            if ka > k_s_max:
                                excluded += 1
                                continue
                            deltas.append(ka - ks)
                    q1, med, q3 = quartiles(deltas)
                    rec = {"pair_set": "block_rule", "block": block["id"], "rule": rule,
                           "alpha": alpha, "constraint_set": set_name,
                           "n_pairs": pairs_total, "n_delta": len(deltas),
                           "n_excluded_asymmetric_kmax": excluded,
                           "median": med, "q1": q1, "q3": q3,
                           "positive": sum(1 for d in deltas if d > 0),
                           "negative": sum(1 for d in deltas if d < 0),
                           "zero": sum(1 for d in deltas if d == 0),
                           "min": min(deltas) if deltas else None,
                           "max": max(deltas) if deltas else None,
                           "feasibility": cats}
                    per_block.append(rec)

    for rule in ("B", "C", "D"):
        for set_name in SETS:
            for alpha in ALPHAS:
                deltas, cats = [], {"both_achieved": 0, "only_dedicated": 0,
                                    "only_shared": 0, "neither_achieved": 0}
                pairs_total = 0
                excluded = 0
                for block in blocks:
                    if rule not in block["rules"]:
                        continue
                    for key in block["rows"][rule]:
                        if key not in block["rows"]["A"]:
                            continue
                        pairs_total += 1
                        ka = unit_k[(block["id"], "A", key, set_name, alpha)]["k"]
                        ks = unit_k[(block["id"], rule, key, set_name, alpha)]["k"]
                        if ka is not None and ks is not None:
                            cats["both_achieved"] += 1
                            if ka > block["k_max_by_rule"][rule]:
                                excluded += 1
                                continue
                            deltas.append(ka - ks)
                        elif ka is not None:
                            cats["only_dedicated"] += 1
                        elif ks is not None:
                            cats["only_shared"] += 1
                        else:
                            cats["neither_achieved"] += 1
                q1, med, q3 = quartiles(deltas)
                aggregates.append({"rule": rule, "alpha": alpha, "constraint_set": set_name,
                                   "n_pairs": pairs_total, "n_delta": len(deltas),
                                   "n_excluded_asymmetric_kmax": excluded,
                                   "median": med, "q1": q1, "q3": q3,
                                   "positive": sum(1 for d in deltas if d > 0),
                                   "negative": sum(1 for d in deltas if d < 0),
                                   "zero": sum(1 for d in deltas if d == 0),
                                   "min": min(deltas) if deltas else None,
                                   "max": max(deltas) if deltas else None,
                                   "feasibility": cats})

    for block in blocks:
        for rule in block["rules"]:
            if rule == "A":
                continue
            for set_name in SETS:
                for alpha in ALPHAS:
                    changed = 0
                    total = 0
                    for key in block["rows"][rule]:
                        if key not in block["rows"]["A"]:
                            continue
                        total += 1
                        base = unit_k[(block["id"], rule, key, "A", 0.05)]["k"]
                        cur = unit_k[(block["id"], rule, key, set_name, alpha)]["k"]
                        if base != cur:
                            changed += 1
                    baseline_changes.append({"block": block["id"], "rule": rule,
                                             "alpha": alpha, "constraint_set": set_name,
                                             "n_units": total, "n_k_changed": changed})

    for alpha in ALPHAS:
        for set_name in SETS:
            rows = [c for c in baseline_changes if c["alpha"] == alpha and c["constraint_set"] == set_name]
            baseline_changes.append({"block": "ALL", "rule": "B/C/D",
                                     "alpha": alpha, "constraint_set": set_name,
                                     "n_units": sum(r["n_units"] for r in rows),
                                     "n_k_changed": sum(r["n_k_changed"] for r in rows)})

    missing = []
    scenario_blocks = [b for b in blocks if b["kind"] == "round4_source_scenario"]
    missing.append({"item": "round4 情景块缺 C_quota 曲线",
                    "expected_files": ["scenario_%s_C_s5.json" % b["id"][len("round4_"):]
                                       for b in scenario_blocks],
                    "why": "情景块的 Delta k 只覆盖 B/D；C 只能引用 round3 REF 块，不能与情景块配对",
                    "status": "未补算（先报告）"})
    missing.append({"item": "round4 情景块只有 seeds 1-5",
                    "expected_files": ["scenario_<sid>_<A|B|D>_s10.json（15 条 s10 曲线）"],
                    "why": "与第三轮 s10 配对/外部时需 6-10 种子；本轮不擅自跑",
                    "status": "未补算（先报告）"})
    missing.append({"item": "B/C/D 的 TPE0330 未扩展到 k>40（A 已扩展）",
                    "expected_files": ["expand_B_pi1_TPE0330_s10.json",
                                       "expand_C_quota_TPE0330_s10.json",
                                       "expand_D_pi2_TPE0330_s10.json"],
                    "why": "A 在该场站可到 k>40 时，B/C/D 的上界不同，Delta 不可比（本轮已剔除不对称对）",
                    "status": "未补算（先报告）"})
    missing.append({"item": "round4 情景块 feeder_kw=120 与 round3 REF 的 336 不同口径",
                    "expected_files": ["scenario_<sid>_<A|B|D>_s5.json（feeder=336 版本，15 条）"],
                    "why": "feeder 容量不同，跨块 Delta k 不可合并；若要与第三轮主口径比较，需按 feeder=336 重跑或仅作分块描述",
                    "status": "未补算（先报告）"})
    missing.append({"item": "round4 情景块只含 5 个训练场站，无 validation 4 场站",
                    "expected_files": ["scenario_<sid>_<A|B|D>_s5.json（TPE0930/TPE1171/TPE1376/TPE1380 扩充）"],
                    "why": "外部效度/validation 验证据不能从情景块得到；第三轮 validation 结果未被本轮情景覆盖",
                    "status": "未补算（先报告）"})

    document = {
        "schema": "review/reanalysis_alpha_constraints/v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": COMMAND,
        "interpreter": "%s | Python %s" % (sys.executable, sys.version.split()[0]),
        "method": {
            "alpha_values": list(ALPHAS),
            "constraint_sets": {k: list(v) for k, v in SETS.items()},
            "fourth_constraint_limit": FOURTH,
            "alpha_applies_to": "A/B 集的前三条约束；第四条（离场缺电量率）固定 <= %.2f" % FOURTH,
            "na_policy": "零分母（service_metrics 分母=0）标 not_applicable 并跳过（PREREGISTRATION.json:61）",
            "true_missing_policy": "rate=None 且分母>0 或 service_metrics 缺失 -> 该 k 记 not achieved",
            "k_none_meaning": "k=None 表示 0..k_max 搜索上界内未达成，不是物理不可行",
            "delta_definition": "Delta k = k_A(dedicated_by_type) - k_shared(rule)；正值=共享规则所需 k 更小",
            "power": "charger_kw=7.0 全部一致；但 feeder_kw 分块不同：round3 REF=336.0，round4 情景块=120.0（各块 meta 实记录）。两块的 Delta 不可当作同一功率口径合并解释；见 missing_curves 的补算项",
            "demand": "round3 REF 与 round4 scenario REF 均为 p_EV=0.10 / q_need=0.36 的独立情景；其余 round4 情景 q_need 取 catalog 的 q_use->q_need 假设性迁移值",
            "censoring": "service_metrics 窗口 horizon_min=1440；期末 pending/右删失不算失败、不进离场能量比（service_metrics.py:14-20）",
            "pooling": "round3 REF 块与 round4 情景块分开报告；跨块合并仅为描述性，不作推断",
            "excluded_pairs": "k_A > 该块该规则的 k_max 时，Delta 不可比，计入 n_excluded_asymmetric_kmax，不进入中位数/四分位",
        },
        "blocks": [{k: b[k] for k in ("id", "kind", "paths", "rules", "k_max_by_rule", "meta")}
                   for b in blocks],
        "aggregate": aggregates,
        "per_block": per_block,
        "baseline_alpha_005_set_A": baseline_changes,
        "missing_curves": missing,
        "summary": {
            "blocks": len(blocks),
            "units": len(unit_k),
            "alpha_005_set_A_changed_units": sum(c["n_k_changed"] for c in baseline_changes
                                                 if c["block"] == "ALL" and c["alpha"] == 0.05
                                                 and c["constraint_set"] == "A"),
            "changed_total_by_comparison": [
                {"alpha": c["alpha"], "constraint_set": c["constraint_set"],
                 "n_units": c["n_units"], "n_k_changed": c["n_k_changed"]}
                for c in baseline_changes if c["block"] == "ALL"],
        },
        "notes": [
            "round3 块：A/B/C/D 各 9 场站 x seeds 1-10，k 0..40；A 的 TPE0330 被 expand 覆盖到 k<=200。",
            "round4 情景块：5 情景(REF/M08-*/M10-*) x 3 规则(A/B/D) x 5 场站 x seeds 1-5 x k 0..40。",
            "以上均是既有结果的重分析；没有新增仿真、没有扩网格、没有改机制实现。",
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "summary": document["summary"],
                      "missing": len(missing)}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
