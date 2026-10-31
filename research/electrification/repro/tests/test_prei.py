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
        day = evaluate.prepare_v2_day(rng, cfg, 0.6, 0.6, "beta")
        self.assertTrue(np.all(np.diff(day["times"]) >= -1e-12))
        self.assertEqual(len(day["times"]), len(day["classes"]))
        self.assertEqual(len(day["times"]), len(day["dwell_min"]))


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
        cls.day = evaluate.prepare_v2_day(rng, cls.settings, 0.7, 0.6, "beta")
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
            "times": np.arange(n, dtype=float) * 0.2,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)