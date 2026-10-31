"""第二轮复算分析：整数配桩服务水平 / 成本-代理 / Erlang 解析 / 样本外验证。

只读 run_cost_curve.py 产出的曲线 JSON；不覆盖任何旧结果。规则：
- 服务水平一律走 allocation.service_level_k；非 achieved 的 k=None，不进均值/MAE/拟合；
- 成本分列：C_proxy(k)=facility_cost(k)+L*U(k)（代理）与完整社会成本（cost_total，仅当 complete）；
- 盈亏平衡只在存在 U(k)<U(0) 的候选时给出，ΔU<=0 不给假平衡点；
- 解析对照用同一 α 和同一占位口径（dwell），load 由拟合参数独立重算（不复用曲线里的负载）。
"""
from __future__ import annotations
import argparse, hashlib, json, math, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from apps.parking_lab.workbench import allocation as alloc  # noqa: E402

SERVICE_KEY = "unmet_no_connector_events"
ALPHAS = (0.02, 0.05, 0.10, 0.20)
LOSS_GRID = (10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0)
SQRT2 = math.sqrt(2.0)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _lognormal_cdf(x, mu, sigma):
    if x <= 0:
        return 0.0
    return 0.5 * math.erfc(-(math.log(x) - mu) / (sigma * SQRT2))


def expected_min_dwell(dwell_dist, horizon=1440.0, steps=16000):
    """E[min(D, horizon)]：对混合对数正态的生存函数数值积分（梯形法）。不引用拟合 mean_min。"""
    comps = dwell_dist.get("components") or []
    total = 0.0
    for comp in comps:
        mu, sigma = comp["params"][:2]
        weight = float(comp["weight"])
        width = horizon / steps
        acc = 0.0
        for index in range(steps):
            low = index * width
            high = low + width
            acc += 0.5 * ((1.0 - _lognormal_cdf(low, mu, sigma))
                          + (1.0 - _lognormal_cdf(high, mu, sigma))) * width
        total += weight * acc
    return total


def analytic_k(load_erlang, alpha, hard_max):
    for count in range(1, int(hard_max) + 1):
        if alloc.erlang_b(load_erlang, count) <= alpha:
            return count
    return None


def group_curve(curve):
    groups = {}
    for row in curve["rows"]:
        groups.setdefault((row["lot_id"], int(row["seed"])), {})[int(row["k"])] = row
    return groups


def check_curve(curve, label):
    issues = []
    groups = group_curve(curve)
    for (lot, seed), by_k in sorted(groups.items()):
        ks = sorted(by_k)
        if 0 not in by_k:
            issues.append(f"{label}:{lot}:{seed} 缺 k=0 基线")
            continue
        if ks != list(range(len(ks))):
            issues.append(f"{label}:{lot}:{seed} k 不连续")
        hashes = {by_k[k]["demand_hash"] for k in ks}
        if len(hashes) != 1:
            issues.append(f"{label}:{lot}:{seed} 需求哈希随 k 变化：{sorted(hashes)[:3]}")
        p_evs = {by_k[k].get("p_ev_used") for k in ks}
        if len(p_evs) != 1:
            issues.append(f"{label}:{lot}:{seed} p_ev 随 k 变化：{p_evs}")
        zero = by_k[0]
        if zero.get("facility_cost") != 0.0:
            issues.append(f"{label}:{lot}:{seed} k=0 facility={zero.get('facility_cost')!r} 应为 0.0")
        if "device_capital" not in (zero.get("facility_not_applicable") or []):
            issues.append(f"{label}:{lot}:{seed} k=0 未标 not_applicable")
        for k in ks:
            f = by_k[k].get("facility_cost")
            if f is not None and not isinstance(f, (int, float)):
                issues.append(f"{label}:{lot}:{seed}:k={k} facility 非数值")
    return issues


def lot_costs(by_k, loss):
    costs = {}
    for k, row in by_k.items():
        facility = row.get("facility_cost")
        unmet = row.get(SERVICE_KEY)
        if facility is None or unmet is None:
            costs[k] = None
        else:
            costs[k] = {"total": facility + loss * unmet, "facility": facility, "unmet": unmet}
    return costs


def break_even(by_k):
    base = by_k[0].get(SERVICE_KEY)
    facility0 = by_k[0].get("facility_cost") or 0.0
    candidates = []
    for k in sorted(by_k):
        if k == 0:
            continue
        unmet = by_k[k].get(SERVICE_KEY)
        facility = by_k[k].get("facility_cost")
        if unmet is None or facility is None or base is None or unmet >= base:
            continue
        delta_u = base - unmet
        delta_c = facility - facility0
        if delta_u > 0:
            candidates.append({"k": k, "loss_per_unserved": delta_c / delta_u,
                               "delta_u": delta_u, "delta_cost": delta_c})
    if not candidates:
        return {"possible": False, "min_loss_per_unserved": None,
                "note": "没有 k 使 U(k)<U(0)：代理成本单调递增，不存在假平衡点"}
    best = min(candidates, key=lambda item: item["loss_per_unserved"])
    return {"possible": True, "min_loss_per_unserved": best["loss_per_unserved"],
            "k": best["k"], "candidates": candidates}


def fit_sqrt(points):
    """k = sqrt(a*load) 过原点：a = Σ(load*k^2)/Σ(load^2)。"""
    num = sum(load * k * k for load, k in points)
    den = sum(load * load for load, _ in points)
    a = num / den if den > 0 else 0.0
    return {"a": a, "predict": lambda load: math.sqrt(max(a * load, 0.0))}


def mae(points, predict):
    if not points:
        return None, 0
    errors = [abs(predict(load) - k) for load, k in points]
    return sum(errors) / len(errors), len(points)


def analyse_curve(curve, params, load_doc, label, usable_lots):
    groups = group_curve(curve)
    lots_meta = {}
    for entry in params.get("per_lot") or []:
        lots_meta[entry["lot_id"]] = entry
    horizon = float((params.get("generator") or {}).get("horizon_min", 1440))
    out = {"label": label, "rows": len(curve.get("rows") or []),
           "issues": check_curve(curve, label), "lots": {}}
    for (lot, seed), by_k in sorted(groups.items()):
        meta = lots_meta.get(lot) or {}
        n_spaces = int(by_k[0]["n_spaces"])
        hard_max = min(n_spaces, max(by_k))
        k0_unmet = by_k[0].get(SERVICE_KEY)
        record = {"seed": seed, "n_spaces": n_spaces, "k_hard_max": hard_max,
                  "unmet_k0": k0_unmet, "p_ev": by_k[0].get("p_ev_used"),
                  "q_need": by_k[0].get("q_need_used"),
                  "observed_ratio_z": by_k[0].get("observed_ratio_z"),
                  "service": {}, "break_even": break_even(by_k)}
        values = {k: row.get(SERVICE_KEY) for k, row in by_k.items()}
        for alpha in ALPHAS:
            status = alloc.service_level_k(values, alpha, k_hard_max=hard_max)
            record["service"][str(alpha)] = status
        for loss in LOSS_GRID:
            costs = lot_costs(by_k, loss)
            usable_costs = {k: v["total"] for k, v in costs.items() if v is not None}
            if not usable_costs:
                record["k_star_loss_" + str(loss)] = None
                continue
            best_k = min(usable_costs, key=lambda k: (usable_costs[k], k))
            record["k_star_loss_" + str(loss)] = best_k
        # 代理成本：L=100 的分解
        costs = lot_costs(by_k, 100.0)
        record["c_proxy_100"] = {str(k): costs[k] for k in costs}
        wells = meta.get("dwell_dist")
        if wells:
            e_min = expected_min_dwell(wells, horizon)
            p_ev = by_k[0].get("p_ev_used") or 0.0
            lam = float(meta.get("lambda_bar_veh_per_hour") or 0.0)
            load_erlang = p_ev * lam * e_min / 60.0
            record["model_load_erlang"] = load_erlang
            record["e_min_dwell_min"] = e_min
            record["analytic_service"] = {
                str(alpha): {"k": analytic_k(load_erlang, alpha, hard_max),
                             "status": ("achieved" if analytic_k(load_erlang, alpha, hard_max) is not None
                                        else "infeasible_upper_bound")}
                for alpha in ALPHAS}
        out["lots"].setdefault(lot, {})[str(seed)] = record
    # 场站级汇总：仅 usable 场站、仅 achieved 的 seed 进入中位数
    summary = {}
    for lot, seeds in out["lots"].items():
        entry = lots_meta.get(lot) or {}
        row = {"n_spaces": entry.get("n_spaces"), "split": entry.get("fit_split"),
               "usable": entry.get("usable"), "seeds": len(seeds), "median": {}}
        for alpha in ALPHAS:
            key = str(alpha)
            achieved = [rec["service"][key]["k"] for rec in seeds.values()
                        if rec["service"][key]["status"] == "achieved"]
            statuses = [rec["service"][key]["status"] for rec in seeds.values()]
            row["median"][key] = {"k_median": (statistics.median(achieved) if achieved else None),
                                  "n_achieved": len(achieved), "statuses": statuses,
                                  "boundary": any(rec["service"][key].get("boundary") for rec in seeds.values())}
        row["analytic"] = {str(alpha): sorted({rec.get("analytic_service", {}).get(str(alpha), {}).get("k")
                                               for rec in seeds.values()} - {None}) or None
                           for alpha in ALPHAS}
        row["break_even_min"] = [rec["break_even"].get("min_loss_per_unserved") for rec in seeds.values()]
        row["k_star_100"] = sorted({rec.get("k_star_loss_100.0") for rec in seeds.values()} - {None}) or None
        summary[lot] = row
    out["summary"] = summary
    # 拟合与样本外验证（模型负载、usable + achieved 才进样本）
    train_points, valid_points, excluded = [], [], []
    for lot, row in summary.items():
        if not row.get("usable"):
            excluded.append({"lot": lot, "why": "unusable_lot"})
            continue
        k5 = row["median"]["0.05"]["k_median"]
        model_load = None
        for rec in out["lots"][lot].values():
            if rec.get("model_load_erlang") is not None:
                model_load = rec["model_load_erlang"]
                break
        observed = ((load_doc.get("lots") or {}).get(lot) or {}).get("observed_load_erlang")
        target = {"lot": lot, "k5": k5, "model_load": model_load, "observed_load": observed,
                  "split": row.get("split")}
        if k5 is None or model_load is None:
            excluded.append({"lot": lot, "why": "k5_not_achieved_or_no_load", "detail": target})
        elif row.get("split") == "train":
            train_points.append((model_load, k5, observed, lot))
            target["used"] = True
        elif row.get("split") == "validation":
            valid_points.append((model_load, k5, observed, lot))
            target["used"] = True
        else:
            excluded.append({"lot": lot, "why": "no_split", "detail": target})
    fits = {}
    if train_points:
        formula = fit_sqrt([(load, k) for load, k, _, _ in train_points])
        train_mae, n_train = mae([(load, k) for load, k, _, _ in train_points], formula["predict"])
        valid_mae, n_valid = mae([(load, k) for load, k, _, _ in valid_points], formula["predict"])
        obs_train = [(obs, k) for _, k, obs, _ in train_points if obs]
        obs_valid = [(obs, k) for _, k, obs, _ in valid_points if obs]
        obs_formula = fit_sqrt(obs_train) if obs_train else None
        fits = {"model_load": {"a": formula["a"], "train_mae": train_mae, "n_train": n_train,
                               "validation_mae": valid_mae, "n_validation": n_valid,
                               "train_mae_old_target": None},
                "observed_load": ({"a": obs_formula["a"],
                                   "train_mae": mae(obs_train, obs_formula["predict"])[0],
                                   "n_train": len(obs_train),
                                   "validation_mae": mae(obs_valid, obs_formula["predict"])[0],
                                   "n_validation": len(obs_valid)} if obs_formula else None),
                "excluded": excluded}
    out["fits"] = fits
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="第二轮整数配桩复算")
    parser.add_argument("--curve", action="append", required=True,
                        help="LABEL=PATH，可重复（同 α/成本口径对比不同情景）")
    parser.add_argument("--params", required=True)
    parser.add_argument("--load", default="research/integer_allocation_20261031/outputs/observed_charging_load.json")
    parser.add_argument("--out", default="research/round2_20261031/results/analysis_v2.json")
    args = parser.parse_args(argv)
    with open(args.params, encoding="utf-8") as handle:
        params = json.load(handle)
    with open(args.load, encoding="utf-8") as handle:
        load_doc = json.load(handle)
    curves = {}
    for spec in args.curve:
        label, path = spec.split("=", 1)
        with open(path, encoding="utf-8") as handle:
            curve = json.load(handle)
        curves[label] = (path, curve)
    document = {"meta": {"python": sys.version.split()[0], "alphas": list(ALPHAS),
                         "loss_grid": list(LOSS_GRID), "service_key": SERVICE_KEY,
                         "params_sha256": sha256_file(args.params),
                         "source_sha256": {label: sha256_file(path) for label, (path, _) in curves.items()},
                         "cost_rule": "C_proxy=facility_cost(k)+L*U(k)；facility_cost 来自 costs.facility_cost",
                         "service_rule": "allocation.service_level_k；非 achieved 的 k 不进任何统计"},
                "curves": {}}
    for label, (path, curve) in curves.items():
        document["curves"][label] = analyse_curve(curve, params, load_doc, label, None)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1, default=str)
    for label, result in document["curves"].items():
        print("==", label, "issues:", result["issues"][:4], "lots:", len(result["lots"]))
        for lot, row in sorted(result["summary"].items()):
            if not row.get("usable"):
                continue
            print(lot, row["split"], "N=%s" % row["n_spaces"],
                  "k5=", row["median"]["0.05"]["k_median"],
                  "statuses=", row["median"]["0.05"]["statuses"],
                  "analytic5=", row["analytic"]["0.05"],
                  "be=", [None if x is None else round(x, 1) for x in row["break_even_min"]],
                  "k*100=", row["k_star_100"])
        print("fits:", json.dumps(result["fits"].get("model_load"), ensure_ascii=False),
              "excluded:", len(result["fits"].get("excluded") or []))
    print(json.dumps({"out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
