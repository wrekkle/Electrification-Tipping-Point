"""固定 k 下的三规则对照：π0 dedicated_by_type / π1 full_open_ice_first / π2 predictive_shared_ice_first。

同一 (lot, seed) 与 k 重放同一外生车流（traffic_hash 必须相等）；配对差用 bootstrap CI。
"""
from __future__ import annotations

import argparse, json, os, sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
for entry in (ROOT, HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import run_cost_curve as runner  # noqa: E402
from apps.parking_lab.workbench import stat_tools  # noqa: E402

RULES = ("dedicated_by_type", "full_open_ice_first", "predictive_shared_ice_first")


def main(argv=None):
    parser = argparse.ArgumentParser(description="固定 k 三规则对照")
    parser.add_argument("--params", required=True)
    parser.add_argument("--analysis", required=True, help="analysis_pi0.json，用于取每场站 k5")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--charger-kw", type=float, default=7.0)
    parser.add_argument("--feeder-kw", type=float, default=120.0)
    parser.add_argument("--cost-file", default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    with open(args.params, encoding="utf-8") as handle:
        params = json.load(handle)
    with open(args.analysis, encoding="utf-8") as handle:
        analysis = json.load(handle)
    cost_params = {}
    if args.cost_file:
        with open(args.cost_file, encoding="utf-8") as handle:
            document = json.load(handle)
        cost_params = document.get("cost", document)
    lots = [row["lot_id"] for row in params.get("per_lot") or []]
    seeds = [int(seed) for seed in args.seeds.split(",")]
    meta_rows, tasks = [], []
    for lot_id in lots:
        info = runner.lot_meta(params, lot_id)
        n_spaces = int(info["n_spaces"])
        record = analysis["lots"].get(lot_id) or {}
        k5 = (record.get("service_level_k") or {}).get("0.05")
        if k5 is None:
            load_value = record.get("observed_load_erlang") or 0.0
            k5 = max(1, int(round(load_value * 2)))
        k_values = sorted({max(0, min(n_spaces, k5 - 1)), max(0, min(n_spaces, k5)),
                           max(0, min(n_spaces, k5 + 2))})
        horizon = float(params.get("generator", {}).get("horizon_min", 1440))
        base = runner.build_base(n_spaces, horizon / 60.0, 11.5, args.charger_kw, args.feeder_kw)
        meta_rows.append({"lot_id": lot_id, "n_spaces": n_spaces, "k_values": k_values, "k5": k5})
        for rule in RULES:
            for seed in seeds:
                tasks.append((lot_id, args.params, seed, k_values, base, rule, cost_params, "per_day"))
    results = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(runner.run_lot_seed, tasks))
    else:
        results = [runner.run_lot_seed(task) for task in tasks]
    rows, failures = [], []
    for result in results:
        if result.get("ok"):
            rows.extend(result["rows"])
        else:
            failures.append(result)
    rows.sort(key=lambda row: (row["lot_id"], row["k"], row["rule"], row["seed"]))

    # 配对比较：同一 (lot,k,seed) 下 π1-π0、π2-π0 与 π2-π1
    index = {(row["lot_id"], row["k"], row["seed"], row["rule"]): row for row in rows}
    pairs = {"pi1_minus_pi0": ("full_open_ice_first", "dedicated_by_type"),
             "pi2_minus_pi0": ("predictive_shared_ice_first", "dedicated_by_type"),
             "pi2_minus_pi1": ("predictive_shared_ice_first", "full_open_ice_first")}
    comparisons = {}
    for name, (left, right) in pairs.items():
        metrics = ("ev_rejected", "ice_rejected", "rejected_total", "unmet_no_connector_events",
                   "unmet_no_connector_energy_kwh", "power_dwell_shortfall_events",
                   "power_dwell_shortfall_kwh", "delivered_energy_kwh")
        summary = {}
        for metric in metrics:
            diffs = []
            for (lot_id, k, seed, rule), row in index.items():
                if rule != left:
                    continue
                other = index.get((lot_id, k, seed, right))
                if other is None:
                    continue
                a, b = row.get(metric), other.get(metric)
                if a is None or b is None:
                    continue
                diffs.append(a - b)
            if diffs:
                ci = stat_tools.bootstrap_ci(diffs, n_boot=2000, seed=7) if len(diffs) > 1 else None
                summary[metric] = {"mean_diff": sum(diffs)/len(diffs), "n": len(diffs),
                                   "ci_low": ci["low"] if ci else None, "ci_high": ci["high"] if ci else None}
        comparisons[name] = summary
    # 同一 (lot,k,seed) 三规则 traffic_hash 必须相等
    hash_check = {}
    for (lot_id, k, seed, rule), row in index.items():
        key = "%s|%s|%s" % (lot_id, k, seed)
        hash_check.setdefault(key, set()).add(row["traffic_hash"])
    hash_violations = [key for key, values in hash_check.items() if len(values) > 1]
    type_totals = {}
    for rule in RULES:
        totals = {}
        for key in ("no_charging_demand_bay_min", "overstay_after_complete_min", "ice_blocking_connector_min"):
            values = [row["type_occupancy"][key] for row in rows if row["rule"] == rule and row["type_occupancy"].get(key) is not None]
            totals[key] = sum(values)/len(values) if values else None
        type_totals[rule] = totals
    document = {"schema": "rule_comparison/v1", "params": args.params, "analysis": args.analysis,
                "seeds": seeds, "lots": meta_rows, "rows": rows, "failures": failures,
                "comparisons": comparisons, "traffic_hash_violations": hash_violations,
                "type_occupancy_mean_by_rule": type_totals,
                "caveat": "合成/校准车流的仿真结果，不是真实场景效果；π2 阈值与窗口未校准。"}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({"out": args.out, "rows": len(rows), "failures": len(failures),
                      "hash_violations": len(hash_violations)}, ensure_ascii=False))
    for name, summary in comparisons.items():
        print(name, json.dumps(summary, ensure_ascii=False)[:500])
    return 0 if not failures and not hash_violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
