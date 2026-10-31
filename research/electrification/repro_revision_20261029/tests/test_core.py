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




class TestCostModel(unittest.TestCase):
    def setUp(self):
        self.cfg, self.settings = load_settings()
        self.cm = costs.CostModel(self.settings, 1)

    def test_time_cost_units(self):
        # eq. (5): 6 min = 0.1 h, k=1.12, mean VOT = exp(mu+sigma^2/2) = 28.4
        vot_mean = math.exp(2.98 + 0.5 * 0.8499 ** 2)
        self.assertAlmostEqual(vot_mean, 28.25, delta=0.05)
        self.assertAlmostEqual(self.cm.time_cost(), 0.1 * 1.12 * vot_mean, places=9)
        self.assertAlmostEqual(self.cm.fuel_cost("ev"), 0.1 * 30.0 * 0.2, places=9)
        self.assertAlmostEqual(self.cm.fuel_cost("icev"), 0.1 * 30.0 * 0.8, places=9)

    def test_pile_cost_period(self):
        # eq. (2) converted to H years: m * (C_char/L + C_om) * H
        self.assertAlmostEqual(self.cm.pile_cost(1), (60000.0 / 5.0) * 5.0, places=6)
        self.assertAlmostEqual(self.cm.pile_cost(10), 600000.0, places=6)
        self.assertAlmostEqual(self.cm.pile_cost(0), 0.0)

    def test_embedded_vs_separate_complaint(self):
        cfg, settings = load_settings()
        settings["cost"]["complaint_accounting"] = "separate"
        sep = costs.CostModel(settings, 1)
        emb = self.cm
        base_emb = emb.event_cost("ev")
        base_sep = sep.event_cost("ev")
        # embedded adds the full C_com; separate adds prob*C_com, so separate is lower
        self.assertLess(base_sep, base_emb)
        self.assertAlmostEqual(
            (base_emb - base_sep) / emb.event_cost_scale,
            emb.c_com - emb.mean_complaint_prob * emb.c_com, places=9)
        # the separate PSC adds eq. (7) back once, never twice
        le = np.array([5.0, 10.0])
        zero = np.zeros_like(le)
        psc_sep = sep.psc(0, le, zero)
        expected = sep.loss_cost(le, zero) + sep.separate_complaint_cost(le)
        self.assertAlmostEqual(psc_sep, expected, places=6)

    def test_event_cost_scale(self):
        cfg, settings = load_settings()
        settings["cost"]["event_cost_scale"] = 1.0
        cm1 = costs.CostModel(settings, 1)
        self.assertAlmostEqual(self.cm.event_cost("ev") / cm1.event_cost("ev"), 36.0, places=6)
        # documented consequence: literal 5.36 RMB/event cannot pay a 60k pile in 5y
        self.assertGreater(cm1.event_cost("ev"), 3.0)
        self.assertGreater(self.cm.event_cost("ev"), 150.0)


class TestDemand(unittest.TestCase):
    def test_beta_domain(self):
        a, b = demand.beta_parameters(0.5, 0.1)
        self.assertAlmostEqual(a / (a + b), 0.5, places=9)
        with self.assertRaises(demand.DemandError):
            demand.beta_parameters(0.2, 0.25)       # var > mean*(1-mean)
        with self.assertRaises(demand.DemandError):
            demand.beta_parameters(0.5, 0.25)       # boundary, not open
        with self.assertRaises(demand.DemandError):
            demand.beta_parameters(1.0, 0.01)       # mean not in (0,1)

    def test_beta_clamp_reports(self):
        v, clamped = demand.clamp_variance(0.9, 0.09)
        self.assertTrue(clamped)
        self.assertLess(v, 0.9 * 0.1)
        v2, clamped2 = demand.clamp_variance(0.5, 0.01)
        self.assertFalse(clamped2)
        self.assertAlmostEqual(v2, 0.01)

    def test_poisson_moments(self):
        rng = np.random.default_rng(7)
        out = demand.poisson_moments_check(rng, 42.0, n=50000)
        self.assertLess(out["relative_gap"], 0.05)

    def test_binomial_conservation(self):
        rng = np.random.default_rng(11)
        scen = demand.draw_scenarios(rng, 500, 63.0, 0.4, beta_variance=0.05,
                                     composition="beta", beta_ceiling=0.99)
        demand.check_integer_conservation(scen)
        self.assertTrue(np.all(scen["D_EV"] >= 0))
        self.assertTrue(np.all(scen["D_ICE"] >= 0))
        self.assertTrue(np.issubdtype(scen["D_EV"].dtype, np.integer))
        # per-vehicle binomial mode still conserves counts
        scen2 = demand.draw_scenarios(rng, 500, 63.0, 0.4, composition="binomial")
        demand.check_integer_conservation(scen2)

    def test_thinning_restores_intensity(self):
        rng = np.random.default_rng(3)

        def intensity(t):
            if t < 100.0:
                return 5.0
            if t < 200.0:
                return 20.0
            return 10.0
        t_end = 600.0
        times = demand.thinning_times(rng, intensity, t_end, lam_star=20.0)
        n = len(times)
        expr = 5.0 * 100 + 20.0 * 100 + 10.0 * 400
        self.assertLess(abs(n - expr) / expr, 0.05)
        for lo, hi, lam in ((0, 100, 5.0), (100, 200, 20.0), (200, 600, 10.0)):
            got = np.sum((times >= lo) & (times < hi))
            want = lam * (hi - lo)
            self.assertLess(abs(got - want) / want, 0.05,
                            msg="segment %s-%s: %d vs %.0f" % (lo, hi, got, want))

    def test_arrival_times_sorted(self):
        cfg = load_v2_settings()
        rng = np.random.default_rng(5)
        day = evaluate.prepare_v2_day(rng, cfg, 0.6, 0.6, "beta", "pnc")
        self.assertEqual(day["time_unit"], "minute")
        self.assertTrue(np.all(np.diff(day["times_min"]) >= -1e-12))
        self.assertEqual(len(day["times_min"]), len(day["classes"]))
        self.assertEqual(len(day["times_min"]), len(day["dwell_min"]))


class TestRulesAndCapacity(unittest.TestCase):
    def test_rule_matrix_exhaustive(self):
        rows = rules.compatibility_matrix(theta=0.4)
        self.assertEqual(len(rows), 3 * 3 * 2)
        states = {(r["rule"], r["demand_class"], r["berth_type"]): r["state"] for r in rows}
        self.assertEqual(states[("pi_S", "ev_charge", "ordinary")], rules.NOT_ADMITTED)
        self.assertEqual(states[("pi_S", "ev_charge", "charging")], rules.ADMITTED)
        self.assertEqual(states[("pi_F", "icev", "charging")], rules.ADMITTED)
        self.assertEqual(states[("pi_F", "ev_park", "charging")], rules.ADMITTED)
        self.assertEqual(states[("pi_theta", "icev", "charging")], rules.CONDITIONAL)
        self.assertEqual(states[("pi_theta", "ev_charge", "charging")], rules.ADMITTED)
        for row in rows:
            self.assertIn(row["state"], (rules.ADMITTED, rules.CONDITIONAL,
                                         rules.RESERVED, rules.NOT_ADMITTED))

    def test_theta_reservation(self):
        self.assertEqual(rules.reserved_berths(50, 0.4), 20)
        self.assertTrue(rules.is_admissible("pi_theta", "icev", "charging",
                                            is_open_charging=False) is False)
        self.assertTrue(rules.is_admissible("pi_theta", "icev", "charging",
                                            is_open_charging=True))
        self.assertFalse(rules.is_admissible("pi_S", "ev_charge", "ordinary"))

    def test_capacity_limits(self):
        self.assertEqual(capacity.max_sessions(50.0, 500.0, 40), 10)
        self.assertEqual(capacity.reachable_berths("fixed", 20, 100), 20)
        self.assertEqual(capacity.reachable_berths("overhead", 40, 100, 2), 80)
        design = {"m": 40, "mode": "fixed", "power_kw": 50.0, "feeder_kw": 500.0}
        cap = capacity.design_capacity(design, 100)
        self.assertEqual(cap["max_sessions"], 10)
        self.assertEqual(cap["berths_reachable"], 40)

    def test_ledger_rejects_overdelivery(self):
        led = capacity.ServiceLedger(10, 5, 50.0, 500.0)
        led.record_request(1, 10.0)
        led.record_admission(1, 0, 0.0, 60.0)
        with self.assertRaises(capacity.CapacityError):
            led.record_session(1, 0, 0.0, 60.0, 11.0, 50.0)
        led.record_session(1, 0, 0.0, 12.0, 10.0, 50.0)
        led.assert_invariants()
        led.record_request(2, 5.0)
        led.record_admission(2, 1, 0.0, 30.0)
        with self.assertRaises(capacity.CapacityError):
            # overlapping sessions on the same device must be rejected
            led.record_session(2, 0, 5.0, 10.0, 4.0, 50.0)
            led.assert_invariants()

    def test_feeder_peak_sweep(self):
        sessions = [(0.0, 1.0, 50.0, 1.0), (0.0, 1.0, 50.0, 1.0),
                    (0.5, 1.5, 50.0, 1.0)]
        conc, pw = capacity.sweep_peaks(sessions)
        self.assertEqual(conc, 3)
        self.assertAlmostEqual(pw, 150.0)


class TestEvaluation(unittest.TestCase):
    def setUp(self):
        _, self.settings = load_settings(scenario_count=60)
        self.cm = costs.CostModel(self.settings, 42)

    def test_integer_vs_grid(self):
        total, daily, ms, _ = evaluate.static_matrices(
            self.settings, self.cm, 42, ev_modes=["binomial"], modes=["partition"])
        N = int(self.settings["lot"]["n_spaces"])
        scen = evaluate.scenario_set(self.settings, 42, "plc", 0.4, "binomial")
        best_int, best_val = None, float("inf")
        for m in range(N + 1):
            le_ev, le_ice = evaluate.static_leavers(scen, "partition", m, N)
            val = self.cm.psc(m, le_ev, le_ice)
            if val < best_val:
                best_val, best_int = val, m
        grid_val = float(total[("plc", "binomial", 0.4, "partition")].mean(axis=0).min())
        self.assertLessEqual(best_val, grid_val + 1e-9)
        self.assertLess(best_int, N + 1)

    def test_determinism_same_seed(self):
        total1, daily1, _, _ = evaluate.static_matrices(
            self.settings, self.cm, 123, ev_modes=["beta"], modes=["partition"])
        total2, daily2, _, _ = evaluate.static_matrices(
            self.settings, self.cm, 123, ev_modes=["beta"], modes=["partition"])
        key = ("plc", "beta", 0.6, "partition")
        self.assertTrue(np.array_equal(total1[key], total2[key]))
        self.assertTrue(np.array_equal(daily1[key], daily2[key]))

    def test_literal_accounting_is_degenerate(self):
        cfg = config.load_config(os.path.join(REPRO, "configs", "baseline.yaml"))
        cfg = cfg.apply_overrides({"cost.event_cost_scale": 1.0})
        settings = cfg.resolved()
        settings["modes"] = self.settings["modes"]
        cm = costs.CostModel(settings, 42)
        scen = evaluate.scenario_set(settings, 42, "pnc", 0.4, "binomial")
        N = int(settings["lot"]["n_spaces"])
        vals = []
        for m in evaluate.m_candidates(N, 0.05):
            le_ev, le_ice = evaluate.static_leavers(scen, "partition", m, N)
            vals.append(cm.psc(m, le_ev, le_ice))
        self.assertEqual(int(np.argmin(vals)), 0,
                         msg="literal 5 RMB/event vs 60k pile must give PPR=0")

    def test_psc_components_add_up(self):
        matrix = self.cm.daily_loss(np.array([3.0]), np.array([2.0]))
        self.assertAlmostEqual(float(matrix[0]),
                               (3.0 * self.cm.event_cost("ev")
                                + 2.0 * self.cm.event_cost("icev")) * 365 * 5,
                               places=6)

