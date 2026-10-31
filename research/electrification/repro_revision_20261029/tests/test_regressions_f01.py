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




class TestF01HalfOpenIntervals(unittest.TestCase):
    """F01a: adjacent supply intervals are half-open; touching != overlapping."""

    def test_abutting_sessions_are_not_summed(self):
        sessions = [(0.0, 10.0, 50.0, 8.3333), (10.0, 20.0, 50.0, 8.3333)]
        # two 50 kW sessions touching at t=10 plus one spanning 50 kW: peak 100
        self.assertAlmostEqual(
            simulator._peak_power_over(sessions, 0.0, 20.0, 50.0), 100.0, places=9)
        self.assertAlmostEqual(
            simulator._peak_power_over(list(reversed(sessions)), 0.0, 20.0, 50.0),
            100.0, places=9)

    def test_spanning_request_is_not_delayed(self):
        # the same three intervals, but asked through the real scheduler:
        # a 50 kW request spanning [0,60) must be allowed to start at t=0.
        _, settings = load_v2_settings()
        ledger = capacity.ServiceLedger(4, 2, 50.0, 100.0)
        ledger.record_request(0, 8.3333)
        ledger.record_session(0, 0, 0.0, 10.0, 8.3333, 50.0)
        ledger.record_request(1, 8.3333)
        ledger.record_session(1, 1, 10.0, 20.0, 8.3333, 50.0)
        t_c, energy, t_d = simulator._schedule_connection(
            ledger, 0.0, 0.0, 120.0, 40.0, 50.0, 100.0)
        self.assertAlmostEqual(t_c, 0.0, places=9)      # was pushed to 10.0
        self.assertAlmostEqual(energy, 40.0, places=9)
        self.assertAlmostEqual(t_d - t_c, 48.0, places=9)


class TestF01RepositionTiming(unittest.TestCase):
    """F01b: a move cannot be paid with idle time from before the arrival."""

    def test_move_starts_at_arrival_and_service_after_the_move(self):
        _, base = load_v2_settings()
        settings = copy.deepcopy(base)
        settings["lot"]["n_spaces"] = 2
        cm = costs.CostModel(settings, 42)
        # device 0 ends its first session at 0.96 min; vehicle 1 arrives at 100
        day = make_day([0.0, 100.0], ["ev_charge", "ev_charge"],
                       [600.0, 600.0], [0.8, 80.0])
        d = design(mode="overhead", m=1, rule="pi_F", coverage=2,
                   reposition_min=10.0)
        out = simulator.simulate_day(settings, cm, d, day)
        rows = out["timeline"]
        # vehicle 0 parks at berth 0 = the device home berth: no move
        self.assertAlmostEqual(rows[0]["t_c"], 0.0, places=6)
        self.assertIsNone(rows[0]["t_move_start"])
        # vehicle 1 parks at berth 1: move from 100 to 110, service at 110
        self.assertAlmostEqual(rows[1]["t_move_start"], 100.0, places=6)
        self.assertAlmostEqual(rows[1]["t_move_end"], 110.0, places=6)
        self.assertAlmostEqual(rows[1]["t_c"], 110.0, places=6)  # was 100.0
        self.assertEqual(out["metrics"]["device_initial_position"], "home_berth")

    def test_no_move_charge_when_already_at_target_berth(self):
        _, base = load_v2_settings()
        settings = copy.deepcopy(base)
        settings["lot"]["n_spaces"] = 2
        cm = costs.CostModel(settings, 42)
        day = make_day([0.0, 50.0], ["ev_charge", "ev_charge"],
                       [10.0, 600.0], [0.8, 0.8])
        d = design(mode="overhead", m=1, rule="pi_F", coverage=2,
                   reposition_min=10.0)
        out = simulator.simulate_day(settings, cm, d, day)
        rows = out["timeline"]
        # vehicle 1 also parks at berth 0 (freed after 10 min), the device's
        # home berth: no reposition, service starts at the arrival instant
        self.assertEqual(rows[1]["berth"], 0)
        for row in rows:
            self.assertIsNone(row["t_move_start"])
            self.assertAlmostEqual(row["t_c"], row["t_a"], places=6)


class TestF01cFailedRequestMove(unittest.TestCase):
    """A move that never starts service must be cancelled, not left on record."""

    def _scenario(self):
        _, base = load_v2_settings()
        settings = copy.deepcopy(base)
        settings["lot"]["n_spaces"] = 2
        cm = costs.CostModel(settings, 42)
        # vehicle 0 parks in berth 0 for the whole day (device home berth);
        # vehicle 1 arrives 10 and leaves 13, so its move 10->20 cannot finish;
        # vehicle 2 arrives 13 and must get a move starting at 13, not 10.
        day = make_day([0.0, 10.0, 13.0],
                       ["ev_park", "ev_charge", "ev_charge"],
                       [600.0, 3.0, 600.0], [0.0, 100.0, 100.0])
        d = design(mode="overhead", m=1, rule="pi_F", coverage=2,
                   reposition_min=10.0)
        return settings, cm, d, day

    def test_failed_move_is_cancelled_and_device_state_unchanged(self):
        settings, cm, d, day = self._scenario()
        out = simulator.simulate_day(settings, cm, d, day)
        rows = out["timeline"]
        self.assertEqual(rows[0]["t_move_status"], "none")
        self.assertEqual(rows[1]["t_move_status"], "cancelled")
        self.assertIsNone(rows[1]["t_c"])
        self.assertIsNone(rows[1]["t_move_start"])
        self.assertIsNone(rows[1]["t_move_end"])
        # the next request starts its own move from its own arrival
        self.assertEqual(rows[2]["t_move_status"], "executed")
        self.assertAlmostEqual(rows[2]["t_move_start"], 13.0, places=9)
        self.assertAlmostEqual(rows[2]["t_move_end"], 23.0, places=9)
        self.assertAlmostEqual(rows[2]["t_c"], 23.0, places=9)
        m = out["metrics"]
        self.assertEqual(m["device_moves_executed"], 1)
        self.assertEqual(m["device_moves_cancelled"], 1)
        self.assertEqual(m["device_move_conflicts"], 0)

    def test_same_device_moves_and_sessions_do_not_overlap(self):
        settings, cm, d, day = self._scenario()
        out = simulator.simulate_day(settings, cm, d, day)
        led = out["ledger"]
        led.assert_invariants()
        intervals = []
        for (a, b, veh) in led.device_moves.get(0, []):
            intervals.append((a, b, "move", veh))
        for (a, b) in led.device_sessions.get(0, []):
            intervals.append((a, b, "session", None))
        intervals.sort()
        for left, right in zip(intervals, intervals[1:]):
            self.assertLessEqual(left[1], right[0] + 1e-9,
                                 "device 0 overlap: %r vs %r" % (left, right))

