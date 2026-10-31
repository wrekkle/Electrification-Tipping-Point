# -*- coding: utf-8 -*-
"""Assemble the machine-readable evidence file for the 2026-10-29 backend fix.

Reads the artefacts produced by the revision (before/after probe, test logs,
baseline runs, synthetic experiments) and writes reports/backend_fix_evidence.json.
No model parameter is re-tuned here; this only records what the commands produced.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import platform
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS = os.path.dirname(os.path.dirname(os.path.dirname(ROOT)))
REPORTS = os.path.join(ROOT, "reports")
VOLATILE = {"timestamp", "run_id", "runtime_seconds", "generated_at",
            "elapsed_seconds", "created", "generated_by", "command"}


def read_text(path):
    """Read a log that may have been written by PowerShell as UTF-16LE."""
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_dir(prefix):
    hits = sorted(glob.glob(os.path.join(ROOT, prefix, "baseline", "*-seed42")))
    return hits[-1] if hits else None


def scrub(obj):
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in sorted(obj.items())
                if k not in VOLATILE and not k.endswith("_seconds")}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def parse_test_log(path):
    if not os.path.exists(path):
        return None
    text = read_text(path)
    m = re.search(r"Ran (\d+) tests?", text)
    fails = len(re.findall(r"^(FAIL|ERROR):", text, flags=re.M))
    return {"path": os.path.relpath(path, ROOT), "tests": int(m.group(1)) if m else None,
            "fail_or_error_lines": fails,
            "ok": bool(re.search(r"^OK\s*$", text, flags=re.M)),
            "before_counts": {
                "failures": len(re.findall(r"^FAIL:", text, flags=re.M)),
                "errors": len(re.findall(r"^ERROR:", text, flags=re.M))}}


def compare_runs(a, b):
    if not a or not b:
        return {"available": False}
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(a, "*.csv")))
    csv_same, csv_diff = [], []
    for name in names:
        if sha256(os.path.join(a, name)) == sha256(os.path.join(b, name)):
            csv_same.append(name)
        else:
            csv_diff.append(name)
    json_same, json_diff, expected = [], [], []
    for name in sorted(os.path.basename(p) for p in glob.glob(os.path.join(a, "*.json"))):
        with open(os.path.join(a, name), encoding="utf-8") as fh:
            ja = scrub(json.load(fh))
        with open(os.path.join(b, name), encoding="utf-8") as fh:
            jb = scrub(json.load(fh))
        if ja == jb:
            json_same.append(name)
            continue
        if name == "manifest.json":
            # the manifest hashes every payload file; params.json and
            # summary.json embed timestamps, so their hashes are expected to
            # differ.  Everything else in the manifest must match.
            volatile = {"params.json", "summary.json"}
            ja["files"] = [f for f in ja.get("files", []) if f.get("file") not in volatile]
            jb["files"] = [f for f in jb.get("files", []) if f.get("file") not in volatile]
            if ja == jb:
                expected.append(name)
                continue
        json_diff.append(name)
    return {"run_a": os.path.relpath(a, ROOT), "run_b": os.path.relpath(b, ROOT),
            "csv_identical": csv_same, "csv_different": csv_diff,
            "json_identical_after_scrub": json_same,
            "json_expected_difference_timestamped_hashes": expected,
            "json_different_after_scrub": json_diff,
            "scrubbed_keys": sorted(VOLATILE),
            "csv_total": len(names)}


def read_csv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def output_facts(new_dir):
    if not new_dir:
        return {}
    g = read_csv(os.path.join(new_dir, "v2_g_curve.csv"))
    neg = [r for r in g if float(r["g_hat"]) < 0.0]
    regions = read_csv(os.path.join(new_dir, "v2_regions.csv"))
    counts = {}
    for r in regions:
        counts[r["region"]] = counts.get(r["region"], 0) + 1
    conf = read_csv(os.path.join(new_dir, "v2_confidence_sets.csv"))
    sizes = [int(r["set_size"]) for r in conf]
    cv = read_csv(os.path.join(new_dir, "v2_cvar.csv"))
    aux_gap = max(abs(float(r["cvar_rmb"]) - float(r["cvar_aux_rmb"])) for r in cv)
    svc = read_csv(os.path.join(new_dir, "v2_service_accounting.csv"))
    denom = []
    for row in svc:
        if "unserved_rate_all" in row and row["unserved_rate_all"] != "":
            denom.append({"design": "%s,%s,m=%s" % (row["mode"], row["rule"],
                                                    row["devices"]),
                          "unserved_rate_all": float(row["unserved_rate_all"]),
                          "shortfall_rate_admitted": float(row["undelivered_rate"])})
    return {"region_counts": counts, "n_g_rows": len(g), "n_g_negative": len(neg),
            "g_range": [min(float(r["g_hat"]) for r in g),
                        max(float(r["g_hat"]) for r in g)],
            "confidence_set_sizes": sorted(set(sizes)),
            "max_abs_cvar_minus_aux": aux_gap,
            "n_service_rows": len(svc),
            "time_unit_columns": sorted(k for k in svc[0] if "time_unit" in k),
            "denominator_columns_present": "unserved_rate_all" in svc[0],
            "denominator_sample": denom[:4]}


def main():
    out = {"revision_dir": os.path.relpath(ROOT, WS),
           "python": {"runtime": platform.python_version(),
                      "executable": sys.executable,
                      "numpy": __import__("numpy").__version__}}
    prov_path = os.path.join(ROOT, "PROVENANCE.json")
    if os.path.exists(prov_path):
        with open(prov_path, encoding="utf-8") as fh:
            prov = json.load(fh)
        out["provenance"] = {"copied_at": prov["copied_at"],
                             "source_root": prov["source_root"],
                             "target_root": prov["target_root"],
                             "files": len(prov["files"]),
                             "all_source_hashes_match_copy": all(
                                 f["match"] for f in prov["files"]),
                             "excluded": prov["excluded"]}
    out["tests"] = {
        "before_on_unfixed_copy": parse_test_log(os.path.join(ROOT, "before_regressions.log")),
        "after_default_python": parse_test_log(os.path.join(ROOT, "after_unittest.log")),
        "after_bundled_python": parse_test_log(os.path.join(ROOT, "after_unittest_bundled.log")),
    }
    ba = os.path.join(REPORTS, "before_after_r1_r6.json")
    if os.path.exists(ba):
        with open(ba, encoding="utf-8") as fh:
            out["r_item_probe"] = json.load(fh)
    exp = os.path.join(REPORTS, "stat_experiment.json")
    if os.path.exists(exp):
        with open(exp, encoding="utf-8") as fh:
            ex = json.load(fh)
        out["stat_experiment"] = {
            "file": "reports/stat_experiment.json",
            "paired_fixed_offset": ex["a_paired_g_interval"]["fixed_offset_K1"],
            "paired_min_selection": ex["a_paired_g_interval"]["min_over_partials"],
            "coverage_separated_max_t": ex["b_confidence_set"]["separated_max_t"],
            "coverage_near_tie_max_t": ex["b_confidence_set"]["near_tie_max_t"],
            "exact_tie": ex["b_confidence_set"]["exact_tie"],
            "cvar": {k: v for k, v in ex["c_cvar"].items() if k != "rows"},
            "etp_grid": {k: ex["d_etp_grid"][k] for k in
                         ("grid_points", "patterns_checked")} | {
                "mismatch_count": len(ex["d_etp_grid"]["mismatches"])},
        }
    run1, run2 = run_dir("outputs_revision"), run_dir("outputs_revision_repeat")
    if run1:
        with open(os.path.join(run1, "summary.json"), encoding="utf-8") as fh:
            summary = json.load(fh)
        out["baseline"] = {
            "command": ("python run_all.py --mode all --seed 42 "
                        "--out outputs_revision --no-canonical"),
            "seed": 42, "run_dir": os.path.relpath(run1, ROOT),
            "runtime_seconds": summary["runtime_seconds"],
            "counts": summary["counts"],
            "v2_etp_points": summary["results"].get("v2_etp_points"),
            "static_etp_points": summary["results"].get("etp_points"),
            "v2_region_counts": summary["results"].get("v2_region_counts"),
            "psc_increase_pct_range": summary["results"].get("psc_increase_pct_range"),
            "output_sha256": {os.path.basename(p): sha256(p) for p in
                              sorted(glob.glob(os.path.join(run1, "*")))},
            "facts": output_facts(run1),
        }
        old = os.path.join(WS, "research", "electrification", "repro", "outputs",
                           "baseline", "canonical-seed42")
        if os.path.isdir(old):
            with open(os.path.join(old, "summary.json"), encoding="utf-8") as fh:
                olds = json.load(fh)
            out["previous_canonical"] = {
                "dir": os.path.relpath(old, WS),
                "runtime_seconds": olds["runtime_seconds"],
                "counts": olds["counts"],
                "v2_etp_points": olds["results"].get("v2_etp_points"),
                "v2_region_counts": olds["results"].get("v2_region_counts"),
                "facts": output_facts(old),
                "note": ("previous canonical output was left untouched; it was "
                         "produced by the pre-fix code and is not comparable "
                         "as a result, only as a before/after record"),
            }
    out["determinism"] = compare_runs(run1, run2)
    log1 = os.path.join(ROOT, "baseline_run1.log")
    if os.path.exists(log1):
        out["baseline_log_tail"] = read_text(log1)[-1500:]
    with open(os.path.join(REPORTS, "backend_fix_evidence.json"), "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, sort_keys=True,
                  default=lambda o: float(o))
        fh.write("\n")
    print("wrote reports/backend_fix_evidence.json")
    print(json.dumps({"checks": out["tests"],
                      "determinism": {k: out["determinism"].get(k) for k in
                                      ("csv_total", "csv_different",
                                       "json_different_after_scrub")},
                      "facts": out.get("baseline", {}).get("facts", {})},
                     ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    main()
