# -*- coding: utf-8 -*-
"""Lock the module boundaries of the evaluate/stats split (no simulation, no big data).

Run:  python -m unittest tests.test_module_layout -v
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPRO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPRO, "src"))

PREI_DIR = os.path.join(REPRO, "src", "prei")

EVALUATE_NAMES = [
    "arrivals_mean", "v2_lot_arrival_scale", "composition_of", "m_candidates",
    "integer_candidates", "scenario_set", "static_leavers", "mode_pile_cost",
    "static_matrices", "curves_rows", "optimum_rows", "modes_summary",
    "etp_rows", "prepare_v2_day", "v2_days", "v2_designs", "v2_pile_cost",
    "design_label", "v2_cell_matrix", "v2_rows", "v2_eval", "v2_best", "_pick",
    "decomposition_rows", "cvar_fields", "v2_cell_stats", "refine_r_grid",
    "v2_etp_points", "_windows_to_text", "v2_g_structure", "fig8_rows",
    "feasibility_rows", "saa_rows", "LOT_TYPES", "STATIC_MODES", "V2_METRIC_KEYS",
]

STATS_NAMES = [
    "block_indices", "bootstrap_means", "normal_cdf",
    "confidence_set", "_interval_meta", "g_interval",
]


def _source(name):
    with open(os.path.join(PREI_DIR, name), encoding="utf-8") as fh:
        return fh.read()


class TestModuleLayout(unittest.TestCase):
    def test_imports_succeed(self):
        import prei.evaluate  # noqa: F401
        import prei.evaluate_base  # noqa: F401
        import prei.evaluate_v2  # noqa: F401
        import prei.evaluate_outputs  # noqa: F401
        import prei.stats  # noqa: F401
        import prei.stats_bootstrap  # noqa: F401

    def test_evaluate_reexports(self):
        import prei.evaluate as ev
        missing = [n for n in EVALUATE_NAMES if not hasattr(ev, n)]
        self.assertEqual(missing, [], f"prei.evaluate missing re-exports: {missing}")

    def test_stats_reexports(self):
        import prei.stats as st
        missing = [n for n in STATS_NAMES if not hasattr(st, n)]
        self.assertEqual(missing, [], f"prei.stats missing re-exports: {missing}")

    def test_layering_no_cycles(self):
        base = _source("evaluate_base.py")
        self.assertNotIn("evaluate_v2", base, "evaluate_base references evaluate_v2")
        self.assertNotIn("evaluate_outputs", base, "evaluate_base references evaluate_outputs")
        self.assertNotIn("from .evaluate import", base, "evaluate_base imports from facade")
        v2 = _source("evaluate_v2.py")
        self.assertNotIn("evaluate_outputs", v2, "evaluate_v2 references evaluate_outputs")
        boot = _source("stats_bootstrap.py")
        self.assertNotIn("from .stats import", boot, "stats_bootstrap imports from facade")

    def test_file_size_limits(self):
        limit = 24000
        offenders = []
        for fn in sorted(os.listdir(PREI_DIR)):
            if not fn.endswith(".py") or fn == "__init__.py":
                continue
            text = _source(fn)
            if len(text) >= limit:
                offenders.append((fn, len(text)))
        self.assertEqual(offenders, [], f"modules at/over {limit} chars: {offenders}")


if __name__ == "__main__":
    unittest.main()
