# -*- coding: utf-8 -*-
"""运行三项审查核查脚本，记录命令/解释器/退出码/输出哈希到 run_manifest.json。

命令：python research/round5_20261031/review/run_all.py
输出：research/round5_20261031/review/run_manifest.json
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRIPTS = ("audit_joint_k.py", "reanalysis_alpha_constraints.py", "four_categories.py")
OUTPUTS = {"audit_joint_k.py": "joint_k_none_audit.json",
           "reanalysis_alpha_constraints.py": "reanalysis_alpha_constraints.json",
           "four_categories.py": "four_categories.json"}
MANIFEST = HERE / "run_manifest.json"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    runs = []
    for script in SCRIPTS:
        command = [sys.executable, str(HERE / script)]
        proc = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        output = HERE / OUTPUTS[script]
        runs.append({
            "script": "research/round5_20261031/review/" + script,
            "command": "python research/round5_20261031/review/" + script,
            "interpreter": "%s | Python %s" % (sys.executable, sys.version.split()[0]),
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip()[-2000:],
            "stderr": proc.stderr.strip()[-2000:],
            "output": "research/round5_20261031/review/" + OUTPUTS[script],
            "output_sha256": sha256(output) if output.exists() else None,
        })
    document = {
        "schema": "review/run_manifest/v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": str(ROOT),
        "runs": runs,
        "all_exit_zero": all(r["exit_code"] == 0 for r in runs),
    }
    MANIFEST.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(MANIFEST),
                      "all_exit_zero": document["all_exit_zero"],
                      "exit_codes": {r["script"]: r["exit_code"] for r in runs}},
                     ensure_ascii=True))
    return 0 if document["all_exit_zero"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
