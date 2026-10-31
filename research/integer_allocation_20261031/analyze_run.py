"""整数配桩结果分析：服务水平整数规则、经验公式、样本外验证、盈亏平衡与 k*(L)（Lead）。

输入：outputs/cost_curve_pi0_*.json（π0 全 k 枚举）+ outputs/observed_charging_load.json。
输出：outputs/analysis_pi0.json + 控制台表格。所有缺参保持 None，不补 0。
"""
from __future__ import annotations

import argparse, json, math, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from apps.parking_lab.workbench import allocation as alloc  # noqa: E402

ALPHAS = (0.02, 0.05, 0.10, 0.20)
LOSS_GRID = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0)


def load_curve(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def aggregate(document):
    per_lot = {}
    for row in document["rows"]:
        lot = row["lot_id"]
        entry = per_lot.setdefault(lot, {"n_spaces": row["n_spaces"], "rows": {}, "seeds": set()})
        entry["seeds"].add(row["seed"])
        bucket = entry["rows"].setdefault(int(row["k"]), [])
        bucket.append(row)
    aggregated = {}
    for lot, entry in per_lot.items():
        by_k = {}
        for k, rows in entry["rows"].items():
            n = len(rows)
            def mean(key):
                values = [row.get(key) for row in rows if row.get(key) is not None]
                return sum(values) / len(values) if values else None
            by_k[k] = {
                "facility_cost": mean("facility_cost"),
                "unserved_events": mean("unserved_charge_events"),
                "unserved_kwh": mean("unserved_charge_energy_kwh"),
                "unmet_no_connector_events": mean("unmet_no_connector_events"),
                "unmet_no_connector_energy_kwh": mean("unmet_no_connector_energy_kwh"),
                "power_dwell_shortfall_events": mean("power_dwell_shortfall_events"),
                "power_dwell_shortfall_kwh": mean("power_dwell_shortfall_kwh"),
                "ev_rejected": mean("ev_rejected"), "ice_rejected": mean("ice_rejected"),
                "overstay_min": mean("type_occupancy") if False else None,
                "charge_requests": mean("charge_requests"),
                "delivered_kwh": mean("delivered_energy_kwh"),
                "n_runs": n,
            }
        # 三类占位分钟（嵌套字段单独取均值）
        for k, rows in entry["rows"].items():
            for key in ("no_charging_demand_bay_min", "overstay_after_complete_min", "ice_blocking_connector_min"):
                values = [row["type_occupancy"][key] for row in rows if row.get("type_occupancy", {}).get(key) is not None]
                by_k[k][key] = sum(values) / len(values) if values else None
        aggregated[lot] = {"n_spaces": entry["n_spaces"], "by_k": dict(sorted(by_k.items())),
                           "n_seeds": len(entry["seeds"])}
    return aggregated


SERVICE_KEY = "unmet_no_connector_events"


def service_level_k(by_k, alpha):
    baseline = by_k.get(0, {}).get(SERVICE_KEY)
    if baseline is None:
        return None
    if baseline <= 0:
        return 0
    for k in sorted(by_k):
        value = by_k[k].get(SERVICE_KEY)
        if value is None:
            continue
        if value <= alpha * baseline:
            return k
    return max(by_k)


def cost_at_L(by_k, loss):
    curve = {}
    for k, row in by_k.items():
        facility, unserved = row.get("facility_cost"), row.get(SERVICE_KEY)
        if facility is None or unserved is None:
            curve[k] = None
        else:
            curve[k] = facility + loss * unserved
    return curve


def break_even_table(by_k):
    rows = {}
    for k in sorted(by_k):
        if k + 1 not in by_k:
            continue
        f0, f1 = by_k[k].get("facility_cost"), by_k[k + 1].get("facility_cost")
        s0, s1 = by_k[k].get(SERVICE_KEY), by_k[k + 1].get(SERVICE_KEY)
        if None in (f0, f1, s0, s1) or s0 - s1 <= 0:
            rows[k] = None
        else:
            rows[k] = (f1 - f0) / (s0 - s1)
    return rows


def fit_sqrt_rule(points):
    """k_alpha ≈ ceil(A + z*sqrt(A))；最小二乘拟合 z（A>0）。"""
    num = 0.0; den = 0.0
    for load, k in points:
        if load <= 0:
            continue
        num += math.sqrt(load) * (k - load)
        den += load
    if den <= 0:
        return {"z": None, "n_points": len(points)}
    return {"z": num / den, "n_points": len(points), "form": "k = ceil(A + z*sqrt(A))"}


def predict(points, formula):
    if formula.get("z") is None:
        return [None] * len(points)
    out = []
    for load, _ in points:
        value = load + formula["z"] * math.sqrt(max(load, 0.0))
        out.append(int(math.ceil(value - 1e-12)))
    return out


def evaluate(validation, predictions):
    details = []
    errors = []
    for (load, k_star, lot), k_hat in zip(validation, predictions):
        if k_hat is None:
            continue
        errors.append(abs(k_hat - k_star))
        details.append({"lot_id": lot, "A": load, "k_star": k_star, "k_hat": k_hat,
                        "abs_error": abs(k_hat - k_star)})
    return {"n": len(details), "mae_k": (sum(errors)/len(errors)) if errors else None,
            "max_abs_error": max(errors) if errors else None, "details": details}


def main(argv=None):
    parser = argparse.ArgumentParser(description="整数配桩结果分析")
    parser.add_argument("--curve", required=True)
    parser.add_argument("--load", default=os.path.join(HERE, "outputs", "observed_charging_load.json"))
    parser.add_argument("--out", default=os.path.join(HERE, "outputs", "analysis_pi0.json"))
    args = parser.parse_args(argv)
    document = load_curve(args.curve)
    with open(args.load, encoding="utf-8") as handle:
        observed = json.load(handle)
    aggregated = aggregate(document)
    lots = {}
    for lot, entry in sorted(aggregated.items()):
        by_k = entry["by_k"]
        obs = observed["lots"].get(lot, {})
        record = {"n_spaces": entry["n_spaces"], "n_seeds": entry["n_seeds"],
                  "observed_load_erlang": obs.get("observed_load_erlang"),
                  "observed_sessions_per_day": obs.get("session_rate_per_day"),
                  "observed_mean_session_min": obs.get("mean_session_min"),
                  "mean_occupancy_vehicles": obs.get("mean_occupancy_vehicles"),
                  "fit_split": obs.get("fit_split"), "usable": obs.get("usable"),
                  "service_level_k": {str(alpha): service_level_k(by_k, alpha) for alpha in ALPHAS},
                  "k_star_by_loss": {str(loss): alloc.evaluate_integer_costs(cost_at_L(by_k, loss))["best_k"]
                                     for loss in LOSS_GRID},
                  "break_even_loss_per_unserved": break_even_table(by_k),
                  "curve": by_k}
        lots[lot] = record
    # 公式拟合（train）与样本外验证（validation）：只用在 validation 场站上的服务层 k_alpha
    train_points = []
    validation_points = []
    for lot, record in lots.items():
        load_value = record.get("observed_load_erlang")
        k_alpha = record["service_level_k"]
        split = record.get("fit_split")
        if load_value is None:
            continue
        for alpha in (0.05, 0.10):
            key = str(alpha)
            k_value = k_alpha.get(key)
            if k_value is None:
                continue
            if split == "train" and record.get("usable"):
                train_points.append((load_value, k_value))
            elif split == "validation" and record.get("usable"):
                validation_points.append((load_value, k_value, lot))
    formula = fit_sqrt_rule(train_points)
    predictions = predict([(load, k) for load, k, _ in validation_points], formula)
    validation = evaluate(validation_points, predictions)
    # 对照：Erlang-B 结构近似（不需要训练）
    erlang_predictions = []
    for load, _, _ in validation_points:
        servers = alloc.min_servers_for_blocking(load, 0.10, max(1, int(load * 10 + 10))) if load > 0 else 0
        erlang_predictions.append(servers if servers is not None else int(math.ceil(load)))
    erlang_validation = evaluate(validation_points, erlang_predictions)
    # 各场站 k*(L) 汇总：给定 L 下全部场站的 k* 与 PPR 分布
    ppr_by_loss = {}
    for loss in LOSS_GRID:
        values = []
        for lot, record in lots.items():
            if not record.get("usable"):
                continue
            curve = cost_at_L(record["curve"], loss)
            best = alloc.evaluate_integer_costs(curve)["best_k"]
            if best:
                ks = min(best)
                values.append((lot, ks, record["n_spaces"], ks / record["n_spaces"]))
        ppr_by_loss[str(loss)] = values
    analysis = {"curve_file": args.curve, "load_file": args.load,
                "alphas": list(ALPHAS), "loss_grid": list(LOSS_GRID),
                "lots": lots, "formula_train": formula,
                "formula_validation": validation,
                "erlang_rule_validation": erlang_validation,
                "k_star_and_ppr_by_loss": ppr_by_loss,
                "caveats": [
                    "设施成本为 P26 迁移情景（75.30 TWD/带枪位·日，FX UNVERIFIED，寿命10年情景）",
                    "未服务事件的社会损失 L 未知；k*(L) 是条件解，不是真实最优桩数",
                    "车流暖启动为 Lead 近似（残余停留分布），未用场站初始真实车型构成",
                    "服务水平规则 k_alpha 是物理量，不依赖货币成本",
                ]}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2, default=str)
    print("wrote", args.out)
    print("lot N usable A_erlang k5 k10 k20 L*=break-even(0->1,1->2)")
    for lot, record in lots.items():
        be = record["break_even_loss_per_unserved"]
        print("%s %s %s %s %s %s %s | %s %s" % (lot, record["n_spaces"], record.get("usable"),
              record.get("observed_load_erlang"), record["service_level_k"].get("0.05"),
              record["service_level_k"].get("0.1"), record["service_level_k"].get("0.2"),
              round(be.get(0), 2) if be.get(0) is not None else None,
              round(be.get(1), 2) if be.get(1) is not None else None))
    print("formula:", json.dumps(formula, ensure_ascii=False))
    print("validation:", json.dumps(validation, ensure_ascii=False)[:600])
    print("erlang:", json.dumps(erlang_validation, ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
