"""第三轮实验驱动：按阶段调用统一 runner，记录命令/退出码/耗时/输出。

用法（仓库根目录）：
    python research/round3_20261031/run_experiments.py --phase pilot
    python research/round3_20261031/run_experiments.py --phase tune
    python research/round3_20261031/run_experiments.py --phase main --seeds-n 10
    python research/round3_20261031/run_experiments.py --phase pq
    python research/round3_20261031/run_experiments.py --phase power
    python research/round3_20261031/run_experiments.py --phase legacy
    python research/round3_20261031/run_experiments.py --phase validation --seeds-n 10

正式结果只用 independent 情景；legacy 仅历史对照。所有输出写 results/，manifest 逐条记录。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNNER = os.path.join(ROOT, "research", "integer_allocation_20261031", "run_cost_curve.py")
PARAMS = os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json")
COST = os.path.join(ROOT, "research", "integer_allocation_20261031", "cost_scenario.json")
OUT = os.path.join(ROOT, "research", "round3_20261031", "results")
TRAIN = ["TPE0008", "TPE0610", "TPE0401", "TPE0695", "TPE0330"]
VALID = ["TPE1376", "TPE0930", "TPE1171", "TPE1380"]
ALL9 = TRAIN + VALID
REF_PEV, REF_Q = 0.10, 0.36
PRED_OBJS = ["charge_arrivals", "ev_arrivals", "connector_load"]
WINDOWS = [10.0, 30.0, 60.0]
MARGINS = [0.0, 1.0, 2.0]
PROTECTED = [0, 1, 2, 3, 4, 6, 8]
MANIFEST = os.path.join(OUT, "run_manifest.json")


def _base(name, lots, seeds, rule, kstep=1, kmax=40, p_ev=REF_PEV, q_need=REF_Q,
          scenario="independent", charger=7.0, feeder=336.0, protected=0,
          obj="charge_arrivals", window=30.0, margin=1.0):
    out = os.path.join(OUT, name + ".json")
    cmd = [sys.executable, RUNNER, "--params", PARAMS, "--lots", ",".join(lots),
           "--seeds", seeds, "--k-max", str(kmax), "--k-step", str(kstep),
           "--rule", rule, "--charger-kw", str(charger), "--feeder-kw", str(feeder),
           "--horizon-min", "1440", "--start-hour", "11.5", "--cost-file", COST,
           "--scenario-model", scenario, "--p-ev", str(p_ev), "--q-need", str(q_need),
           "--prediction-object", obj, "--prediction-window-min", str(window),
           "--prediction-margin", str(margin), "--protected-bays", str(protected),
           "--workers", "8", "--out", out]
    return name, cmd


def steps_pilot():
    return [_base("pilot_pev010_q036_pi0_s1-5", ALL9, "1,2,3,4,5", "dedicated_by_type")]


def steps_tune():
    out = []
    for m in PROTECTED:
        out.append(_base("tune_C_m%d_train_s123" % m, TRAIN, "1,2,3", "protected_quota",
                         kstep=2, protected=m))
    for obj in PRED_OBJS:
        for window in WINDOWS:
            for margin in MARGINS:
                out.append(_base("tune_D_%s_w%d_m%d_train_s123" % (obj, int(window), int(margin)),
                                 TRAIN, "1,2,3", "predictive_shared_ice_first",
                                 kstep=2, obj=obj, window=window, margin=margin))
    return out


def _selection():
    path = os.path.join(OUT, "selection.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _rule_step(name, rule, lots, seeds, selection, **kw):
    if rule == "protected_quota":
        kw["protected"] = int(selection["C"]["protected_bays"])
    if rule == "predictive_shared_ice_first":
        d = selection["D"]
        kw.update(obj=d["prediction_object"], window=float(d["window_min"]),
                  margin=float(d["margin"]))
    return _base(name, lots, seeds, rule, **kw)


def steps_main(seeds_n):
    seeds = ",".join(str(i) for i in range(1, seeds_n + 1))
    sel = _selection()
    out = []
    for rule, tag in (("dedicated_by_type", "A_pi0"), ("full_open_ice_first", "B_pi1"),
                      ("protected_quota", "C_quota"), ("predictive_shared_ice_first", "D_pi2")):
        out.append(_rule_step("main_%s_ref_s%d" % (tag, seeds_n), rule, ALL9, seeds, sel))
    return out


def steps_pq():
    out = []
    for p in (0.05, 0.10, 0.20):
        for q in (0.20, 0.50):
            out.append(_base("pq_p%02d_q%02d_pi0_s123" % (int(p * 100), int(q * 100)),
                             ALL9, "1,2,3", "dedicated_by_type", p_ev=p, q_need=q))
    return out


def steps_power():
    out = []
    out.append(_base("power_kw3p5_feeder336_pi0_s123", ALL9, "1,2,3", "dedicated_by_type", charger=3.5))
    out.append(_base("power_kw22_feeder336_pi0_s123", ALL9, "1,2,3", "dedicated_by_type", charger=22.0))
    out.append(_base("power_kw7_feeder120_pi0_s123", ALL9, "1,2,3", "dedicated_by_type", feeder=120.0))
    out.append(_base("power_kw3p5_feeder120_pi0_s123", ALL9, "1,2,3", "dedicated_by_type",
                     charger=3.5, feeder=120.0))
    return out


def steps_legacy():
    return [_base("legacy_pev010_pi0_s123", ALL9, "1,2,3", "dedicated_by_type", q_need="",
                  scenario="legacy_product", p_ev=0.10)]


def steps_rules_pq():
    """共享规则在低/高 EV 需求情景下是否改变所需设备数（替代条件）。"""
    sel = _selection()
    out = []
    for label, p, q in (("low", 0.05, 0.20), ("high", 0.20, 0.50)):
        for rule, tag in (("dedicated_by_type", "A_pi0"), ("full_open_ice_first", "B_pi1"),
                          ("protected_quota", "C_quota"),
                          ("predictive_shared_ice_first", "D_pi2")):
            out.append(_rule_step("rulespq_%s_%s_s123" % (label, tag), rule, ALL9,
                                  "1,2,3", sel, p_ev=p, q_need=q))
    return out


def steps_expand():
    plan_path = os.path.join(OUT, "expansion_plan.json")
    with open(plan_path, encoding="utf-8") as handle:
        plan = json.load(handle)
    out = []
    for item in plan:
        sel = item["selection"]
        rule = item["rule"]
        kw = {"kmax": int(item["k_max"]), "kstep": 1}
        if rule == "protected_quota":
            kw["protected"] = int(sel["C"]["protected_bays"])
        if rule == "predictive_shared_ice_first":
            d = sel["D"]
            kw.update(obj=d["prediction_object"], window=float(d["window_min"]),
                      margin=float(d["margin"]))
        out.append(_base(item["name"], [item["lot"]],
                         ",".join(str(i) for i in range(1, item["seeds_n"] + 1)),
                         rule, **kw))
    return out


def steps_validation(seeds_n):
    seeds = ",".join(str(i) for i in range(1, seeds_n + 1))
    sel = _selection()
    out = []
    for rule, tag in (("dedicated_by_type", "A_pi0"), ("full_open_ice_first", "B_pi1"),
                      ("protected_quota", "C_quota"), ("predictive_shared_ice_first", "D_pi2")):
        out.append(_rule_step("valid_%s_ref_s%d" % (tag, seeds_n), rule, VALID, seeds, sel))
    return out


def _legacy_cmd(fix, cmd):
    """legacy 模式的 q-need 在 CLI 上是空串会报错：去掉该参数对。"""
    if "--q-need" in cmd:
        i = cmd.index("--q-need")
        if cmd[i + 1] == "":
            del cmd[i:i + 2]
    return cmd


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True,
                        choices=("pilot", "tune", "main", "pq", "rules_pq", "power", "legacy",
                                 "validation", "expand"))
    parser.add_argument("--seeds-n", type=int, default=10)
    parser.add_argument("--only", default=None, help="只跑名字包含该子串的步骤")
    args = parser.parse_args(argv)
    steps = {"pilot": steps_pilot, "tune": steps_tune, "pq": steps_pq,
             "rules_pq": steps_rules_pq,
             "power": steps_power, "legacy": steps_legacy,
             "main": lambda: steps_main(args.seeds_n),
             "validation": lambda: steps_validation(args.seeds_n),
             "expand": steps_expand}[args.phase]()
    if args.only:
        steps = [s for s in steps if args.only in s[0]]
    os.makedirs(OUT, exist_ok=True)
    manifest = []
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as handle:
            manifest = json.load(handle)
    for name, cmd in steps:
        cmd = _legacy_cmd(None, cmd)
        start = time.time()
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        record = {"phase": args.phase, "name": name, "command": " ".join(cmd),
                  "exit_code": proc.returncode, "seconds": round(time.time() - start, 2),
                  "stdout_tail": (proc.stdout or "")[-800:],
                  "stderr_tail": (proc.stderr or "")[-1600:],
                  "out": os.path.join(OUT, name + ".json")}
        manifest.append(record)
        with open(MANIFEST, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=1)
        print(name, "EXIT", proc.returncode, record["seconds"], flush=True)
        if proc.returncode != 0:
            print(record["stderr_tail"], flush=True)
            return proc.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
