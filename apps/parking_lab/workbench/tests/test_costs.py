"""成本模型 v2 的可手算算例与口径约束测试（不依赖随机仿真）。"""
import math
import unittest

from apps.parking_lab.workbench import costs as cost_module
from apps.parking_lab.workbench.config import Config, presets
from apps.parking_lab.workbench.costs import (
    ATTRIBUTION_ITEMS, COST_ITEMS, COST_MODEL_VERSION, LEGACY_COST_MODEL_VERSION, TRANSFER_ITEMS,
    CostLedger, DuplicateCostLineError, annotate_legacy, cost_report, counterfactual_run, dedupe_intervals,
    depreciation_daily, ev_failure_cost, failure_hours, ice_failure_cost, minutes_to_hours,
    paired_occupancy_counterfactual, run_paired_occupancy_counterfactual, traffic_hash, union_minutes,
)
from apps.parking_lab.workbench.demand import Arrival
from apps.parking_lab.workbench.metrics import calculate
from apps.parking_lab.workbench.simulation import Simulation

# 合成成本参数：仅用于手算断言，不是台北实测值（来源标注见 config.ILLUSTRATIVE_COST）。
SYNTHETIC = {
    "vot_per_hour": 600.0, "search_min": 6.0, "detour_min": 4.0, "walking_min": 3.0,
    "detour_km_per_failure": 2.0, "ev_kwh_per_km": 0.18, "ev_energy_price_per_kwh": 5.0,
    "alternative_charging_delta_per_kwh": 4.0, "residual_trip_loss_per_kwh": 8.0,
    "emission_cost_per_km": 1.5, "fuel_l_per_km": 0.08, "fuel_price_per_l": 30.0,
    "activity_loss_per_failure": 50.0, "electricity_price_per_kwh": 3.0,
    "maintenance_per_kwh": 0.5, "maintenance_per_bay_day": 20.0,
    "depreciation_annual": 365000.0, "parking_fee_per_hour": 40.0, "charging_fee_per_kwh": 8.0,
}
SEARCH, DETOUR, WALK = 6.0, 4.0, 3.0
SEQUENTIAL = [(0.0, SEARCH), (SEARCH, SEARCH + DETOUR), (SEARCH + DETOUR, SEARCH + DETOUR + WALK)]
DEPRECIATION_PER_DAY = 365000.0 / 365.0
ELAPSED_DAYS = 60.0 / 1440.0


def config(**changes):
    cost = {"provenance": "illustrative_not_calibrated", **SYNTHETIC}
    cost.update(changes.pop("cost", {}))
    raw = {"n_spaces": 2, "charging_bays": 2, "chargers": 2, "reserve_fixed": 0, "policy": "open",
           "scenario": "steady", "duration_hours": 1, "arrival_rate_hour": 0, "seed": 42, "cost": cost}
    raw.update(changes)
    return Config.parse(raw)


class ArithmeticTests(unittest.TestCase):
    def test_minutes_to_hours(self):
        self.assertAlmostEqual(minutes_to_hours(90), 1.5)
        self.assertAlmostEqual(failure_hours(SEQUENTIAL)[0], 13.0 / 60.0)

    def test_overlapping_intervals_counted_once(self):
        intervals = [(0.0, 6.0), (4.0, 10.0)]
        self.assertEqual(dedupe_intervals(intervals), [(0.0, 10.0)])
        self.assertAlmostEqual(union_minutes(intervals), 10.0)
        items = ice_failure_cost(SYNTHETIC, intervals=intervals, detour_km=2.0)["items"]
        self.assertAlmostEqual(items["user_time"], 600.0 * 10.0 / 60.0)

    def test_ev_failure_hand_calc(self):
        result = ev_failure_cost(SYNTHETIC, intervals=SEQUENTIAL, shortfall_kwh=10.0)
        items = result["items"]
        # Δt = 13 min = 13/60 h；600 × 13/60 = 130
        self.assertAlmostEqual(items["user_time"], 130.0)
        # 绕行能耗 2 km × 0.18 kWh/km × 5 TWD/kWh = 1.8；替代补能 10 kWh × 4 = 40
        self.assertAlmostEqual(items["ev_detour_energy"], 41.8)
        # 外部影响 2 km × 1.5 = 3
        self.assertAlmostEqual(items["ev_external"], 3.0)
        # 剩余行程损失 10 kWh × 8 = 80（不套用售电价）
        self.assertAlmostEqual(items["ev_residual_trip_loss"], 80.0)
        self.assertEqual(result["missing_parameters"], [])

    def test_ice_failure_hand_calc(self):
        result = ice_failure_cost(SYNTHETIC, intervals=SEQUENTIAL, activity_loss_applies=True)
        items = result["items"]
        self.assertAlmostEqual(items["user_time"], 130.0)
        self.assertAlmostEqual(items["ice_vehicle_operating"], 2 * 0.08 * 30.0)  # 4.8
        self.assertAlmostEqual(items["ice_external"], 3.0)
        self.assertAlmostEqual(items["ice_activity_loss"], 50.0)

    def test_ev_failure_activity_loss_hand_calc(self):
        # 放弃活动：与油车共用 activity_loss_per_failure；缺电损失另列，不互相替代/重复
        result = ev_failure_cost(SYNTHETIC, intervals=SEQUENTIAL, shortfall_kwh=10.0,
                                 activity_loss_applies=True)
        items = result["items"]
        self.assertAlmostEqual(items["ev_activity_loss"], 50.0)
        self.assertAlmostEqual(items["ev_residual_trip_loss"], 80.0)
        self.assertEqual(result["missing_parameters"], [])

    def test_missing_parameter_propagates_to_null(self):
        params = {**SYNTHETIC, "vot_per_hour": None}
        result = ice_failure_cost(params, intervals=SEQUENTIAL)
        self.assertIsNone(result["items"]["user_time"])
        self.assertIn("vot_per_hour", result["missing_parameters"])
        ledger = CostLedger(params)
        ledger.add_failure(1, "ICE", intervals=SEQUENTIAL)
        report = ledger.summary(elapsed_min=60.0, chargers=1)
        self.assertIsNone(report["items"]["user_time"])
        self.assertIsNone(report["total"])
        self.assertFalse(report["complete"])
        self.assertIn("vot_per_hour", report["missing_parameters"])

    def test_zero_quantity_does_not_need_parameter(self):
        params = {**SYNTHETIC, "residual_trip_loss_per_kwh": None}
        result = ev_failure_cost(params, intervals=[], shortfall_kwh=0.0, detour_km=0.0)
        self.assertEqual(result["items"]["ev_residual_trip_loss"], 0.0)
        self.assertNotIn("residual_trip_loss_per_kwh", result["missing_parameters"])

    def test_depreciation_hand_calc(self):
        daily, missing = depreciation_daily({"depreciation_annual": 365000.0})
        self.assertAlmostEqual(daily, 1000.0)
        self.assertEqual(missing, ())
        capex_daily, _ = depreciation_daily({"depreciation_capex": 3650000.0, "depreciation_life_years": 10.0})
        self.assertAlmostEqual(capex_daily, 1000.0)
        self.assertAlmostEqual(DEPRECIATION_PER_DAY * ELAPSED_DAYS, 1000.0 / 24.0)

    def test_operator_items_hand_calc(self):
        ledger = CostLedger(SYNTHETIC)
        report = ledger.summary(elapsed_min=60.0, delivered_kwh=10.0, chargers=1)
        self.assertAlmostEqual(report["items"]["operator_capital_depreciation"], 1000.0 / 24.0)
        self.assertAlmostEqual(report["items"]["operator_energy"], 10.0 * 3.0)
        self.assertAlmostEqual(report["items"]["operator_maintenance"], 10.0 * 0.5 + 20.0 / 24.0)
        self.assertAlmostEqual(report["total"], 1000.0 / 24.0 + 30.0 + 5.0 + 20.0 / 24.0)
        self.assertTrue(report["complete"])

    def test_transfers_not_in_total(self):
        ledger = CostLedger(SYNTHETIC)
        report = ledger.summary(elapsed_min=60.0, delivered_kwh=10.0, chargers=1,
                                transfers={"parking_fee": 80.0, "charging_fee": 80.0,
                                           "fines": 0.0, "subsidies": 0.0})
        self.assertAlmostEqual(report["total"], 1000.0 / 24.0 + 30.0 + 5.0 + 20.0 / 24.0)
        self.assertAlmostEqual(report["transfers"]["parking_fee"], 80.0)
        for item in TRANSFER_ITEMS:
            self.assertNotIn(item, COST_ITEMS)

    def test_duplicate_failure_line_rejected(self):
        ledger = CostLedger(SYNTHETIC)
        ledger.add_failure(7, "ICE", intervals=SEQUENTIAL)
        with self.assertRaises(DuplicateCostLineError):
            ledger.add_failure(7, "EV", intervals=SEQUENTIAL)
        self.assertEqual(ledger.failure_count(), 1)


class SimulationCostTests(unittest.TestCase):
    def test_rejected_ev_end_to_end_hand_calc(self):
        c = config(n_spaces=0, charging_bays=0, chargers=0)
        sim = Simulation(c, [Arrival(0, 10, True, True, 60, 10)])
        sim.run()
        m = calculate(sim)
        self.assertEqual(sim.visits[0]["disposition"], "detour_exit")
        self.assertEqual(sim.visits[0]["cost_kind"], "EV")
        self.assertEqual(sim.ledger.failure_count(), 1)
        items = m["cost_items"]
        self.assertAlmostEqual(items["user_time"], 130.0)
        self.assertAlmostEqual(items["ev_detour_energy"], 41.8)
        self.assertAlmostEqual(items["ev_external"], 3.0)
        self.assertAlmostEqual(items["ev_residual_trip_loss"], 80.0)
        # chargers=0 ⇒ 零设备：资本与按位维护都是 0.0（k 乘设备数，R2-D1）
        self.assertEqual(items["operator_capital_depreciation"], 0.0)
        self.assertEqual(items["operator_maintenance"], 0.0)
        self.assertAlmostEqual(m["total_cost"], 130.0 + 41.8 + 3.0 + 80.0)
        self.assertTrue(m["cost_complete"])
        self.assertEqual(m["cost_model_version"], COST_MODEL_VERSION)

    def test_rejected_ice_end_to_end_hand_calc(self):
        c = config(n_spaces=0, charging_bays=0, chargers=0)
        sim = Simulation(c, [Arrival(0, 10, False, False, 60, 0)])
        sim.run()
        m = calculate(sim)
        self.assertEqual(sim.visits[0]["cost_kind"], "ICE")
        items = m["cost_items"]
        self.assertAlmostEqual(items["user_time"], 130.0)
        self.assertAlmostEqual(items["ice_vehicle_operating"], 4.8)
        self.assertAlmostEqual(items["ice_external"], 3.0)
        self.assertEqual(items["ice_activity_loss"], 0.0)  # detour_exit 不放弃活动
        self.assertAlmostEqual(m["total_cost"], 130.0 + 4.8 + 3.0)

    def test_ev_without_charging_demand_has_no_charging_failure(self):
        # 动力类型（电）与本次是否需要充电是两件事：绕行用电耗，但无充电需求不产生缺电损失。
        c = config(n_spaces=0, charging_bays=0, chargers=0)
        sim = Simulation(c, [Arrival(0, 10, True, False, 60, 0)])
        sim.run()
        m = calculate(sim)
        self.assertEqual(sim.visits[0]["cost_kind"], "EV")
        self.assertAlmostEqual(m["cost_items"]["user_time"], 130.0)
        self.assertAlmostEqual(m["cost_items"]["ev_detour_energy"], 1.8)  # 2 km × 0.18 × 5
        self.assertAlmostEqual(m["cost_items"]["ev_external"], 3.0)
        self.assertEqual(m["cost_items"]["ev_residual_trip_loss"], 0.0)  # 没有缺电可言
        self.assertEqual(m["cost_items"]["ice_vehicle_operating"], 0.0)  # 不套燃油公式

    def test_ev_give_up_counts_activity_loss(self):
        # 电车停车失败（无充电需求）且放弃活动：活动损失必须有归属，不能只算时间/电耗
        c = config(n_spaces=0, charging_bays=0, chargers=0,
                   cost={"rejected_disposition": "give_up"})
        sim = Simulation(c, [Arrival(0, 10, True, False, 60, 0)])
        sim.run()
        m = calculate(sim)
        self.assertEqual(sim.visits[0]["disposition"], "give_up")
        self.assertAlmostEqual(m["cost_items"]["ev_activity_loss"], 50.0)
        self.assertEqual(m["cost_items"]["ev_residual_trip_loss"], 0.0)  # 无缺电，不得重复计
        self.assertEqual(m["cost_items"]["ice_activity_loss"], 0.0)
        self.assertAlmostEqual(m["total_cost"], sum(m["cost_items"].values()))
        self.assertTrue(m["cost_complete"])

    def test_ev_activity_loss_missing_parameter_is_null(self):
        c = config(n_spaces=0, charging_bays=0, chargers=0,
                   cost={"rejected_disposition": "give_up", "activity_loss_per_failure": None})
        sim = Simulation(c, [Arrival(0, 10, True, False, 60, 0)])
        sim.run()
        m = calculate(sim)
        self.assertIsNone(m["cost_items"]["ev_activity_loss"])  # 缺参不得计 0
        self.assertIn("activity_loss_per_failure", m["cost_missing_parameters"])
        self.assertIsNone(m["total_cost"])
        self.assertFalse(m["cost_complete"])

    def test_pending_at_horizon_is_not_failure(self):
        c = config(charger_kw=6, feeder_kw=6)
        sim = Simulation(c, [Arrival(0, 10, True, True, 120, 10)])
        sim.run()
        m = calculate(sim)
        self.assertEqual(sim.ledger.failure_count(), 0)
        self.assertAlmostEqual(m["pending_energy_kwh"], 5.0)
        self.assertEqual(m["cost_items"]["ev_residual_trip_loss"], 0.0)
        # 只有运营成本：折旧 2×(1000/24) + 电费 5×3 + 维护 5×0.5 + 按位 20/24 × 2 个带枪位
        self.assertAlmostEqual(m["total_cost"], 2 * 1000.0 / 24.0 + 15.0 + 2.5 + 2 * 20.0 / 24.0)
        self.assertTrue(m["cost_complete"])

    def test_zero_power_is_insufficient_power(self):
        c = config(charger_kw=0)
        sim = Simulation(c, [Arrival(0, 0, True, True, 60, 10)])
        sim.run()
        m = calculate(sim)
        self.assertEqual(sim.visits[0]["charging_failure_reason"], "insufficient_power")
        items = m["cost_items"]
        # 离场仍缺电：后续找替代桩/绕行/步行的额外时间本仿真没有观测，不能隐含为零
        self.assertIsNone(items["user_time"])
        self.assertIsNone(items["ev_detour_energy"])
        self.assertIsNone(items["ev_external"])
        # 缺电量本身有依据（10 kWh × 8），缺电损失仍然可算
        self.assertAlmostEqual(items["ev_residual_trip_loss"], 80.0)
        # 充电失败没有"放弃活动"，不得重复附加活动损失
        self.assertEqual(items["ev_activity_loss"], 0.0)
        for name in ("search_min", "detour_min", "walking_min", "detour_km_per_failure"):
            self.assertIn(name, m["cost_missing_parameters"])
        self.assertIsNone(m["total_cost"])
        self.assertFalse(m["cost_complete"])

    def test_overstay_attribution_not_in_total(self):
        c = config(charger_kw=7)
        sim = Simulation(c, [Arrival(0, 0, True, True, 60, 1)])
        sim.run()
        m = calculate(sim)
        overstay = 60.0 - 60.0 / 7.0
        self.assertAlmostEqual(m["occupancy_minutes"]["overstay_after_complete"], overstay, places=6)
        self.assertIsNone(m["cost_attribution"]["occupancy_impact"])
        # 占桩分钟不进入总成本：只有折旧（2 个带枪位×1000/24）+ 电费 + 维护（按位 × 2 个带枪位）
        self.assertAlmostEqual(m["total_cost"], 2 * 1000.0 / 24.0 + 3.0 + 0.5 + 2 * 20.0 / 24.0)
        self.assertNotIn("occupancy_impact", m["cost_items"])

    def test_no_charging_demand_occupies_connector(self):
        c = config(charger_kw=7)
        sim = Simulation(c, [Arrival(0, 0, True, False, 30, 0)])
        sim.run()
        m = calculate(sim)
        self.assertEqual(m["occupancy_minutes"]["no_charging_demand"], 30.0)
        self.assertEqual(sim.ledger.failure_count(), 0)

    def test_paired_counterfactual_same_traffic(self):
        c = config()
        # 电量必须能在窗口内充满，否则离场缺电的后续成本未知（total=None）
        arrivals = [Arrival(0, 0, True, True, 60, 5), Arrival(1, 5, False, False, 60, 0)]
        base = Simulation(c, arrivals); base.run()
        interrupt = Simulation(c, arrivals); interrupt.run()
        result = paired_occupancy_counterfactual(counterfactual_run(base), counterfactual_run(interrupt))
        self.assertTrue(result["complete"])
        self.assertEqual(result["traffic_hash"], base.traffic_hash)
        self.assertAlmostEqual(result["occupancy_impact"], 0.0)
        for name in ("power_released", "connector_released", "bay_released"):
            self.assertIn(name, result["resources"])

    def test_paired_counterfactual_rejects_different_traffic(self):
        c = config()
        left = Simulation(c, [Arrival(0, 0, True, True, 60, 10)]); left.run()
        right = Simulation(c, [Arrival(0, 0, True, True, 60, 20)]); right.run()
        with self.assertRaises(ValueError):
            paired_occupancy_counterfactual(counterfactual_run(left), counterfactual_run(right))

    def test_traffic_hash_compares_prefix_before_intervention(self):
        head = Arrival(0, 1, False, False, 10, 0)
        left = [head, Arrival(1, 20, True, True, 10, 3)]
        right = [head, Arrival(1, 40, False, False, 1, 0)]
        self.assertNotEqual(traffic_hash(left), traffic_hash(right))
        self.assertEqual(traffic_hash(left, until_min=10), traffic_hash(right, until_min=10))


class ConfigCostTests(unittest.TestCase):
    def test_default_preset_all_null(self):
        c = Config()
        for name, value in c.cost.params().items():
            self.assertIsNone(value, name)
        self.assertIsNone(c.cost.price_year)
        self.assertEqual(c.cost.currency, "TWD")
        self.assertEqual(c.cost.provenance, "unknown_not_calibrated")

    def test_illustrative_preset_is_marked(self):
        for preset in presets():
            parsed = Config.parse(preset["config"])
            if preset["id"] == "illustrative":
                self.assertEqual(parsed.cost.provenance, "illustrative_not_calibrated")
                self.assertIsNotNone(parsed.cost.vot_per_hour)
            else:
                self.assertEqual(parsed.cost.provenance, "unknown_not_calibrated")
                self.assertIsNone(parsed.cost.vot_per_hour)

    def test_v1_cost_keys_rejected(self):
        for key in ("rejection_ice_cost", "rejection_ev_cost", "shortfall_cost_kwh",
                    "electricity_cost_kwh", "charger_cost_day"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                Config.parse({key: 20.0})

    def test_capex_and_depreciation_together_rejected(self):
        with self.assertRaises(ValueError):
            Config.parse({"cost": {"depreciation_annual": 1.0, "depreciation_capex": 1.0}})

    def test_currency_and_year_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            Config.parse({"cost": {"currency": "TWD", "metadata": {"vot_per_hour": {"currency": "EUR"}}}})
        with self.assertRaises(ValueError):
            Config.parse({"cost": {"currency": "TWD", "price_year": 2024,
                                   "metadata": {"vot_per_hour": {"year": 2020}}}})
        with self.assertRaises(ValueError):
            Config.parse({"cost": {"metadata": {"vot_per_hour": {"year": 2024}}}})

    def test_cost_vocabulary_is_v2(self):
        self.assertEqual(COST_MODEL_VERSION, "v2-2026-10-30")
        self.assertEqual(ATTRIBUTION_ITEMS, ("occupancy_impact",))
        self.assertNotIn("complaint", " ".join(COST_ITEMS).lower())
        self.assertNotIn("complaint", " ".join(TRANSFER_ITEMS).lower())
        for item in ATTRIBUTION_ITEMS + TRANSFER_ITEMS:
            self.assertNotIn(item, COST_ITEMS)

    def test_legacy_annotation(self):
        marked = annotate_legacy({"total_cost": 80, "cost_components": {"投诉": 10}})
        self.assertEqual(marked["cost_model_version"], LEGACY_COST_MODEL_VERSION)
        self.assertEqual(marked["total_cost"], 80)
        self.assertIn("cost_components", marked)


class CounterfactualRunnerTests(unittest.TestCase):
    """可运行的占桩配对反事实：同一外生流跑 A=允许占位 / B=及时释放。"""

    def overstay_config(self):
        # 无普通位：release_after_complete 时不得挪车、不得释放（车辆不能凭空消失）
        return config(n_spaces=1, charging_bays=1, chargers=1, charger_kw=7, feeder_kw=7)

    def relocation_config(self):
        # 一个普通位 + 有依据的挪车代价：充斥后挪到普通位并保留原定离场
        return config(n_spaces=2, charging_bays=1, chargers=1, charger_kw=7, feeder_kw=7,
                      policy="strict", cost={"relocation_cost_per_move": 10.0})

    def test_runner_overstay_releases_connector_and_bay(self):
        c = self.relocation_config()
        arrivals = [Arrival(0, 0, True, True, 60, 1),     # EV1 1 kWh 在 60/7≈8.57 min 充满
                    Arrival(1, 20, False, False, 60, 0),  # 油车 strict 下只能停普通位
                    Arrival(2, 30, True, True, 30, 3)]    # EV2 需要充电
        result = run_paired_occupancy_counterfactual(c, "overstay_after_complete", arrivals=arrivals)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["hashes_equal"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["traffic_hash_a"], result["traffic_hash_b"])
        self.assertEqual(result["attribution"]["reason"], "overstay_after_complete")
        # A：EV1 充满后仍占带枪位到 60；油车占普通位；EV2 在 30 被拒
        #    失败 130 + (1.8 绕行 + 12 替代补能) + 3 外部 + 24 剩余 = 170.8
        #    运营 = 1000/24 + 3 + 0.5 + 20/24 = 46.0
        self.assertAlmostEqual(result["cost_a"], 170.8 + 46.0)
        # B：EV1 在 8.5714 min 挪到普通位（保留到 60），油车被拒 130 + 4.8 + 3 = 137.8；
        #    EV2 用上带枪位充 3 kWh，运营 = 1000/24 + 4×3 + 4×0.5 + 20/24 = 56.5；挪车 10
        self.assertAlmostEqual(result["cost_b"], 137.8 + 56.5 + 10.0)
        self.assertAlmostEqual(result["delta_total"], 12.5)
        # A 的 overstay = 60 - 60/7；B 只剩 EV2 充满后的 60 - (30 + 3/7×60)
        self.assertAlmostEqual(result["attribution"]["occupancy_minutes_a"]["overstay_after_complete"],
                               60.0 - 60.0 / 7.0, places=6)
        self.assertAlmostEqual(result["attribution"]["occupancy_minutes_b"]["overstay_after_complete"],
                               60.0 - (30.0 + 3 / 7 * 60.0), places=6)
        # 枪口/带枪位分别记账，都是 A 比 B 多占的分钟数
        self.assertGreater(result["resources"]["connector_released_min"], 0)
        self.assertGreater(result["resources"]["bay_released_min"], 0)
        self.assertAlmostEqual(result["resources"]["connector_released_min"],
                               result["resources"]["bay_released_min"])
        self.assertGreater(result["resources"]["relocation_moves_b"], 0)
        # 挪车并非免费：B 侧把 EV 挪进普通位，普通位占用时间反而增加
        self.assertLess(result["resources"]["ordinary_bay_minutes_delta"], 0)

    def test_runner_no_charging_demand_releases_connector(self):
        c = self.overstay_config()
        arrivals = [Arrival(0, 0, True, False, 60, 0), Arrival(1, 20, True, True, 60, 3)]
        result = run_paired_occupancy_counterfactual(c, "no_charging_demand", arrivals=arrivals)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["attribution"]["reason"], "no_charging_demand")
        # A：无充电需求电车占枪位；需充电电车被拒 → 130 + (1.8+12) + 3 + 24 = 170.8，运营 42.5
        # B：无充电需求电车被拒（电车电耗 130 + 1.8 + 3 + 0 = 134.8，无缺电损失）；
        #    需充电车充到 3 kWh → 运营 53.0
        self.assertAlmostEqual(result["cost_a"], 170.8 + 42.5)
        self.assertAlmostEqual(result["cost_b"], 134.8 + 53.0)
        self.assertAlmostEqual(result["delta_total"], 25.5)
        self.assertAlmostEqual(result["attribution"]["occupancy_minutes_a"]["no_charging_demand"], 60.0)
        self.assertEqual(result["attribution"]["occupancy_minutes_b"]["no_charging_demand"], 0.0)

    def test_runner_rejects_tampered_arrivals(self):
        c = self.overstay_config()
        arrivals = [Arrival(0, 0, True, True, 60, 1), Arrival(1, 20, False, False, 30, 0)]
        tampered = [Arrival(0, 1, True, True, 60, 1), Arrival(1, 20, False, False, 30, 0)]
        result = run_paired_occupancy_counterfactual(c, "overstay_after_complete",
                                                     arrivals=arrivals, arrivals_b=tampered)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["hashes_equal"])
        self.assertIsNone(result["delta_total"])
        self.assertIsNone(result["attribution"]["occupancy_impact"])
        self.assertIn("拒绝", result["note"])

    def test_counterfactual_delta_is_attribution_only(self):
        c = self.overstay_config()
        arrivals = [Arrival(0, 0, True, True, 60, 1), Arrival(1, 20, False, False, 30, 0)]
        result = run_paired_occupancy_counterfactual(c, "overstay_after_complete", arrivals=arrivals)
        # 基准运行的 total 就是分项之和，占桩差值没有被二次计入任何 total
        base = Simulation(c, arrivals); base.run()
        m = calculate(base)
        self.assertAlmostEqual(m["total_cost"], sum(m["cost_items"].values()))
        self.assertIsNone(m["cost_attribution"]["occupancy_impact"])
        self.assertAlmostEqual(result["cost_a"], m["total_cost"])
        self.assertNotIn("occupancy_impact", m["cost_items"])

    def test_unknown_intervention_rejected(self):
        with self.assertRaises(ValueError):
            run_paired_occupancy_counterfactual(self.overstay_config(), "not_a_reason",
                                                arrivals=[Arrival(0, 0, False, False, 10, 0)])



class RelocationAndRealtimeTests(unittest.TestCase):
    """等价回归：挪车反事实（有/无普通位、挪车成本 null）与实时累计截断。"""

    def relocation_setup(self, **cost_changes):
        cost = {"provenance": "illustrative_not_calibrated", **SYNTHETIC}
        cost.update(cost_changes)
        return Config.parse({"n_spaces": 2, "charging_bays": 1, "chargers": 1, "reserve_fixed": 0,
                             "policy": "open", "scenario": "steady", "duration_hours": 1,
                             "arrival_rate_hour": 0, "charger_kw": 7, "feeder_kw": 7,
                             "cost": cost})

    def test_relocation_with_ordinary_bay_keeps_car_until_departure(self):
        sim = Simulation(self.relocation_setup(), [Arrival(0, 0, True, True, 50, 1)],
                         intervention={"release_after_complete": True})
        sim.advance(20)
        # 车辆挪到普通位但仍在场，原定离场时间不变，不得标记离场
        self.assertEqual(list(sim.active), [1])
        self.assertEqual(sim.visits[0]["bay"], 0)  # 原带枪位保留在轨迹里
        self.assertEqual(sim.visits[0]["relocated_to_bay"], 1)
        self.assertAlmostEqual(sim.visits[0]["released_min"], 60 / 7, places=6)
        self.assertAlmostEqual(sim.visits[0]["departure_min"], 50.0)
        self.assertFalse(sim.visits[0]["departed"])
        # 挪车成本参数未知 ⇒ 相关分项与完整成本为 null，并进 missing_parameters
        report = cost_report(sim)
        self.assertIsNone(report["relocation_cost"])
        self.assertIsNone(report["total"])
        self.assertFalse(report["complete"])
        self.assertIn("relocation_cost_per_move", report["missing_parameters"])
        self.assertEqual(report["relocation_count"], 1)
        resources = report["attribution"]["resource_minutes"]
        self.assertAlmostEqual(resources["connector_min"], 60 / 7, places=6)
        self.assertAlmostEqual(resources["ordinary_bay_min"], 20 - 60 / 7, places=6)
        self.assertAlmostEqual(resources["power_kw_min"], 60.0, places=6)  # 1 kWh 在 7 kW 下充了 60/7 min

    def test_relocation_without_ordinary_bay_does_nothing(self):
        sim = Simulation(config(n_spaces=1, charging_bays=1, chargers=1),
                         [Arrival(0, 0, True, True, 50, 1)],
                         intervention={"release_after_complete": True})
        sim.advance(20)
        self.assertEqual(list(sim.active), [0])
        self.assertIsNone(sim.visits[0]["released_min"])
        self.assertEqual(sim.visits[0]["relocation_status"], "blocked_no_ordinary_bay")
        self.assertEqual(cost_report(sim)["relocation_count"], 0)

    def test_runner_without_ordinary_bay_reports_not_implemented(self):
        # 无普通位时挪车干预无法执行：不得把"没发生"报成 delta=0
        c = config(n_spaces=1, charging_bays=1, chargers=1, charger_kw=7, feeder_kw=7)
        arrivals = [Arrival(0, 0, True, True, 60, 1), Arrival(1, 20, False, False, 30, 0)]
        result = run_paired_occupancy_counterfactual(c, "overstay_after_complete",
                                                     arrivals=arrivals)
        self.assertTrue(result["accepted"])
        self.assertIsNone(result["delta_total"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["not_implemented"], "no_ordinary_bay")
        self.assertIn("无法计算", result["note"])
        self.assertGreater(result["resources"]["relocation_blocked_b"], 0)
        self.assertEqual(result["resources"]["relocation_moves_b"], 0)

    def test_relocation_cost_known_is_included_in_total(self):
        sim = Simulation(self.relocation_setup(relocation_cost_per_move=10.0),
                         [Arrival(0, 0, True, True, 50, 1)],
                         intervention={"release_after_complete": True})
        sim.run()
        report = cost_report(sim)
        self.assertTrue(report["complete"])
        self.assertAlmostEqual(report["relocation_cost"], 10.0)
        self.assertAlmostEqual(report["total"], sum(report["items"].values()) + 10.0)
        self.assertNotIn("relocation_cost_per_move", report["missing_parameters"])
        # chargers=1 ⇒ 按位维护 = 1×(60/1440)×20，不是全场总额
        self.assertAlmostEqual(report["items"]["operator_maintenance"], 0.5 + 20.0 / 24.0)

    def test_realtime_occupancy_is_truncated_to_now(self):
        sim = Simulation(config(n_spaces=1, charging_bays=1, chargers=1),
                         [Arrival(0, 0, True, False, 120, 0)])
        sim.advance(1)
        report = cost_report(sim)
        self.assertEqual(report["attribution"]["occupancy_minutes_by_reason"]["no_charging_demand"], 1.0)
        self.assertAlmostEqual(report["transfers"]["parking_fee"], 40.0 / 60.0)
        # 预计最终值单独列为 projected：不得混进实时字段
        self.assertEqual(report["projected"]["occupancy_minutes_by_reason"]["no_charging_demand"], 60.0)
        self.assertAlmostEqual(report["projected"]["transfers"]["parking_fee"], 40.0)

    def test_departed_shortfall_followup_is_unknown(self):
        sim = Simulation(config(charger_kw=0), [Arrival(0, 0, True, True, 30, 3)])
        sim.run()
        report = cost_report(sim)
        self.assertIsNone(report["items"]["user_time"])
        self.assertIsNone(report["items"]["ev_detour_energy"])
        self.assertIsNone(report["total"])
        for name in ("search_min", "detour_min", "walking_min", "detour_km_per_failure"):
            self.assertIn(name, report["missing_parameters"])

    def test_maintenance_scales_with_equipped_bays(self):
        small = Simulation(config(n_spaces=2, charging_bays=1, chargers=1), [])
        large = Simulation(config(n_spaces=3, charging_bays=2, chargers=2), [])
        small.run(); large.run()
        self.assertAlmostEqual(cost_report(large)["items"]["operator_maintenance"],
                               2 * cost_report(small)["items"]["operator_maintenance"])

    def test_zero_depreciation_life_is_rejected(self):
        with self.assertRaises(ValueError):
            Config.parse({"cost": {"depreciation_capex": 100.0, "depreciation_life_years": 0}})
        Config.parse({"cost": {"depreciation_capex": 100.0, "depreciation_life_years": 5}})

    def test_ev_rejection_without_charge_need_has_no_shortfall_loss(self):
        sim = Simulation(config(n_spaces=0, charging_bays=0, chargers=0),
                         [Arrival(0, 0, True, False, 30, 0)])
        sim.run()
        report = cost_report(sim)
        self.assertEqual(sim.visits[0]["cost_kind"], "EV")
        self.assertAlmostEqual(report["items"]["ev_detour_energy"], 1.8)
        self.assertEqual(report["items"]["ev_residual_trip_loss"], 0.0)
        self.assertEqual(report["items"]["ice_vehicle_operating"], 0.0)

# --------------------------------------------------------------------------- #
# R2-A（2026-10-31）：设施成本唯一入口 facility_cost 与三类占位口径
# --------------------------------------------------------------------------- #
R2_CAPEX = 116792.62
R2_LIFE_YEARS = 10.0
R2_CAPITAL_PER_DAY = R2_CAPEX / R2_LIFE_YEARS / 365.0
R2_MAINTENANCE_PER_BAY_DAY = 43.29969863013699
# research/integer_allocation_20261031/cost_scenario.json 的真实情景设备参数（无站级固定成本）
FACILITY_PARAMS = {
    "depreciation_capex": R2_CAPEX, "depreciation_life_years": R2_LIFE_YEARS,
    "maintenance_per_bay_day": R2_MAINTENANCE_PER_BAY_DAY,
    "electricity_price_per_kwh": 4.08,
}


class FacilityCostEntryTests(unittest.TestCase):
    """R2-D1：设施成本只有 facility_cost 一个权威入口；零设备与缺参分开。"""

    def test_k_zero_is_zero_and_not_applicable(self):
        result = cost_module.facility_cost(0, FACILITY_PARAMS, days=1.0)
        self.assertEqual(result["items"]["device_capital"], 0.0)
        self.assertEqual(result["items"]["device_maintenance"], 0.0)
        self.assertEqual(result["value"], 0.0)
        self.assertEqual(result["missing"], [])
        self.assertIn("device_capital", result["not_applicable"])
        self.assertIn("device_maintenance", result["not_applicable"])
        # 缺参也不影响 k=0：零设备没有资本/维护，不是"未知"
        bare = cost_module.facility_cost(0, {}, days=1.0)
        self.assertEqual(bare["value"], 0.0)
        self.assertEqual(bare["missing"], [])

    def test_device_cost_scales_with_k_and_days(self):
        for k, days in ((1, 1.0), (2, 1.0), (1, 0.5), (2, 1.5)):
            report = cost_module.facility_cost(k, FACILITY_PARAMS, days=days)
            self.assertAlmostEqual(report["items"]["device_capital"],
                                   k * R2_CAPITAL_PER_DAY * days, places=9)
            self.assertAlmostEqual(report["items"]["device_maintenance"],
                                   k * R2_MAINTENANCE_PER_BAY_DAY * days, places=9)
            self.assertAlmostEqual(report["value"],
                                   k * (R2_CAPITAL_PER_DAY + R2_MAINTENANCE_PER_BAY_DAY) * days, places=9)
            self.assertEqual(report["missing"], [])
            self.assertEqual(report["not_applicable"], [])

    def test_facility_fixed_is_separate_and_prorated(self):
        params = dict(FACILITY_PARAMS, facility_fixed_cost_per_day=288.0)
        report = cost_module.facility_cost(2, params, days=0.25)
        self.assertAlmostEqual(report["items"]["facility_fixed"], 72.0)
        self.assertAlmostEqual(report["items"]["device_capital"], 2 * R2_CAPITAL_PER_DAY * 0.25)
        self.assertAlmostEqual(report["value"],
                               2 * (R2_CAPITAL_PER_DAY + R2_MAINTENANCE_PER_BAY_DAY) * 0.25 + 72.0)

    def test_facility_fixed_absent_vs_explicit_none(self):
        # 未提供键 = 本次核算不含站级固定成本（旧成本曲线口径）；显式 None 才是"未知"。
        absent = cost_module.facility_cost(1, FACILITY_PARAMS, days=1.0)
        self.assertEqual(absent["items"]["facility_fixed"], 0.0)
        self.assertNotIn("facility_fixed_cost_per_day", absent["missing"])
        unknown = cost_module.facility_cost(
            1, dict(FACILITY_PARAMS, facility_fixed_cost_per_day=None), days=1.0)
        self.assertIsNone(unknown["items"]["facility_fixed"])
        self.assertIsNone(unknown["value"])
        self.assertIn("facility_fixed_cost_per_day", unknown["missing"])

    def test_missing_device_parameters_are_none_not_zero(self):
        no_capital = cost_module.facility_cost(1, {"maintenance_per_bay_day": 20.0}, days=1.0)
        self.assertIsNone(no_capital["items"]["device_capital"])
        self.assertIsNone(no_capital["value"])
        self.assertIn("depreciation_annual", no_capital["missing"])
        no_maintenance = cost_module.facility_cost(
            1, {"depreciation_capex": 3650000.0, "depreciation_life_years": 10.0}, days=1.0)
        self.assertIsNone(no_maintenance["items"]["device_maintenance"])
        self.assertIsNone(no_maintenance["value"])
        self.assertIn("maintenance_per_bay_day", no_maintenance["missing"])

    def test_depreciation_annual_alternative_matches_capex(self):
        annual = cost_module.facility_cost(
            2, {"depreciation_annual": 365000.0, "maintenance_per_bay_day": 20.0}, days=0.5)
        capex = cost_module.facility_cost(
            2, {"depreciation_capex": 3650000.0, "depreciation_life_years": 10.0,
                "maintenance_per_bay_day": 20.0}, days=0.5)
        self.assertAlmostEqual(annual["value"], capex["value"])
        self.assertAlmostEqual(annual["items"]["device_capital"], 2 * 1000.0 * 0.5)

    def test_invalid_inputs_rejected(self):
        for k in (-1, 1.0, True):
            with self.subTest(k=k), self.assertRaises(ValueError):
                cost_module.facility_cost(k, FACILITY_PARAMS, days=1.0)
        for days in (-0.1, float("nan"), float("inf"), "1"):
            with self.subTest(days=days), self.assertRaises(ValueError):
                cost_module.facility_cost(1, FACILITY_PARAMS, days=days)
        with self.assertRaises(ValueError):
            cost_module.facility_cost(
                1, {"depreciation_annual": 1.0, "depreciation_capex": 1.0}, days=1.0)


class LedgerFacilityCostTests(unittest.TestCase):
    """R2-D1：summary 资本折旧乘设备数，窗口口径与折算日口径并列，且不得重复相乘。"""

    def test_capital_scales_with_equipped_bays_and_window(self):
        ledger = CostLedger(SYNTHETIC)
        daily = 365000.0 / 365.0
        for k, minutes in ((0, 1440.0), (1, 1440.0), (2, 1440.0), (1, 720.0), (2, 720.0), (2, 2160.0)):
            report = ledger.summary(elapsed_min=minutes, chargers=k)
            days = minutes / 1440.0
            per_day = report["daily_equivalent"]["operator_capital_depreciation_per_day"]
            item = report["items"]["operator_capital_depreciation"]
            self.assertAlmostEqual(per_day, k * daily, places=9)
            self.assertAlmostEqual(item, k * daily * days, places=9)
            self.assertAlmostEqual(item, per_day * days, places=9)

    def test_maintenance_not_double_multiplied(self):
        report = CostLedger(SYNTHETIC).summary(elapsed_min=1440.0, delivered_kwh=0.0, chargers=2)
        self.assertAlmostEqual(report["items"]["operator_maintenance"], 2 * 20.0)
        self.assertAlmostEqual(report["daily_equivalent"]["operator_maintenance_per_day"], 2 * 20.0)
        self.assertNotAlmostEqual(report["items"]["operator_maintenance"], 2 * 2 * 20.0)

    def test_facility_fixed_item_and_flag(self):
        ledger = CostLedger(dict(SYNTHETIC, facility_fixed_cost_per_day=120.0))
        report = ledger.summary(elapsed_min=720.0, chargers=2)
        self.assertAlmostEqual(report["items"]["operator_facility_fixed"], 60.0)
        self.assertTrue(report["facility_cost"]["facility_fixed_included"])
        self.assertAlmostEqual(report["daily_equivalent"]["operator_facility_fixed_per_day"], 120.0)
        plain = CostLedger(SYNTHETIC).summary(elapsed_min=720.0, chargers=2)
        self.assertEqual(plain["items"]["operator_facility_fixed"], 0.0)
        self.assertFalse(plain["facility_cost"]["facility_fixed_included"])

    def test_facility_cost_block_matches_unique_entry(self):
        report = CostLedger(SYNTHETIC).summary(elapsed_min=720.0, chargers=2)
        block = report["facility_cost"]
        self.assertEqual(block["source"], "costs.facility_cost")
        self.assertEqual(block["k"], 2)
        self.assertAlmostEqual(block["days"], 0.5)
        expected = cost_module.facility_cost(2, SYNTHETIC, days=0.5)
        self.assertEqual(block["items"], expected["items"])
        self.assertEqual(block["missing"], list(expected["missing"]))
        self.assertEqual(block["not_applicable"], list(expected["not_applicable"]))

    def test_cost_report_carries_facility_block(self):
        sim = Simulation(config(), [])
        sim.run()
        report = cost_report(sim)
        self.assertEqual(report["facility_cost"]["source"], "costs.facility_cost")
        self.assertEqual(report["facility_cost"]["k"], 2)
        self.assertIn("device_capital", report["facility_cost"]["items"])
        self.assertAlmostEqual(report["items"]["operator_capital_depreciation"], 2 * (1000.0 / 24.0))
        self.assertAlmostEqual(report["daily_equivalent"]["operator_capital_depreciation_per_day"], 2 * 1000.0)


class OccupancyAttributionTests(unittest.TestCase):
    """R2-D2：三类占位严格分列；旧键 no_charging_demand 保留 deprecated 迁移映射。"""

    def pi1_ice_config(self):
        return config(policy="full_open_ice_first", n_spaces=2, charging_bays=1, chargers=1)

    def test_ice_blocking_connector_is_separate_from_no_charging_demand(self):
        sim = Simulation(self.pi1_ice_config(),
                         [Arrival(0, 0.0, False, False, 10.0, 0.0),
                          Arrival(1, 1.0, False, False, 10.0, 0.0)])
        sim.run()
        minutes = cost_module.occupancy_minutes(sim)
        self.assertAlmostEqual(minutes["ice_blocking_connector"], 10.0)
        self.assertEqual(minutes["no_charging_demand"], 0.0)
        self.assertEqual(minutes["overstay_after_complete"], 0.0)
        # 与 rules.type_occupancy 权威台账一致
        self.assertAlmostEqual(minutes["ice_blocking_connector"],
                               sim.type_occupancy()["metrics"]["ice_blocking_connector_min"])

    def test_pi0_ice_rejected_never_blocks_connector(self):
        sim = Simulation(config(policy="dedicated_by_type", n_spaces=2, charging_bays=1, chargers=1),
                         [Arrival(0, 0.0, False, False, 10.0, 0.0),
                          Arrival(1, 1.0, False, False, 10.0, 0.0)])
        sim.run()
        minutes = cost_module.occupancy_minutes(sim)
        self.assertEqual(minutes["ice_blocking_connector"], 0.0)
        self.assertEqual(minutes["no_charging_demand"], 0.0)

    def test_ev_without_charging_demand_is_ev_only(self):
        sim = Simulation(config(charger_kw=7), [Arrival(0, 0.0, True, False, 30.0, 0.0)])
        sim.run()
        minutes = cost_module.occupancy_minutes(sim)
        self.assertEqual(minutes["no_charging_demand"], 30.0)
        self.assertEqual(minutes["ice_blocking_connector"], 0.0)

    def test_overstay_strictly_after_completion(self):
        sim = Simulation(config(charger_kw=7), [Arrival(0, 0.0, True, True, 60.0, 1.0)])
        sim.run()
        minutes = cost_module.occupancy_minutes(sim)
        self.assertAlmostEqual(minutes["overstay_after_complete"], 60.0 - 60.0 / 7.0, places=6)
        self.assertEqual(minutes["no_charging_demand"], 0.0)
        self.assertEqual(minutes["ice_blocking_connector"], 0.0)

    def test_relocation_ends_connector_occupancy(self):
        c = config(n_spaces=2, charging_bays=1, chargers=1, charger_kw=7, feeder_kw=7, policy="strict",
                   cost={"relocation_cost_per_move": 10.0})
        sim = Simulation(c, [Arrival(0, 0.0, True, True, 50.0, 1.0)],
                         intervention={"release_after_complete": True})
        sim.run()
        minutes = cost_module.occupancy_minutes(sim)
        self.assertAlmostEqual(sim.visits[0]["released_min"], 60.0 / 7.0, places=6)
        self.assertEqual(minutes["overstay_after_complete"], 0.0)  # 释放即结束带枪位占用
        resources = cost_module.resource_minutes(sim)
        self.assertAlmostEqual(resources["connector_min"], 60.0 / 7.0, places=6)

    def test_legacy_key_mapping_reconstructs_old_mixed_value(self):
        minutes = {"no_charging_demand": 4.0, "ice_blocking_connector": 6.0}
        self.assertAlmostEqual(cost_module.legacy_no_charging_demand(minutes), 10.0)
        mapping = cost_module.DEPRECATED_OCCUPANCY_KEY_MAP["no_charging_demand"]
        self.assertTrue(mapping["deprecated"])
        self.assertEqual(tuple(mapping["replacement"]), ("no_charging_demand", "ice_blocking_connector"))
        self.assertIn("迁移", cost_module.occupancy_minutes.__doc__)

    def test_attribution_vocabulary_covers_ice_blocking(self):
        self.assertIn("ice_blocking_connector", cost_module.OCCUPANCY_REASONS)


if __name__ == "__main__":
    unittest.main()
