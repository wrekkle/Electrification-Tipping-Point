#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dataset_qa.py 的 unittest：合成 CSV 精确断言各项计数；空文件与缺列必须退出码非 0。"""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "dataset_qa.py")
PY = sys.executable

HEADER = ["site_id", "event_id", "arrival_ts_utc", "departure_ts_utc", "dwell_min",
          "site_capacity", "day_local", "arrival_local_hour", "source_dataset", "source_row"]


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        for r in rows:
            w.writerow(r)


def run_script(events, out_dir):
    proc = subprocess.run([PY, SCRIPT, "--events", events, "--out", out_dir],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc


class DatasetQATest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qa_test_")
        self.events = os.path.join(self.tmp, "events.csv")
        self.out = os.path.join(self.tmp, "out")

    def make_rows(self):
        """12 行合成数据，期望值见 test_counts。"""
        return [
            # A1 正常
            ["A", "e1", "2026-05-01T08:00:00Z", "2026-05-01T09:00:00Z", "60", "5", "2026-05-01", "8", "synth", "1"],
            # A2 重复 event_id（同 e1）且 dwell 不一致（实际 90 分钟）
            ["A", "e1", "2026-05-01T09:00:00Z", "2026-05-01T10:30:00Z", "60", "5", "2026-05-01", "9", "synth", "2"],
            # A3 负时长（departure < arrival），dwell 一致 => 只计负时长
            ["A", "e3", "2026-05-01T10:00:00Z", "2026-05-01T09:30:00Z", "-30", "5", "2026-05-01", "10", "synth", "3"],
            # A4 跨日：day_local 与到达日不同
            ["A", "e4", "2026-05-01T23:00:00Z", "2026-05-02T00:00:00Z", "60", "5", "2026-05-02", "23", "synth", "4"],
            # A5 坏时间戳
            ["A", "e5", "not-a-timestamp", "2026-05-01T08:00:00Z", "60", "5", "2026-05-01", "8", "synth", "5"],
            # A6 空 site_capacity
            ["A", "e6", "2026-05-01T07:00:00Z", "2026-05-01T08:00:00Z", "60", "0", "2026-05-01", "7", "synth", "6"],
            # B1 容量超载组第 1 个（cap=2，同时在场 3）
            ["B", "b1", "2026-05-01T08:00:00Z", "2026-05-01T09:00:00Z", "60", "2", "2026-05-01", "8", "synth", "7"],
            # B2 容量超载组第 2 个
            ["B", "b2", "2026-05-01T08:30:00Z", "2026-05-01T09:30:00Z", "60", "2", "2026-05-01", "8", "synth", "8"],
            # B3 容量超载组第 3 个（到达时在场 3 > cap 2，计冲突）
            ["B", "b3", "2026-05-01T08:15:00Z", "2026-05-01T09:15:00Z", "60", "2", "2026-05-01", "8", "synth", "9"],
            # C1 重复 (site_id, arrival_ts_utc)
            ["C", "c1", "2026-05-01T08:00:00Z", "2026-05-01T09:00:00Z", "60", "5", "2026-05-01", "8", "synth", "10"],
            # C2 与 C1 同场站同到达时间
            ["C", "c2", "2026-05-01T08:00:00Z", "2026-05-01T09:00:00Z", "60", "5", "2026-05-01", "8", "synth", "11"],
            # D1 缺失必填字段（dwell_min 为空）
            ["D", "d1", "2026-05-01T08:00:00Z", "2026-05-01T09:00:00Z", "", "5", "2026-05-01", "8", "synth", "12"],
        ]

    def test_counts(self):
        write_csv(self.events, self.make_rows())
        proc = run_script(self.events, self.out)
        self.assertEqual(proc.returncode, 1, "有质量问题应退出码 1; stdout=%r stderr=%r" % (proc.stdout, proc.stderr))
        with open(os.path.join(self.out, "qa_stats.json"), encoding="utf-8") as fh:
            s = json.load(fh)
        self.assertEqual(s["total_rows"], 12)
        self.assertEqual(s["missing_required_fields"]["dwell_min"], 1)
        self.assertEqual(sum(s["missing_required_fields"].values()), 1)
        self.assertEqual(s["duplicate_event_ids"], 1)
        self.assertEqual(s["duplicate_site_arrival"], 1)
        self.assertEqual(s["negative_duration"], 1)
        self.assertEqual(s["dwell_mismatch"], 1)
        self.assertEqual(s["cross_day_events"], 1)
        self.assertEqual(s["capacity_conflict_samples"], 1)
        self.assertEqual(s["empty_or_nonpositive_capacity"], 1)
        self.assertEqual(s["unparseable_timestamps"], 1)
        self.assertEqual(s["denominators"]["parseable_rows"], 11)
        self.assertEqual(s["per_site_event_counts"], {"A": 5, "B": 3, "C": 2, "D": 1})
        self.assertEqual(s["full_24h_coverage_days"], {
            "2026-05-01@A": False, "2026-05-01@B": False,
            "2026-05-01@C": False, "2026-05-01@D": False,
            "2026-05-02@A": False,
        })
        q = s["dwell_minutes_quantiles"]
        # dwell 值: 60,60,-30,60,60,60,60,60,60,60,60（11 个，D1 缺失不计）
        self.assertAlmostEqual(q["p50"], 60.0)
        self.assertAlmostEqual(q["max"], 60.0)
        dist = s["arrival_local_hour_distribution"]
        self.assertEqual(dist["8"], 7)
        self.assertEqual(dist["9"], 1)
        self.assertEqual(dist["10"], 1)
        self.assertEqual(dist["23"], 1)
        self.assertEqual(dist["7"], 1)
        self.assertEqual(sum(dist.values()), 11)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "qa_report.md")))

    def test_clean_data_exit_zero(self):
        rows = [["A", "e1", "2026-05-01T08:00:00Z", "2026-05-01T09:00:00Z", "60", "5", "2026-05-01", "8", "synth", "1"]]
        write_csv(self.events, rows)
        proc = run_script(self.events, self.out)
        self.assertEqual(proc.returncode, 0, "干净数据应退出码 0; stderr=%r" % proc.stderr)
        with open(os.path.join(self.out, "qa_stats.json"), encoding="utf-8") as fh:
            s = json.load(fh)
        self.assertEqual(s["total_rows"], 1)
        self.assertEqual(s["capacity_conflict_samples"], 0)

    def test_empty_file_nonzero_exit(self):
        with open(self.events, "w", encoding="utf-8", newline="") as fh:
            fh.write("")
        proc = run_script(self.events, self.out)
        self.assertNotEqual(proc.returncode, 0)

    def test_header_only_nonzero_exit(self):
        write_csv(self.events, [])
        proc = run_script(self.events, self.out)
        self.assertNotEqual(proc.returncode, 0)

    def test_missing_column_nonzero_exit(self):
        with open(self.events, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["site_id", "event_id"])
            w.writerow(["A", "e1"])
        proc = run_script(self.events, self.out)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("缺少必需列", (proc.stderr or "") + (proc.stdout or ""))


if __name__ == "__main__":
    unittest.main()
