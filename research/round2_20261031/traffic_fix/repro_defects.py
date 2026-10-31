# -*- coding: utf-8 -*-
"""R2-B 修复前最小反例 / 修复后回归（Lead 独立验收用，可复跑）。

对 apps/parking_lab/workbench/traffic_gen.py 逐条断言 CONTRACT §2 的要求。
修复前应出现 FAIL；修复后应全部 PASS。只读源码，不写任何已交付 JSON。

跑法（仓库根目录）：
    python research/round2_20261031/traffic_fix/repro_defects.py \
        --out research/round2_20261031/traffic_fix/after_fix_verify.txt
修复前证据（用冻结的旧源码快照，不改工作区实现）：
    $env:TRAFFIC_GEN_SNAPSHOT="research/round2_20261031/traffic_fix/pre_fix_traffic_gen_snapshot.py"
    python research/round2_20261031/traffic_fix/repro_defects.py \
        --out research/round2_20261031/traffic_fix/before_fix_failures.txt

旧源码快照 pre_fix_traffic_gen_snapshot.py 的 SHA-256 必须等于 BASELINE.md 记录的
52DABAAD74A6D89BCCC84D97011D1B138FCC9016F17B740A46FD1E6F3FD2F6F6（17611 字节）。
退出码：0=全部通过；1=有失败（失败行以 FAIL 开头，含观测值）。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

SNAPSHOT = os.environ.get("TRAFFIC_GEN_SNAPSHOT")
if SNAPSHOT:
    import apps.parking_lab.workbench  # noqa: F401  先建包，再把旧源码注册成同名模块
    spec = importlib.util.spec_from_file_location(
        "apps.parking_lab.workbench.traffic_gen", os.path.join(ROOT, SNAPSHOT))
    module = importlib.util.module_from_spec(spec)
    sys.modules["apps.parking_lab.workbench.traffic_gen"] = module
    spec.loader.exec_module(module)

from apps.parking_lab.workbench import traffic_gen  # noqa: E402

LINES = []


def emit(text=""):
    print(text)
    LINES.append(text)


def _dwell_lognormal(mean_min, sigma=1e-6):
    return {"family": "single_lognormal", "mean_min": mean_min,
            "components": [{"name": "only", "weight": 1.0, "family": "lognormal_scenario",
                            "params": [math.log(mean_min) - 0.5 * sigma * sigma, sigma],
                            "mean_min": mean_min}]}


def _params_14kwh(power=7.0):
    """真实需求 14 kWh、额定 7 kW、停留约 60 min：修复前会被削成 7 kWh。"""
    return {
        "schema_version": "traffic_gen_params/v1",
        "bins": {"count": 24, "local_hour": list(range(24)), "minutes_observed": [60.0] * 24},
        "traffic_fit": {
            "train": {"arrival_rate_per_100_spaces_hour": [4.0] * 24,
                      "dwell": _dwell_lognormal(60.0)},
            "cohort_reference": {"arrival_rate_per_100_spaces_hour": [2.0] * 24},
        },
        "ev": {"p_ev_default": 0.5, "product_required_mean": 0.25},
        "energy": {"charger_power_kw": power, "efficiency": 1.0, "deficit_mean_kwh": 14.0,
                   "deficit_sd_kwh": 0.0, "deficit_clip_kwh": [14.0, 14.0]},
        "generator": {"horizon_min": 1440, "minute_step_min": 1.0, "reference_spaces": 100,
                      "default_n_spaces": 100.0, "max_dwell_min": 1440, "min_dwell_min": 1.0,
                      "max_arrivals": 40000},
    }


def _params_two_point():
    """停留两点分布 {1, 9} 等权：平稳长度偏置暖启动 E[剩余]=E[D^2]/(2E[D])=4.1 min。"""
    dwell = {
        "family": "two_point", "mean_min": 5.0,
        "components": [
            {"name": "one", "weight": 0.5, "family": "lognormal_scenario",
             "params": [math.log(1.0), 0.0], "mean_min": 1.0},
            {"name": "nine", "weight": 0.5, "family": "lognormal_scenario",
             "params": [math.log(9.0), 0.0], "mean_min": 9.0},
        ],
    }
    return {
        "schema_version": "traffic_gen_params/v1",
        "bins": {"count": 24, "local_hour": list(range(24)), "minutes_observed": [60.0] * 24},
        "traffic_fit": {"train": {"arrival_rate_per_100_spaces_hour": [0.0] * 24, "dwell": dwell},
                        "cohort_reference": {"arrival_rate_per_100_spaces_hour": [0.0] * 24}},
        "ev": {"p_ev_default": 0.5, "product_required_mean": 0.0},
        "energy": {"charger_power_kw": 7.0, "efficiency": 0.9, "deficit_mean_kwh": 20.0,
                   "deficit_sd_kwh": 5.0, "deficit_clip_kwh": [4.0, 55.0]},
        "generator": {"horizon_min": 60, "minute_step_min": 1.0, "reference_spaces": 100,
                      "default_n_spaces": 100.0, "max_dwell_min": 1440, "min_dwell_min": 1.0,
                      "max_arrivals": 40000},
        "per_lot": [{
            "lot_id": "TWO-POINT", "n_spaces": 20000.0, "fit_split": "train",
            "lambda_hour_by_bin": [0.0] * 24, "lambda_bar_veh_per_hour": 0.0,
            "dwell_dist": dwell, "charge_session_rate_hour_by_bin": [0.0] * 24,
            "charge_session_rate_mean_hour": 0.0, "mean_occupancy_vehicles": 20000.0,
            "connector_availability": 1.0, "usable": True,
        }],
    }


def _params_censored():
    """窗口 120 min、停留约 720 min：期末仍在场的需求必须标删失，不能算离场失败。"""
    dw = _dwell_lognormal(720.0)
    return {
        "schema_version": "traffic_gen_params/v1",
        "bins": {"count": 24, "local_hour": list(range(24)), "minutes_observed": [60.0] * 24},
        "traffic_fit": {"train": {"arrival_rate_per_100_spaces_hour": [4.0] * 24, "dwell": dw},
                        "cohort_reference": {"arrival_rate_per_100_spaces_hour": [2.0] * 24}},
        "ev": {"p_ev_default": 0.5, "product_required_mean": 0.25},
        "energy": {"charger_power_kw": 7.0, "efficiency": 1.0, "deficit_mean_kwh": 60.0,
                   "deficit_sd_kwh": 0.0, "deficit_clip_kwh": [60.0, 60.0]},
        "generator": {"horizon_min": 120, "minute_step_min": 1.0, "reference_spaces": 100,
                      "default_n_spaces": 100.0, "max_dwell_min": 1440, "min_dwell_min": 1.0,
                      "max_arrivals": 40000},
        "per_lot": [{
            "lot_id": "CENSORED", "n_spaces": 500.0, "fit_split": "train",
            "lambda_hour_by_bin": [4.0] * 24, "lambda_bar_veh_per_hour": 4.0,
            "dwell_dist": dw, "charge_session_rate_hour_by_bin": [2.0] * 24,
            "charge_session_rate_mean_hour": 2.0, "mean_occupancy_vehicles": 20.0,
            "connector_availability": 1.0, "usable": True,
        }],
    }


RESULTS = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as error:  # noqa: BLE001 - 反例脚本要把异常也算失败留痕
        ok, detail = False, "%s: %s" % (type(error).__name__, error)
    RESULTS.append((name, ok, detail))
    emit(("PASS " if ok else "FAIL ") + name + " | " + detail)


def c1_true_demand_not_cut():
    params = _params_14kwh(power=7.0)
    arrivals, meta = traffic_gen.generate(params, 7)
    needs = [a for a in arrivals if a.needs_charge]
    if not needs:
        return False, "没有充电需求样本，反例无效"
    energies = sorted({round(a.energy_kwh, 9) for a in needs})
    bad = [a for a in needs if abs(a.energy_kwh - 14.0) > 1e-6]
    detail = "n_need=%d energy_range=%s dwell_range=%.2f..%.2f" % (
        len(needs), energies[:3], min(a.dwell_min for a in needs), max(a.dwell_min for a in needs))
    return (not bad), detail + (" 期望每辆真实需求 14.0 kWh" if bad else "")


def c2_energy_independent_of_power():
    hashes, means = [], []
    for power in (7.0, 3.5, 50.0):
        arrivals, meta = traffic_gen.generate(_params_14kwh(power=power), 11)
        needs = [a.energy_kwh for a in arrivals if a.needs_charge]
        hashes.append(traffic_gen.stream_hash(arrivals))
        means.append(round(sum(needs) / len(needs), 6) if needs else None)
    ok = len(set(hashes)) == 1
    return ok, "power=7/3.5/50 -> demand_mean=%s hash_equal=%s" % (means, ok)


def c3_meta_ledger_columns():
    arrivals, meta = traffic_gen.generate(_params_14kwh(), 7)
    required = ["demand_energy_kwh_total", "theoretical_service_min_total",
                "deliverable_energy_kwh_total", "departed_shortfall_kwh", "pending_energy_kwh"]
    missing = [k for k in required if k not in meta]
    ok = not missing
    if ok:
        total = (meta["deliverable_energy_kwh_total"] + meta["departed_shortfall_kwh"]
                 + meta["pending_energy_kwh"])
        ok = abs(total - meta["demand_energy_kwh_total"]) <= 1e-6
    return ok, "missing=%s demand=%.6f" % (missing, meta.get("demand_energy_kwh_total", float("nan")))


def c4_warm_start_length_biased():
    params = _params_two_point()
    arrivals, meta = traffic_gen.generate_for_lot(params, "TWO-POINT", 3)
    n_warm = int(meta.get("initial_occupancy_n") or 0)
    if n_warm < 1000:
        return False, "暖启动样本不足 n=%r" % n_warm
    residual = [a.dwell_min for a in arrivals[:n_warm]]
    mean = sum(residual) / len(residual)
    ok = abs(mean - 4.1) <= 0.15
    return ok, "n=%d 剩余停留均值=%.4f min（正确值 E[D^2]/(2E[D])=4.1；旧实现 U(0,D) 约 2.5）" % (
        n_warm, mean)


def c5_warm_meta():
    _, meta = traffic_gen.generate_for_lot(_params_two_point(), "TWO-POINT", 3)
    ok = (meta.get("warm_start_method") == "length_biased_stationary"
          and meta.get("length_biased") is True)
    return ok, "warm_start_method=%r length_biased=%r" % (
        meta.get("warm_start_method"), meta.get("length_biased"))


def c6_censoring_marked():
    params = _params_censored()
    arrivals, meta = traffic_gen.generate_for_lot(params, "CENSORED", 5, horizon_min=120)
    keys = ("censored_charge_sessions", "pending_energy_kwh", "charge_shortfall_sessions",
            "charge_shortfall_energy_kwh", "demand_energy_kwh_total")
    missing = [k for k in keys if k not in meta]
    if missing:
        return False, "missing=%s" % missing
    censored = int(meta["censored_charge_sessions"])
    pending = float(meta["pending_energy_kwh"])
    demand = float(meta["demand_energy_kwh_total"])
    ok = censored > 0 and pending > 0 and demand >= pending
    return ok, ("censored=%d pending=%.3f kWh demand_total=%.3f shortfall_sessions=%r "
                "（删失不得计入离场失败）" % (censored, pending, demand,
                                              meta["charge_shortfall_sessions"]))


def c7_public_warm_start_api():
    fn = getattr(traffic_gen, "warm_start_arrivals", None)
    if fn is None:
        return False, "缺少公开 API warm_start_arrivals(lot_info, n, rng, dwell_dist)"
    import inspect
    params = list(inspect.signature(fn).parameters)
    ok = params[:4] == ["lot_info", "n", "rng", "dwell_dist"]
    return ok, "signature=%s" % params


def c8_no_precut_relative_to_stay():
    """真实需求允许超过停留内可交付量；旧实现把每辆都削到上限。"""
    params = _params_14kwh(power=7.0)
    arrivals, _ = traffic_gen.generate(params, 13)
    needs = [a for a in arrivals if a.needs_charge]
    cap = [7.0 * 1.0 * a.dwell_min / 60.0 for a in needs]
    cut = [a for a, c in zip(needs, cap) if a.energy_kwh < c - 1e-9]
    uncut = [a for a, c in zip(needs, cap) if a.energy_kwh > c + 1e-9]
    ok = bool(needs) and len(uncut) == len(needs)
    return ok, "n_need=%d 被提前削减=%d 辆，保留真实需求=%d 辆（停留内可交付上限小于需求时才允许出现缺口）" % (
        len(needs), len(cut), len(uncut))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None, help="UTF-8 证据文件路径")
    args = parser.parse_args(argv)
    emit("traffic_gen version: " + traffic_gen.GENERATOR_VERSION)
    emit("module file: " + str(Path(traffic_gen.__file__).resolve()))
    for name, fn in [("C1 真实需求不被 min(需求,可交付) 削减", c1_true_demand_not_cut),
                     ("C2 需求能量不随生成器额定功率改变", c2_energy_independent_of_power),
                     ("C3 meta 分列五项需求账", c3_meta_ledger_columns),
                     ("C4 暖启动平稳长度偏置 E[剩余]=4.1", c4_warm_start_length_biased),
                     ("C5 meta warm_start_method/length_biased", c5_warm_meta),
                     ("C6 删失标记且不算失败", c6_censoring_marked),
                     ("C7 公开 API warm_start_arrivals", c7_public_warm_start_api),
                     ("C8 不把每辆都削到停留可交付上限", c8_no_precut_relative_to_stay)]:
        check(name, fn)
    failed = [name for name, ok, _ in RESULTS if not ok]
    emit()
    emit("SUMMARY: %d/%d 通过，失败 %d" % (len(RESULTS) - len(failed), len(RESULTS), len(failed)))
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
