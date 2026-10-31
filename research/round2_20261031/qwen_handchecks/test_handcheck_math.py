"""Unit tests for handcheck_math (pure stdlib, independent of apps/)."""

import unittest

from handcheck_math import (
    charge_gap,
    erlang_b_closed_form,
    facility_cost_per_window,
    service_status,
    stationary_residual_mean,
)


class TestErlangBClosedForm(unittest.TestCase):
    def test_single_server_half_load(self):
        self.assertAlmostEqual(erlang_b_closed_form(0.5, 1), 1.0 / 3.0, places=9)

    def test_single_server_unit_load(self):
        self.assertAlmostEqual(erlang_b_closed_form(1, 1), 0.5, places=9)

    def test_two_servers_double_load(self):
        self.assertAlmostEqual(erlang_b_closed_form(2, 2), 0.4, places=9)

    def test_three_servers_five_load(self):
        # Closed form: (5^3/6) / (1 + 5 + 12.5 + 20.8333...) = 0.5297...
        self.assertAlmostEqual(erlang_b_closed_form(5, 3), 0.5297, places=4)


class TestStationaryResidualMean(unittest.TestCase):
    def test_two_point_dwell(self):
        # E[D]=5, E[D^2]=85 -> 85/10 = 8.5? No: (0.5*1+0.5*9)=5, (0.5*1+0.5*81)=41 -> 41/10=4.1
        self.assertAlmostEqual(stationary_residual_mean({1: 0.5, 9: 0.5}), 4.1, places=9)


class TestChargeGap(unittest.TestCase):
    def test_capacity_limited(self):
        # 7 kW * 60 min / 60 = 7 kWh delivered of 14 demanded -> gap 7
        self.assertEqual(charge_gap(14, 7, 60), (7.0, 7.0))

    def test_demand_limited(self):
        self.assertEqual(charge_gap(5, 7, 60), (5.0, 0.0))


class TestFacilityCostPerWindow(unittest.TestCase):
    def test_reference_case(self):
        # 2 * (116792.62/10 + 43.29969863*720/1440) = 2*(11679.262+21.649849315) = 75.2977...
        val = facility_cost_per_window(2, 116792.62, 10, 43.29969863, 720)
        self.assertAlmostEqual(val, 75.2977, places=2)


class TestServiceStatus(unittest.TestCase):
    def test_no_demand(self):
        self.assertEqual(service_status(0, {0: 0, 1: 0}), ("no_demand", 0))

    def test_missing_data(self):
        self.assertEqual(service_status(10, {1: 5}), ("missing_data", None))

    def test_achieved(self):
        self.assertEqual(service_status(10, {0: 10, 1: 4, 2: 0, 3: 0}), ("achieved", 2))

    def test_budget_exhausted(self):
        # Searched up to k=3 (< hard limit 40), never met target.
        self.assertEqual(service_status(10, {0: 10, 1: 6, 2: 4, 3: 2}), ("budget_exhausted", None))

    def test_infeasible_upper_bound(self):
        # Searched up to the hard limit (k=40) and unmet stays positive.
        curve = {k: 5 + k for k in range(41)}
        self.assertEqual(service_status(10, curve), ("infeasible_upper_bound", None))


if __name__ == "__main__":
    unittest.main()
