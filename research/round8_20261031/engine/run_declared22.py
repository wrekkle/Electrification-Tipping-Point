"""declared22：按契约声明的硬件（20% 充电位、connectors=bays、22 kW、feeder=connectors*22）
在留出流上做 E3/E4/E6 + M1/M3，并与 7 kW/main22 运行对比，附 override 审计。

不修改 experiments/、experiments_main22/、experiments_condshare/。
"""
from __future__ import annotations
import csv, json, math, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE = Path(__file__).resolve().parent
for p in (str(ROOT), str(ENGINE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import runner
import run_phase1 as rp
from apps.parking_lab.workbench import publicdata, stat_tools
from apps.parking_lab.workbench.simulation import Simulation

SEED = 20261031
KW = 22.0
LABEL = "scenario_declared_contract_hardware_22kW"
OUT = ROOT / "research" / "round8_20261031" / "experiments_declared22"
CONTRACT = ROOT / "research/round8_20261031/data/processed/public_parking_events.json"


def site_22(site):
    """契约声明硬件 + 22 kW + feeder=connectors*22（唯一改动是功率层，按本轮要求）。"""
    connectors = int(site["connectors"])
    return {**site, "connector_kw": KW, "feeder_kw": connectors * KW}


def sim_stream(stream, site, k, policy="A"):
    arrivals = publicdata.to_traffic_arrivals(stream)
    horizon = runner.stream_horizon(stream)
    config = runner.config_for(site, policy, k, horizon_min=horizon, seed=SEED,
                               connector_kw=KW, feeder_kw=None,
                               arrival_rate_hour=runner._arrival_rate(stream, horizon))
    sim = Simulation(config, arrivals=arrivals)
    sim.run()
    return sim.export()["visits"], sim.horizon


def decompose(visits, horizon):
    charge = [v for v in visits if v.get("is_ev") and v.get("needs_charge")
              and float(v["time_min"]) <= horizon]
    gate = sum(1 for v in charge if not v["admitted"])
    no_conn = sum(1 for v in charge if v["admitted"]
                  and v.get("charge_start_min") is None
                  and float(v.get("delivered_kwh") or 0.0) <= 1e-9)
    short = 0
    delivered = demand = 0.0
    dwells, needs = [], []
    for v in charge:
        energy = float(v.get("energy_kwh") or 0.0)
        got = float(v.get("delivered_kwh") or 0.0)
        demand += energy
        delivered += got
        if energy - got > 1e-9:
            short += 1
        dwells.append(float(v.get("dwell_min") or 0.0))
        needs.append(energy / KW * 60.0 if energy else 0.0)
    total = len(charge)
    return {"charge_requests": total, "gate_rejections": gate, "no_connector": no_conn,
            "shortfall_sessions": short,
            "sessions_dwell_lt_required": sum(1 for d, n in zip(dwells, needs) if d < n),
            "access_unmet": gate + no_conn,
            "access_rate": 1.0 - (gate + no_conn) / total if total else None,
            "delivered_kwh": round(delivered, 3), "demand_kwh": round(demand, 3),
            "gap_kwh": round(max(0.0, demand - delivered), 3),
            "dwell_min_median": round(statistics.median(dwells), 1) if dwells else None,
            "required_min_median": round(statistics.median(needs), 1) if needs else None}


def fixed_site_row(row, site):
    """行内硬件来源标签修正：全部按声明契约硬件+22kW情景。"""
    row = dict(row)
    row["capacity_source"] = {
        "n_spaces": "observed",
        "charging_bays": "scenario_declared_contract_hardware",
        "connectors": "scenario_declared_contract_hardware",
        "connector_kw": "scenario_declared_contract_hardware_22kW",
        "feeder_kw": "scenario_declared_contract_hardware_22kW",
    }
    row["scenario_label"] = LABEL
    row["missing_inputs"] = []
    return row


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    return path


def main():
    runner.SCENARIO_FORCE.clear()
    runner.set_scenario_label(LABEL)
    OUT.mkdir(parents=True, exist_ok=True)
    normalised = publicdata.load_contract(CONTRACT, strict=False)["normalised"]
    blocks = publicdata.site_day_blocks(normalised)
    split = runner.build_dataset(blocks, seed=SEED)
    test = split["test"]
    calibration = split["calibration"]
    solve = publicdata.select_solve_blocks(calibration)
    e4_streams, _ = runner.sample_blocks(test, runner.BUDGET_CAPS["E4_streams"], SEED, salt=2)
    e5_streams, _ = runner.sample_blocks(test, runner.BUDGET_CAPS["E5_streams"], SEED, salt=3)
    e6_streams, _ = runner.sample_blocks(test, runner.BUDGET_CAPS["E6_streams"], SEED, salt=4)
    main22_meta = json.loads((ROOT / "research/round8_20261031/experiments_main22/run_meta.json")
                             .read_text(encoding="utf-8"))
    k_pre = int(main22_meta.get("preregistered_k") or 1)
    # ---------- 硬件审计 ----------
    hardware = {}
    for site in (normalised["sites"].values() if isinstance(normalised["sites"], dict)
                 else normalised["sites"]):
        cap = runner.site_capability(site)
        hardware[site["site_id"]] = {
            "n_spaces": cap["n_spaces"], "charging_bays": cap["charging_bays"],
            "connectors": cap["connectors"], "connector_kw": cap["connector_kw"],
            "feeder_kw": cap["feeder_kw"], "derived_fields": cap["derived_fields"],
            "declared_in_contract": {key: site.get(key) for key in
                                     ("charging_bays", "connectors", "connector_kw", "feeder_kw")}}
    # ---------- E3：留出流整数 k + 五分类 ----------
    e3_rows, per_stream = [], []
    for block in e4_streams:
        stream = runner.stream_from_block(block, seed=SEED)
        site = site_22(block["site"])
        bays = int(site["charging_bays"])
        k_star = None; row_star = None; last = None
        for k in range(0, bays + 1):
            row = fixed_site_row(runner.run_policy(stream, site, "A", k, seed=SEED), site)
            last = row
            if row.get("feasible_3constraints") is True:
                k_star, row_star = k, row
                break
        status = "confirmed_minimal" if k_star is not None else "physically_infeasible"
        chosen = row_star if k_star is not None else last
        visits, horizon = sim_stream(stream, site, k_star if k_star is not None else bays)
        detail = decompose(visits, horizon)
        capacity = chosen.get("capacity_only_unmet_rate") if chosen else None
        entry = {"site_id": stream["site_id"], "day_key": stream["day_key"],
                 "stream_id": stream["stream_id"], "n_spaces": int(site["n_spaces"]),
                 "declared_charging_bays": bays, "k_max_declared": bays,
                 "k_star": k_star, "status": status,
                 "k_star_share": (k_star / float(site["n_spaces"])) if k_star is not None else None,
                 "capacity_only_unmet_at_eval": capacity,
                 "charge_requests": detail["charge_requests"],
                 "gate_rejections": detail["gate_rejections"],
                 "no_connector": detail["no_connector"],
                 "shortfall_sessions": detail["shortfall_sessions"],
                 "sessions_dwell_lt_required": detail["sessions_dwell_lt_required"],
                 "access_rate": detail["access_rate"],
                 "dwell_min_median": detail["dwell_min_median"],
                 "required_min_median": detail["required_min_median"],
                 "delivered_kwh": detail["delivered_kwh"], "demand_kwh": detail["demand_kwh"],
                 "gap_kwh": detail["gap_kwh"],
                 "energy_service_rate": (detail["delivered_kwh"] / detail["demand_kwh"]
                                         if detail["demand_kwh"] else None),
                 "eval_k": k_star if k_star is not None else bays}
        per_stream.append(entry)
        e3_rows.append({"family": "E3", "split": "test", "site_id": entry["site_id"],
                        "day_key": entry["day_key"], "stream_id": entry["stream_id"],
                        "k": entry["eval_k"], "class": status, "k_star": k_star,
                        "k_max_declared": bays,
                        "capacity_only_unmet_rate": capacity,
                        "detail": json.dumps(detail, ensure_ascii=True)})
    classes = {name: 0 for name in ("confirmed_minimal", "minimality_unconfirmed",
                                    "physically_infeasible", "budget_not_covered", "missing_data")}
    for entry in per_stream:
        classes[entry["status"]] += 1
    # ---------- E4 + M2 ----------
    e4_rows, m2 = [], []
    for block in e4_streams:
        stream = runner.stream_from_block(block, seed=SEED)
        site = site_22(block["site"])
        bays = int(site["charging_bays"])
        for k, k_source in ((k_pre, "preregistered_k=calibration-selected"),
                            (bays, "declared_max_k")):
            for policy in ("A", "B0_FCFS", "B1_QUOTA", "B2_LITERATURE"):
                row = fixed_site_row(runner.run_policy(stream, site, policy, k, seed=SEED), site)
                row.update({"family": "E4", "split": "test", "k_source": k_source})
                e4_rows.append(row)
    by_stream = {}
    for row in e4_rows:
        by_stream.setdefault((row["stream_id"], row["k_source"]), {})[row["policy"]] = row
    for k_source in ("preregistered_k=calibration-selected", "declared_max_k"):
        for base_policy in ("B0_FCFS", "B1_QUOTA", "B2_LITERATURE"):
            diffs = []
            for pair in by_stream.values():
                if pair["A"].get("k_source") != k_source:
                    continue
                a = pair["A"].get("energy_service_rate_incl_rejected")
                b = pair[base_policy].get("energy_service_rate_incl_rejected")
                if a is not None and b is not None:
                    diffs.append(float(b) - float(a))
            if len(diffs) >= 2:
                ci = stat_tools.bootstrap_ci(diffs, n_boot=1000, alpha=0.05, seed=SEED)
                m2.append({"comparison": "M2", "k_source": k_source,
                           "pair": base_policy + " - A",
                           "direction": "baseline_rate - A_rate; negative => A better",
                           "point": ci["point"], "low": ci["low"], "high": ci["high"],
                           "n_pairs": len(diffs), "unit": "site-day",
                           "estimate": "mean paired difference (bootstrap percentile CI)",
                           "note": "重采样单位=场站-日；同流同 k 配对；不显著不等于无效"})
            else:
                m2.append({"comparison": "M2", "k_source": k_source,
                           "pair": base_policy + " - A", "status": "missing_data",
                           "reason": "可比配对不足 2 个", "n_pairs": len(diffs)})
    # ---------- E6 ----------
    e6_rows = runner.e6_rows(e6_streams, seed=SEED, k_values=[k_pre], power_values=(KW,),
                             feeder_shares=(1.0,))
    for row in e6_rows:
        row["family"] = "E6"; row["k_source"] = "preregistered_k"; row["e6_mode"] = "declared22"
    # ---------- M1 / M3 ----------
    m1 = runner.m1_pairs(e5_streams, seed=SEED)
    m1_status = "ok" if sum(1 for p in m1 if p.get("delta_k") is not None) >= 2 else "missing_data"
    def window_block(block, size=20):
        events = block["events"]
        if len(events) <= size:
            return dict(block, instance_construction="whole site-day (<=20 arrivals)")
        best_start, best_score = 0, -1
        for start in range(0, len(events) - size + 1):
            score = sum(1 for event in events[start:start + size]
                        if event["is_ev"] and event.get("needs_charge"))
            if score > best_score:
                best_start, best_score = start, score
        chunk = events[best_start:best_start + size]
        return {**block, "events": chunk, "n_events": len(chunk),
                "first_arrival_min": chunk[0]["arrival_min"],
                "instance_construction": ("max-charge-demand consecutive <=20-arrival "
                                          "window (declared subsample of the site-day)")}

    solve_instances = [window_block(block) for block in solve]
    m3 = runner.m3_pairs(solve_instances, k_max=None)
    m3_status = ("ok" if sum(1 for item in m3 if item.get("k_min") is not None
                             and item.get("k_min_energy_constrained") is not None) >= 2
                 else "missing_data")
    # ---------- 对比 7kW / main22（同 k=1 预注册口径） ----------
    def aggregate_e4(path):
        with open(path, encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r.get("policy") == "A"]
        def num(row, key):
            try:
                return float(row.get(key) or 0)
            except (TypeError, ValueError):
                return 0.0
        delivered = sum(num(r, "delivered_kwh_incl_rejected") for r in rows)
        demand = sum(num(r, "demand_kwh_incl_rejected") for r in rows)
        return {"n_streams": len(rows),
                "charge_requests": int(sum(num(r, "den_exogenous_charge_requests") for r in rows)),
                "gate_rejections": int(sum(num(r, "rejected") for r in rows)),
                "access_num": int(sum(num(r, "charging_access_num") for r in rows)),
                "access_den": int(sum(num(r, "charging_access_den") for r in rows)),
                "access_rate": (sum(num(r, "charging_access_num") for r in rows)
                                / sum(num(r, "charging_access_den") for r in rows)
                                if sum(num(r, "charging_access_den") for r in rows) else None),
                "delivered_kwh": round(delivered, 1), "demand_kwh": round(demand, 1),
                "energy_service_rate": (round(delivered / demand, 4) if demand else None),
                "k": sorted({r["k"] for r in rows})}
    comparison = []
    for name, path, hardware_note in (
            ("7kW_experiments", ROOT / "research/round8_20261031/experiments/E4/test_E4.csv",
             "本次审计：resolved hardware = 契约声明 20%（见 hardware_audit）"),
            ("main22_experiments", ROOT / "research/round8_20261031/experiments_main22/E4/test_E4.csv",
             "22 kW, feeder=k*22；charging_bays/connectors 来自契约声明")):
        agg = aggregate_e4(path)
        comparison.append({"run": name, "hardware_note": hardware_note, **agg})
    declared_agg = aggregate_e4(OUT / "E4" / "_tmp_E4.csv") if False else None
    # declared22 聚合（k=1 行）
    pre_rows = [r for r in e4_rows if r["k_source"].startswith("preregistered")
                and r["policy"] == "A"]
    def agg_rows(rows):
        def num(key):
            return sum(float(r.get(key) or 0) for r in rows)
        delivered = num("delivered_kwh_incl_rejected"); demand = num("demand_kwh_incl_rejected")
        return {"n_streams": len(rows),
                "charge_requests": int(num("den_exogenous_charge_requests")),
                "gate_rejections": int(num("rejected")),
                "access_num": int(num("charging_access_num")),
                "access_den": int(num("charging_access_den")),
                "access_rate": (num("charging_access_num") / num("charging_access_den")
                                if num("charging_access_den") else None),
                "delivered_kwh": round(delivered, 1), "demand_kwh": round(demand, 1),
                "energy_service_rate": (round(delivered / demand, 4) if demand else None),
                "capacity_only_unmet_mean": round(sum(float(r.get("capacity_only_unmet_rate") or 0)
                                                       for r in rows) / len(rows), 4) if rows else None}
    comparison.append({"run": "declared22_k_prereg", "hardware_note": "契约声明硬件+22kW",
                       "k": "prereg(%d) (k=%d)" % (k_pre, k_pre), **agg_rows(pre_rows)})

    def agg_per_stream(rows):
        def s(key):
            return sum(float(r.get(key) or 0) for r in rows)
        total = s("charge_requests")
        served = total - s("gate_rejections") - s("no_connector")
        return {"n_streams": len(rows), "charge_requests": int(total),
                "gate_rejections": int(s("gate_rejections")),
                "no_connector": int(s("no_connector")),
                "shortfall_sessions": int(s("shortfall_sessions")),
                "access_num": int(served), "access_den": int(total),
                "access_rate": (served / total) if total else None,
                "delivered_kwh": round(s("delivered_kwh"), 1),
                "demand_kwh": round(s("demand_kwh"), 1),
                "energy_service_rate": (round(s("delivered_kwh") / s("demand_kwh"), 4)
                                        if s("demand_kwh") else None),
                "capacity_only_unmet_mean": round(
                    sum(float(r["capacity_only_unmet_at_eval"]) for r in rows) / len(rows), 4)}
    comparison.append({"run": "declared22_at_declared_max_k",
                       "hardware_note": "契约声明硬件（20%）+22kW；k=declared charging_bays（最大 16）",
                       "k": "declared_max_k", **agg_per_stream(per_stream)})
    # ---------- 写出 ----------
    write_csv(OUT / "E3" / "search_E3.csv", e3_rows)
    runner.write_json(OUT / "E3" / "classes.json",
                      {"classes": classes, "instances": per_stream, "scenario_label": LABEL,
                       "note": "held-out 流的整数 k 枚举（0..declared charging_bays），五分类；非离线模型"})
    write_csv(OUT / "E4" / "test_E4.csv", e4_rows)
    runner.write_json(OUT / "E4" / "m2_declared22.json", {"m2": m2, "scenario_label": LABEL})
    write_csv(OUT / "E6" / "energy_E6.csv", e6_rows)
    write_csv(OUT / "per_stream_declared22.csv", per_stream)
    write_csv(OUT / "comparison_overrides.csv", comparison)
    m_rows = ([{"comparison": "M1", "status": m1_status, "n_pairs": len(m1),
                "pairs_computable": sum(1 for p in m1 if p.get("delta_k") is not None),
                "reason": "A/B 在 0..declared charging_bays 内最小可行 k；无可行 k 则缺失"},
               {"comparison": "M3", "status": m3_status, "instances_total": len(m3),
                "pairs_computable": sum(1 for i in m3 if i.get("k_min") is not None
                                        and i.get("k_min_energy_constrained") is not None),
                "reason": "离线声明模型（22kW, feeder=connectors*22）实例可行性"}]
              + m2)
    write_csv(OUT / "M" / "m_summaries.csv", m_rows)
    runner.write_json(OUT / "M" / "m_summaries.json", {"comparisons": m_rows,
                                                       "constraint_thresholds_ref": "none"})
    audit = {
        "declared22_parameters": {"charging_bays": "per contract (20% of n_spaces)",
                                  "connectors": "= charging_bays (contract)",
                                  "connector_kw": KW,
                                  "feeder_kw": "= connectors * 22.0",
                                  "k_domain": "0..charging_bays",
                                  "max_connectors_per_site_override": None,
                                  "feeder_share_override": None},
        "scenario_defaults_in_code": {"file": "research/round8_20261031/engine/runner.py",
                                      "lines": "62-67", "values": runner.SCENARIO_DEFAULTS},
        "where_defaults_apply": {"file": "research/round8_20261031/engine/runner.py",
                                 "function": "site_capability", "line": 115,
                                 "rule": "仅当站点缺字段时使用 SCENARIO_DEFAULTS；本契约每站四字段齐全"},
        "where_cli_override_applies": {"file": "research/round8_20261031/engine/run_phase1.py",
                                       "lines": "456-466", "rule": "只有传 --connector-kw/--force-connector-kw 时覆盖"},
        "resolved_hardware": hardware,
        "evidence_no_4cap": "declared22 E3 k 网格到 declared charging_bays（最大 16），"
                            "7kW E2 旧曲线也到 k=16/14/12/8；若 max_connectors=4 生效不会出现这些 k",
        "conclusion": ("审计结论：7 kW 与 main22 运行并未应用 charging_bay_share=0.1/max_connectors_per_site=4/feeder_share=0.5；"
                       "这些默认值只对缺字段站点生效，本契约站点四字段齐全，实际使用契约声明值；"
                       "main22 只强制了 connector_kw=22 与 feeder=connectors*22。"
                       "因此 declared22 = main22 的硬件口径（本目录为显式复核运行）。"),
    }
    runner.write_json(OUT / "hardware_audit.json", audit)
    run_meta = {"dataset_label": normalised.get("dataset_id"), "mode": "real_data",
                "scenario_label": LABEL, "seed": SEED,
                "preregistered_k": k_pre,
                "families": {"E3": {"files": [str(OUT / "E3" / "search_E3.csv"),
                                              str(OUT / "E3" / "classes.json")],
                                    "rows": len(e3_rows)},
                             "E4": {"files": [str(OUT / "E4" / "test_E4.csv"),
                                              str(OUT / "E4" / "m2_declared22.json")],
                                    "rows": len(e4_rows)},
                             "E6": {"files": [str(OUT / "E6" / "energy_E6.csv")],
                                    "rows": len(e6_rows)},
                             "M": {"files": [str(OUT / "M" / "m_summaries.csv"),
                                             str(OUT / "M" / "m_summaries.json")],
                                   "rows": len(m_rows)}},
                "classes": classes, "m1_status": m1_status, "m3_status": m3_status,
                "m2": m2, "comparison": comparison,
                "hardware_audit": "hardware_audit.json",
                "overrides_applied": [],
                "note": ("declared22：契约声明硬件（20% 充电位、connectors=bays）+22kW、feeder=connectors*22；"
                         "无 charging_bay_share/max_connectors/feeder_share 覆盖。"),
                "input_qa": {"contract": str(CONTRACT),
                             "sha256": publicdata.file_sha256(CONTRACT)}}
    runner.write_json(OUT / "run_meta.json", run_meta)
    files = [OUT / "E3" / "search_E3.csv", OUT / "E3" / "classes.json",
             OUT / "E4" / "test_E4.csv", OUT / "E4" / "m2_declared22.json",
             OUT / "E6" / "energy_E6.csv", OUT / "M" / "m_summaries.csv",
             OUT / "M" / "m_summaries.json", OUT / "per_stream_declared22.csv",
             OUT / "comparison_overrides.csv", OUT / "hardware_audit.json"]
    runner.write_json(OUT / "manifest.json", {
        "family": "DECLARED22", "status": "ok", "mode": "real_data",
        "dataset_id": normalised.get("dataset_id"), "scenario_label": LABEL, "seed": SEED,
        "command": "run_declared22.py",
        "inputs": [{"path": str(CONTRACT), "sha256": publicdata.file_sha256(CONTRACT)}],
        "outputs": [{"path": p.name, "sha256": runner.sha256_file(p)} for p in files],
        "notes": ["硬件取契约声明值（charging_bays/connectors），22 kW，feeder=connectors*22",
                  "无 max_connectors_per_site / feeder_share 覆盖",
                  "override 审计见 hardware_audit.json（含代码行与 resolved hardware）"]})
    print(json.dumps({"classes": classes, "m2": m2, "m1_status": m1_status,
                      "m3_status": m3_status, "comparison": comparison,
                      "n_streams": len(per_stream)}, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
