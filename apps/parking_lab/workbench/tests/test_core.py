from dataclasses import replace
import json
import math
import tempfile
from pathlib import Path
import unittest

from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.demand import Arrival, generate
from apps.parking_lab.workbench.experiments import compare, export_run, write_output
from apps.parking_lab.workbench.metrics import calculate
from apps.parking_lab.workbench.prediction import Learner
from apps.parking_lab.workbench.simulation import Simulation


def config(**changes):
    return Config.parse({**Config().to_dict(), "n_spaces": 2, "charging_bays": 2, "chargers": 2,
                         "reserve_fixed": 0, "policy": "open", "scenario": "steady",
                         "duration_hours": 1, "arrival_rate_hour": 30, **changes})


class CoreTests(unittest.TestCase):
    def test_zero_capacity_all_rejected(self):
        c = config(n_spaces=0, charging_bays=0, chargers=0)
        arrivals = [Arrival(0, 1, False, False, 60, 0), Arrival(1, 2, True, False, 60, 0), Arrival(2, 3, True, True, 60, 10)]
        s = Simulation(c, arrivals); s.run(); m = calculate(s)
        self.assertEqual((m["arrivals"], m["admitted"], m["rejected"]), (3, 0, 3))
        self.assertEqual(m["energy_delivered_kwh"], 0)
        self.assertEqual(m["rejected_energy_kwh"], 10)
        self.assertEqual(m["departed_shortfall_kwh"], 0)
        # 成本模型 v2：默认成本参数全为 null ⇒ 分项未知、总成本 null、complete=false（不填 0）
        self.assertIsNone(m["total_cost"])
        self.assertFalse(m["cost_complete"])
        self.assertIn("vot_per_hour", m["cost_missing_parameters"])

    def test_feeder_shared_equally(self):
        s = Simulation(config(charger_kw=6, feeder_kw=6), [Arrival(0, 0, True, True, 60, 100), Arrival(1, 0, True, True, 60, 100)])
        s.run()
        self.assertEqual([v["delivered_kwh"] for v in s.visits], [3, 3])
        self.assertEqual(calculate(s)["peak_power_kw"], 6)

    def test_completion_releases_power_not_space(self):
        s = Simulation(config(charger_kw=6, feeder_kw=6), [Arrival(0, 0, True, True, 60, 1), Arrival(1, 0, True, True, 60, 100), Arrival(2, 30, False, False, 60, 0)])
        s.run()
        self.assertAlmostEqual(s.visits[0]["completion_min"], 20)
        self.assertAlmostEqual(s.visits[0]["delivered_kwh"], 1)
        self.assertAlmostEqual(s.visits[1]["delivered_kwh"], 5)
        self.assertFalse(s.visits[2]["admitted"])
        self.assertEqual(calculate(s)["peak_occupancy"], 2)

    def test_no_power_or_connector(self):
        for kwargs in ({"feeder_kw": 0}, {"charger_kw": 0}, {"chargers": 0}):
            with self.subTest(kwargs=kwargs):
                s = Simulation(config(**kwargs), [Arrival(0, 0, True, True, 60, 10)])
                s.run(); m = calculate(s)
                self.assertEqual(m["energy_delivered_kwh"], 0)
                self.assertEqual(m["departed_shortfall_kwh"], 10)
                self.assertEqual(m["charge_completed"], 0)

    def test_pending_is_not_departed_failure(self):
        s = Simulation(config(charger_kw=6, feeder_kw=6), [Arrival(0, 10, True, True, 120, 10)])
        s.run(); m = calculate(s)
        self.assertAlmostEqual(m["energy_delivered_kwh"], 5)
        self.assertAlmostEqual(m["pending_energy_kwh"], 5)
        self.assertEqual(m["departed_shortfall_kwh"], 0)
        self.assertEqual(m["cost_items"]["ev_residual_trip_loss"], 0.0)
        self.assertEqual(m["occupancy"], 1)

    def test_departure_precedes_arrival_at_tie(self):
        s = Simulation(config(n_spaces=1, charging_bays=0, chargers=0), [Arrival(0, 0, False, False, 5, 0), Arrival(1, 5, False, False, 5, 0)])
        s.run()
        self.assertTrue(all(v["admitted"] for v in s.visits))
        self.assertEqual([e["kind"] for e in s.events if e["time_min"] == 5], ["departure", "arrival"])

    def test_fixed_connector_never_moves(self):
        s = Simulation(config(chargers=1), [Arrival(0, 0, True, True, 5, .1), Arrival(1, 1, True, True, 30, 10)])
        s.run()
        self.assertEqual(s.visits[1]["bay"], 1)
        self.assertEqual(s.visits[1]["delivered_kwh"], 0)

    def test_zero_arrivals_has_no_fake_scores(self):
        s = Simulation(config(arrival_rate_hour=0)); s.run(); m = calculate(s)
        self.assertEqual(m["arrivals"], 0)
        self.assertIsNone(m["brier"])
        self.assertIsNone(m["interval_coverage"])
        self.assertEqual(s.learner.seen, 0)
        self.assertGreater(s.learner.exposure, 0)
        self.assertFalse(s.export()["pending_next_forecast"]["observed_next"])
        self.assertEqual(s.export()["pending_next_forecast"]["censored_after_min"], 60)

    def test_all_ev_all_ice_and_no_charging(self):
        for share in (0, 1):
            c = config(ev_share=share, charge_probability=0)
            arrivals = generate(c)
            self.assertGreater(len(arrivals), 0)
            self.assertTrue(all(a.is_ev == bool(share) and not a.needs_charge for a in arrivals))
            s = Simulation(c); s.run()
            self.assertEqual(calculate(s)["energy_requested_all_kwh"], 0)

    def test_no_environment_truth_in_initial_predictor(self):
        first = Learner(config(ev_share=0, arrival_rate_hour=1, charge_probability=0)).forecast()
        second = Learner(config(ev_share=1, arrival_rate_hour=1000, charge_probability=1)).forecast()
        self.assertEqual(first, second)
        self.assertEqual(first["p_ev"], .5)

    def test_first_prediction_precedes_label(self):
        s = Simulation(config(ev_share=1), [Arrival(0, 1, True, True, 10, 1)])
        s.advance(1)
        self.assertEqual(s.scores[0]["p_ev"], .5)
        self.assertEqual(s.scores[0]["brier"], .25)
        self.assertEqual(s.scores[0]["issued_at_min"], 0)
        self.assertGreater(s.learner.forecast()["p_ev"], .5)

    def test_no_future_arrival_can_change_earlier_forecast(self):
        a = Arrival(0, 1, False, False, 10, 0)
        s1 = Simulation(config(), [a, Arrival(1, 20, True, True, 10, 3)])
        s2 = Simulation(config(), [a, Arrival(1, 40, False, False, 1, 0)])
        s1.advance(10); s2.advance(10)
        self.assertEqual(s1.learner.forecast(), s2.learner.forecast())
        self.assertEqual(s1.scores, s2.scores)
        self.assertEqual(s1.active, s2.active)

    def test_exposure_independent_of_step_partition(self):
        a, b = Learner(config()), Learner(config())
        a.advance(60)
        for t in range(1, 61): b.advance(t)
        self.assertAlmostEqual(a.exposure, b.exposure, places=11)
        self.assertAlmostEqual(a.forecast()["wait_upper_min"], b.forecast()["wait_upper_min"], places=10)

    def test_replay_same_seed_and_step_partition(self):
        c = config(n_spaces=12, charging_bays=4, chargers=3, arrival_rate_hour=60)
        a, b, replay = Simulation(c), Simulation(c), Simulation(c)
        a.run(); replay.run()
        self.assertEqual(a.export(), replay.export())
        for t in range(5, 61, 5): b.advance(t)
        left, right = calculate(a), calculate(b)
        for key in ["energy_delivered_kwh", "total_cost", "brier", "interval_coverage", "mean_occupancy_rate"]:
            if left[key] is None:
                self.assertIsNone(right[key])
            else:
                self.assertAlmostEqual(left[key], right[key], places=8)

    def test_energy_integral_and_all_resource_bounds(self):
        s = Simulation(config(n_spaces=12, charging_bays=7, chargers=4, arrival_rate_hour=100,
                              ev_share=.9, charge_probability=1, charger_kw=11, feeder_kw=17))
        s.run(); m = calculate(s)
        energy = sum((r["end_min"] - r["start_min"]) * r["power_kw"] / 60 for r in s.power_segments)
        self.assertAlmostEqual(m["energy_delivered_kwh"], energy, places=8)
        self.assertLessEqual(m["peak_power_kw"], 17)
        self.assertLessEqual(m["peak_charging"], 4)
        self.assertLessEqual(m["peak_occupancy"], 12)
        self.assertAlmostEqual(m["energy_balance_error_kwh"], 0, places=8)

    def test_all_scenarios_finite_export(self):
        for scenario in ("steady", "peaks", "burst", "drift"):
            s = Simulation(config(scenario=scenario)); s.run()
            json.dumps(export_run(s), allow_nan=False)
            self.assertTrue(s.finished)

    def test_policy_comparison_uses_same_flow_and_no_label_censoring(self):
        result = compare(config(), [11, 12, 13])
        self.assertEqual(len(result["runs"]), 12)
        for seed in result["seeds"]:
            runs = [r for r in result["runs"] if r["seed"] == seed]
            self.assertEqual(len({r["demand_hash"] for r in runs}), 1)
            self.assertEqual(len({r["metrics"]["arrivals"] for r in runs}), 1)
            for run in runs:
                self.assertAlmostEqual(run["metrics"]["brier"], runs[0]["metrics"]["brier"], places=12)
        self.assertTrue(all(row["total_cost_std"] is None or row["total_cost_std"] >= 0
                            for row in result["rows"]))
        self.assertFalse(any(row["cost_complete_runs"] for row in result["rows"]))

    def test_zero_demand_comparison_denominators(self):
        result = compare(config(arrival_rate_hour=0), [1, 2, 3])
        self.assertTrue(all(r["rejection_rate"] is None and r["interval_coverage"] is None for r in result["rows"]))

    def test_bad_configs_rejected(self):
        cases = [{"n_spaces": True}, {"chargers": 2.0}, {"charging_bays": 100}, {"ev_share": float("nan")},
                 {"arrival_rate_hour": float("inf")}, {"energy_mean_kwh": -1}, {"duration_hours": 0},
                 {"scenario": []}, {"policy": "unknown"}, {"seed": -1}, {"unknown": 1},
                 {"prior_rate_hour": .01, "prior_strength_min": 1},
                 {"duration_hours": 72, "arrival_rate_hour": 2000}]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError): config(**changes)

    def test_bad_seed_sets_rejected(self):
        for seeds in ([], [1, 1], [True], [1.5], [-1], list(range(9))):
            with self.subTest(seeds=seeds), self.assertRaises(ValueError): compare(config(), seeds)

    def test_output_explicit_and_non_overwriting(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "new-run"
            write_output(target, {"result": 1})
            with self.assertRaises(FileExistsError): write_output(target, {"result": 2})
            self.assertEqual(json.loads((target / "result.json").read_text(encoding="utf-8")), {"result": 1})


if __name__ == "__main__":
    unittest.main()
