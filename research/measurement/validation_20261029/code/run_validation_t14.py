#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T14 F04-F08 修订实验：外生需求日志、可见/真值分离、真保护规则、能量守恒、修正判据。

运行：python research/measurement/validation_20261029/code/run_validation.py
输出：results_t14/results_20261029_T14.json（旧 results/ 不动，不新增个人 Markdown 报告）。
成本范围、种子与失败判据在 PREREG 中预先固定；保留边界最优与无翻转结果，不调参追翻转。
"""
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validation_common import (  # noqa: E402,F401
    S, BND, HERE, ROOT, RES, STATIONS, LEVELS, LEVEL_IDX, PREREG,
    mean, sd, VIEW_KEYS, ROW_KEYS, visible_view, erlang_b, estimate,
    weights_for, cost_given_q, est_cost_per_day, true_cost_per_day,
)
from validation_physics import (  # noqa: E402,F401
    TRUTH_LEDGER_KEYS, e1_counterexample, e2_identity, e3_metrics,
    f04_log_identity, f05_isolation, f06_protection, f07_conservation,
    e4_rules,
)
from validation_decisions import (  # noqa: E402,F401
    _binom_pmf, e5_ablation, e6_holdout, e7_bc_etp,
)
from validation_regressions import (  # noqa: E402,F401
    _reg, _get, _row, _mk_view, f08_regressions, session_regressions,
    regressions, f08_criteria,
)

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="T14 唯一入口")
    ap.add_argument("--out", default=os.path.join(RES, "results_20261029_T14_sessions.json"))
    args = ap.parse_args(argv)
    out_path = os.path.abspath(args.out)
    hist = os.path.abspath(os.path.join(os.path.dirname(RES), "results"))
    if out_path == hist or out_path.startswith(hist + os.sep):
        print("拒绝写入历史结果目录 results/；请用 results_t14/ 或显式 --out", file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    res = dict(prereg=PREREG, generated_by="run_validation_t14.py",
               date="2026-10-29", output=out_path)
    res["E1"] = e1_counterexample()
    res["E2"] = e2_identity()
    res["E3"] = e3_metrics()
    res["F04"] = f04_log_identity()
    res["F05"] = f05_isolation()
    res["F06"] = f06_protection()
    res["F07"] = f07_conservation()
    res["E4"] = e4_rules()
    res["E5"] = e5_ablation()
    res["E6"] = e6_holdout()
    res["E7"] = e7_bc_etp()
    reg = regressions(f08_regressions(), res)
    res["REGRESSIONS"] = reg
    res["F08"] = f08_criteria(res["E5"], res["E7"], reg)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("written", out_path)
    print("REGRESSIONS", sum(1 for r in reg if r["pass"]), "/", len(reg),
          "FAIL", [r["id"] for r in reg if not r["pass"]])
    print("E1 identical", res["E1"]["snapshots_identical"])
    print("F04 all_equal", res["F04"]["all_equal"])
    print("F05 params", _get(res["F05"], "estimate_params", "read_keys"))
    print("F06 differs", res["F06"]["r4_must_differ"], "viol",
          _get(res["F06"]["tight_scenario"], "non_ev_in_protected_during_window", "violations"))
    print("F07 passes", res["F07"]["passes"])
    for cap in PREREG["cost"]["c_cap_range"]:
        key = "c_cap=%g" % cap
        print(key, {lv: (res["E5"][key][lv]["chosen"],
                         res["E5"][key][lv]["reco_status"],
                         res["E5"][key][lv]["reco_q_range"]) for lv in LEVELS})
    print("E5 any_flip", res["E5"]["any_flip"])
    print("E5 q", {lv: (res["E5"]["levels"][lv]["q_status"],
                        round(res["E5"]["levels"][lv]["q_bounds_width_mean"], 3),
                        res["E5"]["levels"][lv]["sessions_lo_mean"],
                        res["E5"]["levels"][lv]["sessions_hi_mean"]) for lv in LEVELS})
    print("E6 partition_ok", res["E6"]["partition_ok"])
    print("E7 tv", round(res["E7"]["observation_equivalence"]["total_variation_distance"], 4))
    for lv, d in res["F08"]["per_level"].items():
        print("F08", lv, d["structural_identification"], "width",
              round(d["precision"]["width"], 3), "prec",
              d["precision"]["meets_precision_target"], "cov",
              d["coverage"]["empirical"], "q", d["q_status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
