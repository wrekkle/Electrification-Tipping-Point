"""R4 机制小算例：共享是否省枪（可枚举、可复跑）。

模型（与 workbench 正式规则同构的最小离散模型，非工作台仿真复现）：
- 1 桩 = 1 枪 = 1 带枪位，charging_bays = chargers = k，总车位 N 固定（与 round3 run_cost_curve 一致）。
- 车道按整分钟到达/离场；到达顺序即处理顺序；无排队、无绕行、无能量/功率、无挪车。
- π0（dedicated_by_type）：电车优先带枪位，无空带枪位时允许停普通位；油车只能用普通位。
- π1（full_open_ice_first）：电车同 π0；油车优先普通位，普通位不足时可用带枪位。
- 容量型未服务：需要充电的电车未进入带枪位（被拒或停普通位）即计一次未服务；
  停车失败：未被准入。分母为窗口内外生到访。三约束均 ≤5%。
- 目标量：k0、k1 分别为两规则满足三约束的最小整数 k；Δk = k0 − k1。

同时枚举两个变体，用来判断"共享不省枪"是机制结果还是规则设定结果：
- variant_strict_pi0：把 π0 改为"电车只能停带枪位（无回落）"——检验回落规则是否关键；
- variant_fixed_zone：charging_bays 固定为 3（不随 k 增长）——检验"每加一枪就挤占一个普通位"是否关键。
"""
import json
import os
import random
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ALPHA = 0.05
K_MAX = None  # 由 N 决定


def make_instance(seed, n, ev_share, q_need, dwell_ev, dwell_ice, rate_per_slot,
                  ev_offset, ice_offset):
    rng = random.Random(seed * 1000 + n)
    arrivals = []
    for t in range(24):
        for kind, share, dwell, offset in (("ev", ev_share, dwell_ev, ev_offset),
                                           ("ice", 1 - ev_share, dwell_ice, ice_offset)):
            lam = rate_per_slot * share
            count = int(lam) + (1 if rng.random() < (lam - int(lam)) else 0)
            for _ in range(count):
                arrive = t + 0.25 * offset + rng.random() * 0.4
                needs = kind == "ev" and rng.random() < q_need
                arrivals.append({"t": arrive, "is_ev": kind == "ev", "needs": needs,
                                 "dwell": dwell + rng.randint(0, 2)})
    arrivals.sort(key=lambda a: a["t"])
    return {"seed": seed, "n": n, "ev_share": ev_share, "q_need": q_need,
            "dwell_ev": dwell_ev, "dwell_ice": dwell_ice,
            "rate_per_slot": rate_per_slot, "ev_offset": ev_offset, "ice_offset": ice_offset,
            "arrivals": arrivals}


def candidates(k, n, is_ev, needs, rule, variant):
    zone = k if variant != "fixed_zone" else min(3, n)  # fixed_zone：充电区固定 3 位
    equipped = list(range(min(k, zone)))
    designated = list(range(min(k, zone), zone))
    ordinary = list(range(zone, n))
    if is_ev:
        if rule == "pi0" and variant == "strict_pi0":
            return equipped  # 变体：π0 电车不允许回落普通位
        return equipped + designated + ordinary
    # ICE：π0 只能用普通位；π1 普通位不足时可用充电区
    if rule == "pi0":
        return ordinary
    return ordinary + equipped + designated


def simulate(instance, k, rule, variant="base"):
    n = instance["n"]
    occupied = {}
    busy = set()
    counters = {"charge_requests": 0, "cap_unmet": 0, "ev_visits": 0, "ev_fail": 0,
                "ice_visits": 0, "ice_fail": 0}
    events = sorted(instance["arrivals"], key=lambda a: (a["t"], a["is_ev"]))
    # 时间推进：按到达时刻逐车处理；离场用 dwell 计算，每处理一车先释放已离场者
    for a in events:
        t = a["t"]
        for bay in [b for b, dep in occupied.items() if dep <= t + 1e-12]:
            del occupied[bay]
        is_ev, needs = a["is_ev"], a["needs"]
        if is_ev:
            counters["ev_visits"] += 1
            if needs:
                counters["charge_requests"] += 1
        else:
            counters["ice_visits"] += 1
        free = [b for b in range(n) if b not in occupied]
        order = [b for b in candidates(k, n, is_ev, needs, rule, variant) if b in free]
        if not order:
            if is_ev:
                counters["ev_fail"] += 1
                if needs:
                    counters["cap_unmet"] += 1
            else:
                counters["ice_fail"] += 1
            continue
        bay = order[0]
        occupied[bay] = t + a["dwell"]
        if is_ev and needs and bay >= k:
            counters["cap_unmet"] += 1
    def rate(num, den):
        return None if den == 0 else num / den
    rates = {
        "capacity_unmet_rate": rate(counters["cap_unmet"], counters["charge_requests"]),
        "ev_parking_failure_rate": rate(counters["ev_fail"], counters["ev_visits"]),
        "ice_parking_failure_rate": rate(counters["ice_fail"], counters["ice_visits"]),
    }
    feasible = all(v is None or v <= ALPHA + 1e-12 for v in rates.values())
    return {"k": k, **counters, "rates": rates, "feasible": feasible}


def joint_k(instance, rule, variant="base"):
    n = instance["n"]
    top = n if variant != "fixed_zone" else min(3, n)
    rows = [simulate(instance, k, rule, variant) for k in range(0, top + 1)]
    feasible = [r for r in rows if r["feasible"]]
    chosen = feasible[0] if feasible else None
    return {"k": chosen["k"] if chosen else None, "rows": rows,
            "rates": chosen["rates"] if chosen else None}


def service_vector(joint):
    return {name: (None if joint["rates"] is None else joint["rates"][name])
            for name in ("capacity_unmet_rate", "ev_parking_failure_rate",
                         "ice_parking_failure_rate")}


def analyse(instance, variant="base"):
    j0 = joint_k(instance, "pi0", variant)
    j1 = joint_k(instance, "pi1", variant)
    out = {
        "instance": {k: instance[k] for k in ("seed", "n", "ev_share", "q_need",
                                               "dwell_ev", "dwell_ice", "rate_per_slot",
                                               "ev_offset", "ice_offset")},
        "variant": variant,
        "k_pi0": j0["k"], "k_pi1": j1["k"],
        "feasible_pi0": j0["k"] is not None, "feasible_pi1": j1["k"] is not None,
        "delta_k": (j0["k"] - j1["k"]) if (j0["k"] is not None and j1["k"] is not None) else None,
        "restoration": bool(j0["k"] is None and j1["k"] is not None),
        "service_pi0_at_min": service_vector(j0) if j0["k"] is not None else None,
        "service_pi1_at_min": service_vector(j1) if j1["k"] is not None else None,
    }
    if j0["k"] is None and j1["k"] is not None:
        out["restoration_k_pi1"] = j1["k"]
    return out


def grid():
    for n in (6, 8, 10):
        for ev_share in (0.2, 0.4, 0.6, 0.8):
            for q_need in (0.1, 0.3, 0.5, 0.7):
                for dwell_ev in (2, 5):
                    for dwell_ice in (2, 5):
                        for rate in (1.0, 1.6):
                            for offset in ((0, 0), (1, -1), (-1, 1)):
                                for seed in (1, 2, 3):
                                    yield make_instance(seed, n, ev_share, q_need,
                                                        dwell_ev, dwell_ice, rate,
                                                        offset[0], offset[1])


def run_variant(variant):
    results = [analyse(inst, variant) for inst in grid()]
    both = [r for r in results if r["delta_k"] is not None]
    return results, {
        "variant": variant,
        "instances": len(results),
        "both_feasible": len(both),
        "positive_delta_k": sum(1 for r in both if r["delta_k"] > 0),
        "zero_delta_k": sum(1 for r in both if r["delta_k"] == 0),
        "negative_delta_k": sum(1 for r in both if r["delta_k"] < 0),
        "restorations_pi0_infeasible_pi1_feasible": sum(1 for r in results if r["restoration"]),
        "pi0_only_feasible": sum(1 for r in results
                                 if r["feasible_pi0"] and not r["feasible_pi1"]),
        "both_infeasible": sum(1 for r in results
                               if not r["feasible_pi0"] and not r["feasible_pi1"]),
        "examples_positive": [r for r in both if r["delta_k"] > 0][:3],
        "examples_negative": [r for r in both if r["delta_k"] < 0][:3],
        "examples_restoration": [r for r in results if r["restoration"]][:3],
        "examples_pi0_only": [r for r in results
                              if r["feasible_pi0"] and not r["feasible_pi1"]][:3],
    }


def monotonicity_check():
    """在 base 变体上检查：π0 的 ICE 失败率是否随 k 增大而单调不减（普通位随 k 缩小）。"""
    violations, cells = 0, 0
    for inst in grid():
        rows = [simulate(inst, k, "pi0") for k in range(inst["n"] + 1)]
        vals = [r["rates"]["ice_parking_failure_rate"] for r in rows]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            continue
        cells += 1
        for a, b in zip(vals, vals[1:]):
            if b < a - 1e-12:
                violations += 1
                break
    return {"instances_checked": cells, "non_monotone_instances": violations}


def dominance_check():
    """同一 k 下检查服务向量支配：π1 的 EV 停车失败率更高、ICE 失败率更低是否恒成立。"""
    violations, cells = [], 0
    for inst in grid():
        cells += 1
        for k in range(inst["n"] + 1):
            r0 = simulate(inst, k, "pi0")
            r1 = simulate(inst, k, "pi1")
            r0, r1 = r0["rates"], r1["rates"]
            ev0 = [r0["capacity_unmet_rate"], r0["ev_parking_failure_rate"]]
            ev1 = [r1["capacity_unmet_rate"], r1["ev_parking_failure_rate"]]
            ice0, ice1 = r0["ice_parking_failure_rate"], r1["ice_parking_failure_rate"]
            ev_bad = any(a is not None and b is not None and b < a - 1e-12
                         for a, b in zip(ev0, ev1))   # π1 的 EV 率反而更低？
            ice_bad = ice0 is not None and ice1 is not None and ice1 > ice0 + 1e-12
            if ev_bad or ice_bad:
                violations.append({"instance": {x: inst[x] for x in (
                    "seed", "n", "ev_share", "q_need", "dwell_ev", "dwell_ice",
                    "rate_per_slot", "ev_offset", "ice_offset")},
                                   "k": k, "ev_violation": ev_bad, "ice_violation": ice_bad})
                break
    return {"instances_checked": cells, "instances_with_violation": len(violations),
            "examples": violations[:5]}


def main():
    summary = {}
    all_results = {}
    for variant in ("base", "strict_pi0", "fixed_zone"):
        results, stats = run_variant(variant)
        summary[variant] = stats
        all_results[variant] = results
    summary["monotonicity_pi0_ice"] = monotonicity_check()
    summary["service_dominance_base"] = dominance_check()
    summary["model"] = {
        "rule_pair": ["dedicated_by_type", "full_open_ice_first"],
        "charging_bays": "k (与 round3 run_cost_curve 一致：1 桩 = 1 枪 = 1 带枪车位)",
        "capacity_unmet": "需要充电的电车未进入带枪位即计一次",
        "constraints": "三率均 ≤5%",
        "not_modeled": "能量/功率、排队、绕行、挪车、预测规则 π2、预约、真实数据",
    }
    payload = {"summary": summary, "results": all_results}
    path = os.path.join(HERE, "shared_capacity_mechanism.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:9000])


if __name__ == "__main__":
    main()
