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




class TestStatistics(unittest.TestCase):
    def test_decomposition_identity(self):
        out = stats.decompose(1000.0, 950.0, 800.0, 700.0)
        self.assertAlmostEqual(out["identity_gap"], 0.0, places=9)
        self.assertAlmostEqual(out["total"], 300.0, places=9)
        self.assertAlmostEqual(
            out["capacity_effect_pathA"] + out["rule_effect_pathA"], 300.0, places=9)
        self.assertAlmostEqual(
            out["capacity_effect_pathB"] + out["rule_effect_pathB"], 300.0, places=9)
        self.assertAlmostEqual(
            out["path_dependence_capacity"],
            out["capacity_effect_pathA"] - out["capacity_effect_pathB"], places=9)

    def test_three_region(self):
        self.assertEqual(stats.three_region(-10.0, -20.0, -1.0), "full_dominant")
        self.assertEqual(stats.three_region(10.0, 1.0, 20.0), "partial_dominant")
        self.assertEqual(stats.three_region(1.0, -2.0, 3.0), "undetermined")

    def test_cvar_tail_and_ties(self):
        losses = np.arange(1.0, 101.0)  # 1..100
        out = stats.empirical_cvar(losses, 0.95)
        self.assertEqual(out["n"], 100)
        self.assertEqual(out["tail_n"], 5)
        self.assertAlmostEqual(out["var"], 96.0)  # smallest value in the 5% tail
        self.assertAlmostEqual(out["cvar"], 98.0)
        self.assertAlmostEqual(out["cvar_aux"], 98.0, places=9)
        tied = np.array([10.0] * 95 + [100.0] * 5)
        out2 = stats.empirical_cvar(tied, 0.95)
        self.assertEqual(out2["tail_n"], 5)
        self.assertAlmostEqual(out2["cvar"], 100.0)

    def test_confidence_set_coverage_synthetic(self):
        true_means = np.array([1.00, 0.985, 0.96, 0.94, 1.02, 1.05, 1.10, 1.15])
        true_best = 3
        covered = 0
        reps = 200
        n_scen = 60
        for rep in range(reps):
            rng = np.random.default_rng(2000 + rep)
            common = rng.normal(0.0, 0.08, size=(n_scen, 1))
            costs_mat = true_means[None, :] + common + rng.normal(
                0.0, 0.05, size=(n_scen, true_means.size))
            cs = stats.confidence_set(costs_mat, n_boot=400, alpha=0.05,
                                      rng=np.random.default_rng(9000 + rep))
            covered += int(true_best in cs["included"])
        self.assertGreaterEqual(covered / reps, 0.90,
                                msg="coverage %.3f below 90%%" % (covered / reps))

    def test_confidence_set_excludes_dominated(self):
        rng = np.random.default_rng(1)
        means = np.array([1.0, 1.5, 2.0, 2.5])
        mat = means[None, :] + rng.normal(0, 0.02, size=(80, 4))
        cs = stats.confidence_set(mat, n_boot=500, alpha=0.05)
        self.assertEqual(cs["best"], 0)
        self.assertIn(0, cs["included"])
        self.assertNotIn(3, cs["included"])


class TestSimulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = load_v2_settings(scenario_count=3)
        cls.cm = costs.CostModel(cls.settings, 42)
        rng = np.random.default_rng(99)
        cls.day = evaluate.prepare_v2_day(rng, cls.settings, 0.7, 0.6, "beta", "pnc")
        cls.N = int(cls.settings["lot"]["n_spaces"])

    def _design(self, mode, m, rule, theta=0.0):
        return {"mode": mode, "m": m, "rule": rule, "theta": theta,
                "coverage": 2 if mode == "overhead" else 1,
                "reposition_min": 10.0 if mode == "overhead" else 0.0,
                "power_kw": 50.0, "feeder_kw": 500.0}

    def test_day_conservation_and_energy(self):
        out = simulator.simulate_day(self.settings, self.cm,
                                     self._design("fixed", 20, "pi_S"), self.day)
        m = out["metrics"]
        self.assertEqual(m["admitted"] + m["blocked_total"], m["arrivals_A"])
        self.assertLessEqual(m["energy_delivered_kwh"], m["energy_requested_kwh"] + 1e-9)
        self.assertAlmostEqual(
            m["energy_delivered_kwh"] + m["shortfall_kwh"],
            m["energy_requested_kwh"], places=9)
        self.assertLessEqual(m["peak_power_kw"], 500.0 + 1e-9)
        self.assertLessEqual(m["peak_concurrency"], 20)

    def test_timeline_order_and_connection(self):
        out = simulator.simulate_day(self.settings, self.cm,
                                     self._design("fixed", 40, "pi_F"), self.day)
        arr = [row["t_a"] for row in out["timeline"]]
        self.assertTrue(all(b >= a - 1e-12 for a, b in zip(arr, arr[1:])))
        for row in out["timeline"]:
            if row["blocked"]:
                self.assertIsNone(row["berth"])
                continue
            self.assertLessEqual(row["t_a"], row["t_r"])
            if row["t_c"] is not None:
                self.assertGreaterEqual(row["t_c"], row["t_a"] - 1e-12)
                self.assertGreaterEqual(row["t_d"], row["t_c"] - 1e-9)
                self.assertLessEqual(row["t_d"], row["t_r"] + 1e-9)
                self.assertLessEqual(row["energy_delivered_kwh"],
                                     row["energy_requested_kwh"] + 1e-9)

    def test_rule_effect_on_admission(self):
        # ICEV-heavy day on a small lot: under pi_S the ICEVs may use ordinary
        # berths only, under pi_F they may also use the free charging berths.
        settings = copy.deepcopy(self.settings)
        settings["lot"]["n_spaces"] = 20
        n = 30
        classes = np.array(["icev"] * 26 + ["ev_park"] * 2 + ["ev_charge"] * 2,
                           dtype=object)
        day = {
            "times_min": np.arange(n, dtype=float) * 12.0,
            "classes": classes,
            "dwell_min": np.full(n, 300.0),
            "energy_req": np.full(n, 5.0),
            "r_draw": 0.15,
            "counts": {"A": n, "ev": 4, "ev_charge": 2, "ev_park": 2, "icev": 26},
        }
        admitted = {}
        for rule in ("pi_S", "pi_F"):
            out = simulator.simulate_day(
                settings, self.cm, self._design("fixed", 10, rule), day)
            admitted[rule] = out["metrics"]["admitted"]
        self.assertGreater(admitted["pi_F"], admitted["pi_S"])

    def test_overhead_energy_and_invariants(self):
        out = simulator.simulate_day(self.settings, self.cm,
                                     self._design("overhead", 40, "pi_F"), self.day)
        m = out["metrics"]
        self.assertLessEqual(m["peak_power_kw"], 500.0 + 1e-9)
        self.assertLessEqual(m["peak_concurrency"], 40)
        out["ledger"].assert_invariants()

    def test_short_stay_can_undeliver(self):
        # a one-minute stay cannot deliver 20 kWh at 50 kW: shortfall, not blocked
        settings = copy.deepcopy(self.settings)
        settings["demand"]["dwell"]["min_min"] = 1.0
        settings["demand"]["dwell"]["max_min"] = 1.0
        out = simulator.simulate_day(settings, self.cm,
                                     self._design("fixed", 100, "pi_F"), self.day)
        self.assertGreater(out["metrics"]["shortfall_kwh"], 0.0)
        out["ledger"].assert_invariants()


class TestConfig(unittest.TestCase):
    def test_sources_present(self):
        cfg = config.load_config(os.path.join(REPRO, "configs", "baseline.yaml"))
        self.assertGreater(len(cfg.params), 30)
        src = set(cfg.source_map().values())
        self.assertEqual(src, {"manuscript", "assumption", "sensitivity"})
        resolved = cfg.resolved()
        self.assertEqual(resolved["cost"]["c_char"], 60000.0)
        self.assertEqual(resolved["cost"]["event_cost_scale"], 36.0)

    def test_invalid_source_rejected(self):
        tree = config.parse_yaml_text(
            "run:\n  horizon_years: {value: 5.0, source: guess}\n")
        cfg = config.Config(tree)
        with self.assertRaises(config.ConfigError):
            cfg.validate(required=["run.horizon_years"])

    def test_missing_parameter_rejected(self):
        tree = config.parse_yaml_text(
            "run:\n  horizon_years: {value: 5.0, source: assumption}\n")
        cfg = config.Config(tree)
        with self.assertRaises(config.ConfigError):
            cfg.validate(required=["run.nope"])

    def test_content_hash_stable(self):
        payload = {"a": 1, "b": [1, 2], "c": "x"}
        self.assertEqual(io.content_hash(payload), io.content_hash(copy.deepcopy(payload)))
        self.assertNotEqual(io.content_hash(payload), io.content_hash({"a": 2}))

    def test_seed_derivation_stable(self):
        self.assertEqual(config.derive_seed(42, "a", 1), config.derive_seed(42, "a", 1))
        self.assertNotEqual(config.derive_seed(42, "a", 1), config.derive_seed(42, "a", 2))

