# -*- coding: utf-8 -*-
"""Lead regression for F11: experiments.write_output must be atomic and retry-safe."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from apps.parking_lab.workbench.experiments import write_output


class AtomicOutputTest(unittest.TestCase):
    def test_success_has_no_temp_and_reads_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "run-ok")
            write_output(target, {"a": 1, "b": [1, 2]})
            self.assertEqual(os.listdir(target), ["result.json"])
            with open(os.path.join(target, "result.json"), encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["b"], [1, 2])

    def test_failure_leaves_no_result_or_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "run-bad")
            with self.assertRaises(ValueError):
                write_output(target, {"x": float("nan")})
            self.assertFalse(os.path.exists(os.path.join(target, "result.json")))
            self.assertFalse(os.path.exists(target))  # empty dir removed so a retry can use it

    def test_existing_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "run-existing")
            os.makedirs(target)
            marker = os.path.join(target, "keep.txt")
            with open(marker, "w", encoding="utf-8") as fh:
                fh.write("keep")
            with self.assertRaises(FileExistsError):
                write_output(target, {"a": 1})
            with open(marker, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "keep")
            self.assertFalse(os.path.exists(os.path.join(target, "result.json")))


if __name__ == "__main__":
    unittest.main()
