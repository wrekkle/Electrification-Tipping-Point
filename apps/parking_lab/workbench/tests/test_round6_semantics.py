# -*- coding: utf-8 -*-
"""第六轮 A：service_semantics 五态语义与三/四约束判定测试。"""
from __future__ import annotations

import math
import unittest

from apps.parking_lab.workbench import service_semantics as S


def make_row(capacity=0.0, charge_requests=10, ev_rate=0.0, ev_visits=5,
             ice_rate=0.0, ice_visits=5, energy_rate=0.0, departed_kwh=10.0,
             requests=10):
    return {
        "capacity_only_unmet_rate": capacity,
        "charge_requests": charge_requests,
        "capacity_only_unmet_requests": (0 if capacity is None else int(round(capacity * charge_requests)) if charge_requests else 0),
        "service_metrics": {
            "rates": {"capacity_only_unmet_rate": capacity,
                      "ev_parking_failure_rate": ev_rate,
                      "ice_parking_failure_rate": ice_rate,
                      "departed_shortfall_energy_rate": energy_rate},
            "numerators": {"capacity_unmet_requests": 0, "ev_parking_failures": 0,
                           "ice_parking_failures": 0, "departed_shortfall_kwh": 0.0},
            "denominators": {"exogenous_charge_requests": requests,
                             "exogenous_ev_visits": ev_visits,
                             "exogenous_ice_visits": ice_visits,
                             "departed_requested_kwh": departed_kwh},
        },
    }


class RateStateTest(unittest.TestCase):
    def test_valid(self):
        row = make_row()
        for name in S.RATE_NAMES:
            cell = S.classify_rate(name, row)
            self.assertEqual(cell["status"], "valid", name)
            self.assertFalse(cell["skipped"])

    def test_zero_demand_not_applicable(self):
        row = make_row(capacity=None, charge_requests=0, ev_rate=None, ev_visits=0,
                       ice_rate=None, ice_visits=0, energy_rate=None,
                       departed_kwh=0.0, requests=0)
        for name in S.RATE_NAMES:
            cell = S.classify_rate(name, row)
            self.assertEqual(cell["status"], "not_applicable_zero_demand", name)
            self.assertTrue(cell["skipped"])
        verdict = S.judge(row)
        self.assertTrue(verdict["achieved"])
        self.assertTrue(verdict["vacuous"])
        self.assertEqual(sorted(verdict["not_applicable"]), sorted(S.CONSTRAINTS_3))

    def test_censored_no_departure(self):
        row = make_row(energy_rate=None, departed_kwh=0.0, requests=3)
        cell = S.classify_rate("departed_shortfall_energy_rate", row)
        self.assertEqual(cell["status"], "censored_no_departure")
        self.assertFalse(cell["skipped"])
        self.assertIn("无离场样本", cell["reason"])
        # 三约束不使用能量率：仍可 achieved；四约束不判成功。
        self.assertTrue(S.judge(row, S.CONSTRAINTS_3)["achieved"])
        four = S.judge(row, S.CONSTRAINTS_4)
        self.assertFalse(four["achieved"])
        self.assertEqual(four["status"], "undecidable_censored")

    def test_missing_rate_and_denominator(self):
        row = make_row(energy_rate=None, departed_kwh=10.0)
        cell = S.classify_rate("departed_shortfall_energy_rate", row)
        self.assertEqual(cell["status"], "missing")
        no_sm = {"capacity_only_unmet_rate": 0.0, "charge_requests": 5}
        self.assertEqual(S.classify_rate("ev_parking_failure_rate", no_sm)["status"], "missing")

    def test_illegal_values(self):
        cases = [float("nan"), float("inf"), -0.1, 1.5, "0.1", True]
        for bad in cases:
            row = make_row(ev_rate=bad)
            self.assertEqual(S.classify_rate("ev_parking_failure_rate", row)["status"],
                             "illegal", repr(bad))
        # 非法值不能被跳过：judge 必须 undecidable 且 achieved=False。
        verdict = S.judge(make_row(ev_rate=float("nan")))
        self.assertFalse(verdict["achieved"])
        self.assertEqual(verdict["status"], "undecidable_illegal")
        self.assertIn("ev_parking_failure_rate", verdict["illegal"])

    def test_missing_not_achieved(self):
        row = make_row(ev_rate=None, ev_visits=5)
        verdict = S.judge(row)
        self.assertFalse(verdict["achieved"])
        self.assertEqual(verdict["status"], "undecidable_missing")
        self.assertEqual(S.feasible(row), None)

    def test_unknown_name(self):
        with self.assertRaises(ValueError):
            S.classify_rate("not_a_rate", make_row())

    def test_rate_boundaries(self):
        self.assertEqual(S.classify_rate("ev_parking_failure_rate",
                                         make_row(ev_rate=0.05))["status"], "valid")
        self.assertTrue(S.judge(make_row(ev_rate=0.05))["achieved"])
        self.assertFalse(S.judge(make_row(ev_rate=0.0501))["achieved"])
        self.assertEqual(S.classify_rate("ev_parking_failure_rate",
                                         make_row(ev_rate=-1e-15))["status"], "valid")


class JudgeTest(unittest.TestCase):
    def test_strict_na_not_success(self):
        row = make_row(capacity=None, charge_requests=0)
        skip = S.judge(row)
        strict = S.judge(row, na_policy="strict")
        self.assertTrue(skip["achieved"])
        self.assertFalse(strict["achieved"])
        self.assertEqual(strict["status"], "not_achieved_strict")
        self.assertEqual(len(skip["satisfied"]), 2)

    def test_four_constraint_blocks(self):
        row = make_row(energy_rate=0.2)
        self.assertTrue(S.judge(row, S.CONSTRAINTS_3)["achieved"])
        four = S.judge(row, S.CONSTRAINTS_4)
        self.assertFalse(four["achieved"])
        self.assertEqual(four["violated"], ["departed_shortfall_energy_rate"])

    def test_minimal_feasible(self):
        rows = {0: make_row(capacity=0.9), 1: make_row(), 2: make_row(ev_rate=0.9),
                4: make_row()}
        shape = S.minimal_feasible(rows, k_max=40)
        self.assertEqual(shape["min_known_feasible"], 1)
        self.assertTrue(shape["confirmed_minimal"])
        self.assertFalse(shape["is_interval"])
        self.assertFalse(shape["truncated_at_kmax"])
        self.assertEqual(shape["feasible"], [1, 4])

    def test_minimal_undecidable_prevents_confirmation(self):
        rows = {0: make_row(capacity=0.9), 1: make_row(ev_rate=None, ev_visits=4),
                2: make_row()}
        shape = S.minimal_feasible(rows, k_max=40)
        self.assertEqual(shape["min_known_feasible"], 2)
        self.assertFalse(shape["confirmed_minimal"])
        self.assertEqual(shape["undecidable_ks"], [1])

    def test_minimal_truncated_and_empty(self):
        rows = {k: make_row() for k in (0, 39, 40)}
        shape = S.minimal_feasible(rows, k_max=40)
        self.assertTrue(shape["truncated_at_kmax"])
        self.assertEqual(shape["min_known_feasible"], 0)
        empty = S.minimal_feasible({0: make_row(capacity=1.0), 1: make_row(capacity=1.0)})
        self.assertTrue(empty["empty_set"])
        self.assertIsNone(empty["min_known_feasible"])

    def test_bad_policy(self):
        with self.assertRaises(ValueError):
            S.judge(make_row(), na_policy="ignore")
        with self.assertRaises(ValueError):
            S.judge(make_row(), constraints=())


if __name__ == "__main__":
    unittest.main()
