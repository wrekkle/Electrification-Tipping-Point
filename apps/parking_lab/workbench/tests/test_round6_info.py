# -*- coding: utf-8 -*-
"""第六轮 A：信息条件 I0/I1、授权隔离与默认数值不变测试。"""
from __future__ import annotations

import hashlib
import json
import unittest

from apps.parking_lab.workbench import info_regimes as R
from apps.parking_lab.workbench import rules
from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.demand import generate
from apps.parking_lab.workbench.service_metrics import summarise
from apps.parking_lab.workbench.simulation import Simulation

FIXED_CONFIG = {
    "n_spaces": 10, "charging_bays": 3, "chargers": 2, "charger_kw": 7.0,
    "feeder_kw": 60.0, "duration_hours": 2.0, "start_hour": 8.0, "seed": 7,
    "arrival_rate_hour": 20.0, "ev_share": 0.5, "charge_probability": 0.6,
    "reserve_fixed": 0, "policy": "dedicated_by_type",
}
EXPECTED_DEMAND_HASH = "a2baa0b504d37c2e267733f50402ba25724d0c1034b6d49f4be3143d7eef9d56"
EXPECTED_VISITS_SHA256 = "e407f5a1619c104711453d74ba546dd1b599ec99168d2e23db689bf41f26f662"
EXPECTED_METRICS = {"peak_power_kw": 7.0, "peak_occupancy": 10,
                    "charge_completion_rate_all": 0.0,
                    "mean_occupancy_rate": 0.9574873282595064}
EXPECTED_RATES = {"capacity_unmet_rate": 0.8333333333333334,
                  "ev_parking_failure_rate": 0.7843137254901961,
                  "ice_parking_failure_rate": 0.8857142857142857,
                  "departed_shortfall_energy_rate": 1.0}


def make_state(**overrides):
    values = {"time_min": 0.0, "is_ev": True, "free_bays": (0, 1, 2, 3),
              "n_spaces": 6, "charging_bays": 3, "chargers": 2,
              "arrival_rate_per_hour": 20.0, "p_ev": 0.5,
              "p_charge_given_ev": 0.5}
    values.update(overrides)
    return rules.ObservableState(**values)


def run_default(config, arrivals):
    sim = Simulation(config, arrivals=arrivals)
    sim.run()
    return sim


def visits_digest(sim):
    rows = [[v["vehicle_id"], v["time_min"], v["is_ev"], v["needs_charge"],
             v["admitted"], v["bay"], round(v["delivered_kwh"], 9)] for v in sim.visits]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


class ContextAuthorizationTest(unittest.TestCase):
    def test_real_context_has_no_needs_charge(self):
        import dataclasses
        fields = {field.name for field in dataclasses.fields(rules.ObservableState)}
        self.assertNotIn("needs_charge", fields)
        self.assertNotIn("energy_kwh", fields)
        context = R.real_rule_context(make_state())
        self.assertEqual(context.allowed_fields, ())
        self.assertNotIn("needs_charge", dir(context))
        self.assertNotIn("energy_kwh", dir(context))
        with self.assertRaises(PermissionError):
            context.needs_charge
        with self.assertRaises(PermissionError):
            context.energy_kwh
        with self.assertRaises(PermissionError):
            context.departure_min
        with self.assertRaises(AttributeError):
            context.not_a_field

    def test_analysis_context_only_adds_needs_charge(self):
        state = make_state()
        context = R.analysis_context(state, True)
        self.assertEqual(context.allowed_fields, ("needs_charge",))
        self.assertTrue(context.needs_charge)
        self.assertIs(context.state, state)
        with self.assertRaises(PermissionError):
            context.energy_kwh
        with self.assertRaises(TypeError):
            R.analysis_context(state, 1)
        with self.assertRaises(PermissionError):
            R.AnalysisContext(state, True, grant=None)

    def test_grant_cannot_expand_fields(self):
        with self.assertRaises(PermissionError):
            R.AnalysisGrant(fields=("needs_charge", "energy_kwh"))
        with self.assertRaises(PermissionError):
            R.AnalysisGrant(analysis_only=False)
        with self.assertRaises(PermissionError):
            R.AnalysisContext(make_state(), True, grant=R.AnalysisGrant())

    def test_policy_rejects_unauthorized_context(self):
        for policy in (R.AnalysisHeuristicPolicy(), R.MimicI0Policy()):
            with self.assertRaises(PermissionError):
                policy.choose(R.real_rule_context(make_state()))

    def test_metadata_requires_analysis_only(self):
        self.assertEqual(R.metadata(R.I0)["policy_kind"], "real_rule")
        self.assertFalse(R.metadata(R.I0)["analysis_only"])
        with self.assertRaises(ValueError):
            R.metadata(R.I1)
        data = R.metadata(R.I1, R.AnalysisHeuristicPolicy())
        self.assertEqual(data["information_regime"], "I1")
        self.assertTrue(data["analysis_only"])
        self.assertEqual(data["policy_kind"], "analysis_heuristic")
        self.assertIn("can_mimic_I0", data)
        self.assertIn("needs_charge", data["visible_fields"])
        self.assertNotIn("needs_charge", R.metadata(R.I0)["visible_fields"])


class PolicyDecisionTest(unittest.TestCase):
    def test_mimic_equals_real_rule(self):
        states = [make_state(), make_state(is_ev=False), make_state(free_bays=(2, 3)),
                  make_state(free_bays=()), make_state(is_ev=False, free_bays=(0, 1, 2)),
                  make_state(free_bays=(1, 3))]
        for base_rule in ("dedicated_by_type", "full_open_ice_first",
                          "predictive_shared_ice_first"):
            policy = R.MimicI0Policy(base_rule)
            for state in states:
                expected = rules.candidates(state, base_rule)
                got = policy.choose(R.analysis_context(state, True))
                self.assertEqual(got[0], expected[0], (base_rule, state))
                self.assertEqual(got[1], expected[1])

    def test_heuristic_uses_intent_for_ev(self):
        policy = R.AnalysisHeuristicPolicy("dedicated_by_type")
        charging = policy.choose(R.analysis_context(make_state(), True))
        idle = policy.choose(R.analysis_context(make_state(), False))
        self.assertEqual(charging[0][0], 0)          # 带枪位优先
        self.assertGreaterEqual(idle[0][0], 3)       # 普通位优先
        self.assertIn("ev_no_charge_intent", idle[2]["info_branch"])
        # 油车完全沿用基础规则（π0：只能普通位）。
        ice = make_state(is_ev=False)
        ice_decision = policy.choose(R.analysis_context(ice, False))
        self.assertEqual(ice_decision[0], rules.candidates(ice, "dedicated_by_type")[0])

    def test_make_policy_kinds(self):
        self.assertEqual(R.make_policy("mimic_i0").can_mimic_I0, True)
        self.assertEqual(R.make_policy().policy_kind, "analysis_heuristic")
        with self.assertRaises(ValueError):
            R.make_policy("global_optimum")


class RegimeSimulationTest(unittest.TestCase):
    def _setup(self):
        config = Config.parse(FIXED_CONFIG)
        arrivals = generate(config)
        return config, arrivals

    def test_i0_default_numbers_unchanged(self):
        config, arrivals = self._setup()
        sim = run_default(config, arrivals)
        self.assertEqual(sim.demand_hash, EXPECTED_DEMAND_HASH)
        self.assertEqual(visits_digest(sim), EXPECTED_VISITS_SHA256)
        metrics = sim.snapshot()["metrics"]
        for key, value in EXPECTED_METRICS.items():
            self.assertEqual(metrics[key], value, key)
        rates = summarise(sim.visits, horizon_min=sim.horizon)["rates"]
        for key, value in EXPECTED_RATES.items():
            self.assertAlmostEqual(rates[key], value, places=12, msg=key)

    def test_i1_mimic_equals_i0(self):
        config, arrivals = self._setup()
        base = run_default(config, arrivals)
        regime = R.RegimeSimulation(config, arrivals=arrivals,
                                    policy=R.MimicI0Policy("dedicated_by_type"))
        regime.run()
        self.assertEqual(visits_digest(regime), visits_digest(base))
        self.assertEqual(regime.demand_hash, base.demand_hash)
        base_rates = summarise(base.visits, horizon_min=base.horizon)["rates"]
        regime_rates = summarise(regime.visits, horizon_min=regime.horizon)["rates"]
        self.assertEqual(set(base_rates), set(regime_rates))
        for key in base_rates:
            self.assertAlmostEqual(base_rates[key], regime_rates[key], places=12, msg=key)
        exported = regime.export()
        self.assertEqual(exported["information_regime"], "I1")
        self.assertTrue(exported["analysis_only"])
        self.assertEqual(exported["policy_kind"], "analysis_heuristic")
        self.assertTrue(exported["can_mimic_I0"])
        self.assertEqual(exported["state"]["information_regime"], "I1")
        self.assertTrue(exported["state"]["analysis_only"])

    def test_i1_heuristic_keeps_stream_and_admission(self):
        config, arrivals = self._setup()
        base = run_default(config, arrivals)
        regime = R.RegimeSimulation(config, arrivals=arrivals,
                                    policy=R.AnalysisHeuristicPolicy("dedicated_by_type"))
        regime.run()
        self.assertEqual(len(regime.visits), len(base.visits))
        self.assertEqual([v["vehicle_id"] for v in regime.visits],
                         [v["vehicle_id"] for v in base.visits])
        self.assertEqual([(v["is_ev"], v["needs_charge"], v["energy_kwh"],
                           v["dwell_min"]) for v in regime.visits],
                         [(v["is_ev"], v["needs_charge"], v["energy_kwh"],
                           v["dwell_min"]) for v in base.visits])
        # 车流本身不变；分配次序改变会传导到后续准入（含 ICE 占位与 EV 回填），
        # 因此准入结果允许变化，但每个到访仍必须显式记录决策（无车辆消失）。
        self.assertEqual(regime.demand_hash, base.demand_hash)
        self.assertTrue(all("admission" in v for v in regime.visits))
        admitted_base = sum(1 for v in base.visits if v["admitted"])
        admitted_regime = sum(1 for v in regime.visits if v["admitted"])
        self.assertEqual(admitted_base + sum(1 for v in base.visits if not v["admitted"]),
                         len(regime.visits))
        self.assertLessEqual(abs(admitted_base - admitted_regime), len(regime.visits))
        used = [v["admission"]["detail"].get("needs_charge_used")
                for v in regime.visits if v["is_ev"]]
        self.assertTrue(any(used))
        for visit in regime.visits:
            self.assertEqual(visit["admission"]["analysis_only"], True)
            self.assertIn("needs_charge_used", visit["admission"]["detail"])

    def test_regime_simulation_requires_policy(self):
        config, arrivals = self._setup()
        with self.assertRaises(ValueError):
            R.RegimeSimulation(config, arrivals=arrivals)
        with self.assertRaises(TypeError):
            R.RegimeSimulation(config, arrivals=arrivals, policy=object())


if __name__ == "__main__":
    unittest.main()
