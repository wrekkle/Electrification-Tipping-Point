# -*- coding: utf-8 -*-
"""Independent verification of the calibrated traffic generator.

Recomputes, from fitted_parameters.json and data/panel_selected_lots.json:
  - warm start: occupancy at t=0 and the 24 h mean occupancy vs the observed mean;
  - hourly arrival counts vs the lot's measured lambda profile;
  - occupancy curve RMSE / correlation per 100 spaces;
  - dwell mixture quantiles vs generated dwells;
  - charge session count and duration KS vs the observed span-duration sample;
  - energy/power feasibility and same-seed cross-process stream hash.
Writes outputs/verify_report.json and outputs/sample_traffic_seed42.json.
"""
from __future__ import annotations

import io
import json
import math
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))

from apps.parking_lab.workbench import traffic_gen  # noqa: E402

SEED = 42
TZ = timezone(timedelta(hours=8))
GRID_MIN = 5
N_GRID = 1440 // GRID_MIN


def pearson(x, y):
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else None


def ks_two_sample(a, b):
    if not a or not b:
        return None
    xs = sorted(set(a) | set(b))
    sa, sb = sorted(a), sorted(b)
    i = j = 0
    best = 0.0
    na, nb = len(sa), len(sb)
    for x in xs:
        while i < na and sa[i] <= x:
            i += 1
        while j < nb and sb[j] <= x:
            j += 1
        best = max(best, abs(i / na - j / nb))
    return best


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    lo = int(math.floor(k))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _mixture_mean(dwell):
    import random as _random
    rng = _random.Random(20261031)
    comps = traffic_gen._components(dwell)
    return sum(traffic_gen._sample_dwell(comps, rng) for _ in range(5000)) / 5000.0


def local_minute(iso):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)
    return dt.hour * 60 + dt.minute


def occupancy_grid(arrivals):
    grid = [0.0] * N_GRID
    for a in arrivals:
        start = int(a.time_min // GRID_MIN)
        end = int(math.ceil((a.time_min + a.dwell_min) / GRID_MIN))
        for idx in range(max(0, start), min(N_GRID, end)):
            grid[idx] += 1.0
    return grid


def weighted_hours(hours, values, minutes):
    num = [0.0] * 24
    den = [0.0] * 24
    for idx, hour in enumerate(hours):
        if idx >= len(values) or values[idx] is None:
            continue
        w = minutes[idx] if idx < len(minutes) else 60.0
        num[hour % 24] += float(values[idx]) * w
        den[hour % 24] += w
    return [num[h] / den[h] if den[h] else 0.0 for h in range(24)]


def main():
    params = traffic_gen.load_params(HERE / "fitted_parameters.json")
    panel = json.loads((HERE / "data" / "panel_selected_lots.json").read_text(encoding="utf-8"))
    charge = json.loads((HERE / "data" / "charge_sessions_summary.json").read_text(encoding="utf-8"))
    slots = panel["slot_start_utc"]
    power = float(params["energy"]["charger_power_kw"])
    eff = float(params["energy"]["efficiency"])
    hours = params["bins"]["local_hour"]
    minutes = params["bins"]["minutes_observed"]
    cons = {r["lot_id"]: r for r in params["consistency"]["rows"]}
    per_lot = []
    sim_charge_durations = []
    for entry in params["per_lot"]:
        if not entry.get("usable"):
            continue
        lot_id = entry["lot_id"]
        lot_panel = panel["lots"].get(lot_id)
        if not lot_panel:
            continue
        cap = float(lot_panel["n_spaces"])
        obs = lot_panel["occupancy_vehicles"]
        arrivals, meta = traffic_gen.generate_for_lot(params, lot_id, SEED)
        grid = occupancy_grid(arrivals)
        n_warm = int(meta["initial_occupancy_n"])
        new_arrivals = arrivals[n_warm:]  # warm-start rows are present at t=0, not new arrivals
        gen_counts = [0] * 24
        for a in new_arrivals:
            gen_counts[int(a.time_min // 60) % 24] += 1
        obs_rate = weighted_hours(hours, entry["lambda_hour_by_bin"], minutes)
        hours_obs = [obs_rate[h] for h in range(24)]
        hours_gen = [float(gen_counts[h]) for h in range(24)]
        gen_at, obs_at = [], []
        for k, slot in enumerate(slots):
            if obs[k] is None:
                continue
            minute = local_minute(slot)
            if not (720 <= minute <= 1430):
                continue  # left edge: previous-day arrivals are unknown
            idx = minute // GRID_MIN
            gen_at.append(100.0 * grid[idx] / cap)
            obs_at.append(100.0 * obs[k] / cap)
        resid = [a - b for a, b in zip(obs_at, gen_at)]
        rmse = math.sqrt(sum(r * r for r in resid) / len(resid)) if resid else None
        dwells = sorted(a.dwell_min for a in new_arrivals)
        lot_charge = sorted(a.energy_kwh / (power * eff) * 60.0 for a in new_arrivals if a.needs_charge)
        sim_charge_durations.extend(lot_charge)
        lot_cons = cons.get(lot_id, {})
        row = {
            "lot_id": lot_id, "fit_split": entry.get("fit_split"), "n_spaces": cap,
            "warm_start_n": meta["initial_occupancy_n"],
            "occupancy_t0": grid[0],
            "occupancy_mean_24h": sum(grid) / len(grid),
            "occupancy_mean_observed": float(entry["mean_occupancy_vehicles"]),
            "occupancy_t0_relative_error": (grid[0] - float(entry["mean_occupancy_vehicles"]))
            / max(1.0, float(entry["mean_occupancy_vehicles"])),
            "n_arrivals_sim": len(new_arrivals),
            "n_arrivals_incl_warm": len(arrivals),
            "lambda_bar_observed_veh_per_hour": entry["lambda_bar_veh_per_hour"],
            "hourly_arrival_rmse_veh_per_hour": math.sqrt(
                sum((a - b) ** 2 for a, b in zip(hours_obs, hours_gen)) / 24.0),
            "hourly_arrival_r": pearson(hours_obs, hours_gen),
            "occupancy_rmse_veh_per_100": rmse,
            "occupancy_relative_rmse": (rmse / (sum(obs_at) / len(obs_at))) if rmse else None,
            "occupancy_r": pearson(obs_at, gen_at),
            "mean_obs_veh_per_100": sum(obs_at) / len(obs_at),
            "mean_sim_veh_per_100": sum(gen_at) / len(gen_at),
            "peak_obs_veh_per_100": max(obs_at), "peak_sim_veh_per_100": max(gen_at),
            "dwell_mean_min": sum(dwells) / len(dwells),
            "dwell_mixture_sampled_mean_min": _mixture_mean(entry["dwell_dist"]),
            "dwell_p50_min": percentile(dwells, 0.5),
            "dwell_p90_min": percentile(dwells, 0.9),
            "dwell_fitted_p50_min": entry["dwell_dist"].get("p50_min"),
            "dwell_fitted_p90_min": entry["dwell_dist"].get("p90_min"),
            "dwell_fitted_mean_min": entry["dwell_dist"].get("mean_min"),
            "mean_dwell_little_min": lot_cons.get("mean_dwell_little_min"),
            "observed_charge_sessions_per_day": meta["observed_sessions_per_day"],
            "target_charge_sessions": meta["target_charge_arrivals"],
            "p_ev": meta["p_ev"], "q_need": meta["q_need"],
            "observed_product_p_ev_q_need": meta["observed_product_p_ev_q_need"],
            "identification_conflict": meta["identification_conflict"],
            "n_charge_sessions_sim": len(lot_charge),
            "charge_shortfall_sessions": meta.get("charge_shortfall_sessions"),
            "stream_hash": meta["stream_hash"],
        }
        per_lot.append(row)
    obs_durations = []
    for key, count in (charge["pooled_train"]["duration_hist_5min"] or {}).items():
        obs_durations.extend([float(key)] * int(count))
    ks = ks_two_sample(sim_charge_durations, obs_durations)
    big_arrivals, big_meta = traffic_gen.generate(params, SEED)
    derived = sorted(a.energy_kwh / (power * eff) * 60.0 for a in big_arrivals if a.needs_charge)
    code = ("import sys; sys.path.insert(0, %r);"
            "from apps.parking_lab.workbench import traffic_gen as t;"
            "p = t.load_params(%r);"
            "a, m = t.generate(p, %d);"
            "print(m['stream_hash'])" % (str(REPO), str(HERE / "fitted_parameters.json"), SEED))
    proc_hashes = []
    for _ in range(2):
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        proc_hashes.append(proc.stdout.strip() if proc.returncode == 0
                           else "ERROR:%s" % proc.stderr.strip()[:200])
    in_process = big_meta["stream_hash"]
    valid_rows = [r for r in per_lot if r["occupancy_r"] is not None]
    report = {
        "generator_version": traffic_gen.GENERATOR_VERSION,
        "seed": SEED,
        "params_file": str(HERE / "fitted_parameters.json"),
        "params_hash": big_meta["params_hash"],
        "split": big_meta["split"],
        "n_lots_verified": len(per_lot),
        "lots": per_lot,
        "pooled": {
            "occupancy_rmse_veh_per_100_mean": sum(r["occupancy_rmse_veh_per_100"] for r in per_lot) / len(per_lot),
            "occupancy_relative_rmse_mean": sum(r["occupancy_relative_rmse"] for r in per_lot) / len(per_lot),
            "occupancy_r_mean": sum(r["occupancy_r"] for r in valid_rows) / len(valid_rows),
            "hourly_arrival_r_mean": sum(r["hourly_arrival_r"] for r in valid_rows) / len(valid_rows),
            "hourly_arrival_rmse_mean": sum(r["hourly_arrival_rmse_veh_per_hour"] for r in per_lot) / len(per_lot),
            "occupancy_t0_relative_error_mean": sum(abs(r["occupancy_t0_relative_error"]) for r in per_lot) / len(per_lot),
            "charge_duration_ks_vs_observed": ks,
            "observed_charge_duration_n": len(obs_durations),
            "sim_charge_duration_n": len(sim_charge_durations),
        },
        "hash_check": {"in_process": in_process, "fresh_process_1": proc_hashes[0],
                       "fresh_process_2": proc_hashes[1],
                       "consistent": bool(proc_hashes[0] == proc_hashes[1] == in_process)},
        "checks": {
            "arrivals_sorted": all(big_arrivals[i].time_min <= big_arrivals[i + 1].time_min
                                   for i in range(len(big_arrivals) - 1)),
            "energy_within_power_window": all(
                a.energy_kwh <= power * eff * a.dwell_min / 60.0 + 1e-6 for a in big_arrivals),
            "needs_charge_implies_ev": all(a.is_ev for a in big_arrivals if a.needs_charge),
            "dwell_mixture_mean_matches_little_by_lot": all(
                abs(r["dwell_mixture_sampled_mean_min"] - r["dwell_fitted_mean_min"])
                / max(1.0, r["dwell_fitted_mean_min"]) < 0.05
                for r in per_lot if r["dwell_fitted_mean_min"]),
        },
    }
    out_dir = HERE / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "verify_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    traffic_gen.save_traffic(out_dir / "sample_traffic_seed42.json", big_arrivals, big_meta)
    print("VERIFY", json.dumps({"n_lots": len(per_lot), "pooled": report["pooled"],
                                "hash_check": report["hash_check"], "checks": report["checks"],
                                "big_n": len(big_arrivals)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
