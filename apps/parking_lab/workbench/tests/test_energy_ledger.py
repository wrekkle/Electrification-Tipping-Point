"""energy_ledger（能量服务结算）单元测试：分母口径 / 拒绝不消失 / 删失分列 / 无免费补能。

只手工构造 visit dict，不跑仿真；口径见 apps/parking_lab/workbench/energy_ledger.py docstring。
"""
import unittest

from apps.parking_lab.workbench.energy_ledger import ledger_rows, settle, settle_export

HORIZON = 240


def visit(vid, arrival, ev=True, needs=None, admitted=True, departed=True,
          departure=None, energy=10.0, delivered=10.0):
    if needs is None:
        needs = ev
    record = {"vehicle_id": vid, "time_min": arrival, "is_ev": ev,
              "needs_charge": needs, "admitted": admitted, "departed": departed,
              "departure_min": departure, "energy_kwh": energy, "delivered_kwh": delivered}
    return record


def fixture():
    return [
        visit("v_rej", 10, admitted=False, departed=False, departure=None,
              energy=10.0, delivered=0.0),
        visit("v_full", 20, departure=100, energy=10.0, delivered=10.0),
        visit("v_short", 30, departure=120, energy=10.0, delivered=6.0),
        visit("v_cens", 40, departed=False, departure=None, energy=10.0, delivered=3.0),
        visit("v_zero", 50, needs=False, departure=80, energy=0.0, delivered=0.0),
        visit("ice_rej", 60, ev=False, needs=False, admitted=False, departed=False,
              departure=None, energy=0.0, delivered=0.0),
        visit("init1", 0, departure=50, energy=8.0, delivered=8.0),
        {"vehicle_id": "bad_missing"},
        visit("v_illegal", 70, departure=90, energy=10.0, delivered=12.0),
        visit("v_late", 300, departure=330, energy=5.0, delivered=0.0),
    ]


class SettleTests(unittest.TestCase):
    def setUp(self):
        self.result = settle(fixture(), horizon_min=HORIZON, initial_ids={"init1"})

    def test_categories_split(self):
        categories = self.result["categories"]
        self.assertEqual(categories["visits_total"], 10)
        self.assertEqual(categories["exogenous_visits"], 6)
        self.assertEqual(categories["initial_vehicles"], 1)
        self.assertEqual(categories["zero_demand"], 1)
        self.assertEqual(categories["censored"], 1)
        self.assertEqual(categories["missing"], 1)
        self.assertEqual(categories["illegal"], 1)
        self.assertEqual(categories["rejected"], 2)
        self.assertEqual(categories["charge_requests"], 4)

    def test_rejected_stay_in_denominator(self):
        parking = self.result["parking_service"]
        self.assertEqual(parking["numerator"], 2)
        self.assertEqual(parking["denominator"], 6)
        self.assertAlmostEqual(parking["rate"], 2 / 6)
        self.assertEqual(parking["by_type"]["ev"]["denominator"], 5)
        self.assertEqual(parking["by_type"]["ice"]["denominator"], 1)
        self.assertEqual(self.result["charging_access"]["denominator"], 4)
        self.assertEqual(self.result["charging_access"]["subcounts"]["rejected_no_bay"], 1)

    def test_charging_access(self):
        access = self.result["charging_access"]
        self.assertEqual(access["numerator"], 3)
        self.assertEqual(access["denominator"], 4)
        self.assertAlmostEqual(access["rate"], 0.75)
        self.assertEqual(access["subcounts"]["admitted_started"], 3)
        self.assertEqual(access["subcounts"]["started_censored"], 1)

    def test_departure_energy_admitted_only(self):
        block = self.result["departure_energy_service"]["admitted_departed"]
        self.assertEqual(block["n_sessions"], 2)
        self.assertEqual(block["n_full"], 1)
        self.assertEqual(block["n_short"], 1)
        self.assertAlmostEqual(block["demand_kwh"], 20.0)
        self.assertAlmostEqual(block["delivered_kwh"], 16.0)
        self.assertAlmostEqual(block["gap_kwh"], 4.0)
        self.assertAlmostEqual(block["gap_rate"], 0.2)
        self.assertAlmostEqual(block["service_rate"], 0.8)
        self.assertTrue(block["condition"])

    def test_no_free_refill_including_rejected(self):
        block = self.result["departure_energy_service"]["including_rejected"]
        self.assertEqual(block["n_requests"], 4)
        self.assertAlmostEqual(block["demand_kwh"], 40.0)
        self.assertAlmostEqual(block["delivered_kwh"], 19.0)
        self.assertAlmostEqual(block["gap_kwh"], 21.0)
        self.assertAlmostEqual(block["gap_rate"], 21 / 40)
        self.assertGreater(block["gap_kwh"], 0.0)
        self.assertTrue(block["condition"])

    def test_censored_and_initial_separate(self):
        censored = self.result["censored"]
        self.assertEqual(censored["n_sessions"], 1)
        self.assertAlmostEqual(censored["pending_demand_kwh"], 10.0)
        self.assertAlmostEqual(censored["delivered_so_far_kwh"], 3.0)
        initial = self.result["initial_vehicles"]
        self.assertEqual(initial["n_sessions"], 1)
        self.assertAlmostEqual(initial["demand_kwh"], 8.0)

    def test_missing_and_illegal_listed(self):
        missing = self.result["missing"]
        self.assertEqual(missing["n_visits"], 1)
        self.assertIn("time_min", [item["field"] for item in missing["fields"]])
        illegal = self.result["illegal"]
        self.assertEqual(illegal["n_visits"], 1)
        self.assertIn("超过", illegal["detail"][0]["reason"])

    def test_illegal_not_in_denominators(self):
        # v_illegal（delivered>energy）与 bad_missing 都不进外生分母
        self.assertEqual(self.result["parking_service"]["denominator"], 6)
        self.assertEqual(self.result["charging_access"]["denominator"], 4)

    def test_late_arrival_not_counted(self):
        # 到达在窗口外的 v_late 既不进外生分母，也不冒充删失样本
        self.assertEqual(self.result["departure_energy_service"]["including_rejected"]["n_requests"], 4)
        self.assertEqual(self.result["censored"]["n_sessions"], 1)

    def test_ledger_rows_carry_numerator_denominator_condition(self):
        rows = ledger_rows(self.result)
        by_metric = {row["metric"]: row for row in rows}
        row = by_metric["rejected_over_exogenous"]
        self.assertEqual(row["numerator"], 2)
        self.assertEqual(row["denominator"], 6)
        self.assertTrue(row["condition"])
        for key in ("delivered_kwh_over_demand_kwh_admitted_departed",
                    "gap_kwh_over_demand_kwh_including_rejected",
                    "delivered_any_over_charge_requests"):
            self.assertIn(key, by_metric)
            self.assertTrue(by_metric[key]["condition"])
        self.assertEqual(by_metric["delivered_kwh_over_demand_kwh_including_rejected"]
                         ["numerator"], 19.0)


class EdgeCaseTests(unittest.TestCase):
    def test_empty_visits(self):
        result = settle([], horizon_min=HORIZON)
        self.assertEqual(result["categories"]["visits_total"], 0)
        self.assertIsNone(result["parking_service"]["rate"])
        self.assertIsNone(result["charging_access"]["rate"])
        self.assertIsNone(result["departure_energy_service"]["admitted_departed"]["gap_rate"])

    def test_settle_export(self):
        export = {"state": {"horizon_min": HORIZON},
                  "visits": [visit("v_full", 20, departure=100)]}
        result = settle_export(export)
        self.assertEqual(result["parking_service"]["denominator"], 1)
        self.assertAlmostEqual(result["departure_energy_service"]["admitted_departed"]
                               ["service_rate"], 1.0)

    def test_missing_delivered_excluded_from_energy_rate(self):
        visits = [visit("a", 20, departure=100, energy=10.0, delivered=None),
                  visit("b", 30, departure=120, energy=10.0, delivered=10.0)]
        result = settle(visits, horizon_min=HORIZON)
        block = result["departure_energy_service"]["admitted_departed"]
        self.assertEqual(block["n_sessions"], 1)
        self.assertAlmostEqual(block["service_rate"], 1.0)
        self.assertIn("delivered_kwh",
                      [item["field"] for item in result["missing"]["fields"]])

    def test_negative_energy_illegal(self):
        visits = [visit("a", 20, departure=100, energy=-1.0, delivered=0.0)]
        result = settle(visits, horizon_min=HORIZON)
        self.assertEqual(result["illegal"]["n_visits"], 1)
        self.assertEqual(result["parking_service"]["denominator"], 0)
        self.assertIsNone(result["parking_service"]["rate"])

    def test_zero_demand_ev_not_in_charge_denominator(self):
        visits = [visit("a", 20, needs=False, departure=100, energy=0.0, delivered=0.0)]
        result = settle(visits, horizon_min=HORIZON)
        self.assertEqual(result["categories"]["zero_demand"], 1)
        self.assertEqual(result["charging_access"]["denominator"], 0)
        self.assertIsNone(result["charging_access"]["rate"])
        self.assertEqual(result["parking_service"]["denominator"], 1)


if __name__ == "__main__":
    unittest.main()
