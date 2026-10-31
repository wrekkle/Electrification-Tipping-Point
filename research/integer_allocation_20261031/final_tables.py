"""汇总报告表格：整数规则、公式基准、样本外误差、服务后悔、盈亏平衡（Lead）。"""
from __future__ import annotations
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from apps.parking_lab.workbench import allocation as alloc  # noqa: E402

LOSS_GRID = (5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0)
ALPHAS = (0.05, 0.10, 0.20)


def mean_curve(curve):
    by_k = {}
    for row in curve["rows"]:
        bucket = by_k.setdefault(int(row["k"]), {"facility": [], "unmet": [], "ev": [], "req": [],
                                                "delivered": [], "initial_occ": [], "occ_rate": []})
        if row.get("facility_cost") is not None:
            bucket["facility"].append(row["facility_cost"])
        if row.get("unmet_no_connector_events") is not None:
            bucket["unmet"].append(row["unmet_no_connector_events"])
        if row.get("ev_arrivals") is not None:
            bucket["ev"].append(row["ev_arrivals"])
        if row.get("charge_requests") is not None:
            bucket["req"].append(row["charge_requests"])
        if row.get("delivered_energy_kwh") is not None:
            bucket["delivered"].append(row["delivered_energy_kwh"])
        if row.get("initial_occupancy_vehicles") is not None:
            bucket["initial_occ"].append(row["initial_occupancy_vehicles"])
        if row.get("mean_occupancy_rate") is not None:
            bucket["occ_rate"].append(row["mean_occupancy_rate"])
    out = {}
    for k, bucket in by_k.items():
        out[k] = {key: (sum(values) / len(values) if values else None) for key, values in bucket.items()}
    return out


def service_k(by_k, alpha):
    base = by_k.get(0, {}).get("unmet")
    if base is None:
        return None
    if base <= 0:
        return 0
    for k in sorted(by_k):
        if by_k[k].get("unmet") is not None and by_k[k]["unmet"] <= alpha * base:
            return k
    return max(by_k)


def k_star(by_k, loss):
    scored = {k: v["facility"] + loss * v["unmet"] for k, v in by_k.items()
              if v.get("facility") is not None and v.get("unmet") is not None}
    if not scored:
        return None
    best = min(scored.values())
    return min(k for k, value in scored.items() if value <= best + 1e-9)


def fit_z(points, key):
    num = den = 0.0
    for x, k in points:
        if x <= 0:
            continue
        num += math.sqrt(x) * (k - x)
        den += x
    return (num / den) if den else None


def predict_z(x, z):
    return int(math.ceil(x + z * math.sqrt(max(x, 0.0)) - 1e-12))


def main():
    curve = json.load(open(os.path.join(OUT, "cost_curve_pi0_k40.json"), encoding="utf-8"))
    params = json.load(open(os.path.join(ROOT, "research", "traffic_generation_20261031",
                                         "fitted_parameters.json"), encoding="utf-8"))
    per = {}
    for row in curve["rows"]:
        per.setdefault(row["lot_id"], []).append(row)
    lot_meta = {row["lot_id"]: row for row in params["per_lot"]}
    lots = {}
    for lot_id, rows in per.items():
        by_k = mean_curve({"rows": rows})
        info = lot_meta.get(lot_id, {})
        dwell = info.get("dwell_dist", {}).get("components") or []
        dwell_mean = sum(c.get("mean_min", 0.0) * c.get("weight", 1.0) for c in dwell) if dwell else None
        ev_arrivals = by_k.get(1, {}).get("ev")
        init_occ = by_k.get(1, {}).get("initial_occ") or 0.0
        p_ev = 0.30  # 生成器默认情景（ev.p_ev_default），非识别值
        ev_stock = (init_occ * p_ev + (ev_arrivals or 0) * min(dwell_mean or 0.0, 1440.0) / 1440.0) if dwell_mean else None
        lots[lot_id] = {
            "n_spaces": int(rows[0]["n_spaces"]), "split": info.get("fit_split"), "usable": info.get("usable"),
            "observed_connectors": info.get("n_connectors"),
            "mean_occupancy_vehicles": info.get("mean_occupancy_vehicles"),
            "ev_arrivals_per_day": ev_arrivals, "charge_requests_per_day": by_k.get(1, {}).get("req"),
            "ev_stock_approx": ev_stock, "dwell_mean_min": dwell_mean,
            "k_5": service_k(by_k, 0.05), "k_10": service_k(by_k, 0.10), "k_20": service_k(by_k, 0.20),
            "k_star": {str(loss): k_star(by_k, loss) for loss in LOSS_GRID},
            "mean_occupancy_rate_sim": by_k.get(1, {}).get("occ_rate"),
            "unmet_at_k5": by_k.get(service_k(by_k, 0.05) or 0, {}).get("unmet"),
            "delivered_kwh_at_k5": by_k.get(service_k(by_k, 0.05) or 0, {}).get("delivered"),
            "curve": by_k,
        }
    # 公式基准
    train = [(lots[lot]["ev_stock_approx"], lots[lot]["k_5"], lot) for lot in lots
             if lots[lot]["usable"] and lots[lot]["split"] == "train" and lots[lot]["k_5"] is not None
             and lots[lot].get("ev_stock_approx")]
    validation = [(lots[lot]["ev_stock_approx"], lots[lot]["k_5"], lot) for lot in lots
                  if lots[lot]["usable"] and lots[lot]["split"] == "validation" and lots[lot]["k_5"] is not None
                  and lots[lot].get("ev_stock_approx")]
    z_ev = fit_z([(x, k) for x, k, _ in train], "ev")
    errors_ev = [(abs(predict_z(x, z_ev) - k), lot) for x, k, lot in validation] if z_ev else []
    # 负荷型规则（A=观测充电占用 Erlang）
    load_path = os.path.join(OUT, "observed_charging_load.json")
    load = json.load(open(load_path, encoding="utf-8"))["lots"] if os.path.exists(load_path) else {}
    train_load = [(load[lot]["observed_load_erlang"], lots[lot]["k_5"]) for lot in lots
                  if lots[lot]["usable"] and lots[lot]["split"] == "train" and lots[lot]["k_5"] is not None
                  and (load.get(lot) or {}).get("observed_load_erlang")]
    val_load = [(load[lot]["observed_load_erlang"], lots[lot]["k_5"], lot) for lot in lots
                if lots[lot]["usable"] and lots[lot]["split"] == "validation" and lots[lot]["k_5"] is not None
                and (load.get(lot) or {}).get("observed_load_erlang")]
    z_load = fit_z(train_load, "load")
    errors_load = [(abs(predict_z(x, z_load) - k), lot) for x, k, lot in val_load] if z_load else []
    # 解析规则：π0 下带枪位被所有电车按停留时长占用，connector 占位负荷 A_conn = p_ev*lambda_bar*E[min(dwell,1440)]/60；
    # 阻塞概率 B(A_conn, k) 即充电车到店无枪概率。p_ev 为情景值（未识别），故 k 随 p_ev 变化。
    analytic = {}
    for alpha in (0.05, 0.10):
        rows = []
        for lot in lots:
            info = lot_meta.get(lot, {})
            lam = float(info.get("lambda_bar_veh_per_hour") or 0.0)
            dwell = lots[lot].get("dwell_mean_min") or 0.0
            p_ev = 0.30
            offered = p_ev * lam * min(dwell, 1440.0) / 60.0
            servers = alloc.min_servers_for_blocking(offered, alpha, max(1, int(offered * 4 + 20))) if offered > 0 else 0
            if lots[lot]["k_5"] is None:
                continue
            rows.append({"lot": lot, "usable": lots[lot]["usable"], "split": lots[lot]["split"],
                         "lambda_ev_per_hour": p_ev * lam, "offered_load_erlang": offered,
                         "k_analytic": servers, "k_sim_5": lots[lot]["k_5"]})
        analytic["alpha_%.2f" % alpha] = rows


    def analytic_errors(rows):
        usable = [r for r in rows if r["usable"] and r["k_analytic"] is not None and r["k_sim_5"] is not None]
        errors = [abs(r["k_analytic"] - r["k_sim_5"]) for r in usable]
        return {"n": len(usable), "mae": sum(errors) / len(errors) if errors else None,
                "max": max(errors) if errors else None,
                "ratios": [round(r["k_sim_5"] / r["k_analytic"], 2) if r["k_analytic"] else None for r in usable]}


    erlang_errors = []
    for x, k, lot in val_load:
        servers = alloc.min_servers_for_blocking(x, 0.10, max(1, int(x * 10 + 10))) if x > 0 else 0
        erlang_errors.append((abs((servers or 0) - k), lot))
    def summarize(errors):
        values = [e[0] for e in errors]
        return {"n": len(values), "mae": sum(values) / len(values) if values else None,
                "max": max(values) if values else None,
                "detail": [{"lot": lot, "abs_error": err} for err, lot in errors]}
    formula = {"ev_stock_rule": {"form": "k = ceil(E_ev + z*sqrt(E_ev))", "z": z_ev,
                                 "train_n": len(train), "validation": summarize(errors_ev)},
               "load_rule": {"form": "k = ceil(A + z*sqrt(A))", "z": z_load,
                             "train_n": len(train_load), "validation": summarize(errors_load)},
               "erlang_rule": {"form": "min k: B(A,k) <= 0.10", "validation": summarize(erlang_errors)},
               "connector_occupancy_rule": {
                   "form": "A = p_ev*lambda_bar*E[min(dwell,1440)]/60; k = min{k: B(A,k)<=alpha}",
                   "p_ev_scenario": 0.30,
                   "alpha_0.05": analytic_errors(analytic["alpha_0.05"]),
                   "alpha_0.10": analytic_errors(analytic["alpha_0.10"]),
                   "rows_alpha_0.05": analytic["alpha_0.05"]}}
    # 聚合
    usable_lots = [lot for lot in lots if lots[lot]["usable"]]
    k5_values = [lots[lot]["k_5"] for lot in usable_lots if lots[lot]["k_5"] is not None]
    ppr = [lots[lot]["k_5"] / lots[lot]["n_spaces"] for lot in usable_lots if lots[lot]["k_5"]]
    observed_sum = sum(int(lots[lot]["observed_connectors"] or 0) for lot in lots)
    report = {"generated_from": "outputs/cost_curve_pi0_k40.json + fitted_parameters.json",
              "lots": {lot: {key: value for key, value in record.items() if key != "curve"}
                       for lot, record in lots.items()},
              "formula_benchmark": formula,
              "aggregates": {
                  "n_lots": len(lots), "n_usable": len(usable_lots),
                  "k5_median": sorted(k5_values)[len(k5_values)//2] if k5_values else None,
                  "k5_values": k5_values, "ppr_k5_values": ppr,
                  "observed_connectors_sum": observed_sum,
                  "observed_connectors_median": sorted([lots[lot]["observed_connectors"] or 0 for lot in lots])[len(lots)//2],
                  "k_star_median_by_loss": {str(loss): sorted([lots[lot]["k_star"][str(loss)] for lot in usable_lots
                                                              if lots[lot]["k_star"].get(str(loss)) is not None])[max(0, len(usable_lots)//2 - 1)]
                                              for loss in LOSS_GRID},
              }}
    path = os.path.join(OUT, "final_tables.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
    print("wrote", path)
    print("lot N split usable obs_conn A_ev k5 k10 PPR5 k*(10) k*(100)")
    for lot in sorted(lots):
        rec = lots[lot]
        print("%s %d %s %s %s %s %s %s %s %s %s" % (lot, rec["n_spaces"], rec["split"], rec["usable"],
              rec["observed_connectors"], rec["ev_arrivals_per_day"], rec["k_5"], rec["k_10"],
              round((rec["k_5"] or 0) / rec["n_spaces"], 3), rec["k_star"].get("10.0"), rec["k_star"].get("100.0")))
    print("aggregates", json.dumps(report["aggregates"], ensure_ascii=False)[:800])
    print("formula", json.dumps(formula, ensure_ascii=False)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
