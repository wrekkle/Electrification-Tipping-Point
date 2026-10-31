# -*- coding: utf-8 -*-
"""结果与 manifest 一致性实测：命令/参数/哈希/输出路径/exit code 对应。

在 safety/tmp/manifest/** 内跑 workbench CLI（固定输入），生成外部 manifest 并逐项核对；
同时只读审计 round4 scenario_manifest.json。全部检查通过退出 0，否则 1。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
TMP = ROOT / "research" / "round5_20261031" / "safety" / "tmp" / "manifest"
PY = sys.executable
CONFIG = {"duration_hours": 2, "arrival_rate_hour": 20, "seed": 5}


def assert_under(path, base) -> None:
    resolved, base = Path(path).resolve(), Path(base).resolve()
    if resolved != base and base not in resolved.parents:
        raise AssertionError(f"refusing to touch outside {base}: {resolved}")


def run_cli(out, tag):
    argv = [PY, "-m", "apps.parking_lab.workbench", "compare", "--config", str(TMP / "config.json"),
            "--seeds", "5", "--out", str(out)]
    p = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    result_path = Path(out) / "result.json"
    record = {"tag": tag, "command": argv, "cwd": str(ROOT), "exit": p.returncode,
              "stdout": p.stdout.strip(), "stderr": p.stderr.strip(),
              "out": str(Path(out).resolve()), "result_exists": result_path.exists(),
              "result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest() if result_path.exists() else None,
              "result_bytes": result_path.stat().st_size if result_path.exists() else None}
    return record, p


def source_hash_check(provenance):
    recorded = provenance.get("source_sha256") or {}
    bad = []
    for rel, digest in recorded.items():
        path = ROOT / "apps" / "parking_lab" / "workbench" / rel
        if not path.exists():
            bad.append({"path": rel, "error": "missing"})
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            bad.append({"path": rel, "recorded": digest, "actual": actual})
    return {"files": len(recorded), "mismatches": bad, "ok": not bad and bool(recorded)}


def audit_round4():
    path = ROOT / "research" / "round4_20261031" / "results" / "scenario_manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = data.get("runs") or []
    missing, nonzero = [], []
    for item in runs:
        out = Path(item.get("out") or "")
        if not out.is_absolute():
            out = ROOT / out
        if not out.exists():
            missing.append(str(out))
        if item.get("exit") != 0:
            nonzero.append(item)
    return {"path": str(path), "runs": len(runs), "missing_outputs": missing, "nonzero_exits": nonzero,
            "has_hash_field": any("sha256" in (item or {}) for item in runs),
            "has_command_cwd": "cwd" in data,
            "ok": not missing and not nonzero}


def main() -> int:
    if TMP.exists():
        assert_under(TMP, TMP.parent)
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)
    (TMP / "config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    checks = {}

    run1, p1 = run_cli(TMP / "run1", "run1")
    checks["exit_zero"] = {"ok": p1.returncode == 0, "exit": p1.returncode, "stderr": p1.stderr.strip()}
    checks["stdout_matches_out"] = {"ok": run1["stdout"] == run1["out"], "stdout": run1["stdout"], "out": run1["out"]}

    payload = json.loads((TMP / "run1" / "result.json").read_text(encoding="utf-8"))
    checks["config_roundtrip"] = {"ok": all(payload["config"].get(k) == v for k, v in CONFIG.items()),
                                  "config_seed": payload["config"].get("seed"), "seeds": payload.get("seeds")}
    checks["seeds_match"] = {"ok": payload.get("seeds") == [5], "seeds": payload.get("seeds")}
    provenance = payload.get("provenance") or {}
    checks["model_version"] = {"ok": provenance.get("model_version") == __import__("apps.parking_lab.workbench", fromlist=["VERSION"]).VERSION,
                               "model_version": provenance.get("model_version")}
    checks["source_hashes"] = source_hash_check(provenance)
    try:
        from apps.parking_lab.workbench.experiments import fingerprint_output
        fingerprint = fingerprint_output(TMP / "run1")
        checks["fingerprint_matches_manifest"] = {
            "ok": fingerprint["sha256"] == run1["result_sha256"] and fingerprint["bytes"] == run1["result_bytes"],
            "fingerprint": fingerprint, "manifest_sha256": run1["result_sha256"]}
    except ImportError:
        checks["fingerprint_matches_manifest"] = {"ok": False, "error": "fingerprint_output 不存在"}
    run_hashes = {r.get("demand_hash") for r in payload.get("runs") or []}
    checks["demand_hash_present"] = {"ok": len(run_hashes) == 1 and isinstance(next(iter(run_hashes)), str)
                                     and len(next(iter(run_hashes))) >= 8,
                                     "demand_hash": sorted(run_hashes)}

    run2, _ = run_cli(TMP / "run2", "run2")
    payload2 = json.loads((TMP / "run2" / "result.json").read_text(encoding="utf-8"))
    checks["fixed_input_deterministic"] = {
        "ok": payload.get("runs") == payload2.get("runs") and payload.get("rows") == payload2.get("rows"),
        "runs_equal": payload.get("runs") == payload2.get("runs"),
        "rows_equal": payload.get("rows") == payload2.get("rows")}

    before_sha = run1["result_sha256"]
    dup, pdup = run_cli(TMP / "run1", "run1-again")
    after_sha = hashlib.sha256((TMP / "run1" / "result.json").read_bytes()).hexdigest()
    checks["rerun_refused_no_overwrite"] = {"ok": pdup.returncode != 0 and before_sha == after_sha,
                                            "exit": pdup.returncode, "stderr": pdup.stderr.strip()[:300],
                                            "sha_unchanged": before_sha == after_sha}

    checks["round4_manifest_audit"] = audit_round4()
    checks["round4_manifest_audit"]["ok"] = checks["round4_manifest_audit"]["ok"]  # 只读审计，不计入总判定
    hard = {k: v for k, v in checks.items() if k != "round4_manifest_audit"}
    report = {"tmp_root": str(TMP), "manifest": {"command": run1["command"], "cwd": run1["cwd"],
                                                 "exit": run1["exit"], "out": run1["out"],
                                                 "result_sha256": run1["result_sha256"],
                                                 "result_bytes": run1["result_bytes"]},
              "checks": checks, "pass": all(v.get("ok") for v in hard.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
