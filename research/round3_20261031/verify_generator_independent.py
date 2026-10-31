# -*- coding: utf-8 -*-
"""R3-G 独立黑盒验收：traffic_gen 新接口（scenario_model / strict / clipped）。

只按规格验收，不读实现源码、不复制实现公式：
  1) independent: p_ev=0.05, q_need=0.70 多次生成，EV 占比与 EV 中需充电比例落在 ±3σ 二项区间；
     且 p_ev < z（z=场站 observed_p_ev_times_q_need）不得报错。
  2) legacy_product: 显式 p_ev=0.30 不传 q_need 时 q_need_used≈product/p_ev；
     q_need=1.2 时 clipped=True 且 q_need_used=1.0；meta 含 scenario_model=legacy_product、product_coupled=True。
  3) strict: q_need=1.2 / NaN / inf 抛 ValueError；independent 模式不给 q_need 抛 ValueError。
  4) 同 seed 同参数两次生成 demand 哈希一致；默认老调用（不传新参数）哈希与第二轮基线
     TPE0008 94b884e19e2f4c7c2cff56f3559692251d9f0f196a5b424a1d4fcb415f7f977a 一致。

输出: research/round3_20261031/results/verify_generator_independent.json
退出码: 0 全部 PASS / 1 存在 FAIL。
"""
import hashlib
import io
import json
import math
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from apps.parking_lab.workbench import traffic_gen  # noqa: E402
from apps.parking_lab.workbench.costs import traffic_hash  # noqa: E402

PARAMS_PATH = REPO / "research" / "traffic_generation_20261031" / "fitted_parameters.json"
OUT_JSON = HERE / "results" / "verify_generator_independent.json"
LOT = "TPE0008"
BASELINE_HASH = "94b884e19e2f4c7c2cff56f3559692251d9f0f196a5b424a1d4fcb415f7f977a"
SEEDS = list(range(1, 25))
TOLERANCE_SIGMA = 3.0

results = []


def record(name, passed, expected, actual, note=""):
    results.append({"name": name, "pass": bool(passed), "expected": expected,
                    "actual": actual, "note": note})
    print("%s %-52s expected=%s actual=%s %s" % (
        "PASS" if passed else "FAIL", name, expected, actual, note))
    return passed


def stream_digest(arrivals):
    payload = [[a.vehicle_id, a.time_min, a.is_ev, a.needs_charge, a.dwell_min, a.energy_kwh]
               for a in arrivals]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def main():
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    lot_entry = next(e for e in params["per_lot"] if e["lot_id"] == LOT)
    z_observed = float(lot_entry["observed_p_ev_times_q_need"])
    product_required = float(params["ev"]["product_required_mean"])

    # ---------- 1) independent 模式统计性质
    p_ev, q_need = 0.05, 0.70
    n_total = n_ev = n_ev_need = 0
    independent_meta = None
    for seed in SEEDS:
        arrivals, meta = traffic_gen.generate_for_lot(
            params, LOT, seed, p_ev=p_ev, q_need=q_need, scenario_model="independent")
        independent_meta = meta
        n_total += len(arrivals)
        n_ev += sum(1 for a in arrivals if a.is_ev)
        n_ev_need += sum(1 for a in arrivals if a.is_ev and a.needs_charge)
    p_hat = n_ev / n_total
    sigma_p = math.sqrt(p_ev * (1.0 - p_ev) / n_total)
    record("independent.p_ev_share_mean_%d_seeds" % len(SEEDS),
           abs(p_hat - p_ev) <= TOLERANCE_SIGMA * sigma_p,
           "%.5f +- %.5f (3 binomial sigma)" % (p_ev, TOLERANCE_SIGMA * sigma_p),
           "%.5f (n=%d, EV=%d)" % (p_hat, n_total, n_ev),
           "seeds=%d..%d" % (SEEDS[0], SEEDS[-1]))
    q_hat = n_ev_need / n_ev
    sigma_q = math.sqrt(q_need * (1.0 - q_need) / n_ev)
    record("independent.q_need_share_given_ev",
           abs(q_hat - q_need) <= TOLERANCE_SIGMA * sigma_q,
           "%.5f +- %.5f (3 binomial sigma)" % (q_need, TOLERANCE_SIGMA * sigma_q),
           "%.5f (EV=%d, EV&charge=%d)" % (q_hat, n_ev, n_ev_need))
    record("independent.meta_echo",
           abs(independent_meta["p_ev"] - p_ev) < 1e-12
           and abs(independent_meta["q_need"] - q_need) < 1e-12
           and independent_meta["scenario_model"] == "independent"
           and independent_meta["product_coupled"] is False,
           "p_ev=0.05, q_need=0.70, scenario_model=independent, product_coupled=False",
           "p_ev=%r q_need=%r scenario_model=%r product_coupled=%r"
           % (independent_meta["p_ev"], independent_meta["q_need"],
              independent_meta["scenario_model"], independent_meta["product_coupled"]))

    small_p = 0.01
    try:
        arrivals_small, meta_small = traffic_gen.generate_for_lot(
            params, LOT, 1, p_ev=small_p, q_need=q_need, scenario_model="independent")
        record("independent.p_ev_below_z_no_error",
               True, "no exception for p_ev=%.3f < z=%.5f" % (small_p, z_observed),
               "ok: n=%d, p_ev=%r, product_coupled=%r"
               % (len(arrivals_small), meta_small["p_ev"], meta_small["product_coupled"]),
               "z=observed_p_ev_times_q_need(TPE0008)")
    except Exception as exc:  # noqa: BLE001 - acceptance evidence must show the failure
        record("independent.p_ev_below_z_no_error", False,
               "no exception", "%s: %s" % (type(exc).__name__, exc))

    # ---------- 2) legacy_product
    arrivals_legacy, meta_legacy = traffic_gen.generate_for_lot(
        params, LOT, 1, p_ev=0.30, scenario_model="legacy_product")
    record("legacy.meta_flags",
           meta_legacy["scenario_model"] == "legacy_product"
           and meta_legacy["product_coupled"] is True,
           "scenario_model=legacy_product, product_coupled=True",
           "scenario_model=%r product_coupled=%r"
           % (meta_legacy["scenario_model"], meta_legacy["product_coupled"]))
    q_legacy = float(meta_legacy["q_need"])
    expected_from_required = product_required / 0.30
    observed_product = meta_legacy.get("observed_product_p_ev_q_need")
    expected_from_observed = (float(observed_product) / 0.30
                              if observed_product is not None else float("nan"))
    # 发布参数里 lambda_bar 与 24 小时 bin 加权均值有 ~2% 差异，两种分母都列出来给审计看
    hours = params["bins"]["local_hour"]
    minutes = params["bins"]["minutes_observed"]
    lam_by_bin = lot_entry["lambda_hour_by_bin"]
    num = den = 0.0
    for idx, hour in enumerate(hours):
        if idx < len(lam_by_bin) and lam_by_bin[idx] is not None:
            weight = minutes[idx] if idx < len(minutes) else 60.0
            num += float(lam_by_bin[idx]) * weight
            den += weight
    lam_profile_mean = num / den if den else float("nan")
    expected_from_profile = (float(meta_legacy["observed_charge_session_per_hour"])
                             / (lam_profile_mean * 0.30)) if lam_profile_mean else float("nan")
    relative_tolerance = 0.05
    candidates = [("product_required_mean/p_ev", expected_from_required),
                  ("observed_product/p_ev", expected_from_observed),
                  ("observed_rate/(profile_lambda_mean*p_ev)", expected_from_profile)]
    scored = [(label, value, abs(q_legacy - value) / value)
              for label, value in candidates if value and not math.isnan(value)]
    best = min(scored, key=lambda item: item[2])
    record("legacy.q_need_equals_product_over_p_ev",
           best[2] <= relative_tolerance,
           "product/p_ev within %.0f%%; required->%.6f, observed->%.6f, profile_lambda->%.6f"
           % (100.0 * relative_tolerance, expected_from_required,
              expected_from_observed, expected_from_profile),
           "q_need_used=%.6f (best match %s, rel err %.2f%%)"
           % (q_legacy, best[0], 100.0 * best[2]),
           "lambda_bar=%.4f vs profile_mean=%.4f"
           % (float(lot_entry.get("lambda_bar_veh_per_hour") or 0.0), lam_profile_mean))

    arrivals_clip, meta_clip = traffic_gen.generate_for_lot(
        params, LOT, 1, p_ev=0.30, q_need=1.2, scenario_model="legacy_product")
    record("legacy.q_need_1p2_clipped",
           float(meta_clip["q_need"]) == 1.0 and meta_clip["clipped"] is True,
           "q_need_used=1.0, clipped=True",
           "q_need_used=%r clipped=%r" % (meta_clip["q_need"], meta_clip["clipped"]))

    # ---------- 3) strict / 非法输入
    strict_cases = [
        ("strict.q_need_1p2_raises", {"p_ev": 0.30, "q_need": 1.2, "strict": True},
         "legacy_product"),
        ("strict.q_need_nan_raises", {"p_ev": 0.30, "q_need": float("nan")},
         "legacy_product"),
        ("strict.q_need_inf_raises", {"p_ev": 0.30, "q_need": float("inf")},
         "legacy_product"),
        ("strict.independent_without_q_need_raises", {"p_ev": 0.30},
         "independent"),
    ]
    for name, kwargs, scenario in strict_cases:
        try:
            traffic_gen.generate_for_lot(params, LOT, 1, scenario_model=scenario, **kwargs)
        except ValueError as exc:
            record(name, True, "ValueError", "ValueError: %s" % str(exc)[:80])
        except Exception as exc:  # noqa: BLE001
            record(name, False, "ValueError", "%s: %s" % (type(exc).__name__, exc))
        else:
            record(name, False, "ValueError", "no exception raised")

    # ---------- 4) 哈希可复现与第二轮基线
    a1, m1 = traffic_gen.generate_for_lot(params, LOT, 1)
    a2, m2 = traffic_gen.generate_for_lot(params, LOT, 1)
    h1 = stream_digest(a1)
    h2 = stream_digest(a2)
    record("repro.same_seed_same_params_same_digest", h1 == h2,
           "two runs share one demand digest", h1[:16] + " .. " + h2[:16])
    baseline_actual = traffic_hash(a1)
    record("repro.default_legacy_call_matches_round2_baseline",
           baseline_actual == BASELINE_HASH,
           BASELINE_HASH[:16] + "..", baseline_actual[:16] + "..",
           "traffic_hash(generate_for_lot(TPE0008, seed=1))")
    a_exp, _ = traffic_gen.generate_for_lot(params, LOT, 1, p_ev=0.30,
                                            scenario_model="legacy_product")
    explicit_hash = traffic_hash(a_exp)
    record("repro.explicit_p_ev_0p30_matches_round2_baseline",
           explicit_hash == BASELINE_HASH,
           BASELINE_HASH[:16] + "..", explicit_hash[:16] + "..",
           "round-2 call form: p_ev=0.30, q_need=None")

    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    overall = passed == total
    payload = {
        "schema": "round3_verify_generator_independent/v1",
        "created": "2026-10-31",
        "generator_version": getattr(traffic_gen, "GENERATOR_VERSION", "unknown"),
        "params_path": str(PARAMS_PATH.relative_to(REPO)),
        "params_sha256": hashlib.sha256(PARAMS_PATH.read_bytes()).hexdigest(),
        "lot": LOT,
        "baseline_traffic_hash": BASELINE_HASH,
        "independent": {"seeds": SEEDS, "p_ev": p_ev, "q_need": q_need,
                        "n_arrivals": n_total, "n_ev": n_ev, "n_ev_need": n_ev_need,
                        "p_hat": p_hat, "q_hat_given_ev": q_hat,
                        "sigma_p": sigma_p, "sigma_q": sigma_q,
                        "z_observed_p_ev_times_q_need": z_observed,
                        "small_p_ev_tested": small_p},
        "hashes": {"demand_digest_same_seed": h1, "default_call_traffic_hash": baseline_actual,
                   "explicit_p_ev_030_traffic_hash": explicit_hash,
                   "default_call_stream_hash": m1.get("stream_hash")},
        "checks": results,
        "passed": passed,
        "total": total,
        "overall": "PASS" if overall else "FAIL",
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("")
    print("RESULT %d/%d PASS -> %s" % (passed, total, "PASS" if overall else "FAIL"))
    print("JSON", str(OUT_JSON.relative_to(REPO)))
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
