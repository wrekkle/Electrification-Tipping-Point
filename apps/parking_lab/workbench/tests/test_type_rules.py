"""阶段四规则引擎、隐藏信息边界与三类占位计量的测试。

覆盖：π0/π1/π2/protected_quota（π3）准入行为差异、protected_quota 的配额端点等价
（m=0≡π1、m=k≡π0）与参数校验、legacy strict 的隐藏意愿泄漏只作历史回归、
同一可观测输入下不同 needs_charge 真值得到相同车位序列、零桩/零需求/期初/期末删失边界、
同外生流不同 k 重放的 traffic_hash 一致性，以及三类占位分钟逐车/逐事件账本。
"""
from dataclasses import fields, replace
import inspect
import math
import unittest

from apps.parking_lab.workbench import rules
from apps.parking_lab.workbench.config import (ALL_POLICIES, LEGACY_POLICIES, POLICIES, RULE_POLICIES,
                                               Config)
from apps.parking_lab.workbench.costs import traffic_hash
from apps.parking_lab.workbench.demand import Arrival, generate, stream_hash
from apps.parking_lab.workbench.prediction import Learner, ObservableOccupancy
from apps.parking_lab.workbench.simulation import Simulation


def config(**changes):
    raw = {"n_spaces": 2, "charging_bays": 1, "chargers": 1, "reserve_fixed": 0,
           "scenario": "steady", "duration_hours": 1, "arrival_rate_hour": 0, "seed": 42}
    raw.update(changes)
    return Config.parse(raw)


def run(arrivals, policy="dedicated_by_type", **changes):
    cfg = replace(config(**changes), policy=policy)
    sim = Simulation(cfg, arrivals)
    sim.run()
    return sim


def run_config(cfg, arrivals, policy):
    sim = Simulation(replace(cfg, policy=policy), arrivals)
    sim.run()
    return sim


def sequence(sim):
    return [(visit["vehicle_id"], visit["bay"], visit["admitted"]) for visit in sim.visits]


class HiddenInformationBoundaryTests(unittest.TestCase):
    """控制器只能看见可观测状态：签名里没有隐藏意愿，也没有未来信息。"""

    def test_observable_state_has_no_hidden_fields(self):
        names = {f.name for f in fields(rules.ObservableState)}
        for hidden in ("needs_charge", "energy_kwh", "soc", "dwell_min", "departure_min",
                       "future_arrivals", "arrivals"):
            self.assertNotIn(hidden, names)
        self.assertEqual(names, {"time_min", "is_ev", "free_bays", "n_spaces", "charging_bays",
                                 "chargers", "arrival_rate_per_hour", "p_ev",
                                 "p_charge_given_ev", "mean_ice_occupancy_min",
                                 "mean_connector_minutes_per_ev", "observed_departures",
                                 "ice_charging_bays"})
        state = rules.ObservableState(time_min=0, is_ev=True, free_bays=(0,), n_spaces=2,
                                      charging_bays=1, chargers=1, arrival_rate_per_hour=20,
                                      p_ev=.5, p_charge_given_ev=.5)
        # 油车占用计数是可观测状态（调用方按已放行车辆类型/车位累计），默认 None 表示未接线。
        self.assertIsNone(state.ice_charging_bays)
        with self.assertRaises(TypeError):
            rules.ObservableState(**{**state.__dict__, "needs_charge": True})
        with self.assertRaises(TypeError):
            rules.decide(state, "dedicated_by_type", needs_charge=True)

    def test_learner_never_receives_hidden_will(self):
        parameters = list(inspect.signature(Learner.observe).parameters)
        self.assertEqual(parameters, ["self", "is_ev"])
        self.assertEqual(list(inspect.signature(Learner.observe_charging_start).parameters), ["self"])

    def test_charging_start_is_observed_after_the_fact(self):
        # 0 时刻到达并停在带枪位：到达当时学习器还没有"充电开始"事件，下一段真正交付电量后才记录。
        cfg = replace(config(charger_kw=6, feeder_kw=6), policy="dedicated_by_type")
        sim = Simulation(cfg, [Arrival(0, 0, True, True, 30, 1), Arrival(1, 40, False, False, 5, 0)])
        sim.advance(0)
        self.assertEqual(sim.learner.charge_starts, 0.0)
        self.assertIsNone(sim.visits[0]["charge_start_min"])
        sim.advance(1)
        self.assertAlmostEqual(sim.learner.charge_starts, 1.0)
        self.assertAlmostEqual(sim.visits[0]["charge_start_min"], 0.0)
        sim.run()
        self.assertEqual(sim.learner.seen, 2)
        self.assertTrue(all(score["issued_at_min"] <= score["observed_at_min"] for score in sim.scores))

    def test_hidden_truth_without_observable_consequence_never_changes_predictions(self):
        """needs_charge 真值不同但没有可观察后果（无桩、永不充电开始）⇒ 预测与决策完全一致。"""

        def flow(needs_charge):
            return [Arrival(0, 0, True, needs_charge, 20, 0), Arrival(1, 1, False, False, 20, 0),
                    Arrival(2, 2, True, needs_charge, 20, 0)]

        left = run(flow(True), "dedicated_by_type", n_spaces=2, charging_bays=0, chargers=0)
        right = run(flow(False), "dedicated_by_type", n_spaces=2, charging_bays=0, chargers=0)
        self.assertEqual(left.learner.charge_starts, 0.0)
        self.assertEqual(right.learner.charge_starts, 0.0)
        self.assertEqual(sequence(left), sequence(right))
        self.assertEqual(left.issued, right.issued)             # 预测只由可见事件决定
        self.assertEqual([s["p_ev"] for s in left.scores], [s["p_ev"] for s in right.scores])
        self.assertTrue(all(s["is_ev"] is not None for s in left.scores))

    def test_prediction_changes_only_after_observed_charging_start(self):
        """同可观察前缀、只有 needs_charge 真值不同：充电开始被观察到之前预测必须相同。"""

        def flow(needs_charge, energy):
            return [Arrival(0, 0, True, needs_charge, 30, energy),
                    Arrival(1, 0, False, False, 30, 0),
                    Arrival(2, 5, False, False, 30, 0),
                    Arrival(3, 10, False, False, 30, 0)]

        cfg = dict(n_spaces=3, charging_bays=2, chargers=2, charger_kw=7, feeder_kw=14)
        left = run(flow(True, 10.0), "predictive_shared_ice_first", **cfg)
        right = run(flow(False, 0.0), "predictive_shared_ice_first", **cfg)
        self.assertGreater(left.learner.charge_starts, right.learner.charge_starts)

        def gate_demands(sim):
            return [(v["time_min"], v["admission"]["detail"]["predicted_demand"])
                    for v in sim.visits if "predicted_demand" in v["admission"]["detail"]]

        left_demands, right_demands = gate_demands(left), gate_demands(right)
        self.assertGreaterEqual(len(left_demands), 3)            # 0 时刻（充电开始前）+ 之后两次
        self.assertEqual(left_demands[0][1], right_demands[0][1])   # 充电开始前：预测相同
        later = [i for i, (t, _) in enumerate(left_demands) if t > left_demands[0][0]]
        self.assertTrue(later)
        for i in later:
            self.assertGreater(left_demands[i][1], right_demands[i][1])

    def test_identical_observable_prefix_same_decisions_and_forecasts(self):
        """同可观察前缀、不同隐藏未来（以及不同 needs_charge 未来）⇒ 前缀内决策与预测相同；
        每个决策的预测都能用"截断到该时刻的同前缀仿真"复算出来（没有偷看未来）。"""
        cfg = dict(n_spaces=6, charging_bays=5, chargers=5, charger_kw=7, feeder_kw=35)
        prefix = [Arrival(0, 0, True, True, 60, 10), Arrival(1, 1, False, False, 60, 0),
                  Arrival(2, 2, True, False, 60, 0), Arrival(3, 3, True, True, 60, 3),
                  Arrival(4, 4, False, False, 60, 0)]
        future_a = [Arrival(5, 30, True, True, 60, 10), Arrival(6, 40, False, False, 60, 0)]
        future_b = [Arrival(5, 30, False, False, 60, 0), Arrival(6, 40, True, False, 60, 0)]
        left = run(prefix + future_a, "predictive_shared_ice_first", **cfg)
        right = run(prefix + future_b, "predictive_shared_ice_first", **cfg)

        def prefix_rows(sim):
            return [(v["vehicle_id"], v["bay"], v["admitted"], v["admission"]["reason"])
                    for v in sim.visits if v["time_min"] <= 10]

        self.assertEqual(prefix_rows(left), prefix_rows(right))
        self.assertEqual(len(prefix_rows(left)), len(prefix))
        # 前缀内确实经过预测闸门（不是"闸门没触发所以相同"）。
        gate = [v for v in left.visits if v["time_min"] <= 10 and not v["is_ev"]
                and v["admission"]["detail"]["free_ordinary_bays"] == 0
                and v["admission"]["detail"]["free_charging_bays"] > 0
                and "predicted_demand" in v["admission"]["detail"]]
        self.assertTrue(gate)
        # 逐步截断复算：决策用的预测只来自此前已观测的事件。
        for visit in left.visits:
            detail = visit["admission"]["detail"]
            if visit["time_min"] > 10 or "predicted_demand" not in detail:
                continue
            cutoff = visit["time_min"]
            early = Simulation(left.config,
                               tuple(a for a in (prefix + future_a) if a.time_min < cutoff))
            early.advance(cutoff)
            forecast = early.learner.forecast()
            recomputed = (forecast["arrival_rate_hour"] / 60 * forecast["p_ev"]
                          * forecast["p_charge_given_ev"] * detail["effective_window_min"])
            self.assertAlmostEqual(detail["predicted_demand"], recomputed, places=9)

    def test_hidden_future_dwell_energy_and_needs_do_not_change_prefix_decisions(self):
        """前缀相同、未来车辆的停留/能量/充电意愿不同 ⇒ 前缀内决策与预测不变。"""
        cfg = dict(n_spaces=6, charging_bays=5, chargers=5, charger_kw=7, feeder_kw=35)
        prefix = [Arrival(0, 0, True, True, 60, 10), Arrival(1, 1, False, False, 60, 0),
                  Arrival(2, 2, True, False, 60, 0)]
        future_a = [Arrival(3, 30, True, True, 240, 40), Arrival(4, 40, False, False, 240, 0)]
        future_b = [Arrival(3, 30, True, False, 5, 0), Arrival(4, 40, False, False, 5, 0)]
        left = run(prefix + future_a, "predictive_shared_ice_first", **cfg)
        right = run(prefix + future_b, "predictive_shared_ice_first", **cfg)

        def prefix_rows(sim):
            return [(v["vehicle_id"], v["time_min"], v["bay"], v["admitted"],
                     v["admission"]["reason"])
                    for v in sim.visits if v["time_min"] <= 10]

        self.assertEqual(prefix_rows(left), prefix_rows(right))
        self.assertEqual(len(prefix_rows(left)), len(prefix))
        # 未来车辆的隐藏字段只影响自己的到达后行为，不进入学习器/车窗预测。
        self.assertEqual([s["p_ev"] for s in left.scores], [s["p_ev"] for s in right.scores])
        self.assertEqual([s["lower_min"] for s in left.scores],
                         [s["lower_min"] for s in right.scores])

    def test_legacy_strict_is_labelled_and_only_kept_for_replay(self):
        self.assertEqual(LEGACY_POLICIES["strict"], "严格分区（legacy，按隐藏意愿分区，仅历史复现）")
        self.assertEqual(POLICIES, LEGACY_POLICIES)              # 历史对比集合不变
        # config.py 的 RULE_POLICIES 由 Lead 接线 protected_quota（本轮不改 config.py）；
        # 三种既有规则必须有文本标签，新规则名只要在正式规则集合里即可（接线后自然相等）。
        self.assertIn("protected_quota", rules.RULE_NAMES)
        self.assertTrue(set(RULE_POLICIES) <= set(rules.RULE_NAMES))
        for name in ("dedicated_by_type", "full_open_ice_first", "predictive_shared_ice_first"):
            self.assertIn(name, RULE_POLICIES)
        self.assertEqual(set(ALL_POLICIES), set(RULE_POLICIES) | set(LEGACY_POLICIES))
        self.assertEqual(config().policy, "dedicated_by_type")    # 默认正式规则是 π0
        self.assertIn("legacy", LEGACY_POLICIES["strict"])
        sim = run([], "strict")
        self.assertTrue(sim.snapshot()["policy_legacy"])
        self.assertIsNone(sim.snapshot()["policy_rule"])
        self.assertIn("legacy", sim.snapshot()["policy_name"])

    def test_old_configs_still_parse(self):
        self.assertEqual(Config.parse({"duration_hours": 1}).policy, "dedicated_by_type")
        for name in LEGACY_POLICIES:
            self.assertEqual(Config.parse({"policy": name}).policy, name)
        with self.assertRaises(ValueError):
            Config.parse({"policy": "unknown"})
        for bad in ({"ice_share_forecast_window_min": 0}, {"ice_share_forecast_window_min": 241},
                    {"ice_share_free_bay_margin": -1}, {"ice_share_free_bay_margin": 2001}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Config.parse(bad)
        # protected_quota 的正式标签由 Lead 在 config.py 接线；接线前后两种状态都必须自洽。
        if "protected_quota" in RULE_POLICIES:
            self.assertEqual(Config.parse({"policy": "protected_quota"}).policy, "protected_quota")
        else:
            with self.assertRaises(ValueError):
                Config.parse({"policy": "protected_quota"})


class RuleEngineUnitTests(unittest.TestCase):
    """规则函数在受控可观测状态下的行为（不依赖随机车流）。"""

    def state(self, **changes):
        raw = {"time_min": 5.0, "is_ev": True, "free_bays": (0, 2, 3), "n_spaces": 4,
               "charging_bays": 3, "chargers": 1, "arrival_rate_per_hour": 60.0,
               "p_ev": 0.5, "p_charge_given_ev": 0.5}
        raw.update(changes)
        return rules.ObservableState(**raw)

    def test_pi0_ev_prefers_connector_then_designated_then_ordinary(self):
        self.assertEqual(rules.decide(self.state(), "dedicated_by_type").bay, 0)
        only_reserved = self.state(free_bays=(2, 3))
        self.assertEqual(rules.decide(only_reserved, "dedicated_by_type").bay, 2)
        only_ordinary = self.state(free_bays=(3,))
        self.assertEqual(rules.decide(only_ordinary, "dedicated_by_type").bay, 3)

    def test_pi0_ice_is_ordinary_only(self):
        state = self.state(is_ev=False)
        decision = rules.decide(state, "dedicated_by_type")
        self.assertEqual(decision.bay, 3)
        self.assertEqual(decision.reason, "ice_ordinary_only")
        no_ordinary = self.state(is_ev=False, free_bays=(0, 2))
        rejected = rules.decide(no_ordinary, "dedicated_by_type")
        self.assertIsNone(rejected.bay)
        self.assertEqual(rejected.reason, "rejected_no_ordinary_bay")

    def test_pi1_ice_uses_charging_bays_only_when_ordinary_full(self):
        ordinary_free = self.state(is_ev=False, free_bays=(0, 3))
        self.assertEqual(rules.decide(ordinary_free, "full_open_ice_first").bay, 3)
        shared = rules.decide(self.state(is_ev=False, free_bays=(0, 2)), "full_open_ice_first")
        self.assertTrue(shared.bay < 3)
        self.assertEqual(shared.reason, "ice_shared_charging_bays")
        empty = rules.decide(self.state(is_ev=False, free_bays=()), "full_open_ice_first")
        self.assertIsNone(empty.bay)
        self.assertEqual(empty.reason, "rejected_no_free_bay")

    def test_pi2_gate_uses_prediction_threshold_and_window(self):
        # 5 个空闲充电位 ⇒ 扣除本次这辆油车后可保护 4 个；预计充电到达 24.7/60*0.5*0.5*30=3.0875。
        state = self.state(is_ev=False, free_bays=(0, 1, 2, 3, 4), n_spaces=9,
                           charging_bays=8, chargers=8, arrival_rate_per_hour=24.7)
        low = rules.decide(state, "predictive_shared_ice_first", safety_margin=0.0)
        self.assertEqual(low.bay, 0)
        self.assertEqual(low.reason, "ice_shared_by_forecast")
        self.assertAlmostEqual(low.detail["predicted_demand"], 24.7 / 60 * .5 * .5 * 30, places=9)
        self.assertEqual(low.detail["predicted_demand"],
                         low.detail["prediction_detail"]["value"])
        self.assertEqual(low.detail["prediction_unit"], "events_in_window")
        self.assertAlmostEqual(low.detail["free_charging_bays"], 5)
        self.assertAlmostEqual(low.detail["usable_after_this_ice"], 4)   # 扣除本次油车占用
        self.assertAlmostEqual(low.detail["forecast_slack_bays"], 4 - 3.0875, places=9)
        self.assertGreaterEqual(low.detail["forecast_slack_bays"], low.detail["safety_margin"])
        # 默认余量 1.0 下同一状态被拒：扣掉本次油车后余量不足。
        default_margin = rules.decide(state, "predictive_shared_ice_first")
        self.assertIsNone(default_margin.bay)
        self.assertEqual(default_margin.reason, "rejected_ice_reserved_for_ev_forecast")
        high = rules.decide(replace(state, p_charge_given_ev=1.0), "predictive_shared_ice_first",
                            safety_margin=0.0)
        self.assertIsNone(high.bay)
        self.assertEqual(high.reason, "rejected_ice_reserved_for_ev_forecast")
        self.assertLess(high.detail["forecast_slack_bays"], high.detail["safety_margin"])
        # 窗口与阈值可配置：同一状态换窗口/余量即可翻转决定，且明细写明所用参数。
        narrow = rules.decide(replace(state, p_charge_given_ev=1.0), "predictive_shared_ice_first",
                              window_min=1.0)
        self.assertEqual(narrow.bay, 0)
        self.assertEqual(narrow.detail["window_min"], 1.0)
        large_margin = rules.decide(state, "predictive_shared_ice_first", safety_margin=4.0)
        self.assertIsNone(large_margin.bay)
        # 普通位有空时不做预测闸门（"普通位不足时"才放行判断）。
        ordinary_free = rules.decide(self.state(is_ev=False, free_bays=(3,)),
                                     "predictive_shared_ice_first")
        self.assertEqual(ordinary_free.bay, 3)
        self.assertEqual(ordinary_free.reason, "ice_ordinary_first")

    def test_pi2_gate_deducts_the_ice_admitted_now(self):
        # 贪心反例：放行前空闲 2 个充电位、预计需求 1.2、余量 0。不扣除本次占用会得到
        # 2-1.2=0.8≥0 而放行，实际放行后只剩 1 个位，不够 1.2 ⇒ 必须拒绝。
        state = self.state(is_ev=False, free_bays=(0, 1), n_spaces=9, charging_bays=8,
                           chargers=8, arrival_rate_per_hour=9.6)
        rejected = rules.decide(state, "predictive_shared_ice_first", safety_margin=0.0)
        self.assertIsNone(rejected.bay)
        self.assertEqual(rejected.reason, "rejected_ice_reserved_for_ev_forecast")
        self.assertAlmostEqual(rejected.detail["predicted_demand"], 1.2, places=9)
        self.assertAlmostEqual(rejected.detail["usable_after_this_ice"], 1.0)
        self.assertLess(rejected.detail["forecast_slack_bays"], 0.0)
        # 恰好够：需求 1.0（到达率 8/h）时扣完只剩 1 位，余量 0 ⇒ 放行。
        exact = rules.decide(replace(state, arrival_rate_per_hour=8.0),
                             "predictive_shared_ice_first", safety_margin=0.0)
        self.assertEqual(exact.bay, 0)
        self.assertAlmostEqual(exact.detail["predicted_demand"], 1.0, places=9)
        self.assertAlmostEqual(exact.detail["forecast_slack_bays"], 0.0, places=9)
        # 同一决策批次里已放行的油车由 pending_shared_bays 声明，继续扣减。
        pending = rules.decide(replace(state, arrival_rate_per_hour=8.0),
                               "predictive_shared_ice_first", safety_margin=0.0,
                               pending_shared_bays=1)
        self.assertIsNone(pending.bay)
        self.assertEqual(pending.detail["usable_after_this_ice"], 0.0)
        self.assertEqual(pending.detail["pending_shared_bays"], 1)
        with self.assertRaises(ValueError):
            rules.decide(state, "predictive_shared_ice_first", pending_shared_bays=-1)

    def test_prediction_objects_are_distinct_and_documented(self):
        self.assertEqual(rules.PREDICTION_OBJECTS,
                         ("charge_arrivals", "ev_arrivals", "connector_load"))
        self.assertEqual(rules.DEFAULT_PREDICTION_OBJECT, "charge_arrivals")
        state = self.state(is_ev=False, free_bays=(0, 2, 3, 4, 5, 6, 7), n_spaces=9,
                           charging_bays=8, chargers=8, arrival_rate_per_hour=24.0,
                           mean_ice_occupancy_min=90.0, mean_connector_minutes_per_ev=120.0,
                           observed_departures=6)
        charge, ev, load = (rules.predicted_demand_bays(state, obj, 30.0)
                            for obj in rules.PREDICTION_OBJECTS)
        self.assertAlmostEqual(charge[0], 3.0)
        self.assertAlmostEqual(ev[0], 6.0)
        self.assertAlmostEqual(load[0], 24.0)     # 24/60 × 0.5 × 120 分钟
        self.assertEqual(charge[1]["unit"], "events_in_window")
        self.assertEqual(ev[1]["unit"], "events_in_window")
        self.assertEqual(load[1]["unit"], "concurrent_connector_bays")
        self.assertNotEqual(charge[1]["unit"], load[1]["unit"])   # 不是同一系数的替换
        # 缺离场估计：connector_load 不伪造占用，退回默认口径并明确标注。
        missing = replace(state, mean_connector_minutes_per_ev=None)
        fallback, fallback_detail = rules.predicted_demand_bays(missing, "connector_load", 30.0)
        self.assertAlmostEqual(fallback, 3.0)
        self.assertEqual(fallback_detail["fallback"], "charge_arrivals")
        self.assertIsNotNone(fallback_detail["fallback_reason"])
        # 有效窗口与已观察油车平均占用协调（取较大者）；明细可复算。
        decision = rules.decide(state, "predictive_shared_ice_first", window_min=30.0,
                                safety_margin=1.0)
        self.assertEqual(decision.detail["window_coordinated"], True)
        self.assertAlmostEqual(decision.detail["effective_window_min"], 90.0)
        self.assertAlmostEqual(decision.detail["predicted_demand"], 9.0)    # × 90/30
        self.assertAlmostEqual(decision.detail["usable_after_this_ice"], 6.0)  # 7 空闲充电位 − 1
        self.assertIsNone(decision.bay)                                     # 6 − 9 < 1
        uncoordinated = rules.decide(state, "predictive_shared_ice_first", window_min=30.0,
                                     safety_margin=1.0, coordinate_window=False)
        self.assertEqual(uncoordinated.detail["window_coordinated"], False)
        self.assertAlmostEqual(uncoordinated.detail["predicted_demand"], 3.0)
        self.assertEqual(uncoordinated.bay, 0)                              # 6 − 3 ≥ 1
        # 三种对象会给出不同结论：connector_load 最保守（并发占位最大）。
        load_decision = rules.decide(state, "predictive_shared_ice_first", window_min=30.0,
                                     safety_margin=1.0, prediction_object="connector_load")
        self.assertIsNone(load_decision.bay)
        self.assertEqual(load_decision.detail["prediction_unit"], "concurrent_connector_bays")
        with self.assertRaises(ValueError):
            rules.predicted_demand_bays(state, "not_an_object", 30.0)

    def test_protected_quota_is_registered_and_documented(self):
        self.assertIn("protected_quota", rules.RULE_NAMES)
        self.assertEqual(rules.decide(self.state(), "protected_quota", protected_bays=1).rule,
                         "protected_quota")
        with self.assertRaises(ValueError):
            rules.decide(self.state(is_ev=False), "protected_quota")   # 缺 protected_bays
        self.assertEqual(rules.reserved_charging_bays("protected_quota", charging_bays=5,
                                                      protected_bays=2), 2)
        self.assertEqual(rules.reserved_charging_bays("protected_quota", charging_bays=5,
                                                      protected_bays=0), 0)
        with self.assertRaises(ValueError):
            rules.reserved_charging_bays("protected_quota", charging_bays=5)

    def test_protected_quota_endpoints_match_pi1_and_pi0(self):
        """m=0 的油车决策与 π1 相同；m=charging_bays 与 π0 的油车行为相同（电车也同 π0）。"""
        states = []
        for free in ((0, 2, 5), (0, 2), (2, 5), (5,), (0,), ()):
            for occupied in (None, 0, 1, 2):
                states.append(self.state(is_ev=False, free_bays=free, n_spaces=6,
                                         charging_bays=4, chargers=2,
                                         ice_charging_bays=occupied))
        for state in states:
            with self.subTest(free=state.free_bays, occupied=state.ice_charging_bays):
                pi1 = rules.decide(state, "full_open_ice_first")
                m0 = rules.decide(state, "protected_quota", protected_bays=0)
                self.assertEqual(m0.bay, pi1.bay)
                pi0 = rules.decide(state, "dedicated_by_type")
                mk = rules.decide(state, "protected_quota", protected_bays=4)
                self.assertEqual(mk.bay, pi0.bay)
        for rule in rules.RULE_NAMES:
            ev_state = self.state(is_ev=True, free_bays=(0, 2, 5), n_spaces=6,
                                  charging_bays=4, chargers=2)
            with self.subTest(rule=rule, is_ev=True):
                options = {"protected_bays": 2} if rule == "protected_quota" else {}
                self.assertEqual(rules.decide(ev_state, rule, **options).bay,
                                 rules.decide(ev_state, "dedicated_by_type").bay)

    def test_protected_quota_quota_semantics_and_validation(self):
        state = self.state(is_ev=False, free_bays=(0, 2), n_spaces=6, charging_bays=4,
                           chargers=2, ice_charging_bays=1)
        admitted = rules.decide(state, "protected_quota", protected_bays=2)   # quota=2, occ=1
        self.assertEqual(admitted.bay, 0)
        self.assertEqual(admitted.reason, "ice_shared_quota")
        self.assertEqual(admitted.detail["protected_bays"], 2)
        self.assertEqual(admitted.detail["ice_charging_quota"], 2)
        self.assertEqual(admitted.detail["quota_rule"], "observed_ice_occupancy")
        full = rules.decide(replace(state, ice_charging_bays=2), "protected_quota",
                            protected_bays=2)
        self.assertIsNone(full.bay)
        self.assertEqual(full.reason, "rejected_ice_quota")
        self.assertFalse(full.detail["quota_allows_this_ice"])
        # 普通位有空时先普通位，不受配额约束。
        ordinary = rules.decide(replace(state, free_bays=(0, 5), ice_charging_bays=4),
                                "protected_quota", protected_bays=2)
        self.assertEqual(ordinary.bay, 5)
        self.assertEqual(ordinary.reason, "ice_ordinary_first")
        # 未接线（ice_charging_bays=None）：保守口径"放行后仍保留 m 个空闲充电位"。
        fallback = rules.decide(replace(state, ice_charging_bays=None), "protected_quota",
                                protected_bays=2)
        self.assertIsNone(fallback.bay)
        self.assertEqual(fallback.detail["quota_rule"], "free_bays_fallback")
        self.assertFalse(fallback.detail["quota_known"])
        fallback_ok = rules.decide(replace(state, ice_charging_bays=None, free_bays=(0, 2, 3)),
                                   "protected_quota", protected_bays=2)
        self.assertEqual(fallback_ok.bay, 0)                     # 3−1=2 ≥ m
        # 没有空闲充电位：直接拒绝，不进入配额判断。
        empty = rules.decide(replace(state, free_bays=(), ice_charging_bays=0),
                             "protected_quota", protected_bays=2)
        self.assertIsNone(empty.bay)
        self.assertEqual(empty.reason, "rejected_no_free_bay")
        # m 校验：必填、整数、0 ≤ m ≤ charging_bays。
        for bad in (None, -1, 5, 2.5, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rules.decide(state, "protected_quota", protected_bays=bad)

    def test_rule_options_are_pure_and_injectable(self):
        state = self.state(is_ev=False, free_bays=(0, 2), n_spaces=6, charging_bays=4,
                           chargers=2, arrival_rate_per_hour=18.0,
                           mean_ice_occupancy_min=45.0,
                           mean_connector_minutes_per_ev=60.0,
                           observed_departures=3, ice_charging_bays=1)
        base = rules.decide(state, "protected_quota", protected_bays=2)
        self.assertEqual(base.bay, 0)
        for extra in (dict(prediction_object="ev_arrivals", window_min=10.0, safety_margin=3.0,
                           coordinate_window=False, pending_shared_bays=2),
                      dict(prediction_object="connector_load", window_min=120.0,
                           safety_margin=0.0, coordinate_window=True, pending_shared_bays=0)):
            with self.subTest(extra=extra):
                again = rules.decide(state, "protected_quota", protected_bays=2, **extra)
                self.assertEqual(again.bay, base.bay)
                self.assertEqual(again.reason, base.reason)
                self.assertEqual(again.detail["protected_bays"], 2)
        # π0/π1 同样忽略预测/配额参数（纯函数，无隐藏信息）。
        for rule in ("dedicated_by_type", "full_open_ice_first"):
            plain = rules.decide(state, rule)
            noisy = rules.decide(state, rule, prediction_object="connector_load",
                                 window_min=1.0, safety_margin=0.0, protected_bays=3)
            self.assertEqual(noisy.bay, plain.bay)
            self.assertEqual(noisy.reason, plain.reason)

    def test_defaults_documented_and_reserved_bays(self):
        self.assertEqual(rules.DEFAULT_PREDICTION_WINDOW_MIN, 30.0)
        self.assertEqual(rules.DEFAULT_FREE_BAY_MARGIN, 1.0)
        cfg = config(n_spaces=4, charging_bays=3, chargers=2)
        self.assertEqual(rules.reserved_charging_bays("dedicated_by_type", charging_bays=3), 3)
        self.assertEqual(rules.reserved_charging_bays("full_open_ice_first", charging_bays=3), 0)
        predictive = rules.reserved_charging_bays(
            "predictive_shared_ice_first", charging_bays=3, arrival_rate_per_hour=60.0,
            p_ev=.5, p_charge_given_ev=.5, window_min=cfg.ice_share_forecast_window_min,
            safety_margin=cfg.ice_share_free_bay_margin)
        self.assertTrue(0 <= predictive <= 3)

    def test_validation_rejects_bad_observable_state(self):
        with self.assertRaises(ValueError):
            self.state(n_spaces=2, charging_bays=3, chargers=1)
        with self.assertRaises(ValueError):
            self.state(free_bays=(0, 0))
        with self.assertRaises(ValueError):
            self.state(free_bays=(0, 9))
        with self.assertRaises(ValueError):
            self.state(p_ev=1.5)
        with self.assertRaises(ValueError):
            self.state(ice_charging_bays=True)
        with self.assertRaises(ValueError):
            self.state(ice_charging_bays=1.5)
        with self.assertRaises(ValueError):
            self.state(ice_charging_bays=self.state().charging_bays + 1)
        with self.assertRaises(ValueError):
            self.state(mean_ice_occupancy_min=-1.0)
        with self.assertRaises(ValueError):
            self.state(mean_connector_minutes_per_ev=-1.0)
        with self.assertRaises(ValueError):
            self.state(observed_departures=1.5)
        with self.assertRaises(ValueError):
            rules.decide(self.state(), "not_a_rule")


class TypeRuleSimulationTests(unittest.TestCase):
    """仿真层面的规则差异、泄漏反例与三类占位计量。"""

    def test_a_pi0_non_charging_ev_in_connector_ice_cannot_enter(self):
        sim = run([Arrival(0, 0, True, False, 10, 0),      # 不充电电车：允许带枪位
                   Arrival(1, 1, False, False, 60, 0),     # 油车：普通位
                   Arrival(2, 15, False, False, 60, 0)])   # 带枪位此时空闲，油车仍不得进入
        self.assertEqual(sim.visits[0]["bay"], 0)
        self.assertEqual(sim.visits[0]["admission"]["reason"], "ev_charging_bays_first")
        self.assertEqual(sim.visits[1]["bay"], 1)
        self.assertEqual(sim.visits[2]["admission"]["reason"], "rejected_no_ordinary_bay")
        self.assertFalse(sim.visits[2]["admitted"])
        self.assertIn(sim.visits[2]["disposition"], ("detour_exit", "alternate_bay", "give_up"))
        self.assertAlmostEqual(sim.type_occupancy()["metrics"]["no_charging_demand_bay_min"], 10.0)

    def test_b_pi1_ice_enters_when_ordinary_full_but_pi0_rejects(self):
        arrivals = [Arrival(0, 0, False, False, 60, 0), Arrival(1, 1, False, False, 60, 0)]
        pi0 = run(arrivals, "dedicated_by_type")
        self.assertEqual([v["bay"] for v in pi0.visits], [1, None])
        self.assertFalse(pi0.visits[1]["admitted"])
        self.assertEqual(pi0.visits[1]["disposition"], "detour_exit")
        self.assertEqual(pi0.type_occupancy()["metrics"]["ice_blocking_connector_min"], 0.0)
        pi1 = run(arrivals, "full_open_ice_first")
        self.assertEqual([v["bay"] for v in pi1.visits], [1, 0])
        self.assertTrue(pi1.visits[1]["admitted"])
        self.assertAlmostEqual(pi1.type_occupancy()["metrics"]["ice_blocking_connector_min"], 59.0)

    def test_c_pi2_admits_or_rejects_ice_from_visible_charging_history(self):
        cfg = config(n_spaces=9, charging_bays=8, chargers=8, charger_kw=7, feeder_kw=56)
        ice_filler = Arrival(0, 0, False, False, 60, 0)          # 占满唯一普通位
        watcher = Arrival(4, 4, False, False, 10, 0)             # 普通位不满时按规则应被拒
        no_demand = [ice_filler, Arrival(1, 1, True, False, 60, 0),
                     Arrival(2, 2, True, False, 60, 0), Arrival(3, 3, True, False, 60, 0), watcher]
        demand = [ice_filler, Arrival(1, 1, True, True, 60, 1),
                  Arrival(2, 2, True, True, 60, 1), Arrival(3, 3, True, True, 60, 1), watcher]
        # 无实际充电开始：预测需求低 ⇒ 放行；实际出现充电开始：预测需求高 ⇒ 拒绝。
        admitted = run_config(cfg, no_demand, "predictive_shared_ice_first")
        self.assertTrue(admitted.visits[-1]["admitted"])
        self.assertLess(admitted.visits[-1]["bay"], 8)
        self.assertEqual(admitted.visits[-1]["admission"]["reason"], "ice_shared_by_forecast")
        rejected = run_config(cfg, demand, "predictive_shared_ice_first")
        self.assertFalse(rejected.visits[-1]["admitted"])
        self.assertEqual(rejected.visits[-1]["admission"]["reason"],
                         "rejected_ice_reserved_for_ev_forecast")
        detail = rejected.visits[-1]["admission"]["detail"]
        self.assertGreater(detail["predicted_demand"], detail["forecast_slack_bays"])
        self.assertEqual(detail["predicted_demand"], detail["prediction_detail"]["value"])
        self.assertEqual(detail["window_min"], config().ice_share_forecast_window_min)
        self.assertEqual(detail["window_coordinated"], False)  # 基础仿真不提供离场占用估计
        self.assertAlmostEqual(detail["usable_after_this_ice"], detail["free_charging_bays"] - 1)
        # 同一车流下 π1 无条件放行，π2 因预测拒绝：差异只来自可见预测。
        pi1 = run_config(cfg, demand, "full_open_ice_first")
        self.assertTrue(pi1.visits[-1]["admitted"])
        # 预测只来自历史：把同一车流截断到决策时刻，用当时的可见统计即可复算出同一预测值。
        cutoff = watcher.time_min
        early = Simulation(rejected.config, tuple(a for a in demand if a.time_min < cutoff))
        early.advance(cutoff)
        stats = early.learner.forecast()
        recomputed = (stats["arrival_rate_hour"] / 60 * stats["p_ev"]
                      * stats["p_charge_given_ev"] * detail["effective_window_min"])
        self.assertAlmostEqual(detail["predicted_demand"], recomputed, places=9)
        self.assertEqual(detail["prediction_object"], rules.DEFAULT_PREDICTION_OBJECT)

    def test_protected_quota_simulation_quota_and_endpoints(self):
        """仿真层：π3 的配额生效，m=0 行为同 π1，m=k 行为同 π0。"""
        arrivals = [Arrival(0, 0, True, True, 60, 5),      # 电车 → 带枪位 0
                    Arrival(1, 0, False, False, 60, 0),    # 油车 → 普通位 2
                    Arrival(2, 0, False, False, 60, 0),    # 油车 → 配额内进充电区 bay 1
                    Arrival(3, 1, False, False, 60, 0)]    # 油车 → 无空闲充电位，被拒
        base = dict(n_spaces=3, charging_bays=2, chargers=2, charger_kw=7, feeder_kw=14)
        pi1 = run(arrivals, "full_open_ice_first", **base)
        m0 = run(arrivals, "protected_quota", protected_bays=0, **base)
        self.assertEqual(sequence(pi1), sequence(m0))
        pi0 = run(arrivals, "dedicated_by_type", **base)
        mk = run(arrivals, "protected_quota", protected_bays=2, **base)
        self.assertEqual(sequence(pi0), sequence(mk))
        quota = run(arrivals, "protected_quota", protected_bays=1, **base)   # quota = 2-1 = 1
        self.assertEqual(sequence(quota), [(0, 0, True), (1, 2, True), (2, 1, True),
                                           (3, None, False)])
        reason = quota.visits[2]["admission"]["reason"]
        self.assertEqual(reason, "ice_shared_quota")
        self.assertEqual(quota.visits[2]["admission"]["detail"]["protected_bays"], 1)
        self.assertEqual(quota.visits[2]["admission"]["detail"]["ice_charging_bays"], 0)
        self.assertEqual(quota.snapshot()["rule_options"]["protected_bays"], 1)

    def test_d_leak_counterexample_same_observable_input_same_bays(self):
        """同一可观测输入、两个不同 needs_charge 真值 → 正式规则分配的车位序完全相同。"""

        def flow(needs_charge):
            energy = 10.0 if needs_charge else 0.0
            return [Arrival(0, 0, True, needs_charge, 30, energy),
                    Arrival(1, 1, False, False, 30, 0),
                    Arrival(2, 2, True, needs_charge, 30, energy),
                    Arrival(3, 3, False, False, 30, 0)]

        for policy in ("dedicated_by_type", "full_open_ice_first", "predictive_shared_ice_first"):
            with self.subTest(policy=policy):
                left = run(flow(True), policy, n_spaces=3, charging_bays=2, chargers=2,
                           charger_kw=7, feeder_kw=14)
                right = run(flow(False), policy, n_spaces=3, charging_bays=2, chargers=2,
                            charger_kw=7, feeder_kw=14)
                self.assertEqual(sequence(left), sequence(right))
                self.assertEqual(sequence(left), [(0, 0, True), (1, 2, True), (2, 1, True), (3, None, False)])
                # 只有交付电量/占用后果不同：隐藏真值只影响结果，不影响分配。
                self.assertAlmostEqual(sum(v["delivered_kwh"] for v in left.visits), 7.0)
                self.assertEqual(sum(v["delivered_kwh"] for v in right.visits), 0.0)
                self.assertEqual(left.type_occupancy()["metrics"]["overstay_after_complete_min"], 0.0)
        # legacy strict 仍然按隐藏意愿分区：同可观测输入、不同真值 → 车位序列不同。
        legacy_left = run(flow(True), "strict")
        legacy_right = run(flow(False), "strict")
        self.assertNotEqual(sequence(legacy_left), sequence(legacy_right))

    def test_type_occupancy_minutes_are_measured_separately(self):
        # 无充电需求电车占带枪位 10 分钟。
        no_need = run([Arrival(0, 0, True, False, 10, 0)])
        self.assertAlmostEqual(no_need.type_occupancy()["metrics"]["no_charging_demand_bay_min"], 10.0)
        # 油车在 π1 共享下占带枪位 10 分钟。
        ice = run([Arrival(0, 0, False, False, 10, 0), Arrival(1, 1, False, False, 10, 0)],
                  "full_open_ice_first")
        self.assertAlmostEqual(ice.type_occupancy()["metrics"]["ice_blocking_connector_min"], 10.0)
        # 充满后仍占位：1 kWh / 7 kW = 8.5714 分钟充满，停车 20 分钟 ⇒ 滞留 11.4286 分钟。
        overstay = run([Arrival(0, 0, True, True, 20, 1)], "dedicated_by_type",
                       charger_kw=7, feeder_kw=7)
        self.assertAlmostEqual(overstay.visits[0]["completion_min"], 60 / 7, places=6)
        self.assertAlmostEqual(overstay.type_occupancy()["metrics"]["overstay_after_complete_min"],
                               20 - 60 / 7, places=6)

    def test_type_occupancy_ledger_export_metrics_consistency(self):
        sim = run([Arrival(0, 0, True, False, 4, 0), Arrival(1, 5, False, False, 5, 0),
                   Arrival(2, 10, True, True, 20, 1)],
                  "dedicated_by_type", n_spaces=2, charging_bays=1, chargers=1,
                  charger_kw=7, feeder_kw=7)
        ledger = sim.type_occupancy()
        exported = sim.export()
        snapshot = sim.snapshot()
        for key in rules.TYPE_OCCUPANCY_METRICS:
            self.assertIn(key, snapshot["metrics"])
            self.assertIn(key, exported["type_occupancy_metrics"])
            self.assertEqual(exported["type_occupancy_metrics"][key], ledger["metrics"][key])
            # 逐车账本求和 = 总量；逐事件区间分钟求和 = 总量。
            self.assertAlmostEqual(sum(row[key] for row in ledger["by_visit"]), ledger["metrics"][key], places=6)
            self.assertAlmostEqual(sum(event["minutes"] for event in ledger["events"]
                                       if event["reason"] == key.replace("_bay_min", "").replace("_min", "")),
                                   ledger["metrics"][key], places=6)
        self.assertTrue(ledger["events"])
        self.assertEqual(len(ledger["by_visit"]), len(sim.visits))
        self.assertAlmostEqual(ledger["metrics"]["no_charging_demand_bay_min"], 4.0)
        self.assertAlmostEqual(ledger["metrics"]["overstay_after_complete_min"], 30 - 10 - 60 / 7, places=6)
        for visit in exported["visits"]:
            for key in rules.TYPE_OCCUPANCY_METRICS:
                self.assertIn(key, visit)
            if visit["needs_charge"]:
                self.assertIsNotNone(visit["charge_start_min"])
        self.assertTrue(ledger["definitions"]["measurement_only"])

    def test_realtime_type_minutes_are_truncated_to_now(self):
        sim = Simulation(config(n_spaces=2, charging_bays=1, chargers=1),
                         [Arrival(0, 0, True, False, 60, 0)])
        sim.advance(5)
        self.assertAlmostEqual(sim.type_occupancy()["metrics"]["no_charging_demand_bay_min"], 5.0)
        sim.run()
        self.assertAlmostEqual(sim.type_occupancy()["metrics"]["no_charging_demand_bay_min"], 60.0)


class ObservableOccupancyTests(unittest.TestCase):
    """离场占用估计：只吃已观察离场事件，在场/右删失样本不计入均值。"""

    def test_only_departed_events_are_used(self):
        estimator = ObservableOccupancy()
        estimate = estimator.estimate()
        self.assertIsNone(estimate["mean_ice_occupancy_min"])
        self.assertIsNone(estimate["mean_connector_minutes_per_ev"])
        self.assertEqual(estimate["observed_departures"], 0)
        estimator.observe_departure(is_ev=False, duration_min=30, connector_minutes=0,
                                    charging_started=False)
        estimator.observe_departure(is_ev=False, duration_min=50, connector_minutes=0,
                                    charging_started=False)
        estimate = estimator.estimate()
        self.assertAlmostEqual(estimate["mean_ice_occupancy_min"], 40.0)
        self.assertIsNone(estimate["mean_connector_minutes_per_ev"])
        estimator.observe_departure(is_ev=True, duration_min=60, connector_minutes=60,
                                    charging_started=True)
        estimator.observe_departure(is_ev=True, duration_min=40, connector_minutes=0,
                                    charging_started=False)
        estimate = estimator.estimate()
        self.assertAlmostEqual(estimate["mean_connector_minutes_per_ev"], 30.0)  # 含未占位 EV
        self.assertAlmostEqual(estimate["mean_charging_session_min"], 60.0)
        self.assertEqual(estimate["observed_departures"], 4)
        self.assertEqual(estimate["observed_ev_departures"], 2)
        self.assertIn("删失", estimate["basis"])
        with self.assertRaises(ValueError):
            estimator.observe_departure(is_ev=True, duration_min=10, connector_minutes=11,
                                        charging_started=True)
        with self.assertRaises(ValueError):
            estimator.observe_departure(is_ev=True, duration_min=-1, connector_minutes=0,
                                        charging_started=False)
        with self.assertRaises(ValueError):
            estimator.observe_departure(is_ev="EV", duration_min=1, connector_minutes=0,
                                        charging_started=False)


class BoundaryTests(unittest.TestCase):
    """零桩、零充电需求、期初到达、期末删失边界。"""

    def test_zero_station_is_not_a_rule_violation(self):
        sim = run([Arrival(0, 0, True, True, 10, 10), Arrival(1, 1, True, False, 10, 0),
                   Arrival(2, 2, False, False, 10, 0)], "dedicated_by_type",
                  n_spaces=2, charging_bays=0, chargers=0)
        self.assertEqual([v["bay"] for v in sim.visits], [0, 1, None])
        self.assertFalse(sim.visits[2]["admitted"])
        self.assertIn(sim.visits[2]["disposition"], ("detour_exit", "alternate_bay", "give_up"))
        self.assertEqual(sim.visits[0]["delivered_kwh"], 0.0)
        self.assertAlmostEqual(sim.visits[0]["energy_kwh"] - sim.visits[0]["delivered_kwh"], 10.0)
        self.assertEqual(sim.type_occupancy()["metrics"],
                         {key: 0.0 for key in rules.TYPE_OCCUPANCY_METRICS})
        self.assertEqual(sim.learner.charge_starts, 0.0)

    def test_zero_charging_demand_keeps_capacity_and_records_occupancy(self):
        sim = run([Arrival(0, 0, True, False, 10, 0), Arrival(1, 11, True, False, 10, 0)],
                  "dedicated_by_type", charger_kw=7, feeder_kw=7)
        self.assertTrue(all(v["admitted"] for v in sim.visits))
        self.assertEqual(sum(v["delivered_kwh"] for v in sim.visits), 0.0)
        self.assertEqual(sim.learner.charge_starts, 0.0)
        self.assertAlmostEqual(sim.type_occupancy()["metrics"]["no_charging_demand_bay_min"], 20.0)
        self.assertEqual(sim.type_occupancy()["metrics"]["overstay_after_complete_min"], 0.0)
        self.assertEqual(sim.type_occupancy()["metrics"]["ice_blocking_connector_min"], 0.0)

    def test_arrival_at_zero_and_empty_lot_state(self):
        sim = Simulation(config(), [Arrival(0, 0, True, False, 10, 0)])
        self.assertEqual(sim.active, {})                       # 期初无在场车辆（本仿真不设初始占用）
        self.assertEqual(sim.type_occupancy()["metrics"]["no_charging_demand_bay_min"], 0.0)
        sim.advance(0)
        self.assertEqual(len(sim.visits), 1)
        self.assertTrue(sim.visits[0]["admitted"])
        self.assertEqual(sim.visits[0]["bay"], 0)
        self.assertEqual(sim.type_occupancy()["metrics"]["no_charging_demand_bay_min"], 0.0)
        zero = run([Arrival(0, 0, True, False, 10, 0)], "dedicated_by_type", n_spaces=0,
                   charging_bays=0, chargers=0)
        self.assertFalse(zero.visits[0]["admitted"])
        self.assertIn(zero.visits[0]["disposition"], ("detour_exit", "alternate_bay", "give_up"))

    def test_end_of_window_censoring_does_not_become_failure(self):
        # 60 分钟窗口；55 分到达，0.05 kWh 在 1 kW 下 3 分钟充满（58 分），
        # 滞留只累计到 60 分（删失），不是整段计划停车 60 分钟。
        overstay = run([Arrival(0, 55, True, True, 60, 0.05)], "dedicated_by_type",
                       charger_kw=1, feeder_kw=1)
        visit = overstay.visits[0]
        self.assertFalse(visit["departed"])
        self.assertTrue(visit["completed"])
        self.assertAlmostEqual(visit["completion_min"], 58.0)
        self.assertAlmostEqual(overstay.type_occupancy()["metrics"]["overstay_after_complete_min"], 2.0)
        self.assertEqual(overstay.snapshot()["metrics"]["departed_shortfall_kwh"], 0.0)
        # 期末仍在场且仍缺电：pending 只作窗口未交付电量，不是离场失败。
        pending = run([Arrival(0, 55, True, True, 60, 10)], "dedicated_by_type",
                      charger_kw=1, feeder_kw=1)
        visit = pending.visits[0]
        self.assertFalse(visit["departed"])
        self.assertAlmostEqual(visit["energy_kwh"] - visit["delivered_kwh"], 10 - 5 / 60, places=6)
        self.assertEqual(pending.snapshot()["metrics"]["departed_shortfall_kwh"], 0.0)
        self.assertGreater(pending.snapshot()["metrics"]["pending_energy_kwh"], 0.0)


class ExogenousFlowReplayTests(unittest.TestCase):
    """同外生车流、不同 k（枪数/充电车位数）与不同规则：traffic_hash 必须一致。"""

    def test_same_flow_different_k_same_traffic_hash(self):
        base = Config.parse({"duration_hours": 2, "arrival_rate_hour": 40, "seed": 9,
                             "n_spaces": 20, "charging_bays": 8, "chargers": 4})
        arrivals = generate(base)
        expected = traffic_hash(arrivals)
        seen = set()
        for charger_count, bay_count in ((3, 6), (6, 10)):
            for policy in RULE_POLICIES:      # 含 protected_quota（config/simulation 已由 Lead 接线）
                sim = Simulation(replace(base, policy=policy, chargers=charger_count,
                                         charging_bays=bay_count), arrivals)
                sim.run()
                self.assertEqual(sim.traffic_hash, expected)
                self.assertEqual(sim.demand_hash, stream_hash(arrivals))
                self.assertNotEqual(sim.visits, [])
                seen.add((sim.traffic_hash, sim.demand_hash))
        self.assertEqual(len(seen), 1)

    def test_repeated_runs_of_the_same_flow_are_identical(self):
        cfg = config(n_spaces=12, charging_bays=5, chargers=3, duration_hours=2,
                     arrival_rate_hour=60, seed=3)
        arrivals = generate(cfg)
        first = Simulation(replace(cfg, policy="predictive_shared_ice_first"), arrivals)
        second = Simulation(replace(cfg, policy="predictive_shared_ice_first"), arrivals)
        first.run()
        second.run()
        self.assertEqual(first.export(), second.export())


if __name__ == "__main__":
    unittest.main()
