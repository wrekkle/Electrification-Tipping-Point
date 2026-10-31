"""条件整数配置分析（conditional integer configuration）：k 允许 0..n_spaces，22 kW，
服务标准与三约束不变，无未来信息；本文件所有容量均为条件情景，不是观测值。

对每条留出流（与 main22 E4 相同的 20 条）从 k=0 向上整数枚举，记录首个满足三约束的 k*；
按同样的五分类归类；再做 M1（A vs B 最小 k 差）与 M2（A vs B0/B1/B2 能量服务率）。
输出到 experiments_condshare/，不覆盖 main22 与 7 kW 输出。
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ENGINE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import runner
from apps.parking_lab.workbench import publicdata, stat_tools

SEED = 20261031
CONNECTOR_KW = 22.0
LABEL = "scenario_conditional_uncapped_connectors_22kW"
POWER_POLICIES = ("A", "B")
BASELINES = ("B0_FCFS", "B1_QUOTA", "B2_LITERATURE")
CLASSES = ("confirmed_minimal", "minimality_unconfirmed", "physically_infeasible",
           "budget_not_covered", "missing_data")
OUT = ROOT / "research" / "round8_20261031" / "experiments_condshare"


def n_spaces_of(site):
    return int(site["n_spaces"])


def site_at_k(site, k):
    return dict(site, charging_bays=int(k), connectors=int(k))


def sweep_stream(stream, site, policy, seed=SEED):
    """从 k=0 向上走到 n_spaces：返回首个可行 k 及逐 k 证据。"""
    n_spaces = n_spaces_of(site)
    trace = []
    for k in range(0, n_spaces + 1):
        row = runner.run_policy(stream, site_at_k(site, k), policy, k, seed=seed,
                                connector_kw=CONNECTOR_KW,
                                feeder_kw=max(CONNECTOR_KW, k * CONNECTOR_KW))
        trace.append(row)
        if row.get("feasible_3constraints") is True:
            return k, row, trace
    return None, trace[-1] if trace else None, trace


def rates_at(row, key):
    value = row.get(key) if row else None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    runner.set_scenario_label(LABEL)
    runner.set_scenario_force(connector_kw=CONNECTOR_KW,
                              feeder_kw_per_connector=CONNECTOR_KW)
    OUT.mkdir(parents=True, exist_ok=True)
    contract = ROOT / "research/round8_20261031/data/processed/public_parking_events.json"
    report = publicdata.load_contract(contract, strict=False)
    blocks = publicdata.site_day_blocks(report["normalised"])
    split = publicdata.split_site_days(blocks, seed=SEED)
    test_blocks = split["test"]
    e4_path = ROOT / "research/round8_20261031/experiments_main22/E4/test_E4.csv"
    with open(e4_path, encoding="utf-8") as handle:
        e4_rows = [row for row in csv.DictReader(handle) if row["policy"] == "A"]
    wanted = {row["stream_hash"]: row["stream_id"] for row in e4_rows}
    by_hash = {}
    for block in test_blocks:
        stream = runner.stream_from_block(block, seed=SEED)
        by_hash[stream["stream_hash"]] = (block, stream)
    selected = [by_hash[h] for h in wanted if h in by_hash]
    if len(selected) != len(wanted):
        raise SystemExit("stream 匹配失败：%d/%d" % (len(selected), len(wanted)))
    summary = {"dataset_id": report["normalised"].get("dataset_id"),
               "scenario_label": LABEL, "connector_kw": CONNECTOR_KW,
               "feeder_rule": "feeder_kw = k * 22 kW (= per-connector 22 kW); 无馈线约束折减",
               "k_domain": "0..n_spaces 整数枚举，无二分", "seed": SEED,
               "constraints": "capacity_only_unmet<=5%, ev_parking_failure<=5%, ice_parking_failure<=5%",
               "note": "条件分析：要求 EV 专用充电位可超过 20% 情景默认；全部容量/充电层为情景，非观测值",
               "n_streams": len(selected), "families": {}}
    sweep_rows, stream_rows = [], []
    kstar = {}
    for block, stream in selected:
        site = block["site"]
        n_spaces = n_spaces_of(site)
        declared_bays = int(site.get("charging_bays") or 0)
        per_stream = {}
        for policy in POWER_POLICIES:
            k_star, row, trace = sweep_stream(stream, site, policy)
            for item in trace:
                sweep_rows.append({"policy": policy, "stream_id": stream["stream_id"],
                                   "site_id": stream["site_id"], "day_key": stream["day_key"],
                                   "n_spaces": n_spaces, "k": item["k"],
                                   "feasible": item.get("feasible_3constraints"),
                                   "capacity_only_unmet_rate": item.get("capacity_only_unmet_rate"),
                                   "ev_parking_failure_rate": item.get("service_ev_parking_failure_rate"),
                                   "ice_parking_failure_rate": item.get("service_ice_parking_failure_rate"),
                                   "departed_shortfall_energy_rate": item.get("service_departed_shortfall_energy_rate"),
                                   "energy_service_rate_incl_rejected": item.get("energy_service_rate_incl_rejected"),
                                   "charge_requests": item.get("den_exogenous_charge_requests"),
                                   "unmet_requests": item.get("num_capacity_unmet_requests")})
            per_stream[policy] = {"k_star": k_star, "row": row, "n_checked": len(trace)}
            kstar.setdefault((stream["stream_id"], policy), k_star)
        row_a = per_stream["A"]["row"]
        k_a = per_stream["A"]["k_star"]
        status = "confirmed_minimal" if k_a is not None else "physically_infeasible"
        reason = None
        if k_a is None and row_a is not None:
            fails = []
            if (rates_at(row_a, "capacity_only_unmet_rate") or 0) > 0.05:
                fails.append("capacity_only_unmet>5%")
            if (rates_at(row_a, "service_ev_parking_failure_rate") or 0) > 0.05:
                fails.append("ev_parking_failure>5%")
            if (rates_at(row_a, "service_ice_parking_failure_rate") or 0) > 0.05:
                fails.append("ice_parking_failure>5%")
            reason = "k=n_spaces=%d 仍不满足：" % n_spaces + ", ".join(fails or ["unknown"])
        entry = {"site_id": stream["site_id"], "day_key": stream["day_key"],
                 "stream_id": stream["stream_id"], "n_spaces": n_spaces,
                 "declared_charging_bays": declared_bays,
                 "k_star_A": k_a, "k_star_B": per_stream["B"]["k_star"],
                 "share_A": (k_a / n_spaces) if k_a is not None else None,
                 "status_A": status, "reason_A": reason,
                 "n_checked_A": per_stream["A"]["n_checked"]}
        if k_a is not None and row_a is not None:
            entry.update({
                "charge_requests_A": row_a.get("den_exogenous_charge_requests"),
                "unmet_requests_A": row_a.get("num_capacity_unmet_requests"),
                "capacity_only_unmet_rate_A": row_a.get("capacity_only_unmet_rate"),
                "delivered_kwh_A": row_a.get("delivered_kwh_incl_rejected"),
                "demand_kwh_A": row_a.get("demand_kwh_incl_rejected"),
                "gap_kwh_A": row_a.get("gap_kwh_incl_rejected"),
                "energy_service_rate_A": row_a.get("energy_service_rate_incl_rejected"),
            })
        stream_rows.append(entry)
        # M2：在 A 的条件配置 k* 上跑基线（同一流同 k 配对）
        if k_a is not None:
            for base_policy in BASELINES:
                row_b = runner.run_policy(stream, site_at_k(site, k_a), base_policy, k_a,
                                          seed=SEED, connector_kw=CONNECTOR_KW,
                                          feeder_kw=max(CONNECTOR_KW, k_a * CONNECTOR_KW))
                stream_rows.append({"site_id": stream["site_id"], "day_key": stream["day_key"],
                                    "stream_id": stream["stream_id"], "n_spaces": n_spaces,
                                    "declared_charging_bays": declared_bays,
                                    "k_star_A": k_a, "policy": base_policy, "k_eval": k_a,
                                    "energy_service_rate": row_b.get("energy_service_rate_incl_rejected"),
                                    "delivered_kwh": row_b.get("delivered_kwh_incl_rejected"),
                                    "demand_kwh": row_b.get("demand_kwh_incl_rejected"),
                                    "gap_kwh": row_b.get("gap_kwh_incl_rejected"),
                                    "charge_requests": row_b.get("den_exogenous_charge_requests"),
                                    "unmet_requests": row_b.get("num_capacity_unmet_requests")})
    # ---------- M1 ----------
    m1_pairs, m1_notes = [], []
    for block, stream in selected:
        a = kstar.get((stream["stream_id"], "A"))
        b = kstar.get((stream["stream_id"], "B"))
        if a is not None and b is not None:
            m1_pairs.append({"stream_id": stream["stream_id"], "k_A": a, "k_B": b, "delta_k": b - a})
        else:
            m1_notes.append({"stream_id": stream["stream_id"],
                             "reason": "A 或 B 在 0..n_spaces 内无可行 k"})
    m1 = {"comparison": "M1", "definition": "留出独立流上 B_shared 与 A_dedicated 的条件最小 k 之差",
          "regime": "conditional_uncapped_connectors_22kW",
          "unit": "independent stream (site-day)",
          "pairs_computable": len(m1_pairs), "pairs_total": len(selected),
          "missing_infeasible": m1_notes}
    if len(m1_pairs) >= 2:
        deltas = [pair["delta_k"] for pair in m1_pairs]
        ci = stat_tools.bootstrap_ci(deltas, n_boot=1000, alpha=0.05, seed=SEED)
        m1.update({"status": "ok", "point": ci["point"], "low": ci["low"],
                   "high": ci["high"], "n_pairs": len(deltas),
                   "estimate": "mean paired difference (bootstrap percentile CI)",
                   "note": "重采样单位=场站-日；正=共享规则需要更多枪；不显著不等于无效"})
    else:
        m1.update({"status": "missing_data", "reason": "可比配对不足 2 个"})
    # ---------- M2 ----------
    m2 = []
    # 直接从 stream_rows 聚合（A 行带 metrics）
    a_metrics = {row["stream_id"]: row for row in stream_rows
                 if "k_star_A" in row and "energy_service_rate_A" in row}
    base_metrics = {}
    for row in stream_rows:
        if row.get("policy") in BASELINES and "energy_service_rate" in row:
            base_metrics.setdefault(row["stream_id"], {})[row["policy"]] = row
    for base_policy in BASELINES:
        diffs = []
        for stream_id, a_row in a_metrics.items():
            b_row = base_metrics.get(stream_id, {}).get(base_policy)
            if b_row is None:
                continue
            diffs.append(float(b_row["energy_service_rate"]) - float(a_row["energy_service_rate_A"]))
        entry = {"comparison": "M2", "pair": "A vs " + base_policy,
                 "definition": "离场能量服务率（含被拒，delivered/demand）的流内配对差（基线减 A）",
                 "regime": "conditional_uncapped_connectors_22kW",
                 "k_eval": "A 的条件最小 k*（同流同 k 配对）",
                 "n_pairs": len(diffs)}
        if len(diffs) >= 2:
            ci = stat_tools.bootstrap_ci(diffs, n_boot=1000, alpha=0.05, seed=SEED)
            entry.update({"status": "ok", "point": ci["point"], "low": ci["low"],
                          "high": ci["high"], "unit": "site-day",
                          "estimate": "mean paired difference (bootstrap percentile CI)"})
        else:
            entry.update({"status": "missing_data", "reason": "可比配对不足 2 个"})
        m2.append(entry)
    # ---------- 聚合 ----------
    feasible_a = [row for row in stream_rows if "share_A" in row and row["share_A"] is not None]
    shares = [row["share_A"] for row in feasible_a]
    over20 = [row for row in feasible_a if row["share_A"] > 0.20]
    over_declared = [row for row in feasible_a
                     if row["k_star_A"] > row["declared_charging_bays"]]
    sites = {}
    for row in stream_rows:
        if "share_A" in row and row["k_star_A"] is not None:
            sites.setdefault(row["site_id"], []).append(row["share_A"])
    aggregates = {"n_streams": len(selected), "n_feasible_A": len(feasible_a),
                  "n_physically_infeasible_A": len(selected) - len(feasible_a),
                  "n_streams_share_gt_20pct": len(over20),
                  "n_streams_kstar_gt_declared_bays": len(over_declared),
                  "n_sites": len({row["site_id"] for row in stream_rows}),
                  "n_sites_with_any_stream_share_gt_20pct":
                      len({row["site_id"] for row in over20}),
                  "n_sites_any_stream_gt_declared_bays":
                      len({row["site_id"] for row in over_declared}),
                  "share_min": min(shares) if shares else None,
                  "share_median": statistics.median(shares) if shares else None,
                  "share_max": max(shares) if shares else None,
                  "kstar_min": min((row["k_star_A"] for row in feasible_a), default=None),
                  "kstar_median": statistics.median([row["k_star_A"] for row in feasible_a]) if feasible_a else None,
                  "kstar_max": max((row["k_star_A"] for row in feasible_a), default=None),
                  "class_counts": {name: 0 for name in CLASSES},
                  "per_site": {site: {"n_streams": len(vals),
                                      "share_max": max(vals), "share_median": statistics.median(vals)}
                               for site, vals in sites.items()}}
    for row in stream_rows:
        if "status_A" in row:
            aggregates["class_counts"][row["status_A"]] += 1
    # ---------- 写出 ----------
    for name, rows_out in (("sweep_condshare", sweep_rows), ("solution_condshare", stream_rows)):
        path = OUT / (name + ".csv")
        fieldnames = []
        for row in rows_out:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows_out)
    payload = {"scenario_label": LABEL, "connector_kw": CONNECTOR_KW, "seed": SEED,
               "m1": m1, "m2": m2, "aggregates": aggregates,
               "note": "条件分析：允许 EV 专用充电位超过 20% 情景默认；非观测硬件；不作无条件外推"}
    (OUT / "conditional_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = [OUT / "sweep_condshare.csv", OUT / "solution_condshare.csv",
             OUT / "conditional_results.json"]
    summary["m1"] = m1
    summary["m2"] = m2
    summary["aggregates"] = aggregates
    summary["families"] = {"conditional": {"files": [str(p) for p in files]}}
    summary["input_qa"] = {"contract": str(contract),
                           "sha256": publicdata.file_sha256(contract),
                           "events_accepted": report["counts"]["events_accepted"]}
    runner.write_json(OUT / "run_meta.json", summary)
    manifest = {"family": "CONDSHARE", "status": "ok", "mode": "real_data",
                "dataset_id": report["normalised"].get("dataset_id"),
                "scenario_label": LABEL, "seed": SEED,
                "command": "run_conditional.py",
                "inputs": [{"path": str(contract),
                            "sha256": publicdata.file_sha256(contract)}],
                "outputs": [{"path": Path(item).name, "sha256": runner.sha256_file(item)}
                            for item in files],
                "notes": ["条件整数配置：k 域 0..n_spaces，22 kW，馈线=枪数*22 kW；",
                          "服务标准与三约束不变；无未来信息；",
                          "要求 EV 专用充电位可超过 20% 情景默认，属条件分析"]}
    runner.write_json(OUT / "manifest.json", manifest)
    print(json.dumps({"out": str(OUT), "n_streams": len(selected), "m1": m1,
                      "m2": m2, "aggregates": aggregates},
                     ensure_ascii=True, default=str))
    return payload


if __name__ == "__main__":
    main()
