# -*- coding: utf-8 -*-
"""v3 申报制准入与混合停车仿真：手算、边界、信息合同与守恒测试。"""
from __future__ import annotations

import inspect
import unittest

from apps.parking_lab.workbench import declared_need as D
from apps.parking_lab.workbench import rules
from apps.parking_lab.workbench.config import RULE_POLICIES, Config
from apps.parking_lab.workbench.metrics import calculate

EPS = 1e-9


def cfg(**overrides):
    """构造测试配置：charging_bays = chargers = k（不设无枪充电位），普通位 = n_spaces-k。"""
    base = dict(n_spaces=3, charging_bays=1, chargers=1, charger_kw=7.0,
                feeder_kw=7.0, duration_hours=4.0, start_hour=8.0,
                arrival_rate_hour=0.0, ev_share=0.5, charge_probability=0.5,
                reserve_fixed=0, policy="dedicated_by_type")
    base.update(overrides)
    return Config(**base)


def arr(i, t, is_ev, need, dwell, energy, declared=None):
    return D.DeclaredArrival(vehicle_id=i, time_min=t, is_ev=is_ev,
                             needs_charge=need, dwell_min=dwell, energy_kwh=energy,
                             declared_need=need if declared is None else declared)


def run_sim(arrivals, rule="A", config=None, **kwargs):
    if config is None:
        config = cfg(policy=D.BASE_RULE[rule])
    return D.DeclaredNeedSimulation(config, arrivals=arrivals, rule=rule, **kwargs)


def state(**overrides):
    values = {"time_min": 0.0, "is_ev": True, "free_bays": (0, 1, 2, 3),
              "n_spaces": 6, "charging_bays": 3, "chargers": 2,
              "arrival_rate_per_hour": 20.0, "p_ev": 0.5, "p_charge_given_ev": 0.5}
    values.update(overrides)
    return rules.ObservableState(**values)


class DecisionTableTests(unittest.TestCase):
    def test_declared_need_only_equipped_bay(self):
        s = state(is_ev=True, free_bays=(1, 3, 4), n_spaces=6, charging_bays=3, chargers=2)
        d = D.decide(s, True, "A")
        self.assertEqual(d.bay, 1)
        self.assertEqual(d.reason, "ev_need_equipped")

    def test_declared_need_leaves_when_no_equipped_bay(self):
        # 有空闲普通位与空闲预留位，但没有带枪位：直接离开，不排队/不占普通位。
        s = state(is_ev=True, free_bays=(2, 4, 5), n_spaces=6, charging_bays=3, chargers=2)
        d = D.decide(s, True, "A")
        self.assertIsNone(d.bay)
        self.assertEqual(d.reason, "no_equipped_bay")
        self.assertEqual(D.rejection_category(d.reason), "no_equipped_bay")

    def test_declared_need_lot_full(self):
        s = state(is_ev=True, free_bays=(), n_spaces=6, charging_bays=3, chargers=2)
        d = D.decide(s, True, "A")
        self.assertIsNone(d.bay)
        self.assertEqual(d.reason, "lot_full")
        self.assertEqual(D.rejection_category(d.reason), "lot_full")

    def test_no_need_ev_ordinary_first_then_fallback(self):
        s = state(is_ev=True, free_bays=(0, 1, 3), n_spaces=6, charging_bays=3, chargers=2)
        d = D.decide(s, False, "A")
        self.assertEqual(d.bay, 3)
        self.assertEqual(d.reason, "ev_no_need_ordinary")
        s2 = state(is_ev=True, free_bays=(0, 1), n_spaces=6, charging_bays=3, chargers=2)
        d2 = D.decide(s2, False, "A")
        self.assertEqual(d2.bay, 0)
        self.assertEqual(d2.reason, "ev_no_need_fallback_equipped")
        d3 = D.decide(s2, False, "A", allow_no_need_fallback=False)
        self.assertIsNone(d3.bay)
        self.assertEqual(d3.reason, "no_ordinary_bay_no_fallback")
        s3 = state(is_ev=True, free_bays=(2,), n_spaces=6, charging_bays=3, chargers=2)
        self.assertEqual(D.decide(s3, False, "A").reason, "ev_no_need_fallback_designated")

    def test_ice_rules_a_b_c_d(self):
        # A：普通位满、带枪位空 → 油车离开（rule_restricted）。
        s = state(is_ev=False, free_bays=(0, 1), n_spaces=6, charging_bays=3, chargers=2)
        d_a = D.decide(s, False, "A")
        self.assertIsNone(d_a.bay)
        self.assertEqual(D.rejection_category(d_a.reason), "rule_restricted")
        # B：普通位满 → 进入充电区（先带枪位）。
        d_b = D.decide(s, False, "B")
        self.assertEqual(d_b.bay, 0)
        # C：m=2, charging_bays=3 → 配额 1；已占 1 个油车 → 再放行被拒。
        s_c = state(is_ev=False, free_bays=(1, 2), n_spaces=6, charging_bays=3, chargers=2,
                    ice_charging_bays=1)
        d_c = D.decide(s_c, False, "C", protected_bays=2)
        self.assertIsNone(d_c.bay)
        self.assertEqual(d_c.reason, "rejected_ice_quota")
        d_c2 = D.decide(s_c, False, "C", protected_bays=0)
        self.assertEqual(d_c2.bay, 1)
        # D：预测需求高 → 保留给 EV，不放行；预测为 0 且余量够 → 放行。
        s_d = state(is_ev=False, free_bays=(0,), n_spaces=6, charging_bays=3, chargers=2,
                    arrival_rate_per_hour=120.0, p_ev=1.0, p_charge_given_ev=1.0)
        d_d = D.decide(s_d, False, "D", window_min=30.0, safety_margin=1.0)
        self.assertIsNone(d_d.bay)
        s_d2 = state(is_ev=False, free_bays=(0, 1), n_spaces=6, charging_bays=3, chargers=2,
                     arrival_rate_per_hour=0.0)
        self.assertEqual(D.decide(s_d2, False, "D", window_min=30.0, safety_margin=1.0).bay, 0)

    def test_decision_table_complete_and_base_rules(self):
        for rule in D.ADMISSION_RULES:
            table = D.v3_decision_table(rule)
            self.assertEqual(table["base_rule"], D.BASE_RULE[rule])
            self.assertIn(D.BASE_RULE[rule], RULE_POLICIES)
            self.assertTrue(table["ev_declared_need"] and table["ev_no_declared_need"])
            self.assertIn("information_contract", table)
            self.assertEqual(table["information_contract"]["version"], "3.0.0")


class InformationContractTests(unittest.TestCase):
    def test_context_hides_forbidden_fields(self):
        ctx = D.declared_need_context(state(), True)
        self.assertTrue(ctx.declared_need)
        for name in ("energy_kwh", "dwell_min", "departure_min", "future_arrivals", "soc"):
            with self.assertRaises(D.HiddenInformationError):
                getattr(ctx, name)
        self.assertIn("declared_need", D.VISIBLE_FIELDS)
        self.assertNotIn("needs_charge", D.VISIBLE_FIELDS)

    def test_decision_signature_has_no_hidden_fields(self):
        params = set(inspect.signature(D.decide).parameters)
        for name in ("needs_charge", "energy_kwh", "dwell_min", "departure_min", "future_arrivals"):
            self.assertNotIn(name, params)
        self.assertIn("declared_need", params)

    def test_controller_uses_declaration_not_truth(self):
        # 真实需要充电但申报“不充电”：只占普通位、不交付电量（控制器按申报分流）。
        arrivals = [arr(0, 0.0, True, True, 60.0, 7.0, declared=False)]
        sim = run_sim(arrivals, "A", config=cfg(policy="dedicated_by_type"))
        sim.run()
        v = sim.visits[0]
        self.assertFalse(v["admitted"] and v["bay"] < sim.config.chargers)
        self.assertEqual(v["delivered_kwh"], 0.0)
        self.assertIsNone(v["charge_start_min"])
        # 真实不需要充电但申报“充电”：占用带枪位但物理上不耗电。
        arrivals = [arr(0, 0.0, True, False, 60.0, 0.0, declared=True)]
        sim2 = run_sim(arrivals, "A")
        sim2.run()
        v2 = sim2.visits[0]
        self.assertLess(v2["bay"], sim2.config.chargers)
        self.assertEqual(v2["delivered_kwh"], 0.0)
        self.assertEqual(v2["declared_need"], True)
        self.assertFalse(v2["needs_charge"])


class SimulationMechanicsTests(unittest.TestCase):
    def test_rejected_charging_request_keeps_energy_denominator(self):
        arrivals = [arr(0, 0.0, True, True, 60.0, 7.0),      # 占用唯一带枪位
                    arr(1, 10.0, False, False, 60.0, 0.0),   # 油车进普通位
                    arr(2, 20.0, True, True, 60.0, 7.0)]     # 普通位空着但无带枪位 → 离开
        sim = run_sim(arrivals, "A")
        sim.run()
        rejected = [v for v in sim.visits if not v["admitted"]]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["rejection_reason"], "no_equipped_bay")
        m = D.content_metrics(sim.visits, sim.config, cut_min=sim.time)
        self.assertEqual(m["counts"]["charging_requests"], 2)
        self.assertEqual(m["counts"]["rejected_charging_requests"], 1)
        self.assertAlmostEqual(m["rates"]["charging_request_rejection_rate"], 0.5)
        self.assertAlmostEqual(m["energy"]["requested_kwh"], 14.0)
        self.assertAlmostEqual(m["energy"]["delivered_kwh"], 7.0)
        self.assertAlmostEqual(m["energy"]["shortfall_kwh"], 7.0)
        self.assertAlmostEqual(m["rates"]["ev_parking_failure_rate"], 0.5)
        self.assertAlmostEqual(m["rates"]["ice_parking_failure_rate"], 0.0)
        self.assertAlmostEqual(m["rates"]["session_target_unmet_rate_settled"], 0.5)
        self.assertAlmostEqual(calculate(sim)["energy_balance_error_kwh"], 0.0, places=9)

    def test_charge_stops_at_completion_but_car_stays(self):
        arrivals = [arr(0, 0.0, True, True, 120.0, 3.5)]
        sim = run_sim(arrivals, "A", config=cfg(n_spaces=2, charging_bays=1, chargers=1,
                                                feeder_kw=7.0, duration_hours=3.0))
        sim.run()
        v = sim.visits[0]
        self.assertAlmostEqual(v["delivered_kwh"], 3.5)
        self.assertAlmostEqual(v["completion_min"], 30.0, places=6)
        self.assertTrue(v["departed"])
        m = D.content_metrics(sim.visits, sim.config, cut_min=sim.time)
        self.assertAlmostEqual(m["occupancy"]["overstay_after_complete_min"], 90.0)
        self.assertGreater(m["rates"]["overstay_after_complete_share"], 0.0)

    def test_no_delivery_after_departure(self):
        arrivals = [arr(0, 0.0, True, True, 10.0, 14.0)]
        sim = run_sim(arrivals, "A", config=cfg(n_spaces=2, charging_bays=1, chargers=1,
                                                feeder_kw=7.0, duration_hours=2.0))
        sim.run()
        v = sim.visits[0]
        self.assertAlmostEqual(v["delivered_kwh"], 7.0 * 10.0 / 60.0, places=9)
        self.assertTrue(v["departed"])
        self.assertEqual(sim.powers(), {})

    def test_power_not_diluted_and_vehicle_cap(self):
        arrivals = [arr(i, 0.0, True, True, 60.0, 7.0) for i in range(4)]
        c = cfg(n_spaces=4, charging_bays=4, chargers=4, charger_kw=7.0, feeder_kw=28.0,
                duration_hours=1.5)
        sim = run_sim(arrivals, "A", config=c, vehicle_max_kw=7.0)
        sim.run()
        for v in sim.visits:
            self.assertAlmostEqual(v["delivered_kwh"], 7.0, places=9)
        self.assertAlmostEqual(sim.peak_power, 28.0)
        # 固定馈线（共享功率池）只能作对照：每车 20/4 = 5 kW。
        c2 = cfg(n_spaces=4, charging_bays=4, chargers=4, charger_kw=7.0, feeder_kw=20.0,
                 duration_hours=1.5)
        sim2 = run_sim([arr(i, 0.0, True, True, 60.0, 7.0) for i in range(4)], "A",
                       config=c2, require_unconstrained_supply=False)
        sim2.run()
        for v in sim2.visits:
            self.assertAlmostEqual(v["delivered_kwh"], 5.0, places=9)
        # 桩额定 60 kW、车端 7 kW：单车按 7 kW 交付，理想上界也用 7 kW。
        c3 = cfg(n_spaces=1, charging_bays=1, chargers=1, charger_kw=60.0, feeder_kw=60.0,
                 duration_hours=1.5)
        sim3 = run_sim([arr(0, 0.0, True, True, 60.0, 30.0)], "A", config=c3,
                       vehicle_max_kw=7.0)
        sim3.run()
        m3 = D.content_metrics(sim3.visits, sim3.config, vehicle_max_kw=7.0, cut_min=sim3.time)
        self.assertAlmostEqual(m3["energy"]["delivered_kwh"], 7.0, places=9)
        self.assertAlmostEqual(m3["energy"]["ideal_kwh"], 7.0, places=9)
        with self.assertRaises(ValueError):
            run_sim([arr(0, 0.0, True, True, 60.0, 7.0)], "A",
                    config=cfg(n_spaces=1, charging_bays=1, chargers=1, feeder_kw=5.0))

    def test_three_occupancy_classes(self):
        # 不充电 EV 回落到带枪位 + 充完滞留 + B 规则下油车占带枪位。
        arrivals = [arr(0, 0.0, True, True, 120.0, 3.5),  # 30 分钟充满后滞留到 120
                    arr(1, 0.5, True, False, 120.0, 0.0),  # 不充电 EV 占普通位
                    arr(2, 1.0, False, False, 120.0, 0.0)]  # 油车占普通位
        c = cfg(n_spaces=2, charging_bays=1, chargers=1, charger_kw=7.0, feeder_kw=7.0,
                duration_hours=3.0, policy="full_open_ice_first")
        sim = run_sim(arrivals, "B", config=c)
        sim.run()
        m = D.content_metrics(sim.visits, sim.config, cut_min=sim.time)
        self.assertGreater(m["occupancy"]["overstay_after_complete_min"], 0.0)
        # 另建一个普通位被占满、油车按 B 进带枪位的例子。
        arrivals2 = [arr(0, 0.0, True, False, 120.0, 0.0), arr(1, 0.0, False, False, 120.0, 0.0),
                     arr(2, 1.0, False, False, 120.0, 0.0)]
        c2 = cfg(n_spaces=2, charging_bays=1, chargers=1, charger_kw=7.0, feeder_kw=7.0,
                 duration_hours=3.0, policy="full_open_ice_first")
        sim2 = run_sim(arrivals2, "B", config=c2)
        sim2.run()
        m2 = D.content_metrics(sim2.visits, sim2.config, cut_min=sim2.time)
        self.assertGreater(m2["occupancy"]["ice_blocking_connector_min"], 0.0)
        self.assertAlmostEqual(m2["rates"]["ice_blocking_connector_share"], 1.0)

    def test_combine_metrics_uses_totals_not_average(self):
        a1 = [arr(0, 0.0, True, True, 60.0, 7.0),
              arr(1, 20.0, True, True, 60.0, 7.0)]
        sim1 = run_sim(a1, "A")
        sim1.run()
        m1 = D.content_metrics(sim1.visits, sim1.config, cut_min=sim1.time)
        a2 = [arr(0, 0.0, True, True, 60.0, 7.0)]
        sim2 = run_sim(a2, "A")
        sim2.run()
        m2 = D.content_metrics(sim2.visits, sim2.config, cut_min=sim2.time)
        self.assertAlmostEqual(m1["rates"]["charging_request_rejection_rate"], 0.5)
        self.assertAlmostEqual(m2["rates"]["charging_request_rejection_rate"], 0.0)
        combined = D.combine_metrics([m1, m2])
        self.assertAlmostEqual(combined["rates"]["charging_request_rejection_rate"], 1.0 / 3.0)
        self.assertAlmostEqual(combined["counts"]["charging_requests"], 3.0)
        self.assertAlmostEqual(combined["energy"]["requested_kwh"], 21.0)

    def test_invariants_reject_wrong_admission(self):
        # 申报充电的 EV 被分到非带枪位必须触发不变量（构造违规后手工检查）。
        sim = run_sim([arr(0, 0.0, True, True, 10.0, 7.0)], "A")
        sim.run()
        sim.visits[0]["bay"] = 2  # 伪造违规
        sim.visits[0]["declared_need"] = True
        with self.assertRaises(AssertionError):
            sim.assert_invariants()


if __name__ == "__main__":
    unittest.main()
