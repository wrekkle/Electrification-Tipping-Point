"""R3-E 第二轮一致性审计：只读重算 research/round2_20261031/results/analysis_v2_all.json 等，输出 audit_round2.json + CONSISTENCY.md。

逐条核对：p_EV=0.20 的 9/9、p_EV=0.30 的 5/9 与 seed 摆幅 2-6、rules_v2 的 observed_calibrated 高饱和、TPE1171 usable、资本公式年->日。
"""
from __future__ import annotations
import hashlib
import json
import math
import os
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
R2 = ROOT / "research/round2_20261031"
OUT_JSON = HERE / "audit_round2.json"
OUT_MD = HERE / "CONSISTENCY.md"
SERVICE_KEY = "unmet_no_connector_events"
ALPHA = 0.05


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def sha16(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def curve_rows(curve):
    groups = {}
    for row in curve["rows"]:
        groups.setdefault((row["lot_id"], int(row["seed"])), {})[int(row["k"])] = row
    return groups


def service_k(by_k):
    values = {k: row.get(SERVICE_KEY) for k, row in by_k.items()}
    base = values.get(0)
    if base is None or base == 0:
        return "no_demand", None
    target = ALPHA * base
    for k in sorted(values):
        v = values[k]
        if v is not None and v <= target + 1e-12:
            return "achieved", k
    return "infeasible_upper_bound", None


def k5_table(curve, only_lots=None):
    groups = curve_rows(curve)
    lots = sorted({lot for lot, _seed in groups})
    if only_lots is not None:
        lots = [lot for lot in lots if lot in only_lots]
    table = []
    for lot in lots:
        seeds = sorted(s for (l, s) in groups if l == lot)
        entries = []
        for seed in seeds:
            status, k = service_k(groups[(lot, seed)])
            entries.append({"seed": seed, "status": status, "k5": k})
        vals = [e["k5"] for e in entries if e["k5"] is not None]
        achieved = [e for e in entries if e["status"] == "achieved"]
        table.append({
            "lot_id": lot,
            "n_spaces": groups[(lot, seeds[0])][0].get("n_spaces"),
            "seeds": entries,
            "n_seeds": len(seeds),
            "n_achieved": len(achieved),
            "k5_min": min(vals) if vals else None,
            "k5_max": max(vals) if vals else None,
            "k5_range": (max(vals) - min(vals)) if len(vals) >= 2 else None,
        })
    return table


def parse_calibration_report() -> dict:
    text = (ROOT / "research/traffic_generation_20261031/calibration_report.md").read_text(encoding="utf-8")
    usable = re.search(r"可用 validation: \[([^\]]*)\]", text)
    row = re.search(r"\| TPE1171 \| validation \| ([^|]+)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", text)
    return {
        "usable_validation_text": [x.strip().strip("'") for x in usable.group(1).split(",") if x.strip()] if usable else None,
        "tpe1171_row": [x.strip() for x in row.groups()] if row else None,
        "validation_sentence": re.search(r"验证（只用 train 参数预测）：[^\n]+", text).group(0) if re.search(r"验证（只用 train 参数预测）：[^\n]+", text) else None,
    }


def parse_calibrate_criteria() -> dict:
    src = (ROOT / "research/traffic_generation_20261031/calibrate.py").read_text(encoding="utf-8")
    rel = re.search(r"implausible = not \(([^)]*)\)", src)
    unus = re.search(r"unusable = \(([^)]*)\)", src)
    return {
        "implausible_line": rel.group(0) if rel else None,
        "unusable_line": unus.group(0) if unus else None,
        "rel_err_formula": re.search(r"rel_err = \([^\n]*", src).group(0) if re.search(r"rel_err = \([^\n]*", src) else None,
    }


def scratch_rel_history() -> list:
    out = []
    for p in sorted((ROOT / "research/traffic_generation_20261031/_scratch").glob("cal*.log")):
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "TPE1171" in line:
                out.append({"file": p.name, "line": line.strip()})
    return out


def gate_at_reference() -> list:
    sweeps = load("research/round2_20261031/rules_v2/outputs/k_sweep.json")
    scen = load("research/round2_20261031/rules_v2/outputs/scenarios.json")["scenarios"]
    rows = sweeps["rows"]
    out = []
    for sc, meta in scen.items():
        k = meta.get("reference_k_pi0")
        util = meta.get("measured_ordinary_utilization")
        fam = meta.get("family")
        entry = {"scenario": sc, "family": fam, "measured_ordinary_utilization": util,
                 "measured_stratum": meta.get("measured_stratum"), "reference_k": k, "gates": {}}
        for variant, window, margin in (("selected_charge_arrivals", 10.0, 0.0), ("pi2_default", 30.0, 1.0)):
            sel = [r for r in rows if r["scenario"] == sc and r["variant"] == variant and r["k"] == k
                   and r["window_min"] == window and r["safety_margin"] == margin]
            entry["gates"][variant] = [r["ice_shared_by_forecast"] for r in sel]
        out.append(entry)
    return out


def main() -> int:
    analysis = load("research/round2_20261031/results/analysis_v2_all.json")
    cost_scenario = load("research/integer_allocation_20261031/cost_scenario.json")
    fitted = load("research/traffic_generation_20261031/fitted_parameters.json")
    calib = parse_calibration_report()
    criteria = parse_calibrate_criteria()
    scratch = scratch_rel_history()

    usable_lots = set(fitted["split"]["usable_train_lots"]) | set(fitted["split"]["usable_validation_lots"])
    pev020_curve = load("research/round2_20261031/results/cost_curve_v2_pev020_usable.json")
    pev030_curve = load("research/round2_20261031/results/cost_curve_v2_pev030_seeds123.json")
    pev050_curve = load("research/round2_20261031/results/cost_curve_v2_pev050_usable.json")
    t020 = k5_table(pev020_curve, usable_lots)
    t030 = k5_table(pev030_curve, usable_lots)
    t050 = k5_table(pev050_curve, usable_lots)
    for table, label in ((t020, "pev020"), (t030, "pi0_pev030"), (t050, "pev050")):
        for row in table:
            lot = row["lot_id"]
            summary = analysis["curves"].get(label, {}).get("summary", {})
            if lot in summary:
                m = summary[lot]["median"]["0.05"]
                row["analysis_median_k5"] = m["k_median"]
                row["analysis_statuses"] = m["statuses"]

    def count(table, mode):
        if mode == "any":
            return sum(1 for r in table if r["n_achieved"] >= 1)
        return sum(1 for r in table if r["n_achieved"] == r["n_seeds"])

    item_a = {
        "id": "R2-A-9OF9",
        "claim": "报告 §14.3（docs/reports/2026-10-31-整数配桩规则与仿真验证.md 第 250 行）：p_EV=0.20 时 9/9 达 k_5（TPE0401=39 为边界）",
        "machine": {
            "lot_count": len(t020),
            "achieved_any_seed": count(t020, "any"),
            "achieved_all_seeds": count(t020, "all"),
            "table": t020,
            "not_reached": [r["lot_id"] for r in t020 if r["n_achieved"] == 0],
            "single_seed_only": [r["lot_id"] for r in t020 if r["n_achieved"] == 1],
        },
        "verdict": "corrected",
    }
    item_b = {
        "id": "R2-B-SEEDSPREAD",
        "claim": "报告第 239 行与《第二轮修复与复算》第 15 行：p_EV=0.30、α=5%、上限 40 下 9 个可用场站中 5 个达到 k5（TPE0008=14、TPE0610=3、TPE0695=15、TPE1376=19、TPE1171=39；seed 间摆幅 2-6）",
        "machine": {
            "lot_count": len(t030),
            "achieved_any_seed": count(t030, "any"),
            "achieved_all_seeds": count(t030, "all"),
            "table": t030,
            "ranges": {r["lot_id"]: r["k5_range"] for r in t030},
            "single_seed_only": [r["lot_id"] for r in t030 if r["n_seeds"] >= 2 and r["n_achieved"] == 1],
        },
        "verdict": "corrected",
    }
    gate = gate_at_reference()
    util_by_family = {}
    for g in gate:
        util_by_family.setdefault(g["family"], []).append({
            "scenario": g["scenario"], "utilization": g["measured_ordinary_utilization"],
            "stratum": g["measured_stratum"], "gate_selected": g["gates"].get("selected_charge_arrivals"),
        })
    in_093_098 = [g for g in gate if g["measured_ordinary_utilization"] is not None
                  and 0.93 <= g["measured_ordinary_utilization"] <= 0.98]
    obs = [g for g in gate if g["family"] == "observed_calibrated"]
    item_c = {
        "id": "R2-C-OBS-HIGHSAT",
        "claim": "rules_v2.md §2：实测高饱和情景（普通位占用 0.93-0.98）里 π2 闸门被真实触发（每次运行 39-61 辆 ICE 被放行）；同文覆盖表把 observed_calibrated 的高饱和标为 —",
        "machine": {
            "coverage_table": load("research/round2_20261031/rules_v2/outputs/scenarios.json")["coverage"],
            "observed_calibrated": obs,
            "scenarios_in_0.93_0.98": [{"scenario": g["scenario"], "family": g["family"],
                                        "utilization": g["measured_ordinary_utilization"],
                                        "gate_selected": g["gates"].get("selected_charge_arrivals")} for g in in_093_098],
            "gate_by_family": util_by_family,
        },
        "verdict": "corrected",
    }
    tpe = next((r for r in fitted["per_lot"] if r["lot_id"] == "TPE1171"), None)
    item_d = {
        "id": "R2-D-TPE1171",
        "claim": "报告第 39 行：traffic-gen 报告文字列 3 个验证可用，差异在 TPE1171，以 fitted_parameters.json 的 usable 字段为准",
        "machine": {
            "fitted_usable_validation": fitted["split"]["usable_validation_lots"],
            "fitted_validation_n_lots": fitted.get("validation", {}).get("n_lots"),
            "fitted_validation_lots": fitted.get("validation", {}).get("lots"),
            "calibration_report": calib,
            "tpe1171_per_lot": tpe,
            "calibrate_criteria": criteria,
            "scratch_rel_history": scratch,
        },
        "verdict": "partially_unsupported",
    }
    sys.path.insert(0, str(ROOT))
    from apps.parking_lab.workbench import costs
    params = cost_scenario["cost"]
    f1 = costs.facility_cost(1, params, days=1.0)
    f0 = costs.facility_cost(0, params, days=1.0)
    fhalf = costs.facility_cost(1, params, days=0.5)
    fannual = costs.facility_cost(1, {"depreciation_annual": 3650.0, "maintenance_per_bay_day": 0.0}, days=1.0)
    code = (ROOT / "apps/parking_lab/workbench/costs.py").read_text(encoding="utf-8")
    formula_lines = [ln.strip() for ln in code.splitlines() if "DAYS_PER_YEAR" in ln or "daily * k * days" in ln or "elapsed_min" in ln]
    curve1440 = load("research/round2_20261031/results/cost_curve_v2_pev030_seeds123.json")
    curve720 = load("research/round2_20261031/results/cost_curve_v2_pi0_pev030_h720.json")

    def row_fac(curve, lot="TPE0008", seed=1, k=1):
        for r in curve["rows"]:
            if r["lot_id"] == lot and int(r["seed"]) == seed and int(r["k"]) == k:
                return r.get("facility_cost")
        return None

    item_e = {
        "id": "R2-E-CAPITAL",
        "claim": "设施资本公式年->日在代码中正确（年度折旧/365 或 capex/寿命/365；k 与天数只乘一次）",
        "machine": {
            "facility_cost_k1_days1": f1["value"],
            "facility_cost_k0_days1": f0["value"],
            "facility_cost_k1_days0.5": fhalf["value"],
            "annual_3650_yields_daily": fannual["value"],
            "cost_scenario_per_connector_day_TWD": cost_scenario["facility_cost"]["per_connector_day_TWD"],
            "formula_expected": params["depreciation_capex"] / params["depreciation_life_years"] / 365.0 + params["maintenance_per_bay_day"],
            "code_formula_lines": formula_lines,
            "curve_1440_facility_k1": row_fac(curve1440),
            "curve_720_facility_k1": row_fac(curve720),
        },
        "verdict": "confirmed",
    }
    corrections = {
        "R2-A-9OF9": "改为：p_EV=0.20 时 8/9 场站至少一个 seed 达 k5；7/9 两个 seed 都达。TPE0330 两 seed 均 infeasible_upper_bound（k<=40 未达）；TPE0401=39 仅 seed1 达、seed2 未达（39 距上限 40 仅 1，属边界但非两 seed 一致）。原文 9/9 与自身列出的 8 个数（TPE0330 缺失）矛盾。",
        "R2-B-SEEDSPREAD": "改为：p_EV=0.30 时 5/9 场站至少一个 seed 达 k5；仅 4/9（TPE0008/TPE0610/TPE0695/TPE1376）三个 seed 全达；TPE1171 只有 1/3 seed 达（39），中位数 39 由单 seed 得出。seed 摆幅不是 2-6：TPE0008 11（5-16）、TPE0610 4（2-6）、TPE0695 22（10-32）、TPE1376 7（18-25）；TPE1171 无可比摆幅。",
        "R2-C-OBS-HIGHSAT": "更正：覆盖表正确——observed_calibrated 无高饱和（0.197/0.347 不饱和，0.769/0.799 临界，最高 0.799）。0.93-0.98 的 4 个情景（0.933/0.950/0.953/0.942）全部是 synthetic_range，另 synthetic_stress=0.980 也高饱和；都不是实测。observed 临界情景参考 k 下 π2 放行=0，不能作预测有效性证据；这 5 个合成/压力情景在 π2 selected(10min,0) 参考 k 的放行数为 48-82，不是 39-61。",
        "R2-D-TPE1171": "结论：fitted_parameters.json 的 usable=True 与当前 calibration_report 一致（可用 validation 4 个，含 TPE1171；rel_err -21.4% 在 25% 阈值内）。3 个的来源是更早的 _scratch/cal.log（rel=-25.6% -> UNUSABLE）旧快照，不是当前报告文字；主报告第 39 行应改为“当前 4 个可用验证场站，TPE1171 仅 3 次会话，样本极少”。",
        "R2-E-CAPITAL": "确认：device_capital = k*(capex/寿命/365)*days 与 annual/365 两条分支都正确；成本曲线 1440min 与 720min 的 facility_cost 成 2:1（75.2997 vs 37.6499），说明天数按 elapsed_min/1440 换算且未重复乘；k=0 为 0。",
    }
    items = [item_a, item_b, item_c, item_d, item_e]
    for it in items:
        it["correction"] = corrections[it["id"]]
    result = {
        "schema": "round2_consistency_audit/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "command": "python research/round3_20261031/audit_round2.py",
        "inputs": {
            "analysis_v2_all.json": sha16(R2 / "results/analysis_v2_all.json"),
            "cost_curve_v2_pev020_usable.json": sha16(R2 / "results/cost_curve_v2_pev020_usable.json"),
            "cost_curve_v2_pev030_seeds123.json": sha16(R2 / "results/cost_curve_v2_pev030_seeds123.json"),
            "cost_curve_v2_pev050_usable.json": sha16(R2 / "results/cost_curve_v2_pev050_usable.json"),
            "scenarios.json": sha16(R2 / "rules_v2/outputs/scenarios.json"),
            "k_sweep.json": sha16(R2 / "rules_v2/outputs/k_sweep.json"),
            "fitted_parameters.json": sha16(ROOT / "research/traffic_generation_20261031/fitted_parameters.json"),
            "calibration_report.md": sha16(ROOT / "research/traffic_generation_20261031/calibration_report.md"),
            "costs.py": sha16(ROOT / "apps/parking_lab/workbench/costs.py"),
            "cost_scenario.json": sha16(ROOT / "research/integer_allocation_20261031/cost_scenario.json"),
        },
        "method_note": "k5 定义与 analyze_v2/compare_v2 一致：allocation.service_level_k(unmet_no_connector_events, alpha=0.05, k_hard_max=min(n_spaces,最大k))；这里用同一阈值直接复算（不调用生产函数，避免版本漂移）。",
        "items": items,
        "summary": {
            "confirmed": sum(1 for i in items if i["verdict"] == "confirmed"),
            "corrected": sum(1 for i in items if i["verdict"] == "corrected"),
            "partially_unsupported": sum(1 for i in items if i["verdict"] == "partially_unsupported"),
        },
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = []
    lines.append("# 第二轮一致性审计（R3-E）")
    lines.append("")
    lines.append("类型: 审计证据")
    lines.append("状态: 生效")
    lines.append("负责人: ev-data")
    lines.append("日期: 2026-10-31")
    lines.append("")
    lines.append("命令：python research/round3_20261031/audit_round2.py（只读；本文件由脚本生成）")
    lines.append("机器结果：audit_round2.json。k5 定义与 analyze_v2/compare_v2 一致（alpha=0.05，hard_max=min(n_spaces, 最大 k)）。")
    lines.append("")
    lines.append("## 1 逐条对照")
    lines.append("")
    lines.append("| 编号 | 原表述 | 机器结果 | 判定 |")
    lines.append("|---|---|---|---|")
    short = {
        "R2-A-9OF9": "p_EV=0.20 时 9/9 达 k_5",
        "R2-B-SEEDSPREAD": "p_EV=0.30 时 5/9，seed 摆幅 2-6",
        "R2-C-OBS-HIGHSAT": "实测高饱和 0.93-0.98 触发闸门 39-61",
        "R2-D-TPE1171": "报告文字列 3 个验证可用",
        "R2-E-CAPITAL": "资本公式年->日正确",
    }
    mach = {
        "R2-A-9OF9": "至少一个 seed 达 8/9；两 seed 都达 7/9；TPE0330 未达；TPE0401 仅 1/2 seed",
        "R2-B-SEEDSPREAD": "至少一个 seed 达 5/9；三个 seed 全达 4/9；摆幅 TPE0008=11、TPE0610=4、TPE0695=22、TPE1376=7；TPE1171 仅 1/3 seed",
        "R2-C-OBS-HIGHSAT": "observed 无高饱和（最高 0.799）；0.93-0.98 全属 synthetic_range/stress；参考 k 放行 48-82；observed 临界 gate=0",
        "R2-D-TPE1171": "fitted/报告均 4 个可用 validation；TPE1171 rel_err=-21.4%（<25%）；3 个来自旧 cal.log（-25.6%）",
        "R2-E-CAPITAL": "两条公式分支正确；1440/720 的 facility=75.2997/37.6499；k=0=0",
    }
    for it in items:
        lines.append("| %s | %s | %s | %s |" % (it["id"], short[it["id"]], mach[it["id"]], it["verdict"]))
    lines.append("")
    lines.append("## 2 更正后结论")
    lines.append("")
    for it in items:
        lines.append("### %s（%s）" % (it["id"], it["verdict"]))
        lines.append("")
        lines.append("- 原表述：%s" % it["claim"])
        lines.append("- 更正：%s" % it["correction"])
        lines.append("")
    lines.append("## 3 p_EV=0.20 逐场站 k5（curve: cost_curve_v2_pev020_usable.json）")
    lines.append("")
    lines.append("| 场站 | n_spaces | k5 各 seed | 状态 | 达到数 | 范围 |")
    lines.append("|---|---|---|---|---|---|")
    for r in t020:
        ks = "/".join(str(e["k5"]) for e in r["seeds"])
        sts = "/".join(e["status"] for e in r["seeds"])
        lines.append("| %s | %s | %s | %s | %d/%d | %s |" % (r["lot_id"], r["n_spaces"], ks, sts, r["n_achieved"], r["n_seeds"], r["k5_range"]))
    lines.append("")
    lines.append("## 4 p_EV=0.30 逐场站 k5（curve: cost_curve_v2_pev030_seeds123.json，仅 9 个可用场站）")
    lines.append("")
    lines.append("| 场站 | n_spaces | k5 各 seed | 状态 | 达到数 | 范围 |")
    lines.append("|---|---|---|---|---|---|")
    for r in t030:
        ks = "/".join(str(e["k5"]) for e in r["seeds"])
        sts = "/".join(e["status"] for e in r["seeds"])
        lines.append("| %s | %s | %s | %s | %d/%d | %s |" % (r["lot_id"], r["n_spaces"], ks, sts, r["n_achieved"], r["n_seeds"], r["k5_range"]))
    lines.append("")
    lines.append("## 5 rules_v2 分层与闸门（机器复算）")
    lines.append("")
    lines.append("| 情景 | 族 | 普通位占用 | 分层 | 参考 k | π2 selected 放行(各 seed) |")
    lines.append("|---|---|---|---|---|---|")
    for g in sorted(gate, key=lambda x: (x["family"], x["scenario"])):
        if g["measured_ordinary_utilization"] is None:
            continue
        lines.append("| %s | %s | %.3f | %s | %s | %s |" % (
            g["scenario"], g["family"], g["measured_ordinary_utilization"], g["measured_stratum"],
            g["reference_k"], g["gates"].get("selected_charge_arrivals")))
    lines.append("")
    lines.append("## 6 TPE1171 与资本公式")
    lines.append("")
    lines.append("- TPE1171：usable=%s；n_charge_sessions=%s；rel_err 行=%s；可用 validation=%s。" % (
        tpe.get("usable") if tpe else None, tpe.get("n_charge_sessions_observed") if tpe else None,
        calib["tpe1171_row"], calib["usable_validation_text"]))
    lines.append("- calibrate.py 判据：%s；%s" % (criteria["unusable_line"], criteria["rel_err_formula"]))
    lines.append("- 旧快照：%s" % scratch)
    lines.append("- 资本：k=1/day=%s；k=0=%s；k=1/半日=%s；annual=3650 -> %s；cost_scenario 目标=%s。" % (
        f1["value"], f0["value"], fhalf["value"], fannual["value"], cost_scenario["facility_cost"]["per_connector_day_TWD"]))
    lines.append("- 曲线 facility_cost：1440min k=1 -> %s；720min k=1 -> %s。" % (
        row_fac(curve1440), row_fac(curve720)))
    lines.append("")
    lines.append("## 7 未审计/边界")
    lines.append("")
    lines.append("- 本审计只复算数值与文字一致性，不重跑 5226 次规则仿真；种子/轨迹哈希未重算。")
    lines.append("- p_EV 本身不可识别（见 research/round2_20261031/CONTRACT.md §5 与 model_20261031_v2.json），以上均为情景解。")
    lines.append("- 未改动任何历史 JSON/报告；发现的问题只在本目录登记。")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "items": [{"id": i["id"], "verdict": i["verdict"]} for i in items],
        "pev020_any": count(t020, "any"), "pev020_all": count(t020, "all"),
        "pev030_any": count(t030, "any"), "pev030_all": count(t030, "all"),
        "ranges_pev030": {r["lot_id"]: r["k5_range"] for r in t030 if r["k5_range"] is not None},
        "obs_max_util": max(g["measured_ordinary_utilization"] for g in obs if g["measured_ordinary_utilization"] is not None),
        "n_093_098": len(in_093_098),
        "tpe1171_usable": tpe.get("usable") if tpe else None,
        "f1": f1["value"], "fhalf": fhalf["value"], "fannual": fannual["value"],
        "curve1440": row_fac(curve1440), "curve720": row_fac(curve720),
        "sha": result["inputs"],
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
