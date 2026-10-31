# -*- coding: utf-8 -*-
"""第五轮安全回归（F12-F15）：写入中断 / 重试恢复 / 并发互斥 / 残缺识别。

缺陷编号、修复前反例与命令见 research/round5_20261031/safety/REPORT.md。
进程级故障注入（os._exit 中断、双进程并发）在 safety/scripts/probe_*.py 中，
本文件用等价的可控状态（残留 .result-*.tmp、空目录、残缺 result.json、线程竞争）覆盖库语义。
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path

from apps.parking_lab.workbench.experiments import (
    RESULT_FILENAME,
    TEMP_PREFIX,
    TEMP_SUFFIX,
    fingerprint_output,
    inspect_output,
    write_output,
)


class InspectOutputTest(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = inspect_output(Path(tmp) / "absent")
            self.assertEqual(state["state"], "missing")
            self.assertIsNone(state["result"])

    def test_complete_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            write_output(target, {"a": 1})
            state = inspect_output(target)
            self.assertEqual(state["state"], "complete")
            self.assertEqual(state["temp_files"], [])
            fingerprint = fingerprint_output(target)
            data = (target / RESULT_FILENAME).read_bytes()
            self.assertEqual(fingerprint["bytes"], len(data))
            self.assertEqual(fingerprint["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(fingerprint["path"], str(target))

    def test_stale_temp_is_incomplete_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.mkdir()
            stale = target / (TEMP_PREFIX + "dead" + TEMP_SUFFIX)
            stale.write_text('{"partial": ', encoding="utf-8")
            state = inspect_output(target)
            self.assertEqual(state["state"], "incomplete")
            self.assertEqual(state["temp_files"], [stale.name])
            self.assertTrue(stale.name.startswith(".") and stale.name.endswith(".tmp"))
            with self.assertRaises(RuntimeError):
                fingerprint_output(target)

    def test_corrupt_result_is_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.mkdir()
            (target / RESULT_FILENAME).write_text('{"marker": "partial"', encoding="utf-8")
            state = inspect_output(target)
            self.assertEqual(state["state"], "corrupt")
            self.assertIn("error", state)
            with self.assertRaises(RuntimeError):
                fingerprint_output(target)

    def test_foreign_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.mkdir()
            (target / "keep.txt").write_text("keep", encoding="utf-8")
            state = inspect_output(target)
            self.assertEqual(state["state"], "foreign")
            self.assertEqual(state["other_files"], ["keep.txt"])

    def test_path_is_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.write_text("x", encoding="utf-8")
            self.assertEqual(inspect_output(target)["state"], "not_a_directory")


class WriteOutputRecoveryTest(unittest.TestCase):
    def test_complete_result_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            write_output(target, {"a": 1})
            before = (target / RESULT_FILENAME).read_bytes()
            with self.assertRaises(FileExistsError) as ctx:
                write_output(target, {"a": 2})
            self.assertIn("force=True", str(ctx.exception))
            self.assertEqual((target / RESULT_FILENAME).read_bytes(), before)

    def test_force_replaces_complete_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            write_output(target, {"a": 1})
            write_output(target, {"a": 2}, force=True)
            self.assertEqual(json.loads((target / RESULT_FILENAME).read_text(encoding="utf-8")), {"a": 2})
            self.assertEqual(sorted(p.name for p in target.iterdir()), [RESULT_FILENAME])

    def test_stale_temp_refused_with_actionable_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.mkdir()
            stale = target / (TEMP_PREFIX + "dead" + TEMP_SUFFIX)
            stale.write_text('{"partial": ', encoding="utf-8")
            with self.assertRaises(FileExistsError) as ctx:
                write_output(target, {"a": 1})
            message = str(ctx.exception)
            self.assertIn(stale.name, message)
            self.assertIn("force=True", message)
            self.assertFalse((target / RESULT_FILENAME).exists())  # 中断不产生“成功”证据
            self.assertTrue(stale.exists())                        # 默认不删除现场

    def test_force_recovers_stale_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.mkdir()
            (target / (TEMP_PREFIX + "dead" + TEMP_SUFFIX)).write_text('{"partial": ', encoding="utf-8")
            write_output(target, {"ok": 1}, force=True)
            self.assertEqual(json.loads((target / RESULT_FILENAME).read_text(encoding="utf-8")), {"ok": 1})
            self.assertEqual(sorted(p.name for p in target.iterdir()), [RESULT_FILENAME])

    def test_empty_directory_requires_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.mkdir()
            with self.assertRaises(FileExistsError):
                write_output(target, {"a": 1})
            write_output(target, {"a": 1}, force=True)
            self.assertEqual(inspect_output(target)["state"], "complete")

    def test_corrupt_result_requires_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.mkdir()
            (target / RESULT_FILENAME).write_text('{"partial"', encoding="utf-8")
            with self.assertRaises(RuntimeError):
                write_output(target, {"a": 1})
            self.assertEqual((target / RESULT_FILENAME).read_text(encoding="utf-8"), '{"partial"')
            write_output(target, {"a": 1}, force=True)
            self.assertEqual(json.loads((target / RESULT_FILENAME).read_text(encoding="utf-8")), {"a": 1})

    def test_force_does_not_delete_foreign_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.mkdir()
            (target / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_output(target, {"a": 1})
            write_output(target, {"a": 1}, force=True)
            self.assertEqual((target / "keep.txt").read_text(encoding="utf-8"), "keep")
            self.assertEqual(sorted(p.name for p in target.iterdir()), ["keep.txt", RESULT_FILENAME])

    def test_serialization_failure_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            with self.assertRaises(ValueError):
                write_output(target, {"x": float("nan")})
            self.assertFalse(target.exists())

    def test_force_serialization_failure_keeps_previous_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            write_output(target, {"a": 1})
            before = (target / RESULT_FILENAME).read_bytes()
            with self.assertRaises(ValueError):
                write_output(target, {"x": float("nan")}, force=True)
            self.assertEqual((target / RESULT_FILENAME).read_bytes(), before)
            self.assertEqual(sorted(p.name for p in target.iterdir()), [RESULT_FILENAME])

    def test_path_is_a_file_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            target.write_text("x", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_output(target, {"a": 1})
            self.assertEqual(target.read_text(encoding="utf-8"), "x")

    def test_threads_racing_same_target_exactly_one_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            barrier = threading.Barrier(2)
            outcomes = []
            lock = threading.Lock()

            def worker(marker):
                barrier.wait()
                try:
                    out = write_output(target, {"marker": marker, "payload": list(range(200))})
                    with lock:
                        outcomes.append(("ok", marker, str(out)))
                except FileExistsError as exc:
                    with lock:
                        outcomes.append(("refused", marker, str(exc)))

            threads = [threading.Thread(target=worker, args=(m,)) for m in ("A", "B")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            winners = [item for item in outcomes if item[0] == "ok"]
            self.assertEqual(len(outcomes), 2)
            self.assertEqual(len(winners), 1)
            payload = json.loads((target / RESULT_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(payload["marker"], winners[0][1])
            self.assertEqual(sorted(p.name for p in target.iterdir()), [RESULT_FILENAME])
            self.assertEqual(winners[0][2], str(target.resolve()))


if __name__ == "__main__":
    unittest.main()
