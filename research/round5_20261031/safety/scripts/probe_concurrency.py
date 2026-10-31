# -*- coding: utf-8 -*-
"""同名输出并发实测：两个独立进程同时写同一 result 目录。

只写 safety/tmp/concurrency/**；清理前断言绝对路径在该目录下。
输出 JSON 摘要；全部检查通过时退出 0，否则 1。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TMP = ROOT / "research" / "round5_20261031" / "safety" / "tmp" / "concurrency"
PY = sys.executable

CHILD = r'''
import sys, time
sys.path.insert(0, sys.argv[4])
from pathlib import Path
from apps.parking_lab.workbench.experiments import write_output
target, go, marker = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
while not go.exists():
    time.sleep(0.005)
try:
    out = write_output(target, {"marker": marker, "payload": list(range(200))})
except BaseException as exc:
    print("ERR %s: %s" % (type(exc).__name__, exc)); sys.exit(2)
print("OK " + str(out)); sys.exit(0)
'''


def assert_under(path, base) -> None:
    resolved, base = Path(path).resolve(), Path(base).resolve()
    if resolved != base and base not in resolved.parents:
        raise AssertionError(f"refusing to touch outside {base}: {resolved}")


def spawn(target, go, marker):
    return subprocess.Popen([PY, "-c", CHILD, str(target), str(go), marker, str(ROOT)],
                            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})


def race(target, go, markers):
    procs = [spawn(target, go, m) for m in markers]
    time.sleep(0.3)
    go.write_text("go", encoding="utf-8")
    outs = [p.communicate(timeout=120) for p in procs]
    return [{"marker": m, "exit": p.returncode, "stdout": o[0].strip(), "stderr": o[1].strip()}
            for m, p, o in zip(markers, procs, outs)]


def result_sha(target):
    path = Path(target) / "result.json"
    return __import__("hashlib").sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    report = {"tmp_root": str(TMP), "trials": []}
    ok = True
    for i in (1, 2, 3):
        d = TMP / f"trial{i}"
        if d.exists():
            assert_under(d, TMP)
            shutil.rmtree(d)
        d.mkdir(parents=True)
        target, go = d / "run", d / "go"
        runs = race(target, go, ["A", "B"])
        files = sorted(p.name for p in target.iterdir()) if target.exists() else []
        payload = json.loads((target / "result.json").read_text(encoding="utf-8")) if (target / "result.json").exists() else None
        winners = [r for r in runs if r["exit"] == 0]
        expected = ["A", "B"][runs.index(winners[0])] if len(winners) == 1 else None
        entry = {"trial": i, "runs": runs, "files": files, "winner_count": len(winners),
                 "winner_marker": (payload or {}).get("marker"), "expected_winner_marker": expected,
                 "single_result": files == ["result.json"],
                 "no_temp_left": not any(n.startswith(".result-") and n.endswith(".tmp") for n in files)}
        entry["ok"] = (len(winners) == 1 and entry["single_result"] and entry["no_temp_left"]
                       and entry["winner_marker"] == expected)
        report["trials"].append(entry)
        ok = ok and entry["ok"]

    # 顺序重复：完整结果已存在时再写同一路径，必须被拒绝且原结果字节不变
    d = TMP / "trial1"
    target, go = d / "run", d / "go"
    before = result_sha(target)
    dup = race(target, go, ["C"])
    after = result_sha(target)
    dup_entry = {"runs": dup, "sha_before": before, "sha_after": after,
                 "unchanged": before is not None and before == after,
                 "refused": dup[0]["exit"] != 0}
    dup_entry["ok"] = dup_entry["refused"] and dup_entry["unchanged"]
    report["sequential_duplicate"] = dup_entry
    ok = ok and dup_entry["ok"]

    report["pass"] = ok
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
