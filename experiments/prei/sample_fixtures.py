"""Sample the fixed PREI fixtures once, then never re-draw during evaluation.

Two fixtures:
* deterministic_24h: the received final_tvr hourly t array and exact v1 rates,
  21 EV-share targets, no RNG.  Directly comparable cell-by-cell with
  audit_numeric.deterministic_formula.
* v2_sampled: four NB/Beta/VOT scenario days from the received v2 parameters,
  21 EV-share targets each.  The Python seed documents Python repetition only;
  it is not a cross-language common random stream and the finite-sample argmin
  is not treated as the .70 acceptance target.

Parameters are read from audit_numeric.parameters() rather than re-typed, and
asserted against the source files before writing.  Run with --force only to
create a deliberately new fixture generation; existing fixtures are hashed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # never write caches into the read-only audit tree

import numpy as np
from scipy.special import expit
from scipy.stats import lognorm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
AUDIT = ROOT / "research" / "electrification" / "matlab_audit_20261029"
CONFIGS = HERE / "configs"
FIXTURES = HERE / "fixtures"
COLUMNS = [
    "scenario_id", "hour", "ev_share_target", "total_arrivals",
    "ev_share_actual", "ev_fuel_cost", "ice_fuel_cost",
    "ev_time_cost", "ice_time_cost",
    "ev_complaint_cost", "ice_complaint_cost",
]
PY_SEED = 20261029
V2_DAYS = 4


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_parameters():
    spec = importlib.util.spec_from_file_location("audit_numeric", AUDIT / "audit_numeric.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parameters()


def read_configs():
    cases = {}
    for path in sorted(CONFIGS.glob("*.json")):
        cfg = json.loads(path.read_text("utf-8"))
        cases.setdefault(cfg["source_case"], {})[cfg["model_variant"]] = (path, cfg)
    return cases


def verify_contract(cases, p, q):
    v1 = cases["final_tvr"]["legacy_reference"][1]
    v2 = cases["final_tvr_v2_fluc_re"]["corrected_baseline"][1]
    assert v1["n_spaces"] == p["n"] == 40, (v1["n_spaces"], p["n"])
    assert v1["installation_cost_rmb_per_pile"] == p["installation"] == 70100
    assert v1["amortization_years"] == p["years"] == 8
    assert v2["n_spaces"] == q["n"] == 10786, (v2["n_spaces"], q["n"])
    assert v2["installation_cost_rmb_per_pile"] == q["installation"] == 60000
    assert v2["amortization_years"] == q["years"] == 5
    assert q["od_arr_min"] == 42 and q["rho_nev_min"] == .09
    assert v1["pile_ratios"] == v2["pile_ratios"]
    assert v1["ev_share_targets"] == v2["ev_share_targets"]


def write_fixture(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def rate_fields(ev_fuel, ice_fuel, ev_time, ice_time, ev_complaint, ice_complaint):
    return {
        "ev_fuel_cost": ev_fuel, "ice_fuel_cost": ice_fuel,
        "ev_time_cost": ev_time, "ice_time_cost": ice_time,
        "ev_complaint_cost": ev_complaint, "ice_complaint_cost": ice_complaint,
    }


def deterministic_fixture(p):
    rates = rate_fields(
        p["cgev"], p["cgicv"], p["ctev"], p["cticv"],
        p["ccev"] * p["ccevp"], p["ccicv"] * p["ccicvp"])
    rows = []
    for target in np.arange(21) / 20:
        for hour, total in enumerate(p["t"]):
            rows.append({
                "scenario_id": "final_tvr_det", "hour": hour,
                "ev_share_target": float(target), "total_arrivals": float(total),
                "ev_share_actual": float(target), **rates,
            })
    meta = {
        "fixture": "deterministic_24h",
        "source_case": "final_tvr",
        "sampling": "none; closed-form received hourly t array and exact rates",
        "seed": None,
        "seed_scope": "not_applicable",
        "n_spaces": p["n"],
        "t_hourly_vehicles": [float(x) for x in p["t"]],
        "unit_rates_rmb_per_rejected_vehicle_per_day": rates,
        "rate_origin": {
            "ev_fuel": "cgev (final_tvr.m:15)",
            "ice_fuel": "cgicv",
            "ev_time": "ctev", "ice_time": "cticv",
            "ev_complaint": "ccev*ccevp", "ice_complaint": "ccicv*ccicvp",
        },
        "comparison": "all 441 (r, EV-share) cells comparable with audit_numeric.deterministic_formula",
    }
    return rows, meta


def v2_fixture(q):
    rng = np.random.default_rng(PY_SEED)
    # VOT: the received script's permuted stratified quantiles (nsim=50).
    nsim = int(q["nsim"])
    quantiles = ((np.arange(nsim) + .5) / nsim)
    permutation = rng.permutation(nsim)
    vot_draws = lognorm.ppf(quantiles[permutation], s=q["sig_ct"],
                            scale=math.exp(q["mu_ct"]))
    day_rate_rows = []
    rows = []
    for day in range(V2_DAYS):
        vot = float(vot_draws[day])
        ctev = vot * 6.81 / 60.0
        ccevp = float(expit(-q["alpha_cp"] - q["beta_cp"] * math.log(vot)))
        rates = rate_fields(
            q["cgev"] + q["cfev"], q["cgicv"] + q["cficv"],
            ctev, ctev, q["ccev"] * ccevp, q["ccicv"] * ccevp)
        arrivals = []
        for mu in q["t"]:
            mu = max(float(mu), 1e-6)
            var = max(mu * q["od_arr_min"], mu + 1e-6)
            shape = mu * mu / max(var - mu, 1e-6)
            prob = shape / (shape + mu)
            arrivals.append(int(rng.negative_binomial(shape, prob)))
        realized = []
        for target in np.arange(21) / 20:
            u = min(max(1.0 - float(target), 1e-4), 1 - 1e-4)
            var_u = q["rho_nev_min"] * u * (1 - u)
            phi = max(u * (1 - u) / var_u - 1.0, 2.0)
            for hour, total in enumerate(arrivals):
                u_actual = float(rng.beta(u * phi, (1 - u) * phi))
                realized.append(1.0 - u_actual)
                rows.append({
                    "scenario_id": f"v2_day{day + 1:02d}", "hour": hour,
                    "ev_share_target": float(target), "total_arrivals": total,
                    "ev_share_actual": 1.0 - u_actual, **rates,
                })
        day_rate_rows.append({
            "day": f"v2_day{day + 1:02d}",
            "vot_rmb_per_hour": vot,
            "ctev_rmb_per_rejected_vehicle": ctev,
            "complaint_probability": ccevp,
            "total_arrivals": int(sum(arrivals)),
            "hourly_arrivals": arrivals,
            "realised_daily_ev_share_by_target": {
                f"{t:.2f}": sum(a * s for a, s in zip(arrivals, realized[i * 24:(i + 1) * 24])) / max(sum(arrivals), 1)
                for i, t in enumerate(np.arange(21) / 20)
            },
        })
    meta = {
        "fixture": "v2_sampled",
        "source_case": "final_tvr_v2_fluc_re",
        "sampling": "one-shot NB arrivals, Beta EV-share, permuted stratified lognormal VOT; sampled before evaluation",
        "python_seed": PY_SEED,
        "rng": "numpy.random.default_rng PCG64",
        "seed_scope": "python_replication_only; not a MATLAB/Octave common random stream",
        "seed_not_acceptance": "finite-sample argmin and ETP are not acceptance targets; .70 remains only a comparison value",
        "n_spaces": q["n"],
        "days_sampled": V2_DAYS,
        "targets_per_day": 21,
        "units_and_variance": {
            "total_arrivals": "vehicles per hour (count)",
            "ev_share_target": "target EV fraction of arrivals, dimensionless",
            "ev_share_actual": "realised EV fraction of arrivals, dimensionless",
            "od_arr_min": "NB variance/mean ratio = 42 (dimensionless); this is dispersion, NOT an absolute variance and NOT the .09 value",
            "rho_nev_min": "relative dispersion rho = Var[u]/(u*(1-u)) = 0.09; absolute Beta variance at target e is rho*(1-e)*e",
            "vot_rmb_per_hour": "lognormal mu=2.9852, sigma=0.8477 on natural-log scale, RMB/hour",
            "ctev": "vot*6.81/60, RMB per rejected vehicle",
            "complaint_probability": "expit(-6.938+2.324*ln(vot)), dimensionless [0,1]",
            "unit_rates": "RMB per rejected vehicle per day, constant within a day",
        },
        "source_parameters": {
            "alpha_cp": q["alpha_cp"], "beta_cp": q["beta_cp"],
            "mu_ct": q["mu_ct"], "sig_ct": q["sig_ct"],
            "rho_nev_min": q["rho_nev_min"], "od_arr_min": q["od_arr_min"],
            "nsim": q["nsim"], "power_kw": q["power"],
            "installation": q["installation"], "years": q["years"],
        },
        "vot_permutation": [int(x) for x in permutation],
        "vot_draws_rmb_per_hour": [float(x) for x in vot_draws],
        "day_draws": day_rate_rows,
    }
    return rows, meta


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing fixture generation (default: refuse)")
    args = parser.parse_args()

    p, q = audit_parameters()
    cases = read_configs()
    verify_contract(cases, p, q)
    outputs = [
        (FIXTURES / "deterministic_24h" / "fixture.csv", *deterministic_fixture(p)),
        (FIXTURES / "v2_sampled" / "fixture.csv", *v2_fixture(q)),
    ]
    for path, rows, meta in outputs:
        if path.exists() and not args.force:
            raise SystemExit(f"refusing to overwrite existing fixture {path}; use --force")
        write_fixture(path, rows)
        meta["fixture_sha256"] = sha256_file(path)
        meta["fixture_file"] = str(path.relative_to(ROOT))
        meta["generated_utc"] = datetime.now(timezone.utc).isoformat()
        meta["environment"] = {
            "python": sys.version, "executable": sys.executable,
            "numpy": np.__version__, "platform": platform.platform(),
        }
        meta["source_hashes"] = {
            "audit_numeric.py": sha256_file(AUDIT / "audit_numeric.py"),
            **{f"originals/{name}": sha256_file(AUDIT / "originals" / name)
               for name in ("final_tvr.m", "final_tvr_v2_fluc_re.m")},
            "sample_fixtures.py": sha256_file(Path(__file__)),
            "schema.json": sha256_file(HERE / "schema.json"),
        }
        (path.parent / "fixture_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", "utf-8")
        (path.parent / "source_hashes.json").write_text(
            json.dumps(meta["source_hashes"], indent=2) + "\n", "utf-8")
        print(f"wrote {path} rows={len(rows)} sha256={meta['fixture_sha256']}")


if __name__ == "__main__":
    main()
