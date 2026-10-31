"""Independent language-neutral reference for the PREI fixed-scenario model.

Reads one config JSON (schema_version=1) and its fixed fixture CSV, allocates
arrivals, prices every rejection event, and writes a raw candidate-by-day cost
matrix plus the mandated daily-optimal CSV.  No random sampling happens here:
scenarios are sampled once by sample_fixtures.py and hashed.  All outputs go to
an explicit --out directory that must be new or empty.

Model notes
-----------
* N is total parking spaces.  At pile ratio r: ordinary bays N*(1-r), charging
  bays N*r.  A fraction h of charging bays is shared with ICEV when r<1.
* ICEV fill ordinary bays first, then shared bays.  EV use dedicated bays
  N*r*(1-h) first, then whatever shared capacity ICEV left.
* r=1 with full_install_open_to_all: only overflow above N is rejected, split
  by the realised EV/ICEV shares (the received scripts' rule change).
* Capital N*r*installation/(365*years) is charged once per day, not per hour.
* legacy_reference reproduces the received full-install omission of the EV
  complaint term and is diagnostic_only; it is not a re-run of the original
  random stream.  corrected_baseline prices every rejected vehicle once.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.json"
FIXTURE_COLUMNS = [
    "scenario_id", "hour", "ev_share_target", "total_arrivals",
    "ev_share_actual", "ev_fuel_cost", "ice_fuel_cost",
    "ev_time_cost", "ice_time_cost",
    "ev_complaint_cost", "ice_complaint_cost",
]
RESULT_COLUMNS = FIXTURE_COLUMNS
MATRIX_COLUMNS = [
    "scenario_id", "ev_share_target", "pile_ratio", "total_arrivals",
    "ev_share_actual", "capital_daily_cost", "ev_rejected", "ice_rejected",
    "ev_fuel_cost", "ice_fuel_cost", "ev_time_cost", "ice_time_cost",
    "ev_complaint_cost", "ice_complaint_cost", "total_daily_cost",
    "is_optimal", "g_full_minus_best_partial", "delta_candidate_minus_full",
]
TOL_ATOL = 1e-8
TOL_RTOL = 1e-10


class ContractError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition, message):
    if not condition:
        raise ContractError(message)


def validate_config(cfg, base_dir: Path):
    """JSON-Schema validation plus semantics the schema cannot express."""
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ContractError("jsonschema is required to validate configs") from exc
    schema = json.loads(SCHEMA_PATH.read_text("utf-8"))
    try:
        jsonschema.validate(cfg, schema)
    except jsonschema.ValidationError as exc:
        raise ContractError(f"config schema error: {exc.message}") from exc

    _require(type(cfg["schema_version"]) is int and cfg["schema_version"] == 1,
             "schema_version must be integer 1")
    ratios = cfg["pile_ratios"]
    _require(ratios == sorted(ratios) and len(set(ratios)) == len(ratios),
             "pile_ratios must be strictly increasing with no duplicates")
    _require(ratios[0] >= 0 and ratios[-1] <= 1, "pile_ratios must lie in [0,1]")
    _require(1 in ratios, "pile_ratios must include 1 (full install is required)")
    targets = cfg["ev_share_targets"]
    _require(targets == sorted(targets) and len(set(targets)) == len(targets),
             "ev_share_targets must be strictly increasing with no duplicates")
    fixture = (base_dir / cfg["fixture_file"]).resolve()
    _require(fixture.is_file(), f"fixture_file not found: {fixture}")
    cfg["_fixture_path"] = fixture
    cfg["_config_dir"] = base_dir
    return cfg


def load_config(path) -> dict:
    path = Path(path).resolve()
    try:
        cfg = json.loads(path.read_text("utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"config is not valid JSON: {exc}") from exc
    cfg = validate_config(cfg, path.parent)
    cfg["_config_path"] = path
    return cfg


def _as_float(value, column, line):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"line {line}: {column} is not numeric: {value!r}") from exc
    _require(math.isfinite(result), f"line {line}: {column} is not finite")
    return result


def load_fixture(cfg) -> list[dict]:
    """Return day dicts: key, hours, rates, daily totals. Validates the contract."""
    path = cfg["_fixture_path"]
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require(reader.fieldnames == FIXTURE_COLUMNS,
                 f"fixture columns must be exactly {FIXTURE_COLUMNS}; got {reader.fieldnames}")
        days = {}
        for line, row in enumerate(reader, start=2):
            scenario_id = (row["scenario_id"] or "").strip()
            _require(scenario_id, f"line {line}: empty scenario_id")
            hour = row["hour"].strip()
            _require(hour.isdigit() and 0 <= int(hour) <= 23,
                     f"line {line}: hour must be an integer in 0..23")
            hour = int(hour)
            target = _as_float(row["ev_share_target"], "ev_share_target", line)
            _require(0 <= target <= 1, f"line {line}: ev_share_target outside [0,1]")
            total = _as_float(row["total_arrivals"], "total_arrivals", line)
            _require(total >= 0, f"line {line}: negative total_arrivals")
            actual = _as_float(row["ev_share_actual"], "ev_share_actual", line)
            _require(0 <= actual <= 1, f"line {line}: ev_share_actual outside [0,1]")
            rates = {
                column: _as_float(row[column], column, line)
                for column in FIXTURE_COLUMNS[5:]
            }
            for name, value in rates.items():
                _require(value >= 0, f"line {line}: negative unit rate {name}")
            key = (scenario_id, target)
            day = days.setdefault(key, {
                "scenario_id": scenario_id, "ev_share_target": target,
                "hours": {}, "rates": None, "fixture_file": path,
            })
            _require(hour not in day["hours"], f"line {line}: duplicate hour {hour} for {key}")
            if day["rates"] is None:
                day["rates"] = rates
            else:
                for name, value in rates.items():
                    _require(math.isclose(value, day["rates"][name], rel_tol=0, abs_tol=1e-12),
                             f"line {line}: unit rate {name} changes inside day {key}")
            day["hours"][hour] = {"total_arrivals": total, "ev_share_actual": actual}

    _require(days, "fixture contains no data rows")
    targets = set(cfg["ev_share_targets"])
    out = []
    for key in sorted(days, key=lambda k: (k[0], k[1])):
        day = days[key]
        _require(set(day["hours"]) == set(range(24)),
                 f"day {key} must contain exactly hours 0..23")
        _require(day["ev_share_target"] in targets,
                 f"fixture day {key} target is not listed in config ev_share_targets")
        hours = [day["hours"][h] for h in range(24)]
        day["total_arrivals"] = sum(h["total_arrivals"] for h in hours)
        if day["total_arrivals"] > 0:
            day["ev_share_actual"] = sum(
                h["total_arrivals"] * h["ev_share_actual"] for h in hours
            ) / day["total_arrivals"]
        else:
            day["ev_share_actual"] = day["ev_share_target"]
        day["hours"] = hours
        out.append(day)
    configured = {t for t in targets}
    present = {d["ev_share_target"] for d in out}
    _require(present == configured,
             f"fixture targets {sorted(present)} != config targets {sorted(configured)}")
    return out


def allocate(total_arrivals, ev_share_actual, n_spaces, pile_ratio,
             shared_fraction, open_to_all):
    """Return (ev_rejected, ice_rejected, accepted_ev, accepted_ice).

    Continuous capacities, no rounding.  Rejections are non-negative and each
    accepted vehicle occupies exactly one bay.
    """
    _require(total_arrivals >= 0, "negative arrivals")
    _require(0 <= ev_share_actual <= 1, "EV share outside [0,1]")
    _require(0 <= pile_ratio <= 1, "pile ratio outside [0,1]")
    _require(0 <= shared_fraction <= 1, "shared fraction outside [0,1]")
    ev_demand = total_arrivals * ev_share_actual
    ice_demand = total_arrivals * (1.0 - ev_share_actual)

    if pile_ratio >= 1.0 and open_to_all:
        overflow = max(total_arrivals - n_spaces, 0.0)
        ev_rejected = overflow * ev_share_actual
        ice_rejected = overflow * (1.0 - ev_share_actual)
    else:
        charging = n_spaces * pile_ratio
        ordinary = n_spaces - charging
        shared = charging * shared_fraction
        dedicated = charging * (1.0 - shared_fraction)
        ice_to_shared = min(max(ice_demand - ordinary, 0.0), shared)
        ice_rejected = max(ice_demand - ordinary - shared, 0.0)
        shared_left = shared - ice_to_shared
        ev_rejected = max(ev_demand - dedicated - shared_left, 0.0)

    ev_accepted = ev_demand - ev_rejected
    ice_accepted = ice_demand - ice_rejected
    scale = max(1.0, total_arrivals)
    _require(ev_rejected >= -1e-12 * scale and ice_rejected >= -1e-12 * scale,
             "negative rejection beyond floating tolerance")
    _require(ev_accepted + ice_accepted <= n_spaces + 1e-9 * max(1.0, n_spaces),
             "accepted vehicles exceed N")
    _require(ev_accepted >= -1e-9 and ice_accepted >= -1e-9,
             "negative accepted count")
    return (max(ev_rejected, 0.0), max(ice_rejected, 0.0),
            max(ev_accepted, 0.0), max(ice_accepted, 0.0))


def evaluate(cfg, days):
    """Return list of raw candidate rows (one per day x pile ratio)."""
    n = cfg["n_spaces"]
    h = cfg["partial_shared_fraction"]
    open_all = cfg["full_install_open_to_all"]
    years = cfg["amortization_years"]
    installation = cfg["installation_cost_rmb_per_pile"]
    legacy = cfg["model_variant"] == "legacy_reference"

    rows = []
    for day in days:
        rates = day["rates"]
        for ratio in cfg["pile_ratios"]:
            ev_rej = ice_rej = 0.0
            for hour in day["hours"]:
                e, i, _, _ = allocate(hour["total_arrivals"],
                                      hour["ev_share_actual"], n, ratio, h, open_all)
                ev_rej += e
                ice_rej += i
            capital = n * ratio * installation / (365.0 * years)
            ev_fuel = ev_rej * rates["ev_fuel_cost"]
            ice_fuel = ice_rej * rates["ice_fuel_cost"]
            ev_time = ev_rej * rates["ev_time_cost"]
            ice_time = ice_rej * rates["ice_time_cost"]
            ev_complaint = ev_rej * rates["ev_complaint_cost"]
            ice_complaint = ice_rej * rates["ice_complaint_cost"]
            if legacy and ratio >= 1.0:
                # Received full-install branch omits the EV complaint term.
                ev_complaint = 0.0
            total = capital + ev_fuel + ice_fuel + ev_time + ice_time + ev_complaint + ice_complaint
            rows.append({
                "scenario_id": day["scenario_id"],
                "ev_share_target": day["ev_share_target"],
                "pile_ratio": ratio,
                "total_arrivals": day["total_arrivals"],
                "ev_share_actual": day["ev_share_actual"],
                "capital_daily_cost": capital,
                "ev_rejected": ev_rej,
                "ice_rejected": ice_rej,
                "ev_fuel_cost": ev_fuel,
                "ice_fuel_cost": ice_fuel,
                "ev_time_cost": ev_time,
                "ice_time_cost": ice_time,
                "ev_complaint_cost": ev_complaint,
                "ice_complaint_cost": ice_complaint,
                "total_daily_cost": total,
            })

    # Optimal set (ties within the shared comparison tolerance) and signed gaps.
    by_day = {}
    for row in rows:
        by_day.setdefault((row["scenario_id"], row["ev_share_target"]), []).append(row)
    for group in by_day.values():
        best = min(r["total_daily_cost"] for r in group)
        full_row = next(r for r in group if r["pile_ratio"] == 1.0)
        partial = [r["total_daily_cost"] for r in group if r["pile_ratio"] < 1.0]
        partial_best = min(partial) if partial else full_row["total_daily_cost"]
        full = full_row["total_daily_cost"]
        for row in group:
            row["is_optimal"] = abs(row["total_daily_cost"] - best) <= (
                TOL_ATOL + TOL_RTOL * abs(best))
            row["g_full_minus_best_partial"] = full - partial_best
            row["delta_candidate_minus_full"] = row["total_daily_cost"] - full
    return rows


def _write_csv(path: Path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row[name] for name in columns})


def write_outputs(cfg, days, rows, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "raw_cost_matrix.csv", MATRIX_COLUMNS, rows)

    optimal_rows = []
    seen = set()
    for row in rows:
        key = (row["scenario_id"], row["ev_share_target"])
        if row["is_optimal"] and key not in seen:
            seen.add(key)
            optimal_rows.append({
                **row,
                "hour": 24,  # 24 means the aggregate whole scenario day
            })
    _write_csv(out_dir / "daily_optimal.csv", RESULT_COLUMNS, optimal_rows)

    source_hashes = {}
    for label, path in (
        ("reference.py", Path(__file__).resolve()),
        ("schema.json", SCHEMA_PATH),
        ("config", cfg["_config_path"]),
        ("fixture", cfg["_fixture_path"]),
    ):
        if path.is_file():
            source_hashes[label] = {"path": str(path), "sha256": sha256_file(path)}
    for path in sorted((HERE.parent.parent / "research" / "electrification"
                        / "matlab_audit_20261029").glob("originals/*.m")):
        source_hashes[f"original/{path.name}"] = {
            "path": str(path), "sha256": sha256_file(path)}

    summary = {
        "schema_version": 1,
        "model_variant": cfg["model_variant"],
        "diagnostic_only": cfg["model_variant"] == "legacy_reference",
        "source_case": cfg["source_case"],
        "contract": {
            "n_spaces": cfg["n_spaces"],
            "installation_cost_rmb_per_pile": cfg["installation_cost_rmb_per_pile"],
            "amortization_years": cfg["amortization_years"],
            "partial_shared_fraction": cfg["partial_shared_fraction"],
            "full_install_open_to_all": cfg["full_install_open_to_all"],
            "pile_ratios": cfg["pile_ratios"],
            "ev_share_targets": cfg["ev_share_targets"],
            "capital_unit": "RMB/day = N*r*installation/(365*years)",
            "cost_unit": "RMB per scenario day",
        },
        "input": {
            "config_sha256": source_hashes.get("config", {}).get("sha256"),
            "fixture_sha256": source_hashes.get("fixture", {}).get("sha256"),
            "fixture_file": str(cfg["_fixture_path"]),
            "days": len(days),
            "candidate_rows": len(rows),
        },
        "seed_scope": "none during evaluation; fixture was sampled once in Python",
        "tolerance": {"atol": TOL_ATOL, "rtol": TOL_RTOL},
        "environment": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "numpy": _module_version("numpy"),
        },
        "command": sys.argv,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "outputs": ["raw_cost_matrix.csv", "daily_optimal.csv", "summary.json", "metadata.json"],
        "sources": source_hashes,
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    (out_dir / "summary.json").write_text(text + "\n", "utf-8")
    (out_dir / "metadata.json").write_text(text + "\n", "utf-8")
    return summary


def _module_version(name):
    try:
        module = __import__(name)
        return getattr(module, "__version__", "unknown")
    except ImportError:
        return "not-installed"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True,
                        help="new or empty output directory; never overwrites non-empty history")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        print(f"refusing to overwrite non-empty output directory: {out}", file=sys.stderr)
        return 2
    try:
        cfg = load_config(args.config)
        days = load_fixture(cfg)
        rows = evaluate(cfg, days)
    except ContractError as exc:
        print(f"contract error: {exc}", file=sys.stderr)
        return 2
    summary = write_outputs(cfg, days, rows, out)
    print(json.dumps({
        "status": "ok",
        "model_variant": summary["model_variant"],
        "diagnostic_only": summary["diagnostic_only"],
        "days": summary["input"]["days"],
        "rows": summary["input"]["candidate_rows"],
        "out": str(out),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
