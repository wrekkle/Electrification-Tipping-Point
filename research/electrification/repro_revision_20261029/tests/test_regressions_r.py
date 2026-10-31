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




class TestImportProvenance(unittest.TestCase):
    """The suite must exercise the revision copy, not an old installed package."""

    def test_imported_package_is_the_revision_directory(self):
        import prei
        path = os.path.abspath(prei.__file__)
        self.assertIn("repro_revision_20261029", path)
        self.assertNotIn(os.sep + "repro" + os.sep, path.replace(
            "repro_revision_20261029", "REV"))
        self.assertEqual(path, os.path.abspath(
            os.path.join(REPRO, "src", "prei", "__init__.py")))


class TestHashAccounting(unittest.TestCase):
    """Manifest/config hashes must hash file bytes, not the path string."""

    def test_file_sha256_is_content_hash(self):
        from prei import io
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.txt")
            b = os.path.join(tmp, "b.txt")
            with open(a, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("same\n")
            with open(b, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("same\n")
            self.assertEqual(io.file_sha256(a), io.file_sha256(b))
            self.assertNotEqual(io.file_sha256(a), io.content_hash(a))


class TestR1TimeUnits(unittest.TestCase):
    """R1: one documented time unit (minutes) across the event layer."""

    @classmethod
    def setUpClass(cls):
        _, cls.settings = load_v2_settings()
        cls.settings = copy.deepcopy(cls.settings)
        cls.settings["lot"]["n_spaces"] = 2
        cls.cm = costs.CostModel(cls.settings, 42)

    def test_hand_example_arrival_dwell_charge(self):
        # arrive 11.5 h after opening = 690 min; dwell 60 min; 20 kWh at 50 kW = 24 min
        day = make_day([690.0], ["ev_charge"], [60.0], [20.0])
        out = simulator.simulate_day(
            self.settings, self.cm, design(m=2, rule="pi_F"), day)
        row = out["timeline"][0]
        self.assertAlmostEqual(row["t_a"], 690.0, places=9)
        self.assertAlmostEqual(row["t_r"] - row["t_a"], 60.0, places=9)
        self.assertAlmostEqual(row["t_c"], 690.0, places=9)
        self.assertAlmostEqual(row["t_d"] - row["t_c"], 24.0, places=9)
        self.assertAlmostEqual(row["energy_delivered_kwh"], 20.0, places=9)
        self.assertEqual(out["metrics"]["time_unit"], "minute")

    def test_energy_power_duration_identity(self):
        # delivered energy must equal rated power x connected minutes / 60
        for req, dwell in ((20.0, 60.0), (5.0, 2.0), (80.0, 480.0)):
            day = make_day([0.0], ["ev_charge"], [dwell], [req])
            out = simulator.simulate_day(
                self.settings, self.cm, design(m=2, rule="pi_F"), day)
            row = out["timeline"][0]
            self.assertIsNotNone(row["t_c"])
            want = min(req, 50.0 * (row["t_r"] - row["t_c"]) / 60.0)
            self.assertAlmostEqual(row["energy_delivered_kwh"], want, places=9)
            self.assertAlmostEqual(
                row["energy_delivered_kwh"],
                50.0 * (row["t_d"] - row["t_c"]) / 60.0, places=9)

    def test_legacy_hour_key_is_rejected(self):
        day = make_day([690.0], ["ev_charge"], [60.0], [20.0])
        day.pop("times_min")
        day["times"] = np.array([11.5])  # legacy hours, must not be guessed
        with self.assertRaises(ValueError) as ctx:
            simulator.simulate_day(
                self.settings, self.cm, design(m=2, rule="pi_F"), day)
        self.assertIn("minute", str(ctx.exception).lower())

    def test_demand_layer_declares_minutes(self):
        _, settings = load_v2_settings()
        rng = np.random.default_rng(5)
        day = evaluate.prepare_v2_day(rng, settings, 0.6, 0.6, "beta", "pnc")
        self.assertEqual(day["time_unit"], "minute")
        self.assertIn("times_min", day)
        window_min = float(settings["demand"]["window_hours"]) * 60.0
        self.assertTrue(np.all(day["times_min"] >= 0.0))
        self.assertTrue(np.all(day["times_min"] < window_min + 1e-9))
        self.assertTrue(np.all(np.diff(day["times_min"]) >= -1e-12))
        # dwell is minutes: median dwell must be an hour-ish, not a day-ish,
        # number of minutes (log-normal mean 60 for the shipped config)
        self.assertTrue(10.0 <= float(np.median(day["dwell_min"])) <= 480.0)


class TestR2GIntervalPairing(unittest.TestCase):
    """R2: full and partial bootstrap draws must stay on the same day index."""

    def test_fixed_offset_is_a_point_interval(self):
        # one partial design, full cheaper by exactly 10 in every scenario
        rng = np.random.default_rng(11)
        part = 100.0 + rng.normal(100.0, 10.0, size=(10, 1))
        full = part[:, 0] + 10.0
        gi = stats.g_interval(full, part, n_boot=400, rng=rng)
        self.assertAlmostEqual(gi["g_hat"], 10.0, places=9)
        self.assertAlmostEqual(gi["g_lo"], 10.0, places=9)
        self.assertAlmostEqual(gi["g_hi"], 10.0, places=9)
        self.assertEqual(gi["n_scenarios"], 10)
        self.assertEqual(gi["best_partial_index"], 0)

    def test_well_separated_partials_stay_paired(self):
        # several partial designs, clearly separated: the winner never switches,
        # so the paired interval still collapses onto the fixed offset
        rng = np.random.default_rng(12)
        common = rng.normal(0.0, 8.0, size=(50, 1))
        part = common + np.array([100.0, 140.0, 180.0])[None, :]
        full = part[:, [0]] + 10.0
        gi = stats.g_interval(full, part, n_boot=400, rng=rng)
        self.assertAlmostEqual(gi["g_hat"], 10.0, places=9)
        self.assertAlmostEqual(gi["g_lo"], 10.0, places=9)
        self.assertAlmostEqual(gi["g_hi"], 10.0, places=9)
        self.assertEqual(gi["best_partial_index"], 0)

    def test_vector_and_column_forms_agree(self):
        rng = np.random.default_rng(13)
        full = rng.normal(80.0, 5.0, size=25)
        part = rng.normal(90.0, 5.0, size=25)
        a = stats.g_interval(full, part, n_boot=300, rng=np.random.default_rng(7))
        b = stats.g_interval(full[:, None], part[:, None], n_boot=300,
                             rng=np.random.default_rng(7))
        self.assertAlmostEqual(a["g_hat"], b["g_hat"], places=12)
        self.assertAlmostEqual(a["g_lo"], b["g_lo"], places=12)
        self.assertAlmostEqual(a["g_hi"], b["g_hi"], places=12)
        self.assertLessEqual(a["g_lo"], a["g_hi"])

    def test_pairing_beats_marginal_width(self):
        # huge common day effect: a paired interval stays narrow
        rng = np.random.default_rng(14)
        common = rng.normal(0.0, 1000.0, size=(200, 1))
        part = common + 100.0 + rng.normal(0.0, 1.0, size=(200, 1))
        full = part + 10.0
        gi = stats.g_interval(full, part, n_boot=600, rng=rng)
        self.assertAlmostEqual(gi["g_hat"], 10.0, places=6)
        self.assertLess(gi["g_hi"] - gi["g_lo"], 5.0)

    def test_interval_is_not_a_b_broadcast(self):
        rng = np.random.default_rng(14)
        full = rng.normal(100.0, 3.0, size=(12, 1))
        part = rng.normal(95.0, 3.0, size=(12, 4))
        gi = stats.g_interval(full, part, n_boot=200, rng=rng)
        self.assertEqual(len(gi), len(locals().get("gi")))
        self.assertTrue(np.isfinite(gi["g_lo"]) and np.isfinite(gi["g_hi"]))


class TestR3ConfidenceSet(unittest.TestCase):
    """R3: simultaneous max-t selection, ties and zero standard error."""

    def test_identical_best_columns_are_both_kept(self):
        rng = np.random.default_rng(21)
        base = rng.normal(100.0, 4.0, size=(60, 1))
        noise = rng.normal(0.0, 2.0, size=(60, 5))
        mat = base + noise + np.array([0.0, 6.0, 8.0, 10.0, 12.0])[None, :]
        mat[:, 3] = mat[:, 0]  # exact duplicate of the best column
        cs = stats.confidence_set(mat, n_boot=500, alpha=0.05,
                                  rng=np.random.default_rng(22))
        self.assertEqual(cs["best"], 0)
        self.assertIn(0, cs["included"])
        self.assertIn(3, cs["included"])
        self.assertEqual(cs["pvalues"][0], 1.0)
        self.assertEqual(cs["pvalues"][3], 1.0)
        self.assertEqual(cs["family_size"], 5)
        self.assertEqual(cs["method"], "max-t")

    def test_zero_variance_dominated_column_is_excluded(self):
        rng = np.random.default_rng(23)
        best = rng.normal(100.0, 3.0, size=50)
        mat = np.column_stack([best, best + 50.0, best + rng.normal(0, 3, 50)])
        cs = stats.confidence_set(mat, n_boot=400, alpha=0.05,
                                  rng=np.random.default_rng(24))
        self.assertIn(cs["best"], cs["included"])
        self.assertNotIn(1, cs["included"])
        self.assertLess(cs["pvalues"][1], 0.01)

    def test_pvalues_are_max_t_not_per_column(self):
        rng = np.random.default_rng(25)
        mat = rng.normal(100.0, 5.0, size=(80, 12))
        mat[:, 0] = rng.normal(100.0, 5.0, size=80)
        cs = stats.confidence_set(mat, n_boot=500, alpha=0.05,
                                  rng=np.random.default_rng(26))
        p = np.asarray(cs["pvalues"], dtype=float)
        t = np.asarray(cs["t_statistics"], dtype=float)
        self.assertTrue(np.all((p >= 0.0) & (p <= 1.0)))
        order = np.argsort(t, kind="stable")
        # ascending t must give non-increasing simultaneous p-values
        self.assertTrue(np.all(np.diff(p[order]) <= 1e-12),
                        msg="max-t p-values must be monotone in the statistic")
        self.assertEqual(p[cs["best"]], 1.0)
        self.assertGreaterEqual(cs["critical_value"], 0.0)
        # an honest simultaneous rule cannot be stricter than the marginal one
        self.assertTrue(np.all(p >= 1.0 / (cs["n_boot"] + 1.0) - 1e-12))

    def test_holm_path_still_available_and_labelled(self):
        rng = np.random.default_rng(27)
        mat = rng.normal(100.0, 4.0, size=(60, 6))
        cs = stats.confidence_set(mat, n_boot=300, alpha=0.05,
                                  rng=np.random.default_rng(28), method="holm")
        self.assertEqual(cs["method"], "holm")
        p = np.asarray(cs["pvalues"], dtype=float)
        self.assertTrue(np.all((p >= 0.0) & (p <= 1.0)))
        self.assertIn(cs["best"], cs["included"])
        with self.assertRaises(ValueError):
            stats.confidence_set(mat, n_boot=50, method="bonferroni")


class TestR5EmpiricalCvar(unittest.TestCase):
    """R5: fractional tail weight, consistent with the auxiliary programme."""

    def test_fractional_tail_example(self):
        losses = list(range(0, 24)) + [100.0]      # 25 observations
        out = stats.empirical_cvar(losses, 0.95)
        self.assertAlmostEqual(out["cvar"], 84.6, places=9)
        self.assertAlmostEqual(out["cvar_aux"], 84.6, places=9)
        self.assertAlmostEqual(out["cvar"], out["cvar_aux"], places=12)
        self.assertAlmostEqual(out["tail_weight"], 1.25, places=12)
        self.assertEqual(out["tail_n"], 2)

    def test_integer_tail_unchanged(self):
        out = stats.empirical_cvar(np.arange(1.0, 101.0), 0.95)
        self.assertEqual(out["tail_n"], 5)
        self.assertAlmostEqual(out["var"], 96.0, places=9)
        self.assertAlmostEqual(out["cvar"], 98.0, places=9)
        self.assertAlmostEqual(out["cvar_aux"], 98.0, places=9)

    def test_ties_and_degenerate_samples(self):
        tied = np.array([10.0] * 95 + [100.0] * 5)
        out = stats.empirical_cvar(tied, 0.95)
        self.assertAlmostEqual(out["cvar"], 100.0, places=9)
        self.assertAlmostEqual(out["cvar_aux"], 100.0, places=9)
        flat = np.full(10, 7.0)
        out = stats.empirical_cvar(flat, 0.95)
        self.assertAlmostEqual(out["cvar"], 7.0, places=12)
        out = stats.empirical_cvar([1.0, 2.0, 3.0, 4.0], 0.5)
        self.assertAlmostEqual(out["cvar"], 3.5, places=12)
        with self.assertRaises(ValueError):
            stats.empirical_cvar([])

    def test_cvar_equals_auxiliary_for_random_samples(self):
        rng = np.random.default_rng(31)
        for n in (10, 25, 257):
            losses = rng.lognormal(2.0, 1.0, size=n)
            for alpha in (0.90, 0.95, 0.99):
                out = stats.empirical_cvar(losses, alpha)
                self.assertAlmostEqual(out["cvar"], out["cvar_aux"], places=10,
                                       msg="n=%d alpha=%.2f" % (n, alpha))


class TestR6EtpSearch(unittest.TestCase):
    """R6: sustained negative suffix on the discrete r grid."""

    def test_late_sustained_negative(self):
        # review counterexample: signs -, +, -, - at r = .2, .4, .6, .8
        rows = rows_for((-1.0, +2.0, -3.0, -1.0))
        self.assertAlmostEqual(stats.etp_from_g(rows), 0.6, places=12)

    def test_zero_is_not_cheaper(self):
        rows = rows_for((+1.0, +2.0, 0.0, -1.0))
        self.assertAlmostEqual(stats.etp_from_g(rows), 0.8, places=12)
        self.assertIsNone(stats.etp_from_g(rows_for((+1.0, 0.0, 0.0, 0.0))))

    def test_endpoints_and_single_grid_point(self):
        self.assertIsNone(stats.etp_from_g(rows_for((+1.0, +2.0, +3.0, +4.0))))
        self.assertAlmostEqual(
            stats.etp_from_g(rows_for((-1.0, -2.0, -3.0, -4.0))), 0.2, places=12)
        self.assertAlmostEqual(stats.etp_from_g(rows_for((-2.0,))), 0.2, places=12)
        self.assertIsNone(stats.etp_from_g(rows_for((+2.0,))))

    def test_unsorted_input_and_missing_values(self):
        rows = [{"r": 0.8, "g_hat": -1.0}, {"r": 0.2, "g_hat": 1.0},
                {"r": 0.4, "g_hat": 2.0}, {"r": 0.6, "g_hat": -3.0}]
        self.assertAlmostEqual(stats.etp_from_g(rows), 0.6, places=12)
        nan_rows = [{"r": 0.2, "g_hat": float("nan")},
                    {"r": 0.4, "g_hat": -1.0}]
        self.assertAlmostEqual(stats.etp_from_g(nan_rows), 0.4, places=12)
        self.assertIsNone(stats.etp_from_g([]))
        with self.assertRaises(ValueError):
            stats.etp_from_g([{"r": 0.4, "g_hat": -1.0},
                              {"r": 0.4, "g_hat": -2.0}])


class TestR4Scheduling(unittest.TestCase):
    """R4: independent devices must not be serialised by a global clock."""

    @classmethod
    def setUpClass(cls):
        _, cls.settings = load_v2_settings()
        cls.settings = copy.deepcopy(cls.settings)
        cls.settings["lot"]["n_spaces"] = 4
        cls.cm = costs.CostModel(cls.settings, 42)

    def _four_request_day(self):
        # overhead, m=2, coverage=2: device0 -> berths {0,2}, device1 -> {1,3}
        times = [0.0, 0.0, 1.0, 3.0]
        classes = ["ev_charge"] * 4
        dwell = [600.0] * 4
        energy = [80.0, 2.5, 2.5, 2.5]
        return make_day(times, classes, dwell, energy)

    def test_second_device_not_pushed_by_future_start(self):
        d = design(mode="overhead", m=2, rule="pi_F", coverage=2,
                   reposition_min=0.0)
        out = simulator.simulate_day(self.settings, self.cm, d,
                                     self._four_request_day())
        rows = out["timeline"]
        self.assertAlmostEqual(rows[0]["t_c"], 0.0, places=9)
        self.assertAlmostEqual(rows[1]["t_c"], 0.0, places=9)
        # request 2 waits for device 0 (busy until 96 min)
        self.assertAlmostEqual(rows[2]["t_c"], 96.0, places=6)
        # request 3 arrives at 3 min and device 1 is free: it must start now
        self.assertAlmostEqual(rows[3]["t_c"], 3.0, places=6)
        out["ledger"].assert_invariants()

    def test_same_instant_arrivals_use_both_devices(self):
        d = design(mode="overhead", m=2, rule="pi_F", coverage=2,
                   reposition_min=0.0)
        day = make_day([0.0, 0.0], ["ev_charge", "ev_charge"],
                       [120.0, 120.0], [10.0, 10.0])
        out = simulator.simulate_day(self.settings, self.cm, d, day)
        starts = sorted(r["t_c"] for r in out["timeline"])
        self.assertEqual(starts[0], 0.0)
        self.assertAlmostEqual(starts[1], 0.0, places=9)

    def test_feeder_limit_is_still_enforced(self):
        settings = copy.deepcopy(self.settings)
        d = design(mode="overhead", m=2, rule="pi_F", coverage=2,
                   reposition_min=0.0, feeder_kw=50.0)
        day = make_day([0.0, 0.0], ["ev_charge", "ev_charge"],
                       [240.0, 240.0], [80.0, 80.0])
        out = simulator.simulate_day(settings, self.cm, d, day)
        self.assertLessEqual(out["metrics"]["peak_power_kw"], 50.0 + 1e-6)
        sessions = sorted(out["ledger"].sessions)
        self.assertGreaterEqual(sessions[1][0], sessions[0][1] - 1e-9)


class TestR7Accounting(unittest.TestCase):
    """R7: candidate set, lot calibration and energy denominators."""

    @classmethod
    def setUpClass(cls):
        _, cls.settings = load_v2_settings()
        cls.settings = copy.deepcopy(cls.settings)
        cls.settings["lot"]["n_spaces"] = 2
        cls.cm = costs.CostModel(cls.settings, 42)

    def test_energy_denominators_separate_rejected_requests(self):
        day = make_day([0.0, 5.0, 10.0, 15.0], ["ev_charge"] * 4,
                       [60.0] * 4, [20.0] * 4)
        out = simulator.simulate_day(
            self.settings, self.cm, design(m=1, rule="pi_F"), day)
        m = out["metrics"]
        self.assertEqual(m["rejected_ev_charge"], 3)
        self.assertAlmostEqual(m["energy_requested_admitted_kwh"], 20.0, places=9)
        self.assertAlmostEqual(m["energy_requested_all_kwh"], 80.0, places=9)
        self.assertAlmostEqual(m["energy_delivered_kwh"], 20.0, places=9)
        self.assertAlmostEqual(m["unserved_energy_kwh"], 60.0, places=9)
        self.assertAlmostEqual(m["unserved_rate_all"], 0.75, places=9)
        self.assertAlmostEqual(m["shortfall_kwh"], 0.0, places=9)
        self.assertAlmostEqual(
            m["unserved_energy_kwh"],
            m["shortfall_kwh"] + m["rejected_energy_kwh"], places=9)

    def test_t12_q_denominator_and_m07_split(self):
        # one admitted EV with insufficient dwell, three rejected: M06 != M07
        day = make_day([0.0, 1.0, 2.0, 3.0], ["ev_charge"] * 4,
                       [10.0] * 4, [100.0] * 4)
        out = simulator.simulate_day(
            self.settings, self.cm, design(m=1, rule="pi_F"), day)
        m = out["metrics"]
        self.assertAlmostEqual(m["ev_arrivals"], 4.0, places=9)
        self.assertAlmostEqual(m["q_request_realized"], 1.0, places=9)
        self.assertAlmostEqual(m["q_plug_realized"], 0.25, places=9)
        self.assertAlmostEqual(m["shortfall_rate"], 91.66666666666667 / 100.0,
                               places=9)
        self.assertAlmostEqual(m["refused_rate_all"], 300.0 / 400.0, places=9)
        self.assertAlmostEqual(m["unserved_rate_all"],
                               (91.66666666666667 + 300.0) / 400.0, places=9)
        self.assertNotAlmostEqual(m["refused_rate_all"],
                                  m["unserved_rate_all"], places=6)

    def test_lot_labels_change_parameters_not_only_seeds(self):
        _, settings = load_v2_settings()
        pnc = evaluate.v2_lot_arrival_scale(settings, "pnc")
        plc = evaluate.v2_lot_arrival_scale(settings, "plc")
        self.assertNotAlmostEqual(pnc, plc, places=6)
        self.assertAlmostEqual(plc, 1.0, places=9)
        # the scale is visible in the generated demand, not only in the seed
        rng = np.random.default_rng(77)
        d_pnc = evaluate.prepare_v2_day(rng, settings, 0.6, 0.6, "beta", "pnc")
        rng = np.random.default_rng(77)
        d_plc = evaluate.prepare_v2_day(rng, settings, 0.6, 0.6, "beta", "plc")
        self.assertLess(len(d_pnc["times_min"]), len(d_plc["times_min"]))
        self.assertAlmostEqual(d_pnc["arrival_scale"], pnc, places=9)
        self.assertAlmostEqual(d_plc["arrival_scale"], plc, places=9)

    def test_candidate_set_declares_zero_charger_design(self):
        _, settings = load_v2_settings()
        designs = evaluate.v2_designs(settings["v2"], int(settings["lot"]["n_spaces"]))
        ms = sorted({d["m"] for d in designs if d["mode"] == "fixed"})
        self.assertIn(0, ms)
        self.assertIn(int(settings["lot"]["n_spaces"]), ms)
        self.assertTrue(all(d["m"] >= 0 for d in designs))
        labels = {evaluate.design_label(d) for d in designs}
        self.assertIn("fixed,pi_F,m=0", labels)

