"""Tests for the calibrated traffic generator (standard library only).

R2-B (2026-10-31) 覆盖：真实需求不被提前削减、需求能量与外生基础设施情景解耦、
暖启动平稳长度偏置（含两点分布闭式校验）、公开 warm_start_arrivals API、
分列需求账与删失标记（删失不算离场失败）。
R3-A (2026-10-31) 覆盖：independent p_EV/q_need 独立输入（不由 product 推导、小 p_EV 不拒绝）、
legacy_product 截断打标、strict 拒 q>1/NaN/inf/超范围、同 seed 确定性、
meta 场景字段齐全、默认调用向后兼容（流哈希固定）。
"""
import copy
import json
import math
import random
import tempfile
import unittest
from pathlib import Path

from apps.parking_lab.workbench import traffic_gen
from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.demand import Arrival, stream_hash as demand_stream_hash
from apps.parking_lab.workbench.simulation import Simulation


def _dwell():
    return {
        "family": "two_component_mixture",
        "mean_min": 300.0,
        "components": [
            {"name": "short_medium", "weight": 0.7, "family": "lognormal_scenario",
             "params": [math.log(180.0) - 0.18, 0.6], "mean_min": 180.0},
            {"name": "overnight_long", "weight": 0.3, "family": "lognormal_scenario",
             "params": [math.log(720.0) - 0.061, 0.35], "mean_min": 720.0, "is_scenario": True},
        ],
    }


def _params():
    hours = list(range(24))
    rate = [float(4 + 6 * math.sin(math.pi * h / 12.0) ** 2) for h in hours]
    return {
        "schema_version": "traffic_gen_params/v1",
        "generated_utc": "2026-10-31T00:00:00+00:00",
        "bins": {"count": 24, "local_hour": hours, "minutes_observed": [60.0] * 24},
        "traffic_fit": {
            "train": {"arrival_rate_per_100_spaces_hour": rate, "dwell": _dwell()},
            "cohort_reference": {"arrival_rate_per_100_spaces_hour": [v / 2.0 for v in rate]},
        },
        "ev": {"p_ev_default": 0.08, "product_required_mean": 0.04},
        "energy": {"charger_power_kw": 11.0, "efficiency": 0.9, "deficit_mean_kwh": 20.0,
                   "deficit_sd_kwh": 5.0, "deficit_clip_kwh": [4.0, 55.0]},
        "generator": {"horizon_min": 1440, "minute_step_min": 1.0, "reference_spaces": 100,
                      "default_n_spaces": 100.0, "max_dwell_min": 1440, "min_dwell_min": 1.0,
                      "max_arrivals": 40000},
        "per_lot": [{
            "lot_id": "LOT-A", "n_spaces": 120.0, "fit_split": "train",
            "lambda_hour_by_bin": [8.0 + (2.0 if 7 <= h <= 9 else 0.0) for h in hours],
            "lambda_bar_veh_per_hour": 9.0,
            "dwell_dist": _dwell(),
            "charge_session_rate_hour_by_bin": [0.3] * 24,
            "charge_session_rate_mean_hour": 0.3,
            "charge_duration_hist_5min": {"60": 3, "120": 2},
            "mean_occupancy_vehicles": 60.0,
            "connector_availability": 0.7,
        }, {
            "lot_id": "LOT-B", "n_spaces": 40.0, "fit_split": "validation",
            "lambda_hour_by_bin": [4.0] * 24,
            "lambda_bar_veh_per_hour": 4.0,
            "dwell_dist": _dwell(),
            "charge_session_rate_hour_by_bin": [0.2] * 24,
            "charge_session_rate_mean_hour": 0.2,
            "charge_duration_hist_5min": {"60": 2},
            "mean_occupancy_vehicles": 20.0,
            "connector_availability": 0.9,
        }],
    }


def _two_point_params():
    """两个停留点 {1, 9} min 等权：平稳剩余 E[D^2]/(2E[D])=4.1 min（旧口径 U(0,D) 为 2.5）。"""
    dwell = {"family": "two_point", "mean_min": 5.0, "components": [
        {"name": "one", "weight": 0.5, "family": "lognormal_scenario",
         "params": [math.log(1.0), 0.0], "mean_min": 1.0},
        {"name": "nine", "weight": 0.5, "family": "lognormal_scenario",
         "params": [math.log(9.0), 0.0], "mean_min": 9.0},
    ]}
    params = _params()
    params["traffic_fit"] = {
        "train": {"arrival_rate_per_100_spaces_hour": [0.0] * 24, "dwell": dwell},
        "cohort_reference": {"arrival_rate_per_100_spaces_hour": [0.0] * 24},
    }
    params["per_lot"] = [{
        "lot_id": "TWO-POINT", "n_spaces": 20000.0, "fit_split": "train",
        "lambda_hour_by_bin": [0.0] * 24, "lambda_bar_veh_per_hour": 0.0,
        "dwell_dist": dwell, "charge_session_rate_hour_by_bin": [0.0] * 24,
        "charge_session_rate_mean_hour": 0.0, "mean_occupancy_vehicles": 20000.0,
        "connector_availability": 1.0, "usable": True,
    }]
    params["generator"] = dict(params["generator"], horizon_min=60)
    return params


def _fixed_demand_params(mean_kwh=14.0, power=7.0, dwell_min=60.0):
    """真实需求恒为 mean_kwh、额定 power、停留约 dwell_min：修复前会被削到 power*dwell/60。"""
    params = _params()
    params["traffic_fit"] = {
        "train": {"arrival_rate_per_100_spaces_hour": [4.0] * 24,
                  "dwell": {"family": "single_lognormal", "mean_min": dwell_min,
                            "components": [{"name": "only", "weight": 1.0,
                                            "family": "lognormal_scenario",
                                            "params": [math.log(dwell_min), 1e-6],
                                            "mean_min": dwell_min}]}},
        "cohort_reference": {"arrival_rate_per_100_spaces_hour": [2.0] * 24},
    }
    params["energy"] = {"charger_power_kw": power, "efficiency": 1.0,
                        "deficit_mean_kwh": mean_kwh, "deficit_sd_kwh": 0.0,
                        "deficit_clip_kwh": [mean_kwh, mean_kwh]}
    params["ev"] = {"p_ev_default": 0.5, "product_required_mean": 0.25}
    return params


def _sim(overrides=None):
    raw = {"n_spaces": 120, "charging_bays": 3, "chargers": 3, "reserve_fixed": 0,
           "scenario": "steady", "duration_hours": 24.0, "arrival_rate_hour": 0.0,
           "seed": 42, "charger_kw": 7.0, "feeder_kw": 120.0}
    raw.update(overrides or {})
    return Config.parse(raw)


class TrafficGenTests(unittest.TestCase):
    def setUp(self):
        self.params = _params()

    def test_schema_and_ordering(self):
        arrivals, meta = traffic_gen.generate(self.params, 7)
        self.assertGreater(len(arrivals), 50)
        times = [a.time_min for a in arrivals]
        self.assertEqual(times, sorted(times))
        self.assertEqual([a.vehicle_id for a in arrivals], list(range(len(arrivals))))
        self.assertTrue(all(0.0 <= a.time_min < 1440.0 for a in arrivals))
        self.assertTrue(all(a.dwell_min >= 1.0 and a.dwell_min <= 1440.0 for a in arrivals))
        for a in arrivals:
            self.assertIsInstance(a.is_ev, bool)
            if a.needs_charge:
                self.assertTrue(a.is_ev)
                self.assertGreater(a.energy_kwh, 0.0)
            else:
                self.assertEqual(a.energy_kwh, 0.0)

    def test_energy_is_true_demand_not_precut(self):
        arrivals, meta = traffic_gen.generate(self.params, 11, horizon_min=1440)
        power = self.params["energy"]["charger_power_kw"]
        eff = self.params["energy"]["efficiency"]
        low, high = self.params["energy"]["deficit_clip_kwh"]
        needs = [a for a in arrivals if a.needs_charge]
        self.assertTrue(needs)
        for a in needs:
            self.assertGreaterEqual(a.energy_kwh, low - 1e-9)
            self.assertLessEqual(a.energy_kwh, high + 1e-9)
        # 真实需求允许超过"停留内按额定功率可交付量"；若全部被压到上限，说明又在提前削减需求。
        capped = [a for a in needs
                  if a.energy_kwh > power * eff * a.dwell_min / 60.0 + 1e-9]
        self.assertTrue(capped, "真实需求必须允许超过停留可交付量，否则说明被提前削减")
        # 分列账恒等式：真实需求 = 停靠内可交付 + 离场缺口 + 期末待交付。
        total = (meta["deliverable_energy_kwh_total"] + meta["departed_shortfall_kwh"]
                 + meta["pending_energy_kwh"])
        self.assertAlmostEqual(total, meta["demand_energy_kwh_total"], places=6)
        self.assertGreater(meta["theoretical_service_min_total"], 0.0)

    def test_fixed_demand_counterexample_14kwh(self):
        params = _fixed_demand_params(mean_kwh=14.0, power=7.0, dwell_min=60.0)
        arrivals, _ = traffic_gen.generate(params, 7)
        needs = [a for a in arrivals if a.needs_charge]
        self.assertTrue(needs)
        for a in needs:
            # 14 kWh 真实需求 + 7 kW / 60 min 停留 -> 需求仍是 14 kWh（缺口 7 kWh 属功率/停留型）
            self.assertAlmostEqual(a.energy_kwh, 14.0, places=6)
            self.assertLess(7.0 * a.dwell_min / 60.0, a.energy_kwh)

    def test_demand_energy_independent_of_power_scenario(self):
        hashes, per_vehicle = [], []
        for power in (7.0, 3.5, 50.0):
            params = _fixed_demand_params(mean_kwh=14.0, power=power)
            arrivals, _ = traffic_gen.generate(params, 11)
            hashes.append(traffic_gen.stream_hash(arrivals))
            per_vehicle.append(tuple(a.energy_kwh for a in arrivals))
        self.assertEqual(len(set(hashes)), 1)
        self.assertEqual(len(set(per_vehicle)), 1)

    def test_demand_stream_invariant_across_k_power_feeder(self):
        arrivals, _ = traffic_gen.generate_for_lot(self.params, "LOT-A", 42)
        hashes, energies = set(), set()
        for overrides in ({"chargers": 1, "charging_bays": 1, "charger_kw": 7.0,
                           "feeder_kw": 120.0},
                          {"chargers": 5, "charging_bays": 5, "charger_kw": 50.0,
                           "feeder_kw": 30.0},
                          {"chargers": 2, "charging_bays": 2, "charger_kw": 7.0,
                           "feeder_kw": 500.0}):
            sim = Simulation(_sim(overrides), arrivals=arrivals)
            sim.run()
            hashes.add(sim.demand_hash)
            energies.add(tuple(a.energy_kwh for a in sim.arrivals))
        self.assertEqual(len(hashes), 1, "同一外生需求流在不同 k/功率/馈线下必须同哈希")
        self.assertEqual(len(energies), 1)
        self.assertEqual(traffic_gen.stream_hash(arrivals),
                         traffic_gen.stream_hash(tuple(arrivals)))

    def test_same_seed_same_hash_and_hash_matches_demand(self):
        a1, m1 = traffic_gen.generate(self.params, 42)
        a2, m2 = traffic_gen.generate(self.params, 42)
        self.assertEqual(m1["stream_hash"], m2["stream_hash"])
        self.assertEqual(traffic_gen.stream_hash(a1), traffic_gen.stream_hash(a2))
        legacy = tuple(Arrival(a.vehicle_id, a.time_min, a.is_ev, a.needs_charge,
                               a.dwell_min, a.energy_kwh) for a in a1)
        self.assertEqual(traffic_gen.stream_hash(legacy), demand_stream_hash(legacy))
        _, m3 = traffic_gen.generate(self.params, 43)
        self.assertNotEqual(m1["stream_hash"], m3["stream_hash"])

    def test_meta_contract_keys(self):
        _, meta = traffic_gen.generate(self.params, 5)
        for key in ("seed", "params_hash", "generator_version", "split", "horizon_min",
                    "n_spaces", "n_arrivals", "stream_hash",
                    "demand_energy_kwh_total", "theoretical_service_min_total",
                    "deliverable_energy_kwh_total", "departed_shortfall_kwh",
                    "pending_energy_kwh", "initial_occupancy_n", "warm_start_method",
                    "length_biased"):
            self.assertIn(key, meta)
        self.assertEqual(meta["split"], "train")
        self.assertEqual(meta["generator_version"], traffic_gen.GENERATOR_VERSION)
        self.assertEqual(len(meta["params_hash"]), 64)
        self.assertEqual(meta["warm_start_method"], "none")
        self.assertFalse(meta["length_biased"])
        self.assertEqual(meta["initial_occupancy_n"], 0)

    def test_split_selection(self):
        _, train_meta = traffic_gen.generate(self.params, 9, split="train")
        _, cohort_meta = traffic_gen.generate(self.params, 9, split="cohort")
        self.assertEqual(train_meta["split"], "train")
        self.assertEqual(cohort_meta["split"], "cohort")
        a_train, _ = traffic_gen.generate(self.params, 9, split="train")
        a_cohort, _ = traffic_gen.generate(self.params, 9, split="cohort")
        self.assertGreater(len(a_train), len(a_cohort))
        with self.assertRaises(ValueError):
            traffic_gen.generate(self.params, 9, split="nonsense")

    def test_generate_for_lot(self):
        arrivals, meta = traffic_gen.generate_for_lot(self.params, "LOT-A", 42)
        self.assertEqual(meta["lot_id"], "LOT-A")
        self.assertEqual(meta["split"], "train")
        self.assertEqual(meta["n_spaces"], 120.0)
        self.assertIn("q_need", meta)
        self.assertTrue(0.0 <= meta["q_need"] <= 1.0)
        big, _ = traffic_gen.generate_for_lot(self.params, "LOT-A", 42)
        small, _ = traffic_gen.generate_for_lot(self.params, "LOT-B", 42)
        self.assertGreater(len(big), len(small))
        with self.assertRaises(KeyError):
            traffic_gen.generate_for_lot(self.params, "NOPE", 42)
        with self.assertRaises(ValueError):
            traffic_gen.generate_for_lot(self.params, "LOT-A", 42, p_ev=0.0)

    def test_warm_start_matches_observed_occupancy(self):
        arrivals, meta = traffic_gen.generate_for_lot(self.params, "LOT-A", 42)
        warm_n = meta["initial_occupancy_n"]
        self.assertEqual(warm_n, 60)
        self.assertEqual(meta["initial_occupancy_vehicles"], 60.0)
        self.assertTrue(meta["warm_start"])
        self.assertEqual(meta["warm_start_method"], "length_biased_stationary")
        self.assertTrue(meta["length_biased"])
        self.assertEqual(meta["n_new_arrivals"], len(arrivals) - warm_n)
        self.assertEqual(meta["initial_occupancy_demand_kwh"]
                         + meta["new_arrival_demand_kwh"], meta["demand_energy_kwh_total"])
        present_at_zero = sum(1 for a in arrivals
                              if a.time_min <= 0.0 < a.time_min + a.dwell_min)
        self.assertEqual(present_at_zero, warm_n)
        dwell = sorted(a.dwell_min for a in arrivals[warm_n:])
        self.assertLess(abs(sum(dwell) / len(dwell) - 300.0), 90.0)

    def test_warm_start_stationary_length_bias_two_point(self):
        params = _two_point_params()
        arrivals, meta = traffic_gen.generate_for_lot(params, "TWO-POINT", 3)
        warm_n = meta["initial_occupancy_n"]
        self.assertGreaterEqual(warm_n, 1000)
        residual = [a.dwell_min for a in arrivals[:warm_n]]
        mean = sum(residual) / len(residual)
        expected = 4.1  # E[D^2]/(2E[D]) = (1+81)/(2*5)
        self.assertAlmostEqual(meta["expected_warm_residual_mean_min"], expected, places=9)
        self.assertLess(abs(mean - expected), 0.15)
        # 旧实现 U(0,D) 给 2.5；偏差 39%
        self.assertGreater(abs(mean - 2.5), 1.0)

    def test_public_warm_start_arrivals_api(self):
        dwell = _two_point_params()["per_lot"][0]["dwell_dist"]
        rng1 = random.Random(20261031)
        rng2 = random.Random(20261031)
        lot = {"p_ev": 0.5, "q_need": 0.0}
        first = traffic_gen.warm_start_arrivals(lot, 500, rng1, dwell)
        second = traffic_gen.warm_start_arrivals(lot, 500, rng2, dwell)
        self.assertEqual(first, second)
        self.assertTrue(all(a.time_min == 0.0 for a in first))
        self.assertTrue(all(isinstance(a, traffic_gen.Arrival) for a in first))
        mean = sum(a.dwell_min for a in first) / len(first)
        self.assertLess(abs(mean - 4.1), 0.4)
        # 给定 energy 块时，充电需求是真实需求而不是由剩余停留反推
        energy = {"charger_power_kw": 7.0, "efficiency": 1.0, "deficit_mean_kwh": 14.0,
                  "deficit_sd_kwh": 0.0, "deficit_clip_kwh": [14.0, 14.0]}
        charged = traffic_gen.warm_start_arrivals(lot, 200, random.Random(7), dwell,
                                                  q_need=1.0, energy=energy)
        needs = [a for a in charged if a.needs_charge]
        self.assertTrue(needs)
        for a in needs:
            self.assertAlmostEqual(a.energy_kwh, 14.0, places=6)

    def test_generator_reuses_public_warm_start(self):
        arrivals, meta = traffic_gen.generate_for_lot(self.params, "LOT-A", 42)
        warm_n = meta["initial_occupancy_n"]
        entry = next(row for row in self.params["per_lot"] if row["lot_id"] == "LOT-A")
        rng = random.Random(42 * 1000003 + 505)
        manual = traffic_gen.warm_start_arrivals(
            entry, warm_n, rng, entry["dwell_dist"], p_ev=meta["p_ev"],
            q_need=meta["q_need"], energy=self.params["energy"],
            min_dwell_min=1.0, max_dwell_min=1440.0, vehicle_id_start=0)
        self.assertEqual(tuple(a.dwell_min for a in manual),
                         tuple(a.dwell_min for a in arrivals[:warm_n]))
        self.assertEqual(tuple(a.energy_kwh for a in manual),
                         tuple(a.energy_kwh for a in arrivals[:warm_n]))

    def test_demand_ledger_columns_and_censoring(self):
        arrivals = (
            traffic_gen.Arrival(0, 0.0, True, True, 60.0, 14.0),     # 离场：14 kWh 需求，停 60min 只能交付 7
            traffic_gen.Arrival(1, 1000.0, True, True, 720.0, 60.0),  # 窗口截断：跨窗口停放
        )
        ledger = traffic_gen.demand_ledger(arrivals, charger_kw=7.0, efficiency=1.0,
                                           horizon_min=1440, initial_occupancy_n=1,
                                           include_vehicles=True)
        totals = ledger["totals"]
        rows = ledger["vehicles"]
        self.assertEqual([row["vehicle_id"] for row in rows], [0, 1])
        self.assertAlmostEqual(rows[0]["demand_energy_kwh"], 14.0)
        self.assertAlmostEqual(rows[0]["required_min"], 120.0)
        self.assertAlmostEqual(rows[0]["deliverable_energy_kwh"], 7.0)
        self.assertAlmostEqual(rows[0]["departed_shortfall_kwh"], 7.0)
        self.assertFalse(rows[0]["censored"])
        self.assertTrue(rows[1]["censored"])
        self.assertAlmostEqual(rows[1]["pending_energy_kwh"], 60.0 - 7.0 * 440.0 / 60.0, places=6)
        self.assertEqual(rows[1]["departed_shortfall_kwh"], 0.0)
        self.assertEqual(totals["charge_shortfall_sessions"], 1, "删失不得计入离场失败")
        self.assertEqual(totals["censored_charge_sessions"], 1)
        self.assertGreater(totals["pending_energy_kwh"], 0.0)
        self.assertAlmostEqual(totals["initial_occupancy_demand_kwh"], 14.0)
        self.assertAlmostEqual(totals["new_arrival_demand_kwh"], 60.0)
        self.assertEqual(
            totals["demand_energy_kwh_total"],
            totals["deliverable_energy_kwh_total"] + totals["departed_shortfall_kwh"]
            + totals["pending_energy_kwh"])

    def test_generate_for_lot_censoring_meta(self):
        horizon = 120.0
        arrivals, meta = traffic_gen.generate_for_lot(self.params, "LOT-A", 7,
                                                      horizon_min=horizon)
        # 120 min 窗口 + 300~720 min 停留：大量期初/新到车辆在期末仍在场。
        cap = (self.params["energy"]["charger_power_kw"]
               * self.params["energy"]["efficiency"])
        short = censored = 0
        demand = deliverable = gap = pending = 0.0
        for a in arrivals:
            if not a.needs_charge:
                continue
            stay = a.dwell_min
            if a.time_min + a.dwell_min > horizon + 1e-9:
                censored += 1
                stay = max(0.0, min(stay, horizon - a.time_min))
                value = min(a.energy_kwh, cap * stay / 60.0)
                pending += a.energy_kwh - value
            else:
                value = min(a.energy_kwh, cap * stay / 60.0)
                gap += a.energy_kwh - value
                short += int(a.energy_kwh - value > 1e-9)
            demand += a.energy_kwh
            deliverable += value
        self.assertEqual(meta["censored_charge_sessions"], censored)
        self.assertEqual(meta["charge_shortfall_sessions"], short)
        self.assertGreater(censored, 0)
        self.assertGreater(pending, 0.0)
        self.assertAlmostEqual(meta["demand_energy_kwh_total"], demand, places=6)
        self.assertAlmostEqual(meta["deliverable_energy_kwh_total"], deliverable, places=6)
        self.assertAlmostEqual(meta["departed_shortfall_kwh"], gap, places=6)
        self.assertAlmostEqual(meta["pending_energy_kwh"], pending, places=6)

    def test_charge_scenarios_and_conflict_flag(self):
        _, meta = traffic_gen.generate_for_lot(self.params, "LOT-A", 42)
        self.assertAlmostEqual(meta["p_ev_times_q_need_used"],
                               meta["p_ev"] * meta["q_need"], places=12)
        self.assertFalse(meta["identification_conflict"])
        _, grown = traffic_gen.generate_for_lot(self.params, "LOT-A", 42, demand_scale=2.0)
        self.assertGreater(grown["target_charge_arrivals"],
                           meta["target_charge_arrivals"])
        self.assertEqual(grown["demand_scale"], 2.0)
        _, tight = traffic_gen.generate_for_lot(self.params, "LOT-A", 42, p_ev=0.01)
        self.assertTrue(tight["identification_conflict"])
        self.assertEqual(tight["q_need"], 1.0)

    def test_scenario_independent_small_p_ev_and_no_product_derivation(self):
        # R3-A: p_EV=0.05 可跑（不因 p_EV 小于观测乘积被拒绝）；q_need 不被 product/p_EV 反推。
        rows, meta = traffic_gen.generate_for_lot(
            self.params, "LOT-A", 42, p_ev=0.05, q_need=0.7,
            scenario_model="independent")
        self.assertEqual(meta["scenario_model"], "independent")
        self.assertFalse(meta["product_coupled"])
        self.assertFalse(meta["clipped"])
        self.assertEqual(meta["p_ev"], 0.05)
        self.assertEqual(meta["q_need"], 0.7)  # 不是 observed_product/p_EV ~ 0.6667 或 0.8
        self.assertAlmostEqual(meta["p_ev_times_q_need_used"], 0.035, places=12)
        self.assertEqual(meta["p_ev_source"], "argument")
        self.assertEqual(meta["q_need_source"], "argument")
        self.assertFalse(meta["identification_conflict"])
        self.assertEqual(meta["demand_calibration_status"], "scenario_not_identified")
        self.assertGreater(meta["target_charge_arrivals"], 0.0)
        # 同一 p_EV/q_need 下 legacy 显式 q 的到达流应与 independent 完全一致（仅 meta 不同）。
        _, legacy = traffic_gen.generate_for_lot(
            self.params, "LOT-A", 42, p_ev=0.05, q_need=0.7,
            scenario_model="legacy_product")
        self.assertEqual(meta["stream_hash"], legacy["stream_hash"])
        self.assertAlmostEqual(meta["target_charge_arrivals"],
                              legacy["target_charge_arrivals"], places=12)
        # 同 seed 同参数确定。
        again, _ = traffic_gen.generate_for_lot(
            self.params, "LOT-A", 42, p_ev=0.05, q_need=0.7,
            scenario_model="independent")
        self.assertEqual([a.to_dict() for a in rows], [a.to_dict() for a in again])

    def test_scenario_independent_validation(self):
        def call(**kwargs):
            return traffic_gen.generate_for_lot(
                self.params, "LOT-A", 42, scenario_model="independent", **kwargs)
        # 缺 q_need 且参数无 q_need_default：不得从 product 推导，明确报错。
        with self.assertRaises(ValueError):
            call(p_ev=0.05)
        for bad_q in (1.2, -0.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                call(p_ev=0.05, q_need=bad_q)
        for bad_p in (0.0, -0.1, 1.2, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                call(p_ev=bad_p, q_need=0.5)
        with self.assertRaises(ValueError):
            traffic_gen.generate_for_lot(self.params, "LOT-A", 42, p_ev=0.05,
                                         q_need=0.5, scenario_model="coupled")
        # 边界值 p_EV=1.0、q_need=1.0 合法。
        _, edge = call(p_ev=1.0, q_need=1.0)
        self.assertEqual(edge["p_ev"], 1.0)
        self.assertEqual(edge["q_need"], 1.0)

    def test_legacy_clipping_is_flagged(self):
        def call(**kwargs):
            return traffic_gen.generate_for_lot(self.params, "LOT-A", 42, **kwargs)
        _, meta = call(q_need=1.2)
        self.assertEqual(meta["scenario_model"], "legacy_product")
        self.assertTrue(meta["product_coupled"])
        self.assertFalse(meta["strict"])
        self.assertEqual(meta["q_need"], 1.0)
        self.assertEqual(meta["q_need_raw"], 1.2)
        self.assertTrue(meta["clipped"])
        self.assertTrue(meta["identification_conflict"])
        _, low = call(q_need=-0.5)
        self.assertEqual(low["q_need"], 0.0)
        self.assertTrue(low["clipped"])
        _, exact = call(q_need=0.5)
        self.assertFalse(exact["clipped"])
        self.assertEqual(exact["q_need"], 0.5)
        _, derived = call(p_ev=0.01)  # q=observed_product/0.01 远超 1
        self.assertEqual(derived["q_need"], 1.0)
        self.assertTrue(derived["clipped"])
        self.assertTrue(derived["identification_conflict"])

    def test_strict_rejects_instead_of_clipping(self):
        def call(**kwargs):
            return traffic_gen.generate_for_lot(self.params, "LOT-A", 42, strict=True,
                                                **kwargs)
        for bad_q in (1.2, -0.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                call(q_need=bad_q)
        for bad_p in (0.0, 1.2, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                call(p_ev=bad_p)
        with self.assertRaises(ValueError):
            call(p_ev=0.01)  # 派生 q_need > 1，strict 不截断
        # 合法值 strict 与默认路径数值一致。
        _, strict_rows = traffic_gen.generate_for_lot(
            self.params, "LOT-A", 42, q_need=0.5, strict=True)
        _, lax_rows = traffic_gen.generate_for_lot(self.params, "LOT-A", 42, q_need=0.5)
        self.assertEqual(strict_rows["stream_hash"], lax_rows["stream_hash"])
        self.assertFalse(strict_rows["clipped"])
        self.assertEqual(strict_rows["q_need"], 0.5)

    def test_scenario_meta_fields_complete_and_backward_compatible(self):
        expected_fields = ("scenario_model", "product_coupled", "clipped", "strict",
                           "q_need_raw", "p_ev_source", "q_need_source",
                           "product_required_mean", "demand_calibration_status",
                           "demand_energy_is_scenario")
        for kwargs in ({}, {"p_ev": 0.05, "q_need": 0.7, "scenario_model": "independent"}):
            _, meta = traffic_gen.generate_for_lot(self.params, "LOT-A", 42, **kwargs)
            for field in expected_fields:
                self.assertIn(field, meta)
            self.assertEqual(meta["demand_calibration_status"],
                             "scenario_not_identified")
            self.assertIsInstance(meta["clipped"], bool)
            self.assertIsInstance(meta["product_coupled"], bool)
            self.assertIsInstance(meta["p_ev_source"], str)
            self.assertIsInstance(meta["q_need_source"], str)
        _, generated = traffic_gen.generate(self.params, 7)
        for field in expected_fields:
            self.assertIn(field, generated)
        self.assertEqual(generated["scenario_model"], "legacy_product")
        self.assertEqual(generated["demand_calibration_status"],
                         "scenario_not_identified")
        self.assertFalse(generated["clipped"])
        # 默认调用（legacy_product/strict=False）流哈希与 R2-B 2.0.0 完全一致。
        self.assertEqual(
            traffic_gen.generate_for_lot(self.params, "LOT-A", 42)[1]["stream_hash"],
            "90a93a6fd2140c28028af51455acb1735237d48b1b3b111cda0a337c0b6d2533")
        self.assertEqual(
            traffic_gen.generate_for_lot(self.params, "LOT-B", 42)[1]["stream_hash"],
            "996baf36ac9be06f7693dab6b119f097af8bdc0412f472b75162750419227103")
        self.assertEqual(traffic_gen.generate(self.params, 7)[1]["stream_hash"],
                         "84207e29e94cb32c38b3bd74c7d796de4153527f10da3c93f3fec8eb47d2b808")
        self.assertEqual(traffic_gen.generate(self.params, 42)[1]["stream_hash"],
                         "d5bd372972474162dfd34726c4d98b90ec0d658c0e006aa65123caafe9b62cf6")
        # 默认暖启动抽样同样冻结（长度偏置平稳口径）。
        dwell = self.params["per_lot"][0]["dwell_dist"]
        warm = traffic_gen.warm_start_arrivals({"p_ev": 0.5, "q_need": 0.0}, 50,
                                               random.Random(20261031), dwell)
        self.assertEqual(len(warm), 50)
        self.assertEqual(sum(1 for a in warm if a.is_ev), 27)
        self.assertAlmostEqual(sum(a.dwell_min for a in warm), 16099.392146, places=6)

    def test_warm_start_scenario_model(self):
        dwell = self.params["per_lot"][0]["dwell_dist"]
        energy = self.params["energy"]
        # legacy 非 strict：q_need=1.2 截断为 1.0，与 q_need=1.0 的抽样完全一致。
        clipped = traffic_gen.warm_start_arrivals(
            {"p_ev": 0.5, "q_need": 0.0}, 30, random.Random(11), dwell,
            p_ev=0.05, q_need=1.2, energy=energy)
        exact = traffic_gen.warm_start_arrivals(
            {"p_ev": 0.5}, 30, random.Random(11), dwell,
            p_ev=0.05, q_need=1.0, energy=energy)
        self.assertEqual([a.to_dict() for a in clipped], [a.to_dict() for a in exact])
        with self.assertRaises(ValueError):
            traffic_gen.warm_start_arrivals(
                {"p_ev": 0.5}, 10, random.Random(11), dwell,
                p_ev=0.05, q_need=1.2, energy=energy, strict=True)
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                traffic_gen.warm_start_arrivals(
                    {"p_ev": 0.5}, 10, random.Random(11), dwell,
                    p_ev=0.05, q_need=bad, energy=energy)
        # legacy 非 strict：负 q_need 截断为 0，等价于 q_need=0。
        negative = traffic_gen.warm_start_arrivals(
            {"p_ev": 0.5}, 10, random.Random(11), dwell,
            p_ev=0.05, q_need=-0.1, energy=energy)
        zero = traffic_gen.warm_start_arrivals(
            {"p_ev": 0.5}, 10, random.Random(11), dwell,
            p_ev=0.05, q_need=0.0, energy=energy)
        self.assertEqual([a.to_dict() for a in negative], [a.to_dict() for a in zero])
        # independent：必须显式 q_need（或 lot_info q_need），不从 product 推导。
        with self.assertRaises(ValueError):
            traffic_gen.warm_start_arrivals(
                {"p_ev": 0.5}, 10, random.Random(11), dwell,
                p_ev=0.05, energy=energy, scenario_model="independent")
        ind = traffic_gen.warm_start_arrivals(
            {"p_ev": 0.5}, 30, random.Random(11), dwell,
            p_ev=0.05, q_need=0.7, energy=energy, scenario_model="independent")
        self.assertEqual(len(ind), 30)
        self.assertTrue(any(a.needs_charge for a in ind))
        info_q = traffic_gen.warm_start_arrivals(
            {"p_ev": 0.05, "q_need": 0.7}, 30, random.Random(11), dwell,
            energy=energy, scenario_model="independent")
        self.assertEqual([a.to_dict() for a in ind], [a.to_dict() for a in info_q])
        for bad_q in (1.2, -0.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                traffic_gen.warm_start_arrivals(
                    {"p_ev": 0.5}, 10, random.Random(11), dwell,
                    p_ev=0.05, q_need=bad_q, energy=energy,
                    scenario_model="independent")
        with self.assertRaises(ValueError):
            traffic_gen.warm_start_arrivals(
                {"p_ev": 0.5}, 10, random.Random(11), dwell,
                p_ev=0.05, q_need=0.5, energy=energy, scenario_model="coupling")

    def test_save_load_roundtrip_and_tamper(self):
        arrivals, meta = traffic_gen.generate(self.params, 3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "traffic.json"
            written = traffic_gen.save_traffic(path, arrivals, meta)
            loaded, loaded_meta = traffic_gen.load_traffic(path)
            self.assertEqual(len(loaded), len(arrivals))
            self.assertEqual(loaded_meta["stream_hash"], written)
            self.assertEqual(traffic_gen.stream_hash(loaded), traffic_gen.stream_hash(arrivals))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["stream_hash"] = "0" * 64
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                traffic_gen.load_traffic(path)

    def test_arrival_cap_guard(self):
        params = _params()
        params["generator"] = dict(params["generator"], max_arrivals=10)
        with self.assertRaises(ValueError):
            traffic_gen.generate(params, 1)


if __name__ == "__main__":
    unittest.main()