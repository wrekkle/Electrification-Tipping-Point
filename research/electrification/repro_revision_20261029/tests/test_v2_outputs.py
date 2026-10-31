# -*- coding: utf-8 -*-
"""Unit tests for the PREI reproduction package (standard library unittest).

Run:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import math
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPRO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPRO, "src"))

from prei import capacity, config, costs, demand, evaluate, io, rules, simulator, stats  # noqa: E402


def load_settings(scenario_count=40):
    cfg = config.load_config(os.path.join(REPRO, "configs", "baseline.yaml"))
    settings = cfg.resolved()
    modes = config.load_config(os.path.join(REPRO, "configs", "modes.yaml")).resolved()
    settings["modes"] = modes["modes"]
    settings["seed"] = 42
    settings["run"]["scenario_count"] = scenario_count
    return cfg, settings


def load_v2_settings(scenario_count=4):
    cfg, settings = load_settings(scenario_count)
    v2 = config.load_config(os.path.join(REPRO, "configs", "v2.yaml")).resolved()["v2"]
    merged = copy.deepcopy(settings)
    merged["v2"] = v2
    merged["demand"] = dict(merged["demand"])
    merged["demand"].update(v2["demand"])
    merged["cost"] = dict(merged["cost"])
    merged["cost"].update(v2.get("cost", {}))
    merged["v2"]["scenario_count"] = scenario_count
    return merged




class TestV2StatisticsAndOutputs(unittest.TestCase):
    """v2 statistical layer, figure-8 grid, CVaR flags and output hygiene."""

    @staticmethod
    def _synthetic_cell(full_value, partial_value):
        designs = [
            {"mode": "fixed", "rule": "pi_S", "theta": 0.0, "m": 20,
             "coverage": 1, "reposition_min": 0.0, "power_kw": 50.0,
             "feeder_kw": 500.0},
            {"mode": "fixed", "rule": "pi_F", "theta": 0.0, "m": 100,
             "coverage": 1, "reposition_min": 0.0, "power_kw": 50.0,
             "feeder_kw": 500.0},
            {"mode": "overhead", "rule": "pi_F", "theta": 0.0, "m": 40,
             "coverage": 2, "reposition_min": 10.0, "power_kw": 50.0,
             "feeder_kw": 500.0},
        ]
        n = 40
        rng = np.random.default_rng(7)
        loss = np.abs(rng.normal(10.0, 1.0, size=(n, len(designs))))
        partial = np.asarray(partial_value, dtype=float)
        V = np.column_stack([np.full(n, partial[0]),
                             np.full(n, full_value),
                             np.full(n, partial[1])])
        V += rng.normal(0.0, 0.2, size=V.shape)
        return {"lot_type": "plc", "ev_mode": "binomial", "r": 0.6, "q": 0.6,
                "designs": designs, "loss": loss, "V": V, "n_days": n}

    def test_arrivals_override_applied(self):
        cfg, settings = load_settings(scenario_count=30)
        settings["lot"]["arrivals_override"] = 10.0
        self.assertAlmostEqual(evaluate.arrivals_mean(settings, "pnc"), 10.0)
        scen = evaluate.scenario_set(settings, 42, "pnc", 0.4, "binomial")
        self.assertAlmostEqual(float(np.mean(scen["A"])), 10.0, delta=1.0)

    def test_cvar_fields_full_install_flag(self):
        best = np.array([10.0] * 100)
        zero = np.zeros(100)
        fields = evaluate.cvar_fields(best, zero)
        self.assertTrue(fields["full_install_evaluated"])
        self.assertEqual(fields["cvar_full_install_rmb"], 0.0)
        self.assertIn("identically zero", fields["full_install_zero_reason"])
        self.assertEqual(fields["cost_basis"], "daily_operating_loss_rmb")
        nonzero = evaluate.cvar_fields(best, best)
        self.assertEqual(nonzero["full_install_zero_reason"], "")
        self.assertGreater(nonzero["cvar_full_install_rmb"], 0.0)

    def test_v2_cell_stats_region_labels(self):
        cfg, settings = load_settings(scenario_count=30)
        _, settings = load_settings(scenario_count=30)
        cell = self._synthetic_cell(full_value=120.0, partial_value=(90.0, 100.0))
        rng = np.random.default_rng(3)
        out = evaluate.v2_cell_stats(cell, settings, n_boot=200, rng=rng)
        self.assertGreater(out["g"]["g_hi"], 0.0)
        self.assertEqual(out["g"]["region"], "partial_dominant")
        self.assertEqual(out["g"]["best_partial"], "fixed,pi_S,m=20")
        cell2 = self._synthetic_cell(full_value=80.0, partial_value=(90.0, 100.0))
        out2 = evaluate.v2_cell_stats(cell2, settings, n_boot=200,
                                      rng=np.random.default_rng(4))
        self.assertLess(out2["g"]["g_hi"], 0.0)
        self.assertEqual(out2["g"]["region"], "full_dominant")

    def test_v2_cell_stats_confidence_set_contains_best(self):
        cfg, settings = load_settings(scenario_count=30)
        cell = self._synthetic_cell(full_value=120.0, partial_value=(90.0, 100.0))
        out = evaluate.v2_cell_stats(cell, settings, n_boot=200,
                                     rng=np.random.default_rng(5),
                                     candidate_modes=None)
        labels = [evaluate.design_label(d) for d in cell["designs"]]
        self.assertIn(out["confidence"]["best"], labels)
        self.assertGreaterEqual(out["confidence"]["set_size"], 1)
        self.assertEqual(out["confidence"]["n_candidates"], len(labels))

    def test_fig8_grid_columns(self):
        cfg, settings = load_settings(scenario_count=25)
        cm = costs.CostModel(settings, 42)
        rows = evaluate.fig8_rows(
            settings, cm, 42, scarcity_values=(0.6,), r_values=(0.2,),
            ev_modes=("binomial",), lot_types=("pnc",), n_boot=100)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["lot_type"], "pnc")
        self.assertAlmostEqual(row["pnc_vacancy_rate"], 0.4)
        self.assertIn(row["region"],
                      {"full_dominant", "partial_dominant", "undetermined"})
        self.assertLessEqual(row["g_lo"], row["g_hi"])

    def test_canonicalize_outputs(self):
        sys.path.insert(0, REPRO)
        import run_all
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = os.path.join(tmp, "baseline")
            run_a = os.path.join(cfg_dir, "20260101-000000-seed42")
            run_b = os.path.join(cfg_dir, "20260102-000000-seed42")
            io.ensure_dir(run_a)
            io.ensure_dir(run_b)
            io.write_json(os.path.join(run_b, "summary.json"), {"ok": True})
            canonical, moved = run_all.canonicalize_outputs(tmp, "baseline", run_b, 42)
            self.assertTrue(os.path.isdir(os.path.join(canonical)))
            self.assertEqual(os.path.basename(canonical), "canonical-seed42")
            self.assertIn(os.path.basename(run_a), moved)
            archive = os.path.join(tmp, "_archive", "baseline", os.path.basename(run_a))
            self.assertTrue(os.path.isdir(archive))
            self.assertEqual(sorted(os.listdir(cfg_dir)), ["canonical-seed42"])

    def test_manifest_metadata_fields(self):
        sys.path.insert(0, REPRO)
        import run_all
        meta = run_all.manifest_metadata(
            ["run_all.py", "--mode", "all"],
            [os.path.join(REPRO, "configs", "baseline.yaml")], {"static": 1.0})
        self.assertIn("python_version", meta)
        self.assertIn("run_all.py", meta["command"])
        self.assertIn("baseline.yaml", meta["config_sha256"])
        self.assertEqual(meta["timings"], {"static": 1.0})

    def test_gitignore_and_readme_reference(self):
        gitignore = os.path.join(REPRO, ".gitignore")
        self.assertTrue(os.path.isfile(gitignore))
        text = open(gitignore, encoding="utf-8").read()
        self.assertIn("outputs/", text)
        self.assertIn("__pycache__/", text)
        readme = open(os.path.join(REPRO, "README.md"), encoding="utf-8").read()
        self.assertIn(".gitignore", readme)
        self.assertIn("canonical-seed", readme)

    def test_saa_rows_shape(self):
        cfg, settings = load_settings(scenario_count=15)
        cm = costs.CostModel(settings, 42)
        rows = evaluate.saa_rows(settings, cm, 42, reps=2)
        self.assertEqual(len(rows), 36)
        for row in rows:
            self.assertGreaterEqual(row["hit_rate"], 0.5)
            self.assertLessEqual(row["hit_rate"], 1.0)
            self.assertGreaterEqual(row["psc_std_rmb"], 0.0)
            self.assertGreater(row["psc_mean_rmb"], 0.0)

    def test_feasibility_rows_scale_effect(self):
        cfg, settings = load_settings(scenario_count=20)
        rows = evaluate.feasibility_rows(
            settings, 42, scales=(1.0, 36.0), horizons=(5.0,),
            r_values=(0.6,), lot_types=("plc",), ev_modes=("binomial",))
        self.assertEqual(len(rows), 2)
        low = [r for r in rows if r["event_cost_scale"] == 1.0][0]
        self.assertFalse(low["interior_optimum"])
        self.assertEqual(low["best_m"], 0)
        for row in rows:
            self.assertIsInstance(row["interior_optimum"], bool)

