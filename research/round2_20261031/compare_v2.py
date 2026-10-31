"""第二轮实验对比：规则、功率、窗口与 p_EV 情景（配对比较，不混读旧 JSON）。

只做比较，不重算模型；服务水平一律 allocation.service_level_k；非 achieved 不进比较。
输出 results/experiments_v2.json。
"""
from __future__ import annotations
import argparse, json, statistics, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from apps.parking_lab.workbench import allocation as alloc  # noqa: E402

SERVICE_KEY = "unmet_no_connector_events"
RULES = ("dedicated_by_type", "full_open_ice_first", "predictive_shared_ice_first")
RULE_KEYS = {"dedicated_by_type": "pi0", "full_open_ice_first": "pi1",
             "predictive_shared_ice_first": "pi2"}


def load_curve(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def index(curve):
    groups = {}
    for row in curve["rows"]:
        groups.setdefault((row["lot_id"], int(row["seed"])), {})[int(row["k"])] = row
    return groups


def k5(by_k, n_spaces):
    values = {k: row.get(SERVICE_KEY) for k, row in by_k.items()}
    return alloc.service_level_k(values, 0.05,
                                 k_hard_max=min(int(n_spaces), max(by_k)))


def proxy(by_k, k, loss=100.0):
    row = by_k.get(k)
    if not row or row.get("facility_cost") is None or row.get(SERVICE_KEY) is None:
        return None
    return row["facility_cost"] + loss * row[SERVICE_KEY]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--pi0", required=True)
    parser.add_argument("--pi1", required=True)
    parser.add_argument("--pi2", required=True)
    parser.add_argument("--kw3p5", required=True)
    parser.add_argument("--kw22", required=True)
    parser.add_argument("--h720", required=True)
    parser.add_argument("--pev020", required=True)
    parser.add_argument("--pev050", required=True)
    parser.add_argument("--out", default="research/round2_20261031/results/experiments_v2.json")
    args = parser.parse_args(argv)
    curves = {name: index(load_curve(getattr(args, name)))
              for name in ("pi0", "pi1", "pi2", "kw3p5", "kw22", "h720", "pev020", "pev050")}
    # 规则/功率/窗口/p_EV 曲线是 seeds 1,2；pi0 基准有 seeds 1,2,3，比较时只保留共同 seed
    seeds_common = {seed for (_, seed) in curves["pi1"]}
    curves["pi0"] = {key: value for key, value in curves["pi0"].items() if key[1] in seeds_common}
    document = {"meta": {"service_key": SERVICE_KEY, "alpha": 0.05,
                         "note": "同一 (lot,seed) 的 demand_hash 在不同规则/功率下必须一致；窗口截断 h720 除外"},
                "traffic_pairing": {}, "rules": {}, "power": {}, "window": {}, "pev": {}}

    # 1) 配对检验：规则/功率不改变需求（除窗口截断与 p_EV 情景）
    pairing = document["traffic_pairing"]
    for lot_seed, base in curves["pi0"].items():
        hashes = {}
        for name in ("pi0", "pi1", "pi2", "kw3p5", "kw22"):
            rows = curves[name].get(lot_seed)
            if rows:
                hashes[name] = sorted({row["demand_hash"] for row in rows.values()})
        if len({tuple(value) for value in hashes.values()}) > 1:
            pairing.setdefault("mismatch", []).append({str(lot_seed): hashes})
    pairing["checked_lot_seed"] = len(curves["pi0"])
    pairing["mismatch_count"] = len(pairing.get("mismatch") or [])

    # 2) 规则对比：同一流量、每个规则各自重选 k；固定 k 下的 U 配对差
    fixed_k = {}
    for lot_seed, base in curves["pi0"].items():
        lot, seed = lot_seed
        n_spaces = base[0]["n_spaces"]
        picks = {}
        for name in ("pi0", "pi1", "pi2"):
            rows = curves[name].get(lot_seed)
            if not rows:
                continue
            status = k5(rows, n_spaces)
            picks[name] = {"status": status["status"], "k": status["k"],
                           "c_proxy_at_k": proxy(rows, status["k"]) if status["k"] is not None else None}
        document["rules"].setdefault(lot, {})[str(seed)] = picks
        for k in sorted(base):
            u0 = base[k].get(SERVICE_KEY)
            for name in ("pi1", "pi2"):
                rows = curves[name].get(lot_seed)
                if not rows or k not in rows:
                    continue
                u = rows[k].get(SERVICE_KEY)
                if u0 is None or u is None or u0 == u:
                    continue
                fixed_k.setdefault(name, {"better": 0, "worse": 0, "pairs": []})
                entry = fixed_k[name]
                if u < u0:
                    entry["better"] += 1
                else:
                    entry["worse"] += 1
                entry["pairs"].append({"lot": lot, "seed": seed, "k": k, "u_pi0": u0, "u_rule": u})
    # 每场站 k5 中位数对比
    rule_summary = {}
    for lot, seeds in document["rules"].items():
        row = {}
        for name in RULES:
            key = RULE_KEYS[name]
            achieved = [rec[key]["k"] for rec in seeds.values()
                        if rec.get(key, {}).get("status") == "achieved"]
            statuses = [rec.get(key, {}).get("status") for rec in seeds.values()]
            row[name] = {"k5_median": statistics.median(achieved) if achieved else None,
                         "n_achieved": len(achieved), "statuses": statuses,
                         "c_proxy_at_k5": [rec[key]["c_proxy_at_k"] for rec in seeds.values()
                                           if rec.get(key, {}).get("k") is not None]}
        rule_summary[lot] = row
    document["rules_summary"] = rule_summary
    document["rules_fixed_k"] = {name: {key: value for key, value in entry.items() if key != "pairs"}
                                 for name, entry in fixed_k.items()}

    # 3) 功率：k5 与功率瓶颈（充电功率不足、未在停留内交付）
    for lot_seed, base in curves["pi0"].items():
        lot, seed = lot_seed
        n_spaces = base[0]["n_spaces"]
        row = {}
        for name, label in (("pi0", "kw7"), ("kw3p5", "kw3.5"), ("kw22", "kw22")):
            rows = curves[name].get(lot_seed)
            if not rows:
                continue
            status = k5(rows, n_spaces)
            best = status["k"]
            metrics = base.get(best if best is not None else 0) or {}
            row[label] = {"status": status["status"], "k5": status["k"],
                          "shortfall_events": (rows.get(best if best is not None else 0) or {}).get("power_dwell_shortfall_events"),
                          "delivered_ratio": (lambda b, d: (b / d) if b is not None and d else None)(
                              (rows.get(best if best is not None else 0) or {}).get("delivered_energy_kwh"),
                              (rows.get(best if best is not None else 0) or {}).get("demand_energy_kwh_total"))}
        document["power"].setdefault(lot, {})[str(seed)] = row

    # 4) 窗口：720 vs 1440（同规则/功率/p_EV；标注为窗口重采样）
    for lot_seed, base in curves["pi0"].items():
        lot, seed = lot_seed
        rows720 = curves["h720"].get(lot_seed)
        if not rows720:
            continue
        n_spaces = base[0]["n_spaces"]
        status_1440 = k5(base, n_spaces)
        status_720 = k5(rows720, n_spaces)
        document["window"].setdefault(lot, {})[str(seed)] = {
            "h1440": {"status": status_1440["status"], "k5": status_1440["k"],
                      "u0": base[0].get(SERVICE_KEY)},
            "h720": {"status": status_720["status"], "k5": status_720["k"],
                     "u0": rows720[0].get(SERVICE_KEY)}}

    # 5) p_EV 情景：同一批 9 场站，比较 k5 与占位负荷（p_EV 非识别，只作情景）
    for lot_seed, base in curves["pev020"].items():
        lot, seed = lot_seed
        rows030 = curves["pi0"].get(lot_seed)
        rows050 = curves["pev050"].get(lot_seed)
        if not rows030:
            continue
        n_spaces = base[0]["n_spaces"]
        entry = {}
        for label, rows in (("p_ev_0.20", base), ("p_ev_0.30", rows030), ("p_ev_0.50", rows050)):
            if not rows:
                continue
            status = k5(rows, n_spaces)
            entry[label] = {"status": status["status"], "k5": status["k"],
                            "p_ev": rows[0].get("p_ev_used"), "q_need": rows[0].get("q_need_used")}
        document["pev"].setdefault(lot, {})[str(seed)] = entry

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1, default=str)
    print(json.dumps({"pairing_mismatch": pairing["mismatch_count"],
                      "fixed_k": document["rules_fixed_k"],
                      "out": args.out}, ensure_ascii=False))
    for lot, row in sorted(rule_summary.items()):
        print(lot, {name: (row[name]["k5_median"], row[name]["n_achieved"]) for name in RULES})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
