# -*- coding: utf-8 -*-
"""Target-contract regressions for the 2026-10-29 review items R1-R7.

These tests are written against the *intended* contract of the revision
directory, not against the current implementation.  Run against the copied
(unfixed) sources they must fail; run against the revised sources they must
pass.  Every expected value is either hand-computable or an exact property of
the stated statistical definition; none of them is tuned to a paper number.

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

from prei import capacity, config, costs, demand, evaluate, simulator, stats  # noqa: E402


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
    return cfg, merged


def design(mode="fixed", m=2, rule="pi_F", theta=0.0, coverage=1,
           reposition_min=0.0, power_kw=50.0, feeder_kw=500.0):
    return {"mode": mode, "m": int(m), "rule": rule, "theta": float(theta),
            "coverage": int(coverage), "reposition_min": float(reposition_min),
            "power_kw": float(power_kw), "feeder_kw": float(feeder_kw)}


def make_day(times_min, classes, dwell_min, energy_req):
    """Build a hand-written day record in the documented minute contract."""
    classes = np.asarray(classes, dtype=object)
    counts = {"A": int(len(classes)),
              "ev_charge": int(np.sum(classes == "ev_charge")),
              "ev_park": int(np.sum(classes == "ev_park")),
              "icev": int(np.sum(classes == "icev"))}
    counts["ev"] = counts["ev_charge"] + counts["ev_park"]
    return {"times_min": np.asarray(times_min, dtype=float),
            "classes": classes,
            "dwell_min": np.asarray(dwell_min, dtype=float),
            "energy_req": np.asarray(energy_req, dtype=float),
            "r_draw": counts["ev"] / max(1, counts["A"]),
            "time_unit": "minute",
            "counts": counts}


def rows_for(signs, r_values=(0.2, 0.4, 0.6, 0.8)):
    return [{"r": float(r), "g_hat": float(g)}
            for r, g in zip(r_values, signs)]




class TestF09GIntervalCoverage(unittest.TestCase):
    """F09: g intervals must keep nominal coverage under near-tie selection."""

    SEEDS = [20261101 + i for i in range(20)]

    @staticmethod
    def _tie_data(seed, K=6, S=120, sigma=1.0, true_g=-5.0):
        rng = np.random.default_rng(seed)
        common = rng.normal(0.0, sigma, size=(S, 1))
        part = common + rng.normal(0.0, sigma, size=(S, K))
        full = common + true_g + rng.normal(0.0, sigma, size=(S, 1))
        return full, part

    def test_default_method_is_simultaneous(self):
        full, part = self._tie_data(self.SEEDS[0])
        gi = stats.g_interval(full, part, n_boot=400,
                              rng=np.random.default_rng(1))
        self.assertEqual(gi["method"], "simultaneous-max-t")
        self.assertEqual(gi["n_partial"], 6)
        self.assertGreater(gi["critical_value"], 1.9)  # selection-adjusted
        self.assertLessEqual(gi["g_lo"], gi["g_hat"])
        self.assertGreaterEqual(gi["g_hi"], gi["g_hat"])
        self.assertAlmostEqual(
            gi["g_hat"], float(full.mean() - part.mean(axis=0).min()), places=9)

    def test_interval_covers_true_g_across_fixed_seeds(self):
        covered, widths = 0, []
        for i, seed in enumerate(self.SEEDS):
            full, part = self._tie_data(seed)
            gi = stats.g_interval(full, part, n_boot=400,
                                  rng=np.random.default_rng(7000 + i))
            covered += int(gi["g_lo"] <= -5.0 <= gi["g_hi"])
            widths.append(gi["g_hi"] - gi["g_lo"])
        self.assertGreaterEqual(
            covered, 18, msg="fixed-seed near-tie coverage %d/20 (need >= 18)"
                             % covered)
        self.assertGreater(float(np.mean(widths)), 0.0)

    def test_percentile_diagnostic_is_narrower(self):
        full, part = self._tie_data(self.SEEDS[0])
        sim = stats.g_interval(full, part, n_boot=400,
                               rng=np.random.default_rng(3))
        pct = stats.g_interval(full, part, n_boot=400,
                               rng=np.random.default_rng(3),
                               method="percentile")
        self.assertEqual(pct["method"], "paired_block_bootstrap_percentile")
        self.assertLess(pct["g_hi"] - pct["g_lo"], sim["g_hi"] - sim["g_lo"])

    def test_single_candidate_and_exact_offset_stay_exact(self):
        rng = np.random.default_rng(11)
        part = 100.0 + rng.normal(100.0, 10.0, size=(10, 1))
        full = part[:, 0] + 10.0
        gi = stats.g_interval(full, part, n_boot=300, rng=rng)
        self.assertAlmostEqual(gi["g_lo"], 10.0, places=9)
        self.assertAlmostEqual(gi["g_hi"], 10.0, places=9)
        self.assertEqual(gi["n_partial"], 1)

    def test_structure_separates_window_from_suffix(self):
        island = [
            {"r": 0.2, "g_hat": -1.0, "g_lo": -2.0, "g_hi": -0.5},
            {"r": 0.4, "g_hat": -2.0, "g_lo": -3.0, "g_hi": -1.0},
            {"r": 0.6, "g_hat": 1.0, "g_lo": 0.5, "g_hi": 2.0},
            {"r": 0.8, "g_hat": 2.0, "g_lo": 1.0, "g_hi": 3.0},
        ]
        st = stats.g_structure(island)
        self.assertIsNone(st["etp_sustained_suffix"])
        self.assertEqual(st["full_dominant_windows"], [[0.2, 0.4]])
        self.assertEqual(st["partial_dominant_windows"], [[0.6, 0.8]])
        self.assertEqual(st["negative_islands"], [[0.2, 0.4]])
        sustained = [
            {"r": 0.2, "g_hat": -1.0, "g_lo": -2.0, "g_hi": -0.5},
            {"r": 0.4, "g_hat": -2.0, "g_lo": -3.0, "g_hi": -1.0},
            {"r": 0.6, "g_hat": -3.0, "g_lo": -4.0, "g_hi": -2.0},
        ]
        st2 = stats.g_structure(sustained)
        self.assertAlmostEqual(st2["etp_sustained_suffix"], 0.2)
        self.assertEqual(st2["negative_islands"], [])
        self.assertEqual(st2["full_dominant_windows"], [[0.2, 0.6]])


class TestF09RuleScope(unittest.TestCase):
    """F09: report whether the g comparison also changes the admission rule."""

    @staticmethod
    def _cell():
        designs = [
            {"mode": "fixed", "rule": "pi_S", "theta": 0.0, "m": 20,
             "coverage": 1, "reposition_min": 0.0, "power_kw": 50.0,
             "feeder_kw": 500.0},
            {"mode": "fixed", "rule": "pi_F", "theta": 0.0, "m": 40,
             "coverage": 1, "reposition_min": 0.0, "power_kw": 50.0,
             "feeder_kw": 500.0},
            {"mode": "fixed", "rule": "pi_F", "theta": 0.0, "m": 100,
             "coverage": 1, "reposition_min": 0.0, "power_kw": 50.0,
             "feeder_kw": 500.0},
        ]
        rng = np.random.default_rng(17)
        n = 60
        V = np.column_stack([np.full(n, 240.0), np.full(n, 260.0),
                             np.full(n, 520.0)])
        V += rng.normal(0.0, 0.5, size=V.shape)
        loss = np.abs(rng.normal(10.0, 1.0, size=(n, 3)))
        return {"lot_type": "plc", "ev_mode": "binomial", "r": 0.6, "q": 0.6,
                "designs": designs, "loss": loss, "V": V, "n_days": n}

    def test_cell_reports_rule_scope_and_same_rule_sensitivity(self):
        _, settings = load_v2_settings()
        cell = self._cell()
        out = evaluate.v2_cell_stats(cell, settings, n_boot=300,
                                     rng=np.random.default_rng(5))
        g = out["g"]
        self.assertIn("best_partial_rule", g)
        self.assertIn("rule_changed_vs_full", g)
        self.assertIn("n_partial_rule_fixed", g)
        self.assertIn("partial_rule_count", g)
        # the cheapest partial is pi_S m=20 here, i.e. the comparison does
        # change the rule at the same time as the capacity
        self.assertTrue(g["rule_changed_vs_full"])
        self.assertEqual(g["best_partial_rule"], "pi_S")
        # the same-rule sensitivity keeps only fixed,pi_F,m=40
        self.assertEqual(g["n_partial_rule_fixed"], 1)
        self.assertIsNotNone(g["g_hat_rule_fixed"])
        want = float(cell["V"][:, 2].mean() - cell["V"][:, 1].mean())
        self.assertAlmostEqual(g["g_hat_rule_fixed"], want, places=9)


class TestF09bIntervalMetadata(unittest.TestCase):
    """A machine flag must follow the applicability conditions, not the name."""

    @staticmethod
    def _data(seed=3, S=60, K=4):
        rng = np.random.default_rng(seed)
        part = rng.normal(100.0, 10.0, size=(S, K))
        full = part[:, [0]] - 5.0 + rng.normal(0.0, 1.0, size=(S, 1))
        return full, part

    def test_iid_scenarios_keep_nominal_flag(self):
        full, part = self._data()
        gi = stats.g_interval(full, part, n_boot=200, block_len=1,
                             rng=np.random.default_rng(1))
        self.assertTrue(gi["nominal_coverage"])
        self.assertFalse(gi["diagnostic_only"])
        self.assertIn("block_len=1", gi["coverage_scope"])
        self.assertIn("iid", gi["coverage_scope"])

    def test_block_bootstrap_blocks_are_diagnostic_only(self):
        full, part = self._data()
        gi = stats.g_interval(full, part, n_boot=200, block_len=8,
                             rng=np.random.default_rng(1))
        self.assertFalse(gi["nominal_coverage"])
        self.assertTrue(gi["diagnostic_only"])
        self.assertIn("block_len=8", gi["coverage_scope"])
        self.assertIn("not establish", gi["coverage_scope"])

    def test_declared_dependence_overrides_block_len_one(self):
        full, part = self._data()
        gi = stats.g_interval(full, part, n_boot=200, block_len=1,
                             rng=np.random.default_rng(1),
                             independent_scenarios=False)
        self.assertFalse(gi["nominal_coverage"])
        self.assertTrue(gi["diagnostic_only"])
        self.assertIn("declared dependent", gi["coverage_scope"])

    def test_percentile_stays_diagnostic(self):
        full, part = self._data()
        gi = stats.g_interval(full, part, n_boot=200, block_len=1,
                             rng=np.random.default_rng(1),
                             method="percentile")
        self.assertFalse(gi["nominal_coverage"])
        self.assertTrue(gi["diagnostic_only"])

    def test_scope_is_per_r_not_joint_across_r(self):
        full, part = self._data()
        gi = stats.g_interval(full, part, n_boot=200, block_len=1,
                             rng=np.random.default_rng(1))
        self.assertEqual(gi["interval_scope"], "per_r_pointwise")
        self.assertFalse(gi["joint_across_r"])


class TestF09bDownstreamScope(unittest.TestCase):
    """Downstream rows must not present a diagnostic interval as nominal."""

    @staticmethod
    def _cell():
        designs = [
            {"mode": "fixed", "rule": "pi_S", "theta": 0.0, "m": 20,
             "coverage": 1, "reposition_min": 0.0, "power_kw": 50.0,
             "feeder_kw": 500.0},
            {"mode": "fixed", "rule": "pi_F", "theta": 0.0, "m": 40,
             "coverage": 1, "reposition_min": 0.0, "power_kw": 50.0,
             "feeder_kw": 500.0},
            {"mode": "fixed", "rule": "pi_F", "theta": 0.0, "m": 100,
             "coverage": 1, "reposition_min": 0.0, "power_kw": 50.0,
             "feeder_kw": 500.0},
        ]
        rng = np.random.default_rng(17)
        n = 60
        V = np.column_stack([np.full(n, 240.0), np.full(n, 260.0),
                             np.full(n, 520.0)])
        V += rng.normal(0.0, 0.5, size=V.shape)
        loss = np.abs(rng.normal(10.0, 1.0, size=(n, 3)))
        return {"lot_type": "plc", "ev_mode": "binomial", "r": 0.6, "q": 0.6,
                "designs": designs, "loss": loss, "V": V, "n_days": n}

    def test_iid_cell_labels_region_nominal(self):
        _, settings = load_v2_settings()
        out = evaluate.v2_cell_stats(self._cell(), settings, n_boot=200,
                                     rng=np.random.default_rng(5))
        g, reg = out["g"], out["regions"]
        self.assertTrue(g["g_nominal_coverage"])
        self.assertFalse(g["g_diagnostic_only"])
        self.assertEqual(g["g_interval_scope"], "per_r_pointwise")
        self.assertFalse(g["g_joint_across_r"])
        self.assertEqual(g["region_confidence"], "nominal")
        self.assertEqual(reg["region_confidence"], "nominal")
        self.assertFalse(reg["g_joint_across_r"])

    def test_block_bootstrap_cell_labels_region_diagnostic(self):
        _, settings = load_v2_settings()
        out = evaluate.v2_cell_stats(self._cell(), settings, n_boot=200,
                                     block_len=8,
                                     rng=np.random.default_rng(5))
        g, reg = out["g"], out["regions"]
        self.assertFalse(g["g_nominal_coverage"])
        self.assertTrue(g["g_diagnostic_only"])
        self.assertEqual(g["region_confidence"], "diagnostic")
        self.assertEqual(reg["region_confidence"], "diagnostic")
        self.assertFalse(reg["g_joint_across_r"])

    def test_g_structure_carries_scope_flags(self):
        rows = []
        for r, nominal in ((0.2, True), (0.4, True), (0.6, False)):
            rows.append({"lot_type": "plc", "ev_mode": "beta", "r": r,
                         "q": 0.6, "g_hat": -10.0, "g_lo": -20.0,
                         "g_hi": -1.0, "g_nominal_coverage": nominal})
        st = evaluate.v2_g_structure(rows)
        self.assertEqual(len(st), 1)
        row = st[0]
        self.assertFalse(row["joint_across_r"])
        self.assertEqual(row["interval_scope"], "per_r_pointwise")
        self.assertEqual(row["rows_nominal"], 2)
        self.assertEqual(row["rows_diagnostic"], 1)
        self.assertFalse(row["all_rows_nominal"])
        self.assertIn("point estimate", row["suffix_basis"])
        self.assertIn("g_hi", row["full_dominant_basis"])


class TestF09bStructureNonFinite(unittest.TestCase):
    """NaN is missing information, never a negative value."""

    def test_nan_is_not_a_negative_island(self):
        rows = [
            {"r": 0.2, "g_hat": -1.0, "g_lo": -2.0, "g_hi": -0.5},
            {"r": 0.4, "g_hat": float("nan"), "g_lo": float("nan"),
             "g_hi": float("nan")},
            {"r": 0.6, "g_hat": -2.0, "g_lo": -3.0, "g_hi": -1.0},
            {"r": 0.8, "g_hat": -3.0, "g_lo": -4.0, "g_hi": -2.0},
        ]
        st = stats.g_structure(rows)
        self.assertEqual(st["negative_islands"], [[0.2, 0.2]])
        self.assertAlmostEqual(st["etp_sustained_suffix"], 0.6)
        self.assertEqual(st["n_non_finite"], 1)
        # windows skip the missing point instead of treating it as dominant
        self.assertEqual(st["full_dominant_windows"], [[0.2, 0.2], [0.6, 0.8]])

    def test_partially_finite_row_is_not_a_window(self):
        # A NaN g_hat with finite bounds is still a MISSING row: the finite
        # bound alone must not turn it into a full/partial-dominant window.
        rows = [
            {"r": 0.2, "g_hat": float("nan"), "g_lo": -2.0, "g_hi": -1.0},
            {"r": 0.4, "g_hat": float("nan"), "g_lo": 1.0, "g_hi": 2.0},
        ]
        st = stats.g_structure(rows)
        self.assertEqual(st["full_dominant_windows"], [])
        self.assertEqual(st["partial_dominant_windows"], [])
        self.assertEqual(st["negative_islands"], [])
        self.assertEqual(st["n_non_finite"], 2)

    def test_missing_value_cannot_extend_the_suffix(self):
        rows = [
            {"r": 0.2, "g_hat": -1.0, "g_lo": -2.0, "g_hi": -0.5},
            {"r": 0.4, "g_hat": -2.0, "g_lo": -3.0, "g_hi": -1.0},
            {"r": 0.6, "g_hat": None, "g_lo": None, "g_hi": None},
            {"r": 0.8, "g_hat": -3.0, "g_lo": -4.0, "g_hi": -2.0},
        ]
        st = stats.g_structure(rows)
        # negative at 0.2 and 0.4 cannot be prolonged through the missing 0.6
        self.assertAlmostEqual(st["etp_sustained_suffix"], 0.8)
        self.assertEqual(st["negative_islands"], [[0.2, 0.4]])
        self.assertEqual(st["n_non_finite"], 1)
        self.assertEqual(st["full_dominant_windows"], [[0.2, 0.4], [0.8, 0.8]])
        # same convention as etp_from_g: a missing value behaves like NaN,
        # i.e. "not cheaper", so it breaks the suffix instead of extending it
        as_nan = [{**row, "g_hat": float("nan")} if row["g_hat"] is None else row
                  for row in rows]
        self.assertAlmostEqual(st["etp_sustained_suffix"],
                               stats.etp_from_g(as_nan))

