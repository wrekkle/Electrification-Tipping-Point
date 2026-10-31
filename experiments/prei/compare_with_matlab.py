"""Cross-language comparison entry for PREI outputs.

Reads the Python reference run and a MATLAB/Octave candidate run, first proving
that both declare the same fixed config and fixture hashes, then comparing every
numeric column at atol=1e-8 / rtol=1e-10 and the tied-optimal set per day.

A missing candidate is pending (exit 2), never a pass.  A candidate without
verifiable config/fixture hashes is unverified (exit 1), even if numbers match.
A same-path self-comparison is not a cross-language pass (exit 1).

Exit codes: 0 = same hashes + full matrix + all numbers/ties match;
1 = failed, unverified, partial, malformed or self-comparison;
2 = candidate output not delivered yet.  Never writes into either run.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ATOL = 1e-8
RTOL = 1e-10
KEY_COLUMNS = ("scenario_id", "ev_share_target", "pile_ratio")
NUMERIC_COLUMNS = (
    "total_arrivals", "ev_share_actual", "capital_daily_cost",
    "ev_rejected", "ice_rejected", "ev_fuel_cost", "ice_fuel_cost",
    "ev_time_cost", "ice_time_cost", "ev_complaint_cost", "ice_complaint_cost",
    "total_daily_cost", "g_full_minus_best_partial", "delta_candidate_minus_full",
)
DAILY_COLUMNS = (
    "total_arrivals", "ev_share_actual", "ev_fuel_cost", "ice_fuel_cost",
    "ev_time_cost", "ice_time_cost", "ev_complaint_cost", "ice_complaint_cost",
)
CONFIG_ALIASES = {
    "configsha256", "configsha", "confighash", "configchecksum",
    "configfilesha256", "sha256config", "configfilehash",
}
FIXTURE_ALIASES = {
    "fixturesha256", "fixturesha", "fixturehash", "fixturechecksum",
    "fixturefilesha256", "sha256fixture", "fixturefilehash", "scenariosha256",
    "scenariohash", "inputsha256", "inputsha", "inputhash", "inputchecksum",
}
METADATA_NAMES = ("run_metadata.json", "metadata.json", "summary.json", "manifest.json")


class CompareError(Exception):
    """Contract problem that should be reported, not raised as a traceback."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hex(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if value.startswith("sha256:"):
        value = value[7:]
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else None


def _collect_hashes(node, found):
    if isinstance(node, dict):
        for key, value in node.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            kind = None
            if normalized in CONFIG_ALIASES or (
                    "config" in normalized and normalized.endswith(("sha256", "sha", "hash", "checksum"))):
                kind = "config"
            elif normalized in FIXTURE_ALIASES or (
                    "fixture" in normalized and normalized.endswith(("sha256", "sha", "hash", "checksum"))):
                kind = "fixture"
            if kind and isinstance(value, str):
                cleaned = _hex(value)
                if cleaned:
                    found.setdefault(kind, set()).add(cleaned)
            elif kind and isinstance(value, dict):
                for subkey, subvalue in value.items():
                    if isinstance(subvalue, str) and re.sub(r"[^a-z0-9]", "", subkey.lower()) in (
                            "sha256", "sha", "hash", "checksum"):
                        cleaned = _hex(subvalue)
                        if cleaned:
                            found.setdefault(kind, set()).add(cleaned)
            _collect_hashes(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_hashes(item, found)


def read_metadata(directory: Path):
    if directory.is_file():
        directory = directory.parent
    if not directory.is_dir():
        return None, None
    for name in METADATA_NAMES:
        path = directory / name
        if path.is_file():
            try:
                data = json.loads(path.read_text("utf-8-sig"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CompareError(f"cannot read metadata {path}: {exc}") from exc
            found = {}
            _collect_hashes(data, found)
            hashes = {}
            for kind in ("config", "fixture"):
                values = found.get(kind, set())
                if len(values) > 1:
                    raise CompareError(
                        f"conflicting {kind} hashes in {path}: {sorted(values)}")
                if values:
                    hashes[kind] = next(iter(values))
            return path, hashes
    return None, None


def read_csv(path: Path, required):
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise CompareError(f"empty CSV: {path}") from exc
            header = [name.strip() for name in header]
            if len(set(header)) != len(header):
                duplicate = sorted({name for name in header if header.count(name) > 1})
                raise CompareError(f"duplicate CSV columns in {path}: {duplicate}")
            missing = [name for name in required if name not in header]
            if missing:
                raise CompareError(f"missing required columns in {path}: {missing}")
            rows = []
            for line_number, values in enumerate(reader, start=2):
                if not any(value.strip() for value in values):
                    continue
                if len(values) != len(header):
                    raise CompareError(
                        f"{path}:{line_number}: {len(values)} fields, expected {len(header)}")
                rows.append(dict(zip(header, values)))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise CompareError(f"cannot read CSV {path}: {exc}") from exc
    if not rows:
        raise CompareError(f"CSV has no data rows: {path}")
    return header, rows


def locate(candidate: Path):
    if candidate.is_file():
        return candidate
    if not candidate.is_dir():
        return None
    direct = [candidate / name for name in ("raw_cost_matrix.csv", "daily_optimal.csv")
              if (candidate / name).is_file()]
    if direct:
        return direct[0]
    found = sorted(candidate.glob("**/raw_cost_matrix.csv")) or sorted(
        candidate.glob("**/daily_optimal.csv"))
    if len(found) > 1:
        raise CompareError(f"multiple candidate result CSVs under {candidate}: "
                           f"{[str(p) for p in found]}")
    return found[0] if found else None


def numeric(value):
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def parse_flag(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return None


def key_of(row, with_ratio):
    scenario = str(row.get("scenario_id", "")).strip()
    if not scenario:
        return None, "empty scenario_id"
    try:
        target = float(row["ev_share_target"])
        if with_ratio:
            ratio = float(row["pile_ratio"])
    except (KeyError, TypeError, ValueError):
        return None, "non-numeric key"
    values = (target, ratio) if with_ratio else (target,)
    if any(not math.isfinite(v) for v in values):
        return None, "non-finite key"
    key = (scenario, round(target, 6))
    if with_ratio:
        key += (round(ratio, 6),)
    return key, None


def index_rows(rows, with_ratio):
    indexed, duplicates, bad = {}, [], []
    for row in rows:
        key, reason = key_of(row, with_ratio)
        if key is None:
            bad.append(reason)
            continue
        if key in indexed:
            duplicates.append(list(key))
        indexed[key] = row
    if duplicates:
        raise CompareError(f"duplicate result keys: {duplicates[:10]}")
    if bad:
        raise CompareError(f"invalid key rows: {bad[:10]}")
    return indexed


def optimal_sets(rows, with_ratio):
    """Derive ties from costs with the shared tolerance; validate flags if present."""
    groups, flag_errors = {}, []
    for key, row in rows.items():
        day = key[:2]
        cost = numeric(row.get("total_daily_cost"))
        if cost is None:
            raise CompareError(f"missing/non-numeric total_daily_cost for {key}")
        groups.setdefault(day, []).append((key[2] if with_ratio else None, cost, row))
    result, mismatches = {}, []
    for day, group in groups.items():
        best = min(cost for _, cost, _ in group)
        tie = {ratio for ratio, cost, _ in group
               if abs(cost - best) <= ATOL + RTOL * abs(best)}
        result[day] = tie
        for ratio, cost, row in group:
            flag = parse_flag(row.get("is_optimal"))
            if flag is None:
                flag_errors.append({"day": list(day), "pile_ratio": ratio,
                                    "reason": "is_optimal missing or not true/false/0/1"})
            elif flag != (ratio in tie):
                mismatches.append({"day": list(day), "pile_ratio": ratio,
                                   "flag": flag, "derived_from_cost": ratio in tie})
    return result, flag_errors, mismatches


def verify_metadata(label, directory, metadata_path, hashes):
    report = {"side": label, "metadata": str(metadata_path) if metadata_path else None,
              "hashes": hashes or {}}
    if metadata_path is None:
        report["status"] = "missing"
        return report
    report["status"] = "present" if hashes else "present_without_hashes"
    return report


def compare(reference: Path, candidate: Path):
    reference = reference.resolve()
    candidate = candidate.resolve()
    ref_meta_path, ref_hashes = read_metadata(reference)
    if not ref_hashes:
        return 2, {
            "status": "bad_reference",
            "reason": "reference metadata lacks verifiable config/fixture SHA-256",
            "metadata": str(ref_meta_path) if ref_meta_path else None,
        }
    cand_path = locate(candidate)
    if cand_path is None:
        return 2, {
            "status": "pending_matlab_output",
            "reason": f"no raw_cost_matrix.csv or daily_optimal.csv under {candidate}",
            "verdict": "NOT VERIFIED - do not treat as a pass",
        }
    if ref_meta_path and cand_path.parent == reference and cand_path.name == "raw_cost_matrix.csv":
        return 1, {"status": "self_comparison", "reason": "reference and candidate are the same run",
                   "verdict": "not a cross-language pass"}

    cand_meta_path, cand_hashes = read_metadata(cand_path.parent)
    input_identity = {
        "reference": verify_metadata("reference", reference, ref_meta_path, ref_hashes),
        "candidate": verify_metadata("candidate", cand_path.parent, cand_meta_path, cand_hashes),
        "config_sha256": {"reference": ref_hashes.get("config"),
                          "candidate": (cand_hashes or {}).get("config")},
        "fixture_sha256": {"reference": ref_hashes.get("fixture"),
                           "candidate": (cand_hashes or {}).get("fixture")},
    }
    identity_errors = []
    for kind in ("config", "fixture"):
        if kind not in (cand_hashes or {}):
            identity_errors.append(f"candidate metadata missing {kind} SHA-256")
        elif ref_hashes.get(kind) != cand_hashes[kind]:
            identity_errors.append(
                f"{kind} SHA-256 differs: reference {ref_hashes.get(kind)} "
                f"candidate {cand_hashes[kind]}")
    if cand_meta_path is None:
        identity_errors.append("candidate metadata missing")
    input_identity["same_fixed_input"] = not identity_errors
    input_identity["errors"] = identity_errors

    full_matrix = cand_path.name == "raw_cost_matrix.csv"
    columns = NUMERIC_COLUMNS if full_matrix else DAILY_COLUMNS
    full_required = list(KEY_COLUMNS) + list(NUMERIC_COLUMNS) + ["is_optimal"]
    daily_required = list(KEY_COLUMNS[:2]) + list(DAILY_COLUMNS)
    _, ref_rows_all = read_csv(reference / "raw_cost_matrix.csv", full_required)
    ref_all = index_rows(ref_rows_all, True)
    if full_matrix:
        _, cand_rows = read_csv(cand_path, full_required)
        ref = ref_all
        cand = index_rows(cand_rows, True)
    else:
        _, cand_rows = read_csv(cand_path, daily_required)
        cand = index_rows(cand_rows, False)
        ref_ties_all, _, _ = optimal_sets(ref_all, True)
        ref = {}
        for day, tie in ref_ties_all.items():
            if not tie:
                raise CompareError(f"no tied-optimal candidate for day {day}")
            ratio = min(tie)  # deterministic representative for the partial CSV check
            ref[day] = ref_all[(day[0], day[1], ratio)]
    missing = sorted(set(ref) - set(cand))
    extra = sorted(set(cand) - set(ref))
    failures, worst = [], {}
    for key in sorted(set(ref) & set(cand)):
        for column in columns:
            a, b = numeric(ref[key][column]), numeric(cand[key][column])
            if a is None or b is None:
                failures.append({"key": key, "column": column, "reason": "missing/non-numeric"})
                continue
            error = abs(a - b)
            allowed = ATOL + RTOL * abs(a)
            worst[column] = max(worst.get(column, 0.0), error)
            if error > allowed:
                failures.append({"key": key, "column": column,
                                 "reference": a, "candidate": b,
                                 "abs_error": error, "allowed": allowed})

    tie_mismatches, flag_errors = [], []
    optimal_compared = False
    if full_matrix:
        ref_ties, ref_flag_errors, ref_flag_mismatches = optimal_sets(ref, True)
        cand_ties, cand_flag_errors, cand_flag_mismatches = optimal_sets(cand, True)
        flag_errors = ([dict(item, side="reference") for item in ref_flag_errors]
                       + [dict(item, side="candidate") for item in cand_flag_errors])
        for day in sorted(set(ref_ties) | set(cand_ties)):
            if ref_ties.get(day, set()) != cand_ties.get(day, set()):
                tie_mismatches.append({"day": list(day),
                                       "reference": sorted(ref_ties.get(day, set())),
                                       "candidate": sorted(cand_ties.get(day, set()))})
        if ref_flag_mismatches or cand_flag_mismatches:
            flag_errors.extend([dict(item, side="reference") for item in ref_flag_mismatches])
            flag_errors.extend([dict(item, side="candidate") for item in cand_flag_mismatches])
        optimal_compared = True

    passed = (input_identity["same_fixed_input"] and full_matrix
              and not missing and not extra and not failures
              and not tie_mismatches and not flag_errors)
    if not input_identity["same_fixed_input"]:
        status = "unverified"
    elif not full_matrix:
        status = "partial_daily_optimal_only"
    else:
        status = "pass" if passed else "fail"
    report = {
        "status": status,
        "reference": str(reference),
        "candidate": str(cand_path),
        "candidate_csv_sha256": sha256_file(cand_path),
        "candidate_contract": "raw_matrix" if full_matrix else
                              "daily_optimal_only; tied-optimal set unavailable",
        "tolerance": {"atol": ATOL, "rtol": RTOL},
        "input_identity": input_identity,
        "rows": {"reference": len(ref), "candidate": len(cand)},
        "missing_keys": [list(k) for k in missing[:20]],
        "extra_keys": [list(k) for k in extra[:20]],
        "mismatches": failures[:50],
        "mismatch_count": len(failures),
        "max_abs_error_by_column": worst,
        "tie_mismatches": tie_mismatches,
        "flag_errors": flag_errors[:20],
        "optimal_set_compared": optimal_compared,
    }
    if not input_identity["same_fixed_input"]:
        report["verdict"] = "NOT VERIFIED - same fixed input is not proven; numbers alone do not pass"
        return 1, report
    if not full_matrix:
        report["verdict"] = ("daily-optimal-only CSV is NOT a full cross-language pass; "
                             "raw matrix and tied set are required")
        return 1, report
    report["verdict"] = "pass" if passed else "fail"
    return (0 if passed else 1), report


def compare_safe(reference: Path, candidate: Path):
    try:
        return compare(reference, candidate)
    except CompareError as exc:
        return 1, {"status": "contract_error", "reason": str(exc),
                   "verdict": "NOT VERIFIED - malformed or missing contract fields"}
    except Exception as exc:  # report, never dump an unexplained traceback
        return 1, {"status": "comparison_error", "reason": f"{type(exc).__name__}: {exc}",
                   "verdict": "NOT VERIFIED"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reference", type=Path, required=True,
                        help="directory produced by reference.py --out")
    parser.add_argument("--candidate", type=Path, required=True,
                        help="MATLAB/Octave output directory or result CSV")
    args = parser.parse_args(argv)
    code, report = compare_safe(args.reference, args.candidate)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
