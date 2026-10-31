# -*- coding: utf-8 -*-
"""写入中断 + 重试恢复实测。

故障注入只发生在 safety/tmp/crash_retry/**；清理前断言绝对路径在该目录下。
记录修复前后行为（force/inspect_output 在修复前不存在，按 TypeError/ImportError 记录）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
TMP = ROOT / "research" / "round5_20261031" / "safety" / "tmp" / "crash_retry"
PY = sys.executable

CHILD_CRASH = r'''
import os, sys
sys.path.insert(0, sys.argv[2])
from apps.parking_lab.workbench import experiments as E
def boom(obj, fp, **kw):
    fp.write('{"marker": "partial", "payload": [1, 2')
    fp.flush()
    os._exit(7)
E.json.dump = boom
E.write_output(sys.argv[1], {"marker": "crash"})
print("SHOULD-NOT-REACH")
'''

CHILD_WRITE = r'''
import sys
sys.path.insert(0, sys.argv[2])
from apps.parking_lab.workbench.experiments import write_output
kwargs = {}
if len(sys.argv) > 3 and sys.argv[3] == "force":
    kwargs["force"] = True
try:
    print("OK " + str(write_output(sys.argv[1], {"marker": "retry", "payload": list(range(50))}, **kwargs)))
except BaseException as exc:
    print("ERR %s: %s" % (type(exc).__name__, exc)); sys.exit(2)
'''


def assert_under(path, base) -> None:
    resolved, base = Path(path).resolve(), Path(base).resolve()
    if resolved != base and base not in resolved.parents:
        raise AssertionError(f"refusing to touch outside {base}: {resolved}")


def run(code, *args):
    p = subprocess.run([PY, "-c", code, *map(str, args)], cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    return {"exit": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}


def state(target):
    try:
        from apps.parking_lab.workbench.experiments import inspect_output
    except ImportError:
        return {"state": "NO_INSPECT_API"}
    try:
        return inspect_output(target)
    except BaseException as exc:  # noqa: BLE001 - 记录即可
        return {"state": "INSPECT_ERROR", "error": f"{type(exc).__name__}: {exc}"}


def tree(target):
    target = Path(target)
    return sorted(p.name for p in target.iterdir()) if target.is_dir() else []


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    report = {"tmp_root": str(TMP), "steps": {}}

    # 1) 硬中断：写临时文件后进程直接退出
    crash_dir = TMP / "crash"
    if crash_dir.exists():
        assert_under(crash_dir, TMP)
        shutil.rmtree(crash_dir)
    crash = run(CHILD_CRASH, crash_dir, ROOT)
    report["steps"]["hard_crash"] = {"run": crash, "tree": tree(crash_dir), "state": state(crash_dir),
                                     "result_exists": (crash_dir / "result.json").exists(),
                                     "temp_files": [n for n in tree(crash_dir) if n.startswith(".result-")],
                                     "crash_evidence_absent": not (crash_dir / "result.json").exists()}

    # 2) 直接重试（默认语义）
    retry = run(CHILD_WRITE, crash_dir, ROOT)
    report["steps"]["retry_default"] = {"run": retry, "state": state(crash_dir), "tree": tree(crash_dir)}

    # 3) 显式 force 重试
    force = run(CHILD_WRITE, crash_dir, ROOT, "force")
    payload = None
    if (crash_dir / "result.json").exists():
        try:
            payload = json.loads((crash_dir / "result.json").read_text(encoding="utf-8"))
        except ValueError as exc:
            payload = {"parse_error": str(exc)}
    report["steps"]["retry_force"] = {"run": force, "state": state(crash_dir), "tree": tree(crash_dir),
                                      "marker": (payload or {}).get("marker")}

    # 4) 序列化异常（可控失败）：不得留下目录或临时文件
    bad_dir = TMP / "serialize_fail"
    if bad_dir.exists():
        assert_under(bad_dir, TMP)
        shutil.rmtree(bad_dir)
    sys.path.insert(0, str(ROOT))
    from apps.parking_lab.workbench.experiments import write_output
    try:
        write_output(bad_dir, {"x": float("nan")})
        graceful = {"raised": None}
    except BaseException as exc:  # noqa: BLE001
        graceful = {"raised": f"{type(exc).__name__}: {exc}"}
    report["steps"]["serialize_fail"] = {**graceful, "dir_exists": bad_dir.exists(), "tree": tree(bad_dir)}

    # 5) 残缺 result.json：不得被当作成功结果
    corrupt_dir = TMP / "corrupt"
    if corrupt_dir.exists():
        assert_under(corrupt_dir, TMP)
        shutil.rmtree(corrupt_dir)
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "result.json").write_text('{"marker": "partial"', encoding="utf-8")
    corrupt_retry = run(CHILD_WRITE, corrupt_dir, ROOT)
    corrupt_force = run(CHILD_WRITE, corrupt_dir, ROOT, "force")
    report["steps"]["corrupt_result"] = {"retry": corrupt_retry, "state": state(corrupt_dir),
                                         "force": corrupt_force, "tree": tree(corrupt_dir)}

    # 6) 外来文件目录：默认拒绝；force 不得删除外来文件
    foreign_dir = TMP / "foreign"
    if foreign_dir.exists():
        assert_under(foreign_dir, TMP)
        shutil.rmtree(foreign_dir)
    foreign_dir.mkdir(parents=True)
    (foreign_dir / "keep.txt").write_text("keep", encoding="utf-8")
    foreign_retry = run(CHILD_WRITE, foreign_dir, ROOT)
    foreign_force = run(CHILD_WRITE, foreign_dir, ROOT, "force")
    report["steps"]["foreign_dir"] = {"retry": foreign_retry, "state": state(foreign_dir),
                                      "force": foreign_force, "tree": tree(foreign_dir),
                                      "keep_intact": (foreign_dir / "keep.txt").read_text(encoding="utf-8") == "keep"}

    # 7) 空目录（中断在创建临时文件之前）：默认拒绝；force 可恢复
    empty_dir = TMP / "empty"
    if empty_dir.exists():
        assert_under(empty_dir, TMP)
        shutil.rmtree(empty_dir)
    empty_dir.mkdir(parents=True)
    empty_retry = run(CHILD_WRITE, empty_dir, ROOT)
    empty_force = run(CHILD_WRITE, empty_dir, ROOT, "force")
    report["steps"]["empty_dir"] = {"retry": empty_retry, "state": state(empty_dir), "force": empty_force}

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
