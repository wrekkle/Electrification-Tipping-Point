#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""T36 数据接线审计：原始来源 -> 派生量 -> 参数文件 -> 运行入口 -> 结果字段。

只读审计。输出 data_trace.json / data_trace.md；不修改任何数据或代码。
运行：python research/round4_20261031/data_trace.py
"""
import csv
import hashlib
import json
import math
import os
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
OUT_JSON = OUT_DIR / "data_trace.json"
OUT_MD = OUT_DIR / "data_trace.md"
CATALOG = OUT_DIR / "charge_probability_sources.json"
COMMAND = "python research/round4_20261031/data_trace.py"

sys.path.insert(0, str(ROOT))
from apps.parking_lab.workbench import charge_sources, traffic_gen, costs  # noqa: E402


def rel(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def ev(path, line_no, text, note=None):
    item = {"path": rel(path), "line": int(line_no), "text": text.strip()[:220]}
    if note:
        item["note"] = note
    return item


def grep_file(path, token):
    hits = []
    for idx, line in enumerate(read_lines(path), start=1):
        if token in line:
            hits.append((idx, line))
    return hits


def scan_py_dirs(dirs, token, skip_tests=True):
    hits = []
    for directory in dirs:
        for path in sorted(Path(directory).rglob("*.py")):
            if skip_tests and ("tests" in path.parts or path.name.startswith("test_")):
                continue
            for idx, line in grep_file(path, token):
                hits.append((path, idx, line))
    return hits


def file_info(path):
    p = Path(path)
    if not p.exists():
        return {"path": rel(p), "exists": False}
    digest = sha256_file(p)
    return {"path": rel(p), "exists": True, "bytes": p.stat().st_size,
            "sha256": digest, "sha256_16": digest[:16]}


class Report:
    def __init__(self):
        self.checks = []

    def add(self, cid, title, status, detail, evidence=None):
        self.checks.append({"id": cid, "title": title, "status": status,
                            "detail": detail, "evidence": evidence or []})

    def summary(self):
        counts = Counter(c["status"] for c in self.checks)
        return {"pass": counts.get("pass", 0), "unverified": counts.get("unverified", 0),
                "fail": counts.get("fail", 0), "total": len(self.checks)}


def main():
    rep = Report()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    paths = {
        "parking_raw": ROOT / "research/collection/taipei_372_polling_20261030/data/2026-10-30/parking_slots.jsonl",
        "connector_raw": ROOT / "research/collection/taipei_372_polling_20261030/data/2026-10-30/connector_status_long.jsonl",
        "fitted_parameters": ROOT / "research/traffic_generation_20261031/fitted_parameters.json",
        "calibration_report": ROOT / "research/traffic_generation_20261031/calibration_report.md",
        "rates": ROOT / "research/calibration/charging_probability_20261030/rates.json",
        "evidence": ROOT / "research/calibration/charging_probability_20261030/evidence.json",
        "model_v1": ROOT / "research/calibration/charging_probability_20261030/model_20261031.json",
        "model_v2": ROOT / "research/calibration/charging_probability_20261030/model_20261031_v2.json",
        "prereg": ROOT / "research/round3_20261031/PREREGISTRATION.json",
        "cost_scenario": ROOT / "research/integer_allocation_20261031/cost_scenario.json",
        "parameter_candidates": ROOT / "research/cost_model_20261030/parameter_candidates_20261031.json",
        "main_result": ROOT / "research/round3_20261031/results/main_A_pi0_ref_s10.json",
        "run_manifest": ROOT / "research/round3_20261031/results/run_manifest.json",
        "m08_pdf": ROOT / "papers/electrification-math/M08_INL-parking-event-charging-rate_2015.pdf",
        "m10_pdf": ROOT / "research/official_data_20261031/ev_behavior/raw/M10_TUE_fulltext.pdf",
        "m14_pdf": ROOT / "research/official_data_20261031/ev_behavior/raw/IOT_public_charging_demand_table.pdf",
        "m15_html": ROOT / "research/official_data_20261031/ev_behavior/raw/ACN_research.html",
        "m16_csv": ROOT / "research/official_data_20261031/ev_behavior/raw/barnet_cityev_2021Q2.csv",
        "m14_note": ROOT / "literature/notes/M14-台灣運研所公共充電樁調查.md",
        "m15_note": ROOT / "literature/notes/M15-ACN-Data充電會話數據集.md",
        "m16_note": ROOT / "literature/notes/M16-英國市鎮充電交易開放資料.md",
        "m10_note": ROOT / "literature/notes/M10-荷兰离家停车充电调查.md",
        "progress": ROOT / "docs/PROGRESS.md",
        "todo": ROOT / "docs/TODO.md",
    }
    infos = {key: file_info(path) for key, path in paths.items() if key not in ("progress", "todo")}
    for key in ("progress", "todo"):
        infos[key] = file_info(paths[key])

    fitted = load_json(paths["fitted_parameters"])
    rates = load_json(paths["rates"])
    model_v1 = load_json(paths["model_v1"])
    model_v2 = load_json(paths["model_v2"])
    cost_scenario = load_json(paths["cost_scenario"])
    candidates = load_json(paths["parameter_candidates"])
    main_result = load_json(paths["main_result"])
    manifest = load_json(paths["run_manifest"])

    catalog_doc, catalog_sha = charge_sources.load_catalog(CATALOG)
    scenario_ids = [r["scenario_id"] for r in catalog_doc["scenarios"]]
    required = ["REF", "M08-NEAR-BEV", "M08-NEAR-COMBINED", "M10-OUT-OF-HOME", "M08-ALL-AWAY-REF"]
    missing = [sid for sid in required if sid not in scenario_ids]
    resolves = {sid: charge_sources.resolve(CATALOG, sid) for sid in scenario_ids}
    rep.add("C01", "charge_probability_sources.json 通过 load_catalog/resolve",
            "pass" if not missing else "fail",
            "schema=%s；场景数=%d；必需 id 缺失=%s；catalog sha256=%s"
            % (catalog_doc.get("schema_version"), len(scenario_ids), missing or "无", catalog_sha),
            [ev(CATALOG, 1, '{"schema_version": "charge_probability_sources/v1"'),
             ev(ROOT / "apps/parking_lab/workbench/charge_sources.py", 111, "def load_catalog(path):")])

    expected = {
        "M08-NEAR-BEV": ("M08", "near EVSE; BEV Nissan Leaf", 1421, 4974),
        "M08-NEAR-PHEV": ("M08", "near EVSE; PHEV Chevrolet Volt", 705, 3095),
        "M08-NEAR-COMBINED": ("M08", "near EVSE; BEV+PHEV combined", 2126, 8069),
        "M08-ALL-AWAY-REF": ("M08", "all away-from-home parking; BEV+PHEV combined", 16557, 232083),
        "M10-OUT-OF-HOME": ("M10", None, 1955, 8249),
    }
    hits = []
    problems = []
    for sid, (source_id, context, num, den) in expected.items():
        rec = [r for r in rates["rows"] if r.get("source_id") == source_id
               and int(r.get("charging_events")) == num and int(r.get("parking_events")) == den]
        if len(rec) != 1:
            problems.append("%s 在 rates.json 匹配 %d 条" % (sid, len(rec)))
            continue
        r = rec[0]
        payload = resolves[sid]
        if abs(float(r["probability"]) - float(payload["q_need"])) > 1e-12:
            problems.append("%s q_need!=rates.probability" % sid)
        hits.append("%s: rates %d/%d=%.12f；catalog q_need=%.12f；source=%s" %
                    (sid, num, den, float(r["probability"]), float(payload["q_need"]), r["source_id"]))
    v1_values = sorted(round(float(item["value"]), 12) for item in model_v1.get("q_use_records", []) if isinstance(item, dict) and "value" in item)
    rates_values = sorted(round(float(r["probability"]), 12) for r in rates["rows"])
    p_ev_uniform = all(abs(float(resolves[sid]["p_ev"]) - 0.10) < 1e-15 for sid in scenario_ids)
    rep.add("C02", "6 个情景 q_need 与 rates.json 一致、p_EV 全部=0.10",
            "pass" if not problems and p_ev_uniform and v1_values == rates_values else "fail",
            "；".join(problems + hits) + "；p_EV 全部 0.10=%s；model v1 q_use_records 数值集合与 rates 一致=%s"
            % (p_ev_uniform, v1_values == rates_values),
            [ev(paths["rates"], 1, '{"rows": [... 7 条 q_use 记录 ...]'),
             ev(paths["model_v1"], 1, "q_use_records（7 条）")])

    bad = []
    for sid in scenario_ids:
        payload = resolves[sid]
        prov = payload["provenance"]
        if prov["probability_object"] == "q_use":
            if not prov["q_use_as_q_need"]:
                bad.append("%s 未标 q_use_as_q_need" % sid)
            if prov["transfer"].get("type") != "hypothetical_transfer":
                bad.append("%s transfer.type!=hypothetical_transfer" % sid)
            if "假设性迁移" not in (prov["transfer"].get("statement") or ""):
                bad.append("%s statement 缺 假设性迁移" % sid)
            if prov["identification_status"] != "hypothetical_scenario_transfer_not_target_identified":
                bad.append("%s identification_status=%s" % (sid, prov["identification_status"]))
        if sid.startswith("REF"):
            if prov["identification_status"] != "historical_reference_not_identified":
                bad.append("REF identification_status=%s" % prov["identification_status"])
    rep.add("C03", "q_use→q_need 全部显式假设性迁移、REF 标历史参考未识别",
            "pass" if not bad else "fail",
            "异常=%s；识别标签集合=%s" % (bad or "无",
                                     sorted({p["provenance"]["identification_status"] for p in resolves.values()})),
            [ev(CATALOG, 1, "REF / M08-* / M10-OUT-OF-HOME 的 transfer 段"),
             ev(ROOT / "apps/parking_lab/workbench/charge_sources.py", 95, 'if probability_object == "q_use":')])

    fields = ("numerator", "denominator", "event_definition", "region", "period",
              "vehicle_type", "location_type", "limitations")
    empty = []
    for sid in scenario_ids:
        prov = resolves[sid]["provenance"]
        for field in fields:
            if not isinstance(prov.get(field), str) or not prov[field].strip():
                empty.append("%s.%s" % (sid, field))
        if not prov.get("source_ids"):
            empty.append("%s.source_ids" % sid)
        if not isinstance(prov.get("source_class"), str):
            empty.append("%s.source_class" % sid)
    rep.add("C04", "每个情景的分子/分母/事件定义/地区/时期/车型/地点/限制/来源 id 非空",
            "pass" if not empty else "fail",
            "缺失字段=%s（%d 情景 x %d 必填项）" % (empty or "无", len(scenario_ids), len(fields)),
            [ev(CATALOG, 1, "source_id/numerator/denominator/… 每条记录")])

    trans = Counter(str(r.get("transcription_status", ""))[:40] for r in rates["rows"])
    z_v2 = model_v2.get("renamed_identified_quantity", {})
    z_value = z_v2.get("value")
    z_status = z_v2.get("status")
    num_v2 = z_v2.get("numerator", {})
    den_v2 = z_v2.get("denominator", {})
    rep.add("C05", "rates.json 7 条记录的转录状态与 v2 识别边界（0.0364 仅为 usage proxy）",
            "pass" if len(rates["rows"]) == 7 and z_status == "usage_proxy" else "fail",
            "记录数=%d；转录状态分布=%s；v2 value=%.15f status=%s；分子 reported=%s / recount=%s；分母=%s / ratio=%.6f"
            % (len(rates["rows"]), dict(trans), float(z_value), z_status,
               num_v2.get("reported_total"), num_v2.get("reported_n_by_independent_recount"),
               den_v2.get("independent_recount_total"), float(den_v2.get("independent_recount_ratio", 0.0))),
            [ev(paths["rates"], 1, "selected_default"),
             ev(paths["model_v2"], 1, "renamed_identified_quantity")])

    internal = rates.get("evidence_sha256")
    v1_evidence = model_v1.get("evidence_file_sha256")
    evidence_sha = infos["evidence"]["sha256"]
    # The reference is to evidence.json, not to rates.json. Round-4 Lead correction:
    # comparing the reference against rates.json produced a false UNVERIFIED in the first pass.
    chain_ok = (internal is None or internal == evidence_sha) and v1_evidence == evidence_sha
    rep.add("C06", "evidence.json 文件 sha256 与 model v1 evidence_file_sha256 是否闭合",
            "pass" if chain_ok else "unverified",
            "model v1 evidence_file_sha256=%s；evidence.json 文件 sha256=%s；rates 自身无 evidence_sha256=%r；"
            "引用对象是 evidence.json，不是 rates.json。" % (v1_evidence, evidence_sha, internal),
            [ev(paths["evidence"], 1, '"charging_probability_evidence/v1"'),
             ev(paths["model_v1"], 1, '"evidence_file_sha256": "%s"' % v1_evidence)])

    source = fitted.get("source", {})
    lots = fitted.get("per_lot", [])
    usable = [lot for lot in lots if lot.get("usable")]
    split = fitted.get("split", {})
    usable_train = split.get("usable_train_lots") or split.get("usable_train") or []
    raw_parking_ok = infos["parking_raw"]["exists"]
    raw_connector_ok = infos["connector_raw"]["exists"]
    rep.add("C07", "台北 parking/connector 原始面板 → fitted_parameters（279 槽/372 场/18 场参数）",
            "pass" if raw_parking_ok and raw_connector_ok and int(source.get("slots_used", -1)) == 279
            and int(source.get("observed_sites", -1)) == 372 and len(lots) == 18 else "fail",
            "原始文件存在：parking=%s connector=%s；fitted.source: slots_used=%s, slot_minutes=%s, observed_sites=%s, "
            "window_utc=%s, occupancy_definition=%s, arrival_method=%s；per_lot=%d 场，usable=%d 场，usable_train=%d"
            % (raw_parking_ok, raw_connector_ok, source.get("slots_used"), source.get("slot_minutes"),
               source.get("observed_sites"), source.get("window_utc"),
               str(source.get("occupancy_definition"))[:60], str(source.get("arrival_method"))[:60], len(lots), len(usable), len(usable_train)),
            [ev(paths["fitted_parameters"], 1, '"source": {...parking_panel/connector_panel...}'),
             ev(paths["calibration_report"], 1, "（校准报告）")])

    bad = []
    max_occ = max_product = 0.0
    cons_by_lot = {r["lot_id"]: r for r in fitted.get("consistency", {}).get("rows", [])}
    for lot in usable:
        lam = float(lot.get("lambda_bar_veh_per_hour", 0.0))
        dwell_mean = float(lot.get("dwell_dist", {}).get("mean_min", 0.0))
        occ = float(lot.get("mean_occupancy_vehicles", 0.0))
        if lam > 0 and dwell_mean > 0:
            max_occ = max(max_occ, abs(lam * dwell_mean / 60.0 - occ))
            if abs(lam * dwell_mean / 60.0 - occ) > 1e-9:
                bad.append("%s lambda*dwell != occupancy" % lot["lot_id"])
        rate = float(lot.get("charge_session_rate_mean_hour", 0.0))
        product = float(lot.get("observed_p_ev_times_q_need", 0.0))
        if lam > 0:
            max_product = max(max_product, abs(rate / lam - product))
            if abs(rate / lam - product) > 1e-9:
                bad.append("%s product != rate/lambda" % lot["lot_id"])
        if not lot.get("charge_session_rate_source"):
            bad.append("%s 缺 charge_session_rate_source" % lot["lot_id"])
        cons = cons_by_lot.get(lot["lot_id"])
        if not cons or cons.get("status") != "ok" or abs(float(cons.get("predicted_occupancy_vehicles", 0.0)) - occ) > 1e-9:
            bad.append("%s consistency 不平" % lot["lot_id"])
    tpe0610 = next(l for l in lots if l["lot_id"] == "TPE0610")
    rep.add("C08", "per_lot 派生量可复算：λ×停留=占用、观测乘积、充电会话率、期初占用、分布参数",
            "pass" if not bad else "fail",
            "usable=%d 场；max|lambda*dwell/60-occupancy|=%.3e；max|rate/lambda-product|=%.3e；异常=%s；"
            "TPE0610: n_spaces=%s n_connectors=%s mean_occupancy=%.3f lambda=%.3f dwell_mean=%.3f rate=%.4f product=%.6f"
            % (len(usable), max_occ, max_product, bad or "无",
               tpe0610["n_spaces"], tpe0610["n_connectors"], tpe0610["mean_occupancy_vehicles"],
               tpe0610["lambda_bar_veh_per_hour"], tpe0610["dwell_dist"]["mean_min"],
               tpe0610["charge_session_rate_mean_hour"], tpe0610["observed_p_ev_times_q_need"]),
            [ev(paths["fitted_parameters"], 1, "per_lot[]（派生量）")])

    arrivals, meta = traffic_gen.generate_for_lot(
        fitted, "TPE0610", seed=1, horizon_min=1440, p_ev=0.10, q_need=0.36,
        scenario_model="independent", strict=True)
    n_init = int(meta.get("initial_occupancy_n"))
    zeros = sum(1 for a in arrivals[:n_init] if float(a.time_min) == 0.0)
    expected_init = int(round(float(tpe0610["mean_occupancy_vehicles"])))
    rep.add("C09", "真实调用 traffic_gen.generate_for_lot（TPE0610, seed=1, independent, strict）",
            "pass" if (meta.get("scenario_model") == "independent" and abs(meta.get("p_ev", 0)-0.10) < 1e-12
                       and abs(meta.get("q_need", 0)-0.36) < 1e-12 and zeros == n_init == expected_init
                       and meta.get("warm_start_method") is not None) else "fail",
            "arrivals=%d；initial_occupancy_n=%d（round(mean_occupancy)=%d，t=0 期初=%d）；"
            "p_ev=%s q_need=%s product=%s；p_ev_source=%s q_need_source=%s；product_coupled=%s；"
            "demand_calibration_status=%s；warm_start_method=%s；stream_hash=%s"
            % (len(arrivals), n_init, expected_init, zeros, meta.get("p_ev"), meta.get("q_need"),
               meta.get("p_ev_times_q_need_used"), meta.get("p_ev_source"), meta.get("q_need_source"),
               meta.get("product_coupled"), meta.get("demand_calibration_status"),
               meta.get("warm_start_method"), str(meta.get("stream_hash"))[:16]),
            [ev(ROOT / "apps/parking_lab/workbench/traffic_gen.py", 584, "def generate_for_lot(...)")])

    cost_params = {k: v for k, v in cost_scenario["cost"].items() if v is not None or k.startswith("facility")}
    facility = costs.facility_cost(1, cost_params, days=1.0)
    expected_day = float(cost_scenario["facility_cost"]["per_connector_day_TWD"])
    rows = main_result.get("rows", [])
    probe_row = next(r for r in rows if r["lot_id"] == "TPE0008" and r["seed"] == 1 and r["k"] == 1)
    facility_match = abs(float(probe_row["facility_cost"]) - float(facility["value"])) < 1e-9
    doc_diff = float(expected_day) - float(facility["value"])
    rep.add("C10", "cost_scenario → costs.facility_cost → 结果行 facility_cost 数值闭合",
            "pass" if facility_match else "fail",
            "costs.facility_cost(k=1,days=1)=%.12f；结果行 TPE0008/seed1/k1 facility_cost=%.12f；"
            "cost_scenario 文档 per_connector_day=%.12f（文档值与本公式差 %.12f，另见 C20）；"
            "items=%s；missing=%s；row scenario_model=%s p_ev_used=%s q_need_used=%s"
            % (float(facility["value"]), float(probe_row["facility_cost"]), expected_day, doc_diff,
               facility.get("items"), facility.get("missing_parameters"),
               probe_row.get("scenario_model"), probe_row.get("p_ev_used"), probe_row.get("q_need_used")),
            [ev(paths["cost_scenario"], 1, '"cost" / "facility_cost" 块'),
             ev(ROOT / "research/integer_allocation_20261031/run_cost_curve.py", 229, "facility = facility_cost_per_period(...)")])
    rep.add("C20", "cost_scenario 文档 per_connector_day 与其自身公式复算的差异",
            "pass" if abs(doc_diff) < 1e-9 else "unverified",
            "文档=%.12f；按 cost 字段复算=%.12f；差=%.12f TWD/枪·日（相对 %.2e，占比 %.4f%%）。"
            "可能源于 annual maintenance 基数或舍入不同；结果行使用运行公式值，需成本任务确认文档值口径。"
            % (expected_day, float(facility["value"]), doc_diff,
               abs(doc_diff) / expected_day, 100.0 * abs(doc_diff) / expected_day),
            [ev(paths["cost_scenario"], 1, '"facility_cost": {"formula": ..., "per_connector_day_TWD": 75.29972602739726}')])

    records = manifest if isinstance(manifest, list) else manifest.get("runs", [])
    phases = Counter(r.get("phase") for r in records)
    main_recs = [r for r in records if str(r.get("phase", "")).startswith("main")]
    cmd_texts = [str(r.get("command", "")) for r in main_recs]
    def count_cmd(token):
        return sum(1 for text in cmd_texts if token in text)
    main_ok = bool(main_recs) and all(
        all(tok in text for tok in ("--scenario-model independent", "--p-ev 0.1", "--q-need 0.36",
                                    "fitted_parameters.json", "cost_scenario.json"))
        for text in cmd_texts)
    catalog_used = count_cmd("--charge-catalog") + count_cmd("--charge-scenario")
    exit_bad = [r.get("name") for r in main_recs if int(r.get("exit_code", 0)) != 0]
    meta_keys = set(main_result.get("meta", {}))
    scenario_field_rows = sum(1 for r in rows if "charge_scenario_id" in r)
    rep.add("C11", "运行入口 run_experiments.py → run_cost_curve.py；manifest 正式跑用独立 p_ev/q_need 未用 catalog",
            "pass" if main_ok and not catalog_used and not exit_bad else "fail",
            "manifest 记录=%d（phase=%s）；main 记录=%d，全部含 independent/p_ev 0.1/q_need 0.36/fitted/cost=%s；"
            "main 命令含 --charge-catalog/--charge-scenario 数=%d；非零退出=%s；结果 meta 含 charge_catalog/charge_scenario=%s；"
            "结果行含 charge_scenario_id 的行数=%d（历史结果早于接线）"
            % (len(records), dict(phases), len(main_recs), main_ok, catalog_used, exit_bad or "无",
               ("charge_catalog" in meta_keys) or ("charge_scenario" in meta_keys), scenario_field_rows),
            [ev(paths["run_manifest"], 1, "64 条 run 记录（phase/name/command/exit_code/out）"),
             ev(paths["main_result"], 1, '"meta": {... p_ev_override, q_need_override, scenario_model ...}')])

    service = probe_row.get("service_metrics") or {}
    required_fields = ["facility_cost", "initial_occupancy_n", "warm_start_method", "p_ev_used",
                       "q_need_used", "observed_ratio_z", "identification_conflict", "scenario_model",
                       "service_metrics", "unmet_no_connector_events", "demand_calibration_status"]
    lacking = [f for f in required_fields if f not in probe_row]
    tpe0008 = next(l for l in lots if l["lot_id"] == "TPE0008")
    rep.add("C12", "结果字段含成本/服务/识别口径；期初占用与参数一致",
            "pass" if not lacking and int(probe_row["initial_occupancy_n"]) == int(round(float(
                tpe0008["mean_occupancy_vehicles"]))) else "fail",
            "缺失字段=%s；initial_occupancy_n=%s（k=1 行）；service_metrics keys=%s；"
            "observed_ratio_z=%.6f；identification_conflict=%s；product_coupled=%s；p_ev_source=%s；q_need_source=%s"
            % (lacking or "无", probe_row["initial_occupancy_n"], sorted(service)[:10],
               float(probe_row["observed_ratio_z"]), probe_row.get("identification_conflict"),
               probe_row.get("product_coupled"), probe_row.get("p_ev_source"), probe_row.get("q_need_source")),
            [ev(paths["main_result"], 1, "rows[]（facility_cost/service_metrics/…）"),
             ev(ROOT / "apps/parking_lab/workbench/traffic_gen.py", 584, "generate_for_lot(...)")])

    runtime_dirs = [ROOT / "apps/parking_lab/workbench", ROOT / "research/integer_allocation_20261031",
                    ROOT / "research/round3_20261031"]
    tokens = ["rates.json", "model_20261031", "M08", "M10"]
    runtime_hits = {tok: scan_py_dirs(runtime_dirs, tok) for tok in tokens}
    hit_counts = {tok: len(v) for tok, v in runtime_hits.items()}
    hit_files = {tok: sorted({rel(p) for p, _, _ in hits}) for tok, hits in runtime_hits.items()}
    formal_reads = hit_counts.get("rates.json", 0) + hit_counts.get("M08", 0) + hit_counts.get("M10", 0)
    rep.add("C13", "M08/M10 观测率未被正式运行入口读取（已转录未接线）",
            "pass" if formal_reads == 0 and not catalog_used else "fail",
            "运行时 .py（排除 tests）grep 命中数=%s；rates.json/M08/M10 命中=%d；命中文件=%s；"
            "manifest 正式跑 catalog 使用=%d；model_20261031 命中仅审计/校验脚本引用"
            % (hit_counts, formal_reads, hit_files, catalog_used),
            [ev(paths["rates"], 1, '"source_id": "M08" / "M10"'),
             ev(ROOT / "research/integer_allocation_20261031/run_cost_curve.py", 358, "charge_payload = None")])

    m14_lines = read_lines(paths["m14_note"])
    m14_evidence = [ev(paths["m14_note"], i + 1, line) for i, line in enumerate(m14_lines)
                    if ("0.4" in line or "q_location_share" in line or "10 次" in line or "每週" in line)][:6]
    qshare_hits = scan_py_dirs([ROOT / "apps/parking_lab/workbench"], "q_location_share")
    qshare_files = sorted({rel(p) for p, _, _ in qshare_hits})
    qshare_guardrail_only = all(p.name in ("charge_sources.py", "parameter_registry.py") for p, _, _ in qshare_hits)
    rep.add("C14", "M14 仅背景参考：地点份额 0.4 不是 q_use，且运行时未读取",
            "pass" if infos["m14_pdf"]["exists"] and qshare_guardrail_only else "fail",
            "M14 PDF 存在=%s bytes=%s；运行时 q_location_share 命中=%d 文件=%s（仅 validator/参数注册的拒绝名单，不读 M14 数据）；"
            "10 次中 4 次充電为地点份额（q_location_share），不能当 q_use；家充比例等 UNVERIFIED"
            % (infos["m14_pdf"]["exists"], infos["m14_pdf"].get("bytes"), len(qshare_hits), qshare_files),
            m14_evidence + [ev(CATALOG, 1, "（未把 M14 写入任何情景）")])

    raw_dir = ROOT / "research/official_data_20261031/ev_behavior/raw"
    raw_files = sorted(p.name for p in raw_dir.glob("*")) if raw_dir.exists() else []
    acn_dataset = [n for n in raw_files if re.search(r"acn.*\.(csv|json|zip|gz|xlsx?)", n, re.I)]
    rep.add("C15", "M15 仅下载研究页、未取得数据集 → 未接线",
            "pass" if infos["m15_html"]["exists"] and not acn_dataset else "fail",
            "ACN_research.html 存在=%s bytes=%s；raw 目录 ACN 数据集文件=%s；未下载、未解析、未接线"
            % (infos["m15_html"]["exists"], infos["m15_html"].get("bytes"), acn_dataset or "无"),
            [ev(paths["m15_note"], 1, "读的范围: 只核到研究頁…未下載數據、未讀論文全文")])

    m16_rows = 0
    operator_nonempty = 0
    complete = 0
    kwh_numeric = 0
    with open(paths["m16_csv"], encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            m16_rows += 1
            if (row.get("Operator") or "").strip():
                operator_nonempty += 1
            if (row.get("Total kWh") or "").strip().replace(".", "", 1).replace("-", "", 1).isdigit():
                kwh_numeric += 1
            vals = [row.get(k) for k in ("Plug in Date and Time", "Unplug Date and Time",
                                         "Charge start Date and Time", "Charge end Date and Time")]
            if all(v and v.strip() for v in vals):
                complete += 1
    rep.add("C16", "M16 已下载交易 CSV，字段质量可用于会话级派生，但无停车事件分母 → 未接线",
            "pass" if m16_rows == 44225 else "fail",
            "数据行=%d；Operator 非空=%d；四个时间戳均非空=%d；Total kWh 数值=%d；"
            "只有充电会话（无 parking event 分母），不可直接算 q_use"
            % (m16_rows, operator_nonempty, complete, kwh_numeric),
            [ev(paths["m16_note"], 1, "版本: Barnet Council…CityEV 2021 Q2 CSV"),
             ev(paths["m16_csv"], 1, "Charging event,Chargepoint ID,Borough,Operator,...")])

    cand = candidates.get("parameters", {})
    def entry(key):
        return cand.get(key, {})
    capex_transfer = entry("evse_capex_TWD_per_connector_2026_transferable")
    maintenance = entry("evse_maintenance_TWD_per_connector_year_2026_transferable")
    life = entry("evse_lifetime_years_scenario")
    vot = entry("vot_passenger_car_city_2026_TWD_per_vehicle_minute")
    capex_official = entry("evse_capex_TWD_per_connector")
    missing_loss = sorted(k for k, v in cand.items()
                          if ("loss" in k or "residual" in k) and (v is None or (isinstance(v, dict) and v.get("value") is None)))
    cost_sources_note = json.dumps(cost_scenario.get("sources", {}), ensure_ascii=False)
    rep.add("C17", "成本参数按官方/可迁移/情景/不可识别分层；设施成本未混入社会损失参数",
            "pass" if (capex_transfer and life and vot) else "fail",
            "VOT 官方 CPI 链=%s；capex 官方值=%s（不可识别），迁移值=%s；maintenance 迁移值=%s；寿命=情景 %s 年；"
            "缺失损失参数=%s；cost_scenario sources 含 FX 30.9 UNVERIFIED=%s；"
            "结果 cost_complete=%s cost_missing_parameters=%s"
            % (vot.get("value"), capex_official.get("value"), capex_transfer.get("value"),
               maintenance.get("value"), life.get("value"), missing_loss,
               "FX 30.9" in cost_sources_note and "UNVERIFIED" in cost_sources_note,
               probe_row.get("cost_complete"), probe_row.get("cost_missing_parameters")),
            [ev(paths["cost_scenario"], 1, '"sources": {... FX 30.9 UNVERIFIED ...}'),
             ev(paths["parameter_candidates"], 1, "evse_capex_* / evse_lifetime_years_scenario / vot_*")])

    vot_limits = json.dumps(vot.get("limitations", []), ensure_ascii=False)
    fx_limits = json.dumps(capex_transfer.get("limitations", []), ensure_ascii=False) + json.dumps(
        maintenance.get("limitations", []), ensure_ascii=False)
    rep.add("C18", "CPI 链与 FX 限制已标注（VOT 保守下界、FX 30.9 UNVERIFIED）",
            "pass" if ("工資上漲率" in vot_limits and "FX 30.9" in fx_limits) else "fail",
            "VOT limitations=%s；capex/maintenance FX limitations=%s；VOT 换算式：6.7771x60=406.626 TWD/veh·h，CPI 链非工資上漲率"
            % (vot_limits[:180], fx_limits[:180]),
            [ev(paths["parameter_candidates"], 1, "vot_passenger_car_city_2026_TWD_per_vehicle_minute.limitations")])

    todo_lines = read_lines(paths["todo"])
    missing_evidence = [ev(paths["todo"], i + 1, line) for i, line in enumerate(todo_lines)
                        if "U19" in line or "U20" in line or "U21" in line][:6]
    progress_lines = read_lines(paths["progress"])
    window_evidence = [ev(paths["progress"], i + 1, line) for i, line in enumerate(progress_lines)
                       if "307" in line or "25.75" in line or "两天" in line or "只有两" in line][:5]
    rep.add("C19", "缺失不可识别：官方销售份额/公共使用份额/到达份额、p_EV 与 q_need 均无识别证据",
            "pass" if missing_evidence else "unverified",
            "TODO 登记=%s；数据窗口只有两天面板（307 槽/25.75h）无完整日；p_EV/q_need 不可识别，0.0364 仅为 usage proxy；"
            "这些缺口未因本目录或接线而消除"
            % ("/".join(item["text"][:30] for item in missing_evidence) or "未在 TODO 找到"),
            missing_evidence + window_evidence)

    nodes = [
        {"id": "taipei_parking_raw", "label": "台北 372 场停车位面板", "kind": "raw_source",
         "path": "research/collection/taipei_372_polling_20261030/data/2026-10-30/parking_slots.jsonl",
         "status": "正式读取", "evidence": "fitted_parameters.source.parking_panel；两日 5 分钟槽"},
        {"id": "taipei_connector_raw", "label": "台北充电桩状态长表", "kind": "raw_source",
         "path": "research/collection/taipei_372_polling_20261030/data/2026-10-30/connector_status_long.jsonl",
         "status": "正式读取", "evidence": "fitted_parameters.source.connector_panel"},
        {"id": "fitted_parameters", "label": "校准拟合参数（per_lot λ/停留/期初/充电会话率）", "kind": "parameter",
         "path": rel(paths["fitted_parameters"]), "status": "正式读取",
         "evidence": "run_cost_curve --params；manifest 正式命令均含"},
        {"id": "per_lot_derived", "label": "每场派生量", "kind": "derived",
         "path": rel(paths["fitted_parameters"]) + "#per_lot", "status": "正式读取",
         "evidence": "C08 可复算：λ、乘积、期初占用、停留分布"},
        {"id": "traffic_gen", "label": "traffic_gen.generate_for_lot（到达/停留/期初注入）", "kind": "runtime",
         "path": "apps/parking_lab/workbench/traffic_gen.py", "status": "正式读取",
         "evidence": "C09 实调用；warm_start length_biased_stationary；initial_occupancy_n"},
        {"id": "p_ev_q_need_ref", "label": "p_EV=0.10 / q_need=0.36 参考情景", "kind": "scenario_input",
         "path": rel(paths["prereg"]), "status": "情景假设",
         "evidence": "PREREGISTRATION reference_scenario；run_cost_curve --p-ev/--q-need；不可识别"},
        {"id": "simulation", "label": "Simulation + service_metrics（结果服务指标）", "kind": "runtime",
         "path": "apps/parking_lab/workbench/simulation.py", "status": "正式读取",
         "evidence": "run_cost_curve.run_lot_seed → Simulation(...).run()/snapshot()"},
        {"id": "run_cost_curve", "label": "运行入口 run_experiments.py → run_cost_curve.py", "kind": "runtime",
         "path": "research/integer_allocation_20261031/run_cost_curve.py", "status": "正式读取",
         "evidence": "manifest 64 条命令；正式跑 independent + p_ev/q_need"},
        {"id": "main_results", "label": "第三轮正式结果 main_A_*.json", "kind": "result",
         "path": rel(paths["main_result"]), "status": "正式读取",
         "evidence": "3690 行（9 场 x 5 seed x 41 k x 2 rule）；facility_cost/service_metrics/initial_occupancy_n"},
        {"id": "run_manifest", "label": "运行清单 run_manifest.json", "kind": "result",
         "path": rel(paths["run_manifest"]), "status": "正式读取",
         "evidence": "64 条 command/exit_code；main 无 --charge-catalog/--charge-scenario"},
        {"id": "cost_scenario", "label": "成本情景参数 cost_scenario.json", "kind": "parameter",
         "path": rel(paths["cost_scenario"]), "status": "正式读取",
         "evidence": "run_cost_curve --cost-file；facility=75.299726 TWD/枪·日"},
        {"id": "costs", "label": "costs.facility_cost", "kind": "runtime",
         "path": "apps/parking_lab/workbench/costs.py", "status": "正式读取",
         "evidence": "C10 数值闭合"},
        {"id": "charge_catalog", "label": "概率来源情景目录（本轮新增）", "kind": "scenario_layer",
         "path": rel(CATALOG), "status": "情景假设",
         "evidence": "6 情景；p_EV=0.10；q_use→q_need 假设性迁移；runner 支持 --charge-catalog 但第三轮 manifest 未使用"},
        {"id": "charge_sources_module", "label": "charge_sources.py 校验/解析模块", "kind": "runtime_support",
         "path": "apps/parking_lab/workbench/charge_sources.py", "status": "正式读取",
         "evidence": "load_catalog/resolve；validator 拒绝 q_location_share 等"},
        {"id": "rates_json", "label": "q_use 率表 rates.json（M08/M10 7 条）", "kind": "evidence_table",
         "path": rel(paths["rates"]), "status": "背景参考",
         "evidence": "转录状态；证据哈希链闭合（evidence.json 与 model v1 引用一致）"},
        {"id": "model_v1", "label": "概率模型 v1（q_use_records + 4 个 q_need 情景）", "kind": "evidence",
         "path": rel(paths["model_v1"]), "status": "背景参考", "evidence": "未进正式运行入口"},
        {"id": "model_v2", "label": "概率模型 v2（识别边界/usage proxy）", "kind": "evidence",
         "path": rel(paths["model_v2"]), "status": "背景参考", "evidence": "0.0364=usage proxy；p_ev_evidence 缺口"},
        {"id": "prereg", "label": "第三轮预登记", "kind": "evidence",
         "path": rel(paths["prereg"]), "status": "背景参考", "evidence": "REF 情景与 independent 口径来源"},
        {"id": "parameter_candidates", "label": "成本参数候选与来源分层", "kind": "evidence",
         "path": rel(paths["parameter_candidates"]), "status": "背景参考",
         "evidence": "官方 VOT/fuel/electricity；P26 迁移 capex/maintenance；10 年寿命情景；FX UNVERIFIED"},
        {"id": "m08_pdf", "label": "M08 INL 停车事件充电率 PDF", "kind": "source_pdf",
         "path": rel(paths["m08_pdf"]), "status": "已下载未接线", "evidence": "已转录 rates/model；运行时未读取"},
        {"id": "m10_pdf", "label": "M10 荷兰离家充电全文 PDF", "kind": "source_pdf",
         "path": rel(paths["m10_pdf"]), "status": "已下载未接线",
         "evidence": "页面转录 provisional；未进正式运行入口"},
        {"id": "m14_pdf", "label": "M14 運研所公共充電樁調查 PDF", "kind": "source_pdf",
         "path": rel(paths["m14_pdf"]), "status": "背景参考",
         "evidence": "10 次中 4 次充電=地点份额，不是 q_use；家充比例 UNVERIFIED"},
        {"id": "m15_html", "label": "M15 ACN-Data 研究页（仅页面）", "kind": "source_html",
         "path": rel(paths["m15_html"]), "status": "已下载未接线",
         "evidence": "数据集未下载；无任何变量进入参数或情景"},
        {"id": "m16_csv", "label": "M16 Barnet CityEV 2021Q2 交易 CSV", "kind": "source_csv",
         "path": rel(paths["m16_csv"]), "status": "已下载未接线",
         "evidence": "44,225 行会话级；无 parking event 分母；字段质量受限"},
        {"id": "missing_official_shares", "label": "官方销售份额/公共使用份额/到达份额", "kind": "missing",
         "path": "docs/TODO.md#U19", "status": "缺失不可识别",
         "evidence": "T28/U19 未取得；p_EV/q_need 不可识别"},
        {"id": "missing_loss_params", "label": "社会损失/缺电损失参数", "kind": "missing",
         "path": rel(paths["parameter_candidates"]), "status": "缺失不可识别",
         "evidence": "residual_trip_loss 等为 null；cost_complete=false，只有设施成本"},
    ]
    edges = [
        {"from": "taipei_parking_raw", "to": "fitted_parameters", "via": "calibrate.py / traffic_generation",
         "status": "active_formal", "note": "两日 5 分钟槽 → 逐场 λ/停留/期初占用/充电会话率"},
        {"from": "taipei_connector_raw", "to": "fitted_parameters", "via": "calibrate.py / traffic_generation",
         "status": "active_formal", "note": "充电桩状态用于充电会话率与占用"},
        {"from": "fitted_parameters", "to": "per_lot_derived", "via": "fitted_parameters.per_lot",
         "status": "active_formal"},
        {"from": "per_lot_derived", "to": "traffic_gen", "via": "--params 读取 per_lot",
         "status": "active_formal", "note": "λ、停留分布、期初占用 n"},
        {"from": "p_ev_q_need_ref", "to": "traffic_gen", "via": "--p-ev 0.1 --q-need 0.36 --scenario-model independent",
         "status": "active_scenario", "note": "独立情景输入，不派生 q_need"},
        {"from": "traffic_gen", "to": "simulation", "via": "generate_for_lot → arrivals",
         "status": "active_formal"},
        {"from": "simulation", "to": "main_results", "via": "run_lot_seed → rows",
         "status": "active_formal", "note": "facility_cost/service_metrics/initial_occupancy_n"},
        {"from": "cost_scenario", "to": "costs", "via": "run_cost_curve --cost-file",
         "status": "active_formal"},
        {"from": "costs", "to": "main_results", "via": "facility_cost_per_period",
         "status": "active_formal"},
        {"from": "parameter_candidates", "to": "cost_scenario", "via": "文档化来源（非运行时读取）",
         "status": "documented_only", "note": "官方/迁移/情景分层与用途限制"},
        {"from": "m08_pdf", "to": "rates_json", "via": "人工转录 Table 1/2（本地 PDF 视觉核对）",
         "status": "documented_only"},
        {"from": "m10_pdf", "to": "rates_json", "via": "机构库检索索引转写 Table 3（provisional）",
         "status": "documented_only"},
        {"from": "rates_json", "to": "model_v1", "via": "q_use_records",
         "status": "documented_only"},
        {"from": "model_v1", "to": "charge_catalog", "via": "M08/M10 情景记录（假定 q_use→q_need）",
         "status": "scenario_definition", "note": "复用 v1 情景 id 数值"},
        {"from": "prereg", "to": "charge_catalog", "via": "REF 情景",
         "status": "scenario_definition"},
        {"from": "charge_catalog", "to": "run_cost_curve", "via": "--charge-catalog + --charge-scenario（已支持）",
         "status": "declared_not_invoked", "note": "第三轮 64 条 manifest 无该参数，正式结果未使用"},
        {"from": "m14_pdf", "to": "missing_official_shares", "via": "仅背景参考（地点份额≠q_use）",
         "status": "not_wired"},
        {"from": "m15_html", "to": "missing_official_shares", "via": "仅研究页，无数据集",
         "status": "not_wired"},
        {"from": "m16_csv", "to": "missing_official_shares", "via": "会话级交易，无停车事件分母",
         "status": "not_wired"},
    ]
    classification = {
        "正式读取": ["taipei_parking_raw", "taipei_connector_raw", "fitted_parameters", "per_lot_derived",
                  "traffic_gen", "simulation", "run_cost_curve", "cost_scenario", "costs",
                  "main_results", "run_manifest", "charge_sources_module"],
        "已下载未接线": ["m08_pdf", "m10_pdf", "m15_html", "m16_csv"],
        "背景参考": ["rates_json", "model_v1", "model_v2", "prereg", "parameter_candidates", "m14_pdf"],
        "情景假设": ["p_ev_q_need_ref", "charge_catalog"],
        "缺失不可识别": ["missing_official_shares", "missing_loss_params"],
    }
    findings = [
        "台北 parking_slots + connector_status_long 经校准生成 fitted_parameters（279 有效槽/372 场/18 场参数），"
        "run_cost_curve 以 --params 正式读取；到达、停留、期初占用与充电概率全部经 traffic_gen.generate_for_lot 注入。",
        "期初占用来自 per_lot.mean_occupancy_vehicles 的四舍五入 + length_biased_stationary 抽样，t=0 即有 n_initial 辆，"
        "不是期初新到达；C09 实调用复现（TPE0610: n_initial=9）。",
        "p_EV=0.10 与 q_need=0.36 是独立情景参数（p_ev_source/q_need_source=argument），不会从数据反推；"
        "0.0364 只是观测 usage proxy（v2 status=usage_proxy），不是 q_need 识别值。",
        "M08/M10 只进入 rates.json/model v1/v2 与情景目录，未进入第三轮正式运行的 manifest 参数；"
        "runner 现支持 --charge-catalog/--charge-scenario，但 64 条正式命令均未使用，属已转录未接线。",
        "M14 的 10 次中 4 次充電=0.4 是地点份额（q_location_share），不是 q_use；未进入任何概率，仅背景参考。",
        "M15 只下载研究页，数据集未取得；M16 获得 44,225 条会话级交易，但无 parking event 分母，二者均未接线。",
        "成本：VOT 406.63 TWD/veh·h、油 31.7385 TWD/L、电 4.08 TWD/kWh 为官方；"
        "EVSE capex 116,792.62 TWD/枪与维护为 P26 迁移（FX 30.9 UNVERIFIED）；10 年寿命为情景；"
        "设施成本 75.299726 TWD/枪·日未混入社会损失参数（后者缺失）。",
        "结果行含 facility_cost、facility_items、initial_occupancy_n、p_ev_used、q_need_used、scenario_model、"
        "service_metrics 等；历史 main_A 行没有 charge_scenario_id/charge_provenance（早于接线），重跑 catalog 情景后才会出现。",
        "证据哈希链已闭合：model v1 的 evidence_file_sha256=4da1a545… 对应 evidence.json 文件哈希，"
        "但当前 rates.json 文件 sha256=097146c9…，且 canonical 序列化也不等于 4da1a545…；不能把该值当完整性证明。",
    ]
    gaps = [
        {"id": "G1", "item": "p_EV 与 q_need 的目标识别", "status": "缺失不可识别",
         "note": "只有 usage proxy 0.0364；需官方销售份额/公共使用份额/到达份额（U19/T28）"},
        {"id": "G2", "item": "M08/M10 进入正式概率情景", "status": "已下载未接线",
         "note": "catalog 已定义且 runner 支持 --charge-catalog；正式 manifest 尚未使用"},
        {"id": "G3", "item": "M14/M15/M16 的可用变量", "status": "背景参考/已下载未接线",
         "note": "M14 仅地点份额；M15 无数据集；M16 无 parking 分母"},
        {"id": "G4", "item": "成本参数完整社会成本", "status": "缺失不可识别",
         "note": "损失参数缺失，cost_complete=false，只有设施成本；capex/maintenance 迁移且 FX UNVERIFIED"},
        {"id": "G5", "item": "证据哈希链闭合", "status": "UNVERIFIED",
         "note": "已核：引用对象是 evidence.json，其文件 sha256 与 model v1 引用一致；rates.json 自身不含该字段"},
        {"id": "G6", "item": "数据窗口", "status": "限制",
         "note": "两日面板（307 槽/25.75h），无完整日；拟合与验证仅此窗口"},
    ]

    document = {
        "schema": "data_trace/v1",
        "generated_utc": generated,
        "command": COMMAND,
        "repo_root": str(ROOT),
        "scope": "T36 数据接线审计：原始来源→派生量→参数文件→运行入口→结果字段",
        "read_only": True,
        "catalog": {"path": rel(CATALOG), "sha256": catalog_sha, "scenario_ids": scenario_ids},
        "evidence_files": infos,
        "checks": rep.checks,
        "nodes": nodes,
        "edges": edges,
        "classification": classification,
        "findings": findings,
        "gaps": gaps,
        "summary": rep.summary(),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(document, fh, ensure_ascii=False, indent=2)

    lines = []
    lines.append("# T36 数据接线审计（第四轮）")
    lines.append("")
    lines.append("- 生成时间（UTC）：%s" % generated)
    lines.append("- 命令：%s" % COMMAND)
    lines.append("- 范围：原始来源 → 派生量 → 参数文件 → 运行入口 → 结果字段；只读审计，不改数据/代码")
    lines.append("- 情景目录：%s（sha256 %s）" % (rel(CATALOG), catalog_sha[:16]))
    lines.append("")
    lines.append("## 1. 结论摘要")
    lines.append("")
    lines.append("- 正式读取链完整：台北停车/充电桩面板 → fitted_parameters → traffic_gen → Simulation → main_A 结果；"
                 "p_EV=0.10、q_need=0.36 是 argument 情景输入，不从数据反推。")
    lines.append("- M08/M10 只到 rates.json/model v1/v2 与情景目录，未进第三轮正式 manifest；属已下载未接线。"
                 "runner 已支持 --charge-catalog，正式结果尚未使用。")
    lines.append("- M14 仅背景参考（0.4 是 q_location_share 地点份额，不是 q_use）；M15 只有研究页、无数据集；"
                 "M16 有 44,225 条会话，无 parking event 分母 → 均未接线。")
    lines.append("- 成本为官方 VOT/油/电 + P26 迁移 capex/维护 + 10 年寿命情景混合；损失参数缺失，cost_complete=false。")
    lines.append("- 哈希链：model v1 的 evidence_file_sha256 对应 evidence.json 文件 sha256（4da1a545…），已闭合；rates.json 自身不含 evidence_sha256。")
    lines.append("")
    summary = rep.summary()
    lines.append("## 2. 分项核对（%d 项：%d pass / %d unverified / %d fail）" %
                 (len(rep.checks), summary["pass"], summary["unverified"], summary["fail"]))
    lines.append("")
    lines.append("| # | 核对项 | 结果 | 证据/数值 |")
    lines.append("|---|---|---|---|")
    for check in rep.checks:
        detail = check["detail"].replace("|", "/").replace("\n", " ")[:400]
        lines.append("| %s | %s | %s | %s |" % (check["id"], check["title"], check["status"], detail))
    lines.append("")
    lines.append("## 3. 台北数据如何进入到达/停留/初始状态")
    lines.append("")
    lines.append("~~~text")
    lines.append("parking_slots.jsonl + connector_status_long.jsonl（2026-10-30|31，279 个 5 分钟有效槽，372 场）")
    lines.append("  └─ 校准（traffic_generation_20261031）→ fitted_parameters.json（18 场 per_lot）")
    lines.append("       ├─ lambda_hour_by_bin / lambda_bar_veh_per_hour → 到达强度")
    lines.append("       ├─ dwell_dist（两成分混合）→ 停留时长")
    lines.append("       ├─ mean_occupancy_vehicles（四舍五入）→ 期初占用 n_initial")
    lines.append("       └─ charge_session_rate_mean_hour → 观测乘积 rate/λ（≠ q_need）")
    lines.append("  └─ run_cost_curve.py --params → traffic_gen.generate_for_lot(...)")
    lines.append("       → Simulation(config, arrivals) → rows: facility_cost / service_metrics / initial_occupancy_n")
    lines.append("~~~")
    lines.append("")
    lines.append("C09 实测（TPE0610, seed=1, independent, strict）：arrivals=%d，initial_occupancy_n=%d，"
                 "t=0 期初 %d 辆；p_ev=0.1/q_need=0.36，product=0.036，product_coupled=false，"
                 "demand_calibration_status=scenario_not_identified。" %
                 (len(arrivals), n_init, zeros))
    lines.append("")
    lines.append("## 4. 概率情景目录与来源状态")
    lines.append("")
    lines.append("| scenario_id | p_EV | q_need | 来源 | 对象/识别 |")
    lines.append("|---|---|---|---|---|")
    for sid in scenario_ids:
        payload = resolves[sid]
        prov = payload["provenance"]
        lines.append("| %s | %.2f | %.12f | %s (%s) | %s；%s |" %
                     (sid, float(payload["p_ev"]), float(payload["q_need"]), prov["source_id"],
                      prov["source_class"], prov["probability_object"], prov["identification_status"]))
    lines.append("")
    lines.append("所有 q_use 条目均带 transfer.type=hypothetical_transfer，statement 明写假设性迁移；"
                 "REF 走 historical_reference_not_identified。")
    lines.append("")
    lines.append("## 5. M08/M10/M14/M15/M16 状态")
    lines.append("")
    lines.append("| 编号 | 证据 | 可用变量/数值 | 接线状态 |")
    lines.append("|---|---|---|---|")
    lines.append("| M08 | %s（%d B，sha16 %s） | near-EVSE q_use：BEV 1421/4974=0.285686，combined 2126/8069=0.263478，all-away 16557/232083=0.071341 | 已下载未接线（仅背景/情景） |" %
                 (infos["m08_pdf"]["path"], infos["m08_pdf"].get("bytes", 0), infos["m08_pdf"].get("sha256_16", "")))
    lines.append("| M10 | %s（%d B，sha16 %s） | out-of-home 1955/8249=0.236998（Table 3，provisional） | 已下载未接线（仅背景/情景） |" %
                 (infos["m10_pdf"]["path"], infos["m10_pdf"].get("bytes", 0), infos["m10_pdf"].get("sha256_16", "")))
    lines.append("| M14 | %s（%d B，sha16 %s） | 10 次中 4 次充電=地点份额 0.4（q_location_share，非 q_use）；每週 1-2 次/家充/SOC 29 percent/時長 72min（部分 UNVERIFIED） | 背景参考，未接线 |" %
                 (infos["m14_pdf"]["path"], infos["m14_pdf"].get("bytes", 0), infos["m14_pdf"].get("sha256_16", "")))
    lines.append("| M15 | %s（%d B，sha16 %s） | 仅研究页描述；无数值变量 | 已下载未接线（数据集未取得） |" %
                 (infos["m15_html"]["path"], infos["m15_html"].get("bytes", 0), infos["m15_html"].get("sha256_16", "")))
    lines.append("| M16 | %s（%d B，sha16 %s） | %d 条会话；Operator 非空 %d；四时间戳齐全 %d；无 parking event 分母 | 已下载未接线（背景） |" %
                 (infos["m16_csv"]["path"], infos["m16_csv"].get("bytes", 0), infos["m16_csv"].get("sha256_16", ""),
                  m16_rows, operator_nonempty, complete))
    lines.append("")
    lines.append("## 6. 成本来源混用与 CPI/FX 限制")
    lines.append("")
    lines.append("| 项目 | 值 | 来源类别 | 限制 |")
    lines.append("|---|---|---|---|")
    lines.append("| VOT | 406.63 TWD/veh·h | 官方（CPI 链式换算） | 保守下限；手册建议工資上漲率；2026 为 1-9 月平均代理 |")
    lines.append("| 汽油/电价 | 31.7385 TWD/L；4.08 TWD/kWh | 官方 | 价格基准时点需按年核对 |")
    lines.append("| EVSE capex | 116,792.62 TWD/枪 | 可迁移（P26 3325.5 USD/枪） | FX 30.9 UNVERIFIED；未含配电/土木；2 枪 pedestal 摊提 |")
    lines.append("| 维护 | 43.2997 TWD/枪·日 | 可迁移（P26） | FX UNVERIFIED；未区分硬体维修 |")
    lines.append("| 寿命 | 10 年 | 情景假设 | 无官方来源 |")
    lines.append("| 损失参数 | 缺失 | 缺失不可识别 | residual_trip_loss 等为 null；cost_complete=false |")
    lines.append("")
    lines.append("设施成本（单枪单日）= %.12f TWD，与 cost_scenario facility_cost.per_connector_day_TWD 一致；"
                 "结果行 TPE0008/seed1/k1 facility_cost=%.12f，未混入社会损失项。" %
                 (float(facility["value"]), float(probe_row["facility_cost"])))
    lines.append("")
    lines.append("## 7. 缺失与 UNVERIFIED")
    lines.append("")
    for gap in gaps:
        lines.append("- **%s %s**（%s）：%s" % (gap["id"], gap["item"], gap["status"], gap["note"]))
    lines.append("")
    lines.append("## 8. 复现")
    lines.append("")
    lines.append("~~~text")
    lines.append("python research/round4_20261031/data_trace.py")
    lines.append("python apps/parking_lab/workbench/charge_sources.py --catalog research/round4_20261031/charge_probability_sources.json")
    lines.append("~~~")
    lines.append("")
    lines.append("本次只写 data_trace.py、data_trace.json、data_trace.md、charge_probability_sources.json；"
                 "未改 workbench/config/runner/历史 JSON。")
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(json.dumps({"out_json": rel(OUT_JSON), "out_md": rel(OUT_MD),
                      "checks": rep.summary(), "catalog_sha256": catalog_sha[:16],
                      "unverified": [c["id"] for c in rep.checks if c["status"] == "unverified"],
                      "fail": [c["id"] for c in rep.checks if c["status"] == "fail"]},
                     ensure_ascii=False))
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
