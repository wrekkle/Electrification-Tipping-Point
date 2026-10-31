# -*- coding: utf-8 -*-
"""Lead 独立复核 Q1：用一个机制反例实例逐事件重放 k=0 与 k=1，解释 ICE 失败 8->7。
独立实现（按 shared_capacity_mechanism.py 文档规则重写），不调用其 simulate。
输出 research/round6_20261031/lead/q1_indep.json"""
from __future__ import annotations
import importlib.util, json
from pathlib import Path

ROOT = Path(r"C:\Projects\停车场充电桩优化方案")
MECH = ROOT / "research/round4_20261031/mechanism/shared_capacity_mechanism.py"
OUT = ROOT / "research/round6_20261031/lead/q1_indep.json"
spec = importlib.util.spec_from_file_location("scm", MECH)
scm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scm)
EPS = 1e-12


def replay(instance, k, trace=False):
    n = instance["n"]
    slots = [None] * n
    c = {"ev": 0, "ev_fail": 0, "ice": 0, "ice_fail": 0, "ev_ordinary": 0, "req": 0, "cup": 0}
    events = sorted(instance["arrivals"], key=lambda a: (a["t"], a["is_ev"]))
    log = []
    for a in events:
        released = [b for b in range(n) if slots[b] is not None and slots[b] <= a["t"] + EPS]
        for b in released:
            slots[b] = None
        is_ev, needs = a["is_ev"], a["needs"]
        if is_ev:
            c["ev"] += 1
            c["req"] += int(bool(needs))
        else:
            c["ice"] += 1
        order = ([b for b in range(k)] + [b for b in range(k, n)]) if is_ev else [b for b in range(k, n)]
        free = [b for b in order if slots[b] is None]
        if not free:
            if is_ev:
                c["ev_fail"] += 1
                if needs:
                    c["cup"] += 1
                outcome = "EV_REJECT"
            else:
                c["ice_fail"] += 1
                outcome = "ICE_REJECT"
            log.append({"t": round(a["t"], 3), "veh": a.get("id", "?"), "is_ev": is_ev, "needs": needs,
                        "dwell": a["dwell"], "released": released, "bay": None, "outcome": outcome})
            continue
        bay = free[0]
        slots[bay] = a["t"] + a["dwell"]
        if is_ev and bay >= k:
            c["ev_ordinary"] += 1
            if needs:
                c["cup"] += 1
        log.append({"t": round(a["t"], 3), "veh": a.get("id", "?"), "is_ev": is_ev, "needs": needs,
                    "dwell": a["dwell"], "released": released, "bay": bay,
                    "outcome": "EV_ORDINARY" if (is_ev and bay >= k) else "PARK"})
    return c, log


def main():
    params = {"seed": 1, "n": 6, "ev_share": 0.4, "q_need": 0.1, "dwell_ev": 5,
              "dwell_ice": 5, "rate_per_slot": 1.6, "ev_offset": -1, "ice_offset": 1}
    inst = scm.make_instance(**params)
    out = {"schema": "round6/lead_q1_indep/v1", "instance": params,
           "n_arrivals": len(inst["arrivals"]), "cases": {}}
    for k in (0, 1):
        c, log = replay(inst, k, trace=True)
        out["cases"][str(k)] = {
            "ice_fail": c["ice_fail"], "ice": c["ice"], "ice_rate": c["ice_fail"] / c["ice"],
            "ev_fail": c["ev_fail"], "ev_ordinary": c["ev_ordinary"],
            "capacity_unmet": c["cup"], "req": c["req"],
        }
        if k == 0:
            out["events_k0"] = log
    # 对照：同一到达顺序下 k=1 时释放/占用差异
    _, log1 = replay(inst, 1)
    diffs = []
    for a, b in zip(out["events_k0"], log1):
        if (a["bay"], a["outcome"]) != (b["bay"], b["outcome"]):
            diffs.append({"t": a["t"], "is_ev": a["is_ev"], "needs": a["needs"],
                          "k0": {"bay": a["bay"], "outcome": a["outcome"]},
                          "k1": {"bay": b["bay"], "outcome": b["outcome"]}})
    out["diffs_k0_k1"] = diffs
    out["check"] = {
        "ice_fail_decreased": out["cases"]["1"]["ice_fail"] < out["cases"]["0"]["ice_fail"],
        "expected": "8->7", "ev_ordinary": "8->2",
        "matches": (out["cases"]["0"]["ice_fail"] == 8 and out["cases"]["1"]["ice_fail"] == 7
                    and out["cases"]["0"]["ev_ordinary"] == 8 and out["cases"]["1"]["ev_ordinary"] == 2),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out["check"], ensure_ascii=False))
    print("diffs:", json.dumps(diffs[:6], ensure_ascii=False))
    print("k0:", json.dumps(out["cases"]["0"]), "k1:", json.dumps(out["cases"]["1"]))


if __name__ == "__main__":
    main()
