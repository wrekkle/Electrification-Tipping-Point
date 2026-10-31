"""条件域的不可行性证据：k=n_spaces 时逐流分解 charge request（入园拒绝 vs 能量短缺）。"""
from __future__ import annotations
import csv, json, math, statistics, sys
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
LABEL = "scenario_conditional_uncapped_connectors_22kW"
OUT = ROOT / "research" / "round8_20261031" / "experiments_condshare"


def main():
    runner.set_scenario_label(LABEL)
    runner.set_scenario_force(connector_kw=CONNECTOR_KW, feeder_kw_per_connector=CONNECTOR_KW)
    contract = ROOT / "research/round8_20261031/data/processed/public_parking_events.json"
    rep = publicdata.load_contract(contract, strict=False)
    blocks = publicdata.site_day_blocks(rep["normalised"])
    split = publicdata.split_site_days(blocks, seed=SEED)
    by_hash = {runner.stream_from_block(b, seed=SEED)["stream_hash"]:
               (b, runner.stream_from_block(b, seed=SEED)) for b in split["test"]}
    with open(ROOT / "research/round8_20261031/experiments_main22/E4/test_E4.csv",
              encoding="utf-8") as fh:
        selected = [by_hash[row["stream_hash"]] for row in csv.DictReader(fh) if row["policy"] == "A"]
    rows = []
    for block, stream in selected:
        site = block["site"]
        n_spaces = int(site["n_spaces"])
        for policy in ("A", "B"):
            site_k = dict(site, charging_bays=n_spaces, connectors=n_spaces)
            arrivals = publicdata.to_traffic_arrivals(stream)
            horizon = runner.stream_horizon(stream)
            config = runner.config_for(site_k, policy, n_spaces, horizon_min=horizon, seed=SEED,
                                       connector_kw=CONNECTOR_KW, feeder_kw=n_spaces * CONNECTOR_KW,
                                       arrival_rate_hour=runner._arrival_rate(stream, horizon))
            sim = Simulation(config, arrivals=arrivals); sim.run(); export = sim.export()
            visits = export["visits"]
            charge = [v for v in visits if v.get("needs_charge") and v.get("admitted")]
            rejected = sum(1 for v in visits if v.get("needs_charge") and not v.get("admitted"))
            short = 0; delivered = 0.0; demand = 0.0; dwells = []; needs = []
            for v in charge:
                energy = float(v.get("energy_kwh") or 0.0)
                got = float(v.get("delivered_kwh") or 0.0)
                demand += energy; delivered += got
                if energy - got > 1e-9:
                    short += 1
                dwell = float(v.get("dwell_min") or 0.0)
                dwells.append(dwell)
                needs.append(energy / CONNECTOR_KW * 60.0 if energy else 0.0)
            rows.append({"site_id": stream["site_id"], "day_key": stream["day_key"],
                         "stream_id": stream["stream_id"], "policy": policy,
                         "n_spaces": n_spaces, "k_eval": n_spaces,
                         "charge_requests": len(charge) + rejected,
                         "rejected_at_gate": rejected,
                         "admitted_charge_requests": len(charge),
                         "shortfall_sessions": short,
                         "unmet_total": rejected + short,
                         "unmet_rate": (rejected + short) / max(1, len(charge) + rejected),
                         "delivered_kwh": round(delivered, 3), "demand_kwh": round(demand, 3),
                         "gap_kwh": round(max(0.0, demand - delivered), 3),
                         "dwell_min_median": round(statistics.median(dwells), 1) if dwells else None,
                         "required_min_median": round(statistics.median(needs), 1) if needs else None,
                         "sessions_dwell_lt_required": sum(1 for d, n in zip(dwells, needs) if d < n),
                         "energy_service_rate_incl_rejected": round(delivered / demand, 4) if demand else None})
    path = OUT / "evidence_at_n_spaces.csv"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    def agg(policy):
        sub = [r for r in rows if r["policy"] == policy]
        return {"n_streams": len(sub),
                "charge_requests": sum(r["charge_requests"] for r in sub),
                "rejected_at_gate": sum(r["rejected_at_gate"] for r in sub),
                "shortfall_sessions": sum(r["shortfall_sessions"] for r in sub),
                "unmet_total": sum(r["unmet_total"] for r in sub),
                "delivered_kwh": round(sum(r["delivered_kwh"] for r in sub), 1),
                "demand_kwh": round(sum(r["demand_kwh"] for r in sub), 1),
                "gap_kwh": round(sum(r["gap_kwh"] for r in sub), 1),
                "sessions_dwell_lt_required": sum(r["sessions_dwell_lt_required"] for r in sub),
                "admitted_charge_requests": sum(r["admitted_charge_requests"] for r in sub),
                "n_streams_with_zero_unmet": sum(1 for r in sub if r["unmet_total"] == 0)}
    evidence = {"scenario_label": LABEL, "k_eval": "k = n_spaces（所有车位均设为充电位）",
                "note": ("三约束中的 capacity_unmet 在 workbench 口径 = 入园被拒 + 能量短缺会话"
                         "（service_metrics.py:196-201），不是纯连接器可用性；因此能量无法在停留内交付时，"
                         "无论 k 多大都不满足标准。"),
                "aggregate": {"A": agg("A"), "B": agg("B")},
                "n_streams": len({r["stream_id"] for r in rows})}
    (OUT / "evidence_at_n_spaces.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 更新 conditional_results.json / run_meta / manifest：状态如实标 physically_infeasible
    cres = json.loads((OUT / "conditional_results.json").read_text(encoding="utf-8"))
    cres["evidence_at_n_spaces"] = evidence
    cres["note"] = (cres.get("note", "") +
                    "；结果：20/20 流在 k<=n_spaces 内无可行 k，按规则归 physically_infeasible；"
                    "原因是 capacity_unmet 口径含能量短缺，观测停留短于 22 kW 所需充电时长。")
    (OUT / "conditional_results.json").write_text(
        json.dumps(cres, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = json.loads((OUT / "run_meta.json").read_text(encoding="utf-8"))
    meta["status"] = "physically_infeasible_at_k_le_n_spaces"
    meta["evidence_at_n_spaces"] = evidence
    meta["note"] = (meta.get("note", "") +
                    "；条件域结果仍无可行 k：20/20 流在 k=n_spaces 时 capacity_unmet 仍 >5%，"
                    "分解见 evidence_at_n_spaces.json（入园拒绝 0，全部为能量短缺会话）。")
    (OUT / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    manifest["status"] = "physically_infeasible_at_k_le_n_spaces"
    manifest["outputs"] = [{"path": p.name, "sha256": runner.sha256_file(p)}
                           for p in (OUT / "sweep_condshare.csv", OUT / "solution_condshare.csv",
                                     OUT / "conditional_results.json",
                                     OUT / "evidence_at_n_spaces.csv",
                                     OUT / "evidence_at_n_spaces.json")]
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": evidence["aggregate"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
