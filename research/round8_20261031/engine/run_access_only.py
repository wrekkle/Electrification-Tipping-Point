"""SUPPLEMENTARY access-only 诊断（不是声明的三约束标准）。

定义：charge request 的 access 失败 = 入园被拒，或入园后从未拿到连接器开始充电
（visit.charge_start_min is None 且 delivered<=0）。能量短缺（拿到连接器但未充满）不计入 access，
单独作为 energy service 指标报告。k 域 0..n_spaces，整数、从 0 向上穷举，无未来信息。
"""
from __future__ import annotations
import csv, json, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE = Path(__file__).resolve().parent
for p in (str(ROOT), str(ENGINE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import runner
from apps.parking_lab.workbench import publicdata
from apps.parking_lab.workbench.simulation import Simulation

SEED = 20261031
CONNECTOR_KW = 22.0
LABEL = "scenario_supplementary_access_only_22kW_not_standard"
OUT = ROOT / "research" / "round8_20261031" / "experiments_condshare" / "access_only"
ALPHA = 0.05


def main():
    runner.set_scenario_label(LABEL)
    runner.set_scenario_force(connector_kw=CONNECTOR_KW, feeder_kw_per_connector=CONNECTOR_KW)
    OUT.mkdir(parents=True, exist_ok=True)
    contract = ROOT / "research/round8_20261031/data/processed/public_parking_events.json"
    rep = publicdata.load_contract(contract, strict=False)
    blocks = publicdata.site_day_blocks(rep["normalised"])
    split = publicdata.split_site_days(blocks, seed=SEED)
    by_hash = {runner.stream_from_block(b, seed=SEED)["stream_hash"]:
               (b, runner.stream_from_block(b, seed=SEED)) for b in split["test"]}
    with open(ROOT / "research/round8_20261031/experiments_main22/E4/test_E4.csv",
              encoding="utf-8") as fh:
        selected = [by_hash[row["stream_hash"]] for row in csv.DictReader(fh) if row["policy"] == "A"]
    rows, sweep = [], []
    for block, stream in selected:
        site = block["site"]
        n_spaces = int(site["n_spaces"])
        k_star = None; at = None
        for k in range(0, n_spaces + 1):
            site_k = dict(site, charging_bays=k, connectors=k)
            arrivals = publicdata.to_traffic_arrivals(stream)
            horizon = runner.stream_horizon(stream)
            config = runner.config_for(site_k, "A", k, horizon_min=horizon, seed=SEED,
                                       connector_kw=CONNECTOR_KW, feeder_kw=max(CONNECTOR_KW, k * CONNECTOR_KW),
                                       arrival_rate_hour=runner._arrival_rate(stream, horizon))
            sim = Simulation(config, arrivals=arrivals); sim.run(); visits = sim.export()["visits"]
            charge = [v for v in visits if v.get("is_ev") and v.get("needs_charge")
                      and v["time_min"] + v["dwell_min"] > 0]
            # 只看窗口内外生请求（与本任务其它家族同口径）：窗口内到达，或期初车辆
            charge = [v for v in charge if float(v["time_min"]) <= horizon]
            gate_rej = sum(1 for v in charge if not v["admitted"])
            no_conn = sum(1 for v in charge if v["admitted"]
                          and v.get("charge_start_min") is None
                          and float(v.get("delivered_kwh") or 0.0) <= 1e-9)
            unmet = gate_rej + no_conn
            rate = unmet / len(charge) if charge else 0.0
            delivered = sum(float(v.get("delivered_kwh") or 0.0) for v in charge)
            demand = sum(float(v.get("energy_kwh") or 0.0) for v in charge)
            sweep.append({"stream_id": stream["stream_id"], "k": k, "charge_requests": len(charge),
                          "gate_rejections": gate_rej, "no_connector": no_conn,
                          "access_unmet": unmet, "access_unmet_rate": rate,
                          "delivered_kwh": round(delivered, 3), "demand_kwh": round(demand, 3),
                          "gate_only_rate": gate_rej / len(charge) if charge else 0.0})
            if k_star is None and rate <= ALPHA:
                k_star = k; at = sweep[-1]
                break
        if k_star is None:
            at = sweep[-1] if sweep else None
        rows.append({"site_id": stream["site_id"], "day_key": stream["day_key"],
                     "stream_id": stream["stream_id"], "n_spaces": n_spaces,
                     "declared_charging_bays": int(site.get("charging_bays") or 0),
                     "k_star_access_only": k_star,
                     "share_k_star": (k_star / n_spaces) if k_star is not None else None,
                     "status": "confirmed_minimal" if k_star is not None else "physically_infeasible",
                     "k_checked": (k_star + 1) if k_star is not None else (len([s for s in sweep if s['stream_id'] == stream['stream_id']])),
                     "charge_requests": at["charge_requests"] if at else None,
                     "gate_rejections": at["gate_rejections"] if at else None,
                     "no_connector": at["no_connector"] if at else None,
                     "access_unmet_rate": at["access_unmet_rate"] if at else None,
                     "energy_delivered_kwh": at["delivered_kwh"] if at else None,
                     "energy_demand_kwh": at["demand_kwh"] if at else None,
                     "energy_gap_kwh": (round(max(0.0, at["demand_kwh"] - at["delivered_kwh"]), 3) if at else None),
                     "energy_service_rate": (round(at["delivered_kwh"] / at["demand_kwh"], 4)
                                             if at and at["demand_kwh"] else None)})
    # 聚合
    feasible = [r for r in rows if r["k_star_access_only"] is not None]
    shares = [r["share_k_star"] for r in feasible]
    ks = [r["k_star_access_only"] for r in feasible]
    sites = {}
    for r in feasible:
        sites.setdefault(r["site_id"], []).append(r["share_k_star"])
    delivered = sum(r["energy_delivered_kwh"] or 0 for r in feasible)
    demand = sum(r["energy_demand_kwh"] or 0 for r in feasible)
    summary = {
        "scenario_label": LABEL,
        "status": "supplementary_diagnostic_not_declared_standard",
        "definition": ("access-only 失败 = 入园被拒 或 入园后从未拿到连接器开始充电；"
                       "能量短缺不计入 access，单独报告。阈值沿用 5%（此阈值来自三约束标准，仅借用为诊断尺度，"
                       "不因此把该指标升级为声明标准）。"),
        "k_domain": "0..n_spaces 整数穷举，从 0 向上；无未来信息",
        "alpha": ALPHA, "connector_kw": CONNECTOR_KW, "seed": SEED,
        "n_streams": len(rows), "n_feasible": len(feasible),
        "n_physically_infeasible": len(rows) - len(feasible),
        "class_counts": {"confirmed_minimal": len(feasible),
                         "minimality_unconfirmed": 0,
                         "physically_infeasible": len(rows) - len(feasible),
                         "budget_not_covered": 0, "missing_data": 0},
        "k_star_min": min(ks) if ks else None,
        "k_star_median": statistics.median(ks) if ks else None,
        "k_star_max": max(ks) if ks else None,
        "share_min": min(shares) if shares else None,
        "share_median": statistics.median(shares) if shares else None,
        "share_max": max(shares) if shares else None,
        "n_streams_share_gt_20pct": sum(1 for s in shares if s > 0.20),
        "n_streams_kstar_gt_declared_bays": sum(1 for r in feasible
                                                if r["k_star_access_only"] > r["declared_charging_bays"]),
        "n_sites": len({r["site_id"] for r in rows}),
        "n_sites_any_share_gt_20pct": len({r["site_id"] for r in feasible if r["share_k_star"] > 0.20}),
        "energy_at_k_star": {"streams": len(feasible),
                             "delivered_kwh": round(delivered, 1),
                             "demand_kwh": round(demand, 1),
                             "gap_kwh": round(max(0.0, demand - delivered), 1),
                             "energy_service_rate": round(delivered / demand, 4) if demand else None},
        "note": "SUPPLEMENTARY：access-only 是诊断口径，不是声明的三约束标准；能量服务按 delivered/demand 单独报告。",
    }
    with open(OUT / "access_only_solution.csv", "w", encoding="utf-8", newline="") as fh:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        w = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader(); w.writerows(rows)
    with open(OUT / "access_only_sweep.csv", "w", encoding="utf-8", newline="") as fh:
        fieldnames = []
        for row in sweep:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        w = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader(); w.writerows(sweep)
    (OUT / "access_only_results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = [OUT / "access_only_solution.csv", OUT / "access_only_sweep.csv",
             OUT / "access_only_results.json"]
    manifest = {"family": "CONDSHARE_ACCESS_ONLY", "status": "ok", "mode": "real_data",
                "dataset_id": rep["normalised"].get("dataset_id"),
                "scenario_label": LABEL, "seed": SEED, "command": "run_access_only.py",
                "inputs": [{"path": str(contract), "sha256": publicdata.file_sha256(contract)}],
                "outputs": [{"path": p.name, "sha256": runner.sha256_file(p)} for p in files],
                "notes": ["SUPPLEMENTARY 诊断：access-only 口径，不是声明的三约束标准",
                          "access 失败=入园被拒或无连接器；能量短缺单独报告",
                          "k 域 0..n_spaces 整数穷举；无未来信息；22 kW 情景非观测"]}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, default=str))
    return summary


if __name__ == "__main__":
    main()
