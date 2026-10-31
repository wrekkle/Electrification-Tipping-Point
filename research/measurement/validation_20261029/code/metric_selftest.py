#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指标公式的固定算例自检（M01/M02/M03/M06/M07/M13）。

任何期望值都来自手算，见 SPEC_metrics.md 第 4 节。系数 0.5/0.3/1.0/2.0 是情景参数，不是实测。
"""
import math
import sys


def acceptance_rate(vehs):
    """M01 接纳率：分母=请求充电的到达车辆数（含被拒）。"""
    req = [v for v in vehs if v["requests_charge"]]
    return sum(1 for v in req if v["admitted"]) / len(req) if req else float("nan")


def service_success_rate(vehs):
    """M02 服务成功率：分母=已接纳且请求充电者；分子=交付>=需求。"""
    adm = [v for v in vehs if v["admitted"] and v["requests_charge"]]
    return sum(1 for v in adm if v["delivered_kwh"] + 1e-9 >= v["need_kwh"]) / len(adm) if adm else float("nan")


def wait_stats(vehs):
    """M03/M04：只统计已接纳车辆；P90 用最近秩。"""
    w = sorted(v["wait_min"] for v in vehs if v["admitted"] and v["wait_min"] is not None)
    if not w:
        return {"mean": float("nan"), "median": float("nan"), "p90": float("nan")}
    n = len(w)
    median = w[n // 2] if n % 2 else 0.5 * (w[n // 2 - 1] + w[n // 2])
    return {"mean": sum(w) / n, "median": median, "p90": w[math.ceil(0.9 * n) - 1]}


def energy_gap_kwh(vehs):
    """M05/M06/M07：把已接纳缺口与拒绝缺口分开。"""
    adm = [v for v in vehs if v["admitted"]]
    rej = [v for v in vehs if v["requests_charge"] and not v["admitted"]]
    return {
        "delivered": sum(v["delivered_kwh"] for v in adm),
        "admitted_need": sum(v["need_kwh"] for v in adm),
        "admitted_gap": sum(max(0.0, v["need_kwh"] - v["delivered_kwh"]) for v in adm),
        "refusal_gap": sum(v["need_kwh"] for v in rej),
    }


def total_cost(n_cap, vehs):
    """M13 总成本。系数是情景参数，不是实测。"""
    g = energy_gap_kwh(vehs)
    return 0.5 * n_cap + 0.3 * g["delivered"] + 1.0 * g["admitted_gap"] + 2.0 * g["refusal_gap"]


TEST_LOG = [
    {"vid": "v1", "is_ev": True, "requests_charge": True, "admitted": True,
     "wait_min": 2.0, "need_kwh": 20.0, "delivered_kwh": 20.0},
    {"vid": "v2", "is_ev": True, "requests_charge": True, "admitted": False,
     "wait_min": None, "need_kwh": 15.0, "delivered_kwh": 0.0},
    {"vid": "v3", "is_ev": True, "requests_charge": True, "admitted": True,
     "wait_min": 20.0, "need_kwh": 20.0, "delivered_kwh": 12.0},
    {"vid": "v4", "is_ev": False, "requests_charge": False, "admitted": True,
     "wait_min": None, "need_kwh": 0.0, "delivered_kwh": 0.0},
    {"vid": "v5", "is_ev": True, "requests_charge": False, "admitted": True,
     "wait_min": None, "need_kwh": 0.0, "delivered_kwh": 0.0},
]


def main():
    fails = []

    def check(name, got, want):
        ok = (isinstance(got, float) and math.isclose(got, want, abs_tol=1e-9)) or got == want
        print(("PASS" if ok else "FAIL") + "  %-14s got=%r want=%r" % (name, got, want))
        if not ok:
            fails.append(name)

    check("acceptance", acceptance_rate(TEST_LOG), 2.0 / 3.0)
    check("success", service_success_rate(TEST_LOG), 0.5)
    ws = wait_stats(TEST_LOG)
    check("wait.mean", ws["mean"], 11.0)
    check("wait.median", ws["median"], 11.0)
    check("wait.p90", ws["p90"], 20.0)
    g = energy_gap_kwh(TEST_LOG)
    check("delivered", g["delivered"], 32.0)
    check("admitted_need", g["admitted_need"], 40.0)
    check("admitted_gap", g["admitted_gap"], 8.0)
    check("refusal_gap", g["refusal_gap"], 15.0)
    check("total_cost(3)", total_cost(3, TEST_LOG), 49.1)
    sep = (g["admitted_gap"] == 8.0 and g["refusal_gap"] == 15.0)
    print(("PASS" if sep else "FAIL") + "  gap_separation refused_kwh_not_in_admitted_gap")
    if not sep:
        fails.append("gap_separation")

    if fails:
        print("FAILED: " + ", ".join(fails))
        return 1
    print("ALL PASS  (5 条固定算例，注意：这验证公式实现，不验证真实系统)")
    return 0


if __name__ == "__main__":
    sys.exit(main())