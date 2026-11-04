# -*- coding: utf-8 -*-
"""Unit tests for the T64 three-scheme engine, cost ledger and backend service."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WB = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(WB)))
if WB not in sys.path:
    sys.path.insert(0, WB)
REF_DIR = os.path.join(REPO, "research", "model_architecture_20261102")
if REF_DIR not in sys.path:
    sys.path.insert(0, REF_DIR)

import schemes
import scheme_engine
import social_cost
import scheme_service


def tiny_stream(vehicles, N=4, W=1440, T=2880, station_kw=7.2, initial=None, stream_id="tiny"):
    H = max([T] + [v["arrival"] + v["dwell"] for v in vehicles
                   if W <= v["arrival"] < T])
    stream = schemes.FrozenStream(stream_id=stream_id, site_id="test", mode="R2",
                                  scenario_id="test", N=N, station_kw=station_kw,
                                  W=W, T=T, H=H, vehicles=vehicles,
                                  initial=initial or [], source="synthetic_demo",
                                  provenance={"kind": "unit_test"})
    stream.validate()
    return stream


def veh(sid, arrival, dwell, cls, energy=0.0, accept_power=None, vid=None):
    return {"session_id": sid, "vehicle_id": vid or sid, "arrival": arrival,
            "dwell": dwell, "cls": cls, "energy": energy,
            "accept_power": accept_power, "origin": "unit_test"}


PARAMS = schemes.CostParams.theta_center()


class SchemeContractTests(unittest.TestCase):
    def test_scheme_rejects_invalid_combinations(self):
        with self.assertRaises(schemes.SchemeError):
            schemes.SchemeSpec("S1", "fallback",
                               schemes.OpenRule(open_rule="opportunity"),
                               schemes.MobileFleet(count=0)).validate()
        with self.assertRaises(schemes.SchemeError):
            schemes.SchemeSpec("S2", "fallback", schemes.OpenRule(),
                               schemes.MobileFleet(count=1)).validate()
        with self.assertRaises(schemes.SchemeError):
            schemes.SchemeSpec("S3", "fallback", schemes.OpenRule(),
                               schemes.MobileFleet(count=1, discharge_efficiency=1.5)).validate()

    def test_stream_validation(self):
        with self.assertRaises(schemes.SchemeError):
            tiny_stream([veh("a", 100, 60, "E1", 10.0), veh("a", 200, 60, "I")])
        with self.assertRaises(schemes.SchemeError):
            tiny_stream([veh("a", 100, 60, "I", energy=5.0)])
        with self.assertRaises(schemes.SchemeError):
            tiny_stream([veh("a", 100, 60, "X")])
        ok = tiny_stream([veh("a", 1500, 60, "E1", 10.0)])
        self.assertEqual(len(ok.cohort()), 1)

    def test_domain_validation(self):
        domain = schemes.FeasibleDomain(5, n_grid=[0, 3, 5], m_grid=[0, 1])
        domain.validate("S3")
        self.assertEqual(len(domain.configs("S3")), 6)
        with self.assertRaises(schemes.SchemeError):
            schemes.FeasibleDomain(5, n_grid=[0, 6]).validate("S1")
        with self.assertRaises(schemes.SchemeError):
            schemes.FeasibleDomain(5, n_grid=[0, 1], m_grid=[0, 2], m_max=1).validate("S3")

    def test_config_validation(self):
        stream = tiny_stream([veh("a", 100, 60, "E1", 10.0)])
        with self.assertRaises(schemes.SchemeError):
            schemes.validate_config(stream, "S1", {"n": 3, "m": 1})
        with self.assertRaises(schemes.SchemeError):
            schemes.validate_config(stream, "S3", {"n": 9, "m": 0})
        self.assertEqual(schemes.validate_config(stream, "S2", {"n": 2}), {"n": 2, "m": 0})

    def test_cost_anchor_is_registered(self):
        anchor = schemes.cost_anchor()
        self.assertAlmostEqual(anchor["a_usd_per_bay_day"], 3.112, places=3)
        self.assertEqual(anchor["status"], "read")
        mobile = schemes.mobile_anchor()
        self.assertAlmostEqual(mobile["a_mob_usd_per_device_day"], 42.691, places=2)


class EngineAlignmentTests(unittest.TestCase):
    def test_s1_matches_reference_model(self):
        import reference_model_v3 as REF
        vehicles = [
            veh("e1a", 1500, 120, "E1", 20.0), veh("i1", 1510, 90, "I"),
            veh("e0a", 1520, 300, "E0"), veh("e1b", 1600, 30, "E1", 40.0),
            veh("i2", 1700, 400, "I"), veh("e1c", 1800, 60, "E1", 5.0),
        ]
        stream = tiny_stream(vehicles, N=4)
        sc = REF.Scenario("t", stream.N, stream.T,
                          [REF.Vehicle(v["vehicle_id"], v["session_id"], v["arrival"],
                                       v["dwell"], v["cls"], v["energy"])
                           for v in stream.vehicles],
                          station_power=stream.station_kw, account_from=stream.W, initial=[])
        REF.validate(sc)
        for rule_name in ("strict", "fallback"):
            rule = REF.Rule(rule_name)
            spec = schemes.SchemeSpec.s1(rule_name)
            for n in range(0, stream.N + 1):
                ref = REF.features(sc, n, rule)
                res = scheme_engine.run_scheme(stream, spec, {"n": n, "m": 0}, PARAMS)
                f = res["features"]
                self.assertAlmostEqual(f["R_I"], ref["R_I"], places=9)
                self.assertAlmostEqual(f["R_E0"], ref["R_E0"], places=9)
                self.assertAlmostEqual(f["R_EP"], ref["R_EP"], places=9)
                self.assertAlmostEqual(f["S_kwh"], ref["shortfall_kwh"], places=9)
                self.assertAlmostEqual(f["D_fixed_kwh"], ref["delivered_kwh"], places=9)
                self.assertAlmostEqual(f["requested_E1_kwh"], ref["demand_kwh"], places=9)

    def test_degeneracy_s2_never_is_s1(self):
        stream = tiny_stream([veh("e1", 1500, 120, "E1", 20.0), veh("i", 1501, 60, "I")], N=2)
        s1 = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s1("fallback"),
                                      {"n": 1, "m": 0}, PARAMS)["features"]
        s2 = scheme_engine.run_scheme(
            stream, schemes.SchemeSpec("S2", "fallback", schemes.OpenRule(open_rule="never"),
                                       schemes.MobileFleet(count=0)),
            {"n": 1, "m": 0}, PARAMS)["features"]
        for key in ("R_I", "R_E0", "R_EP", "S_kwh", "D_fixed_kwh", "moves", "opened"):
            self.assertEqual(s1[key], s2[key], key)

    def test_degeneracy_s3_zero_mobile_is_s2(self):
        stream = tiny_stream([veh("e1", 1500, 200, "E1", 30.0), veh("i", 1501, 60, "I"),
                              veh("e1b", 1600, 100, "E1", 10.0)], N=3)
        s2 = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s2("fallback"),
                                      {"n": 1, "m": 0}, PARAMS)["features"]
        s3 = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s3("fallback", m=0),
                                      {"n": 1, "m": 0}, PARAMS)["features"]
        for key in ("R_I", "R_E0", "R_EP", "S_kwh", "D_fixed_kwh", "D_mobile_kwh", "moves"):
            self.assertEqual(s2[key], s3[key], key)

    def test_empty_stream(self):
        stream = tiny_stream([], N=2)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s1("fallback"),
                                       {"n": 1, "m": 0}, PARAMS)
        self.assertEqual(res["features"]["cohort_n"], 0)
        self.assertEqual(res["features"]["R_EP"], 0)
        self.assertTrue(all(c["ok"] for c in res["checks"]))

    def test_n_zero_rejects_all_e1(self):
        stream = tiny_stream([veh("e1", 1500, 100, "E1", 20.0)], N=2)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s1("strict"),
                                       {"n": 0, "m": 0}, PARAMS)
        self.assertEqual(res["features"]["R_EP"], 1)
        self.assertAlmostEqual(res["features"]["S_kwh"], 20.0, places=9)

    def test_n_equals_N_rejects_non_e1(self):
        stream = tiny_stream([veh("i", 1500, 100, "I"), veh("e1", 1501, 100, "E1", 10.0)], N=2)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s1("strict"),
                                       {"n": 2, "m": 0}, PARAMS)
        self.assertEqual(res["features"]["R_I"], 1)
        self.assertEqual(res["features"]["R_EP"], 0)

    def test_energy_identity_and_partial_delivery(self):
        stream = tiny_stream([veh("e1", 1500, 60, "E1", 20.0)], N=1)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s1("strict"),
                                       {"n": 1, "m": 0}, PARAMS)
        f = res["features"]
        self.assertAlmostEqual(f["D_fixed_kwh"], 7.2, places=6)
        self.assertAlmostEqual(f["S_kwh"], 12.8, places=6)
        self.assertAlmostEqual(f["requested_E1_kwh"], 20.0, places=6)
        self.assertTrue(all(c["ok"] for c in res["checks"]))

    def test_full_charge_then_hold_bay(self):
        stream = tiny_stream([veh("e1", 1500, 300, "E1", 5.0), veh("e1b", 1520, 60, "E1", 5.0)], N=1)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s1("strict"),
                                       {"n": 1, "m": 0}, PARAMS)
        f = res["features"]
        self.assertAlmostEqual(f["D_fixed_kwh"], 5.0, places=6)
        self.assertEqual(f["R_EP"], 1)  # the second E1 finds the bay held

    def test_mobile_serves_only_parked_ordinary_e1(self):
        stream = tiny_stream([veh("e1", 1500, 300, "E1", 20.0)], N=1)
        spec = schemes.SchemeSpec.s3("fallback", m=1)
        res = scheme_engine.run_scheme(stream, spec, {"n": 0, "m": 1}, PARAMS)
        f = res["features"]
        self.assertEqual(f["admitted_E1_ordinary"], 1)
        self.assertGreater(f["D_mobile_kwh"], 0.0)
        self.assertLessEqual(f["D_mobile_kwh"], f["mobile_grid_kwh"] + 1e-9)
        self.assertTrue(all(c["ok"] for c in res["checks"]))

    def test_mobile_single_device_no_overlap(self):
        vehicles = [veh("e%d" % i, 1500 + 10 * i, 300, "E1", 20.0) for i in range(4)]
        stream = tiny_stream(vehicles, N=4)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s3("fallback", m=1),
                                       {"n": 0, "m": 1}, PARAMS)
        spans = sorted((e["t_assign"], e["t_release"]) for e in res["mobile_timeline"]
                       if e.get("kind") != "recharge")
        for (a1, b1), (a2, b2) in zip(spans, spans[1:]):
            self.assertLessEqual(b1, a2 + 1e-9)
        self.assertTrue(all(c["ok"] for c in res["checks"]))

    def test_mobile_energy_limit(self):
        fleet = {"count": 1, "capacity_kwh": 12.0, "soc_reserve_kwh": 2.0,
                 "discharge_efficiency": 0.9, "output_kw": 7.2}
        spec = schemes.SchemeSpec.s3("fallback", m=1, mobile_kw=fleet)
        stream = tiny_stream([veh("e1", 1500, 600, "E1", 60.0)], N=1)
        res = scheme_engine.run_scheme(stream, spec, {"n": 0, "m": 1}, PARAMS)
        visits = [e for e in res["mobile_timeline"] if e.get("kind") != "recharge"]
        self.assertTrue(visits)
        for visit in visits:
            self.assertLessEqual(visit["delivered_kwh"], (12.0 - 2.0) * 0.9 + 1e-9)
        self.assertGreater(res["features"]["D_mobile_kwh"], 0.0)

    def test_opening_rule_uses_incremental_opportunity_cost(self):
        # low E1 arrival pressure -> opening a charging bay to an I vehicle pays off
        vehicles = [veh("i1", 1500, 120, "I"), veh("i2", 1501, 120, "I")]
        stream = tiny_stream(vehicles, N=2)
        spec = schemes.SchemeSpec.s2("fallback", open_rule="opportunity",
                                     kappa=1.0, recall_lead_min=15,
                                     fallback_e1_per_hour=0.05)
        res = scheme_engine.run_scheme(stream, spec, {"n": 1, "m": 0}, PARAMS)
        f = res["features"]
        self.assertEqual(f["open_attempts"], 1)
        self.assertEqual(f["opened"], 1)
        self.assertEqual(f["R_I"], 0)

    def test_recall_swap_frees_bay_for_e1(self):
        vehicles = [veh("i0", 1400, 130, "I"), veh("i1", 1500, 100, "I"),
                    veh("e1", 1550, 100, "E1", 10.0)]
        stream = tiny_stream(vehicles, N=2)
        spec = schemes.SchemeSpec.s2("fallback", open_rule="opportunity",
                                     recall_lead_min=60, move_minutes=3,
                                     fallback_e1_per_hour=0.05)
        res = scheme_engine.run_scheme(stream, spec, {"n": 1, "m": 0}, PARAMS)
        f = res["features"]
        self.assertEqual(f["opened"], 1)
        self.assertEqual(f["moves"], 1)
        self.assertEqual(f["admitted_E1_charge"], 1)
        self.assertEqual(f["R_EP"], 0)


class CostLedgerTests(unittest.TestCase):
    def test_cost_items_and_identity(self):
        stream = tiny_stream([veh("e1", 1500, 60, "E1", 20.0)], N=1)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s1("strict"),
                                       {"n": 1, "m": 0}, PARAMS)
        c = social_cost.cost(res["features"], PARAMS)
        self.assertTrue(c["complete"])
        self.assertAlmostEqual(c["items"]["facility_fixed"]["value"],
                               3.112 * 1 * 1, places=6)
        self.assertAlmostEqual(c["items"]["unmet_energy"]["value"],
                               0.3112 * 12.8, places=6)
        manual = sum(item["value"] for item in c["items"].values())
        self.assertAlmostEqual(c["total"], manual, places=6)
        self.assertAlmostEqual(c["total_per_day"], c["total"], places=6)

    def test_missing_parameter_gives_null_not_zero(self):
        params = schemes.CostParams.parse({"c_E": None})
        stream = tiny_stream([veh("e1", 1500, 60, "E1", 20.0)], N=1)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s1("strict"),
                                       {"n": 1, "m": 0}, PARAMS)
        c = social_cost.cost(res["features"], params)
        self.assertFalse(c["complete"])
        self.assertIsNone(c["total"])
        self.assertIn("c_E", c["missing_parameters"])
        self.assertIsNone(c["items"]["unmet_energy"]["value"])

    def test_mobile_costs_are_counted(self):
        stream = tiny_stream([veh("e1", 1500, 300, "E1", 20.0)], N=1)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s3("fallback", m=1),
                                       {"n": 0, "m": 1}, PARAMS)
        c = social_cost.cost(res["features"], PARAMS)
        self.assertGreater(c["items"]["facility_mobile"]["value"], 0)
        self.assertGreater(c["items"]["mobile_active"]["value"], 0)
        self.assertGreater(c["items"]["mobile_energy"]["value"], 0)
        self.assertGreater(c["items"]["resource_energy"]["value"], 0)

    def test_transfers_excluded(self):
        stream = tiny_stream([veh("e1", 1500, 60, "E1", 5.0)], N=1)
        res = scheme_engine.run_scheme(stream, schemes.SchemeSpec.s1("strict"),
                                       {"n": 1, "m": 0}, PARAMS)
        c = social_cost.cost(res["features"], PARAMS)
        self.assertTrue(c["transfers"]["excluded"])
        self.assertNotIn("parking_fee", c["items"])


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.stream = scheme_service.create_synthetic_stream(days=1, N=8,
                                                            arrivals_per_hour=6.0, seed=3)

    def test_run_compare_search(self):
        sid = self.stream.stream_id
        run = scheme_service.run_payload(sid, "S1", {"n": 2, "m": 0}, params=PARAMS)
        self.assertEqual(run["scheme"], "S1")
        self.assertTrue(run["cost"]["complete"])
        self.assertEqual(run["versions"]["math"], schemes.MATH_VERSION)
        cmp = scheme_service.compare_payload(sid, configs={"S1": {"n": 2},
                                                           "S2": {"n": 2},
                                                           "S3": {"n": 2, "m": 1}},
                                             params=PARAMS)
        self.assertEqual([r["scheme"] for r in cmp["rows"]], ["S1", "S2", "S3"])
        self.assertEqual(cmp["rows"][0]["delta_vs_S1"]["total"], 0.0)
        search = scheme_service.search_payload(sid, "S2",
                                               {"n_grid": [0, 1, 2], "m_grid": [0]},
                                               params=PARAMS)
        self.assertEqual(search["grid_points"], 3)
        self.assertIn(search["best"]["n"], [0, 1, 2])
        self.assertTrue(search["declared_domain"]["declared"])

    def test_r0_mode_is_not_evaluable(self):
        stream = scheme_service.create_synthetic_stream(days=1, N=4, mode="R0", seed=4)
        with self.assertRaises(schemes.SchemeError):
            scheme_service.run_payload(stream.stream_id, "S1", {"n": 1, "m": 0},
                                       params=PARAMS)

    def test_exports(self):
        sid = self.stream.stream_id
        run = scheme_service.run_payload(sid, "S1", {"n": 1, "m": 0}, params=PARAMS)
        body, ctype, name = scheme_service.export_run(run["run_id"], "json")
        doc = json.loads(body.decode("utf-8"))
        self.assertEqual(doc["run_id"], run["run_id"])
        self.assertIn("vehicles", doc)
        body, ctype, name = scheme_service.export_run(run["run_id"], "csv")
        self.assertIn(b"session_id", body)
        stream_body, ctype, name = scheme_service.export_stream(sid, "csv")
        self.assertIn(b"arrival", stream_body)

    def test_http_layer_dispatch(self):
        status, body = scheme_service.handle_get("/api/t64/health", {})
        self.assertEqual(status, 200)
        self.assertEqual(body["math_version"], schemes.MATH_VERSION)
        status, body = scheme_service.handle_get(
            "/api/t64/streams/" + self.stream.stream_id, {})
        self.assertEqual(status, 200)
        status, body = scheme_service.handle_post(
            "/api/t64/validate", {"stream_id": self.stream.stream_id,
                                  "scheme": "S1", "config": {"n": 1}})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_job_runner(self):
        sid = self.stream.stream_id
        job = scheme_service._job_run("search", scheme_service._run_job,
                                      {"kind": "search", "stream_id": sid,
                                       "scheme": "S2", "n_grid": [0, 1], "m_grid": [0]})
        for _ in range(100):
            payload = scheme_service.job_payload(job["job_id"])
            if payload["status"] in ("done", "failed"):
                break
            import time
            time.sleep(0.05)
        self.assertEqual(payload["status"], "done", payload.get("error"))
        self.assertEqual(payload["result"]["grid_points"], 2)


if __name__ == "__main__":
    unittest.main()

class MobileBoundaryTests(unittest.TestCase):
    """Hand-calculated boundaries for the two follow-up audit findings (U34)."""

    def _run(self, vehicles, m=1, mobile_kw=None, N=4, W=0, T=2880, station_kw=7.2):
        stream = tiny_stream(vehicles, N=N, W=W, T=T, station_kw=station_kw)
        spec = schemes.SchemeSpec.s3(m=m, mobile_kw=mobile_kw)
        return scheme_engine.run_scheme(stream, spec, {"n": 0, "m": m}, PARAMS)

    def test_accept_power_caps_mobile_delivery(self):
        # 100 available minutes at 3.6 kW -> 6 kWh, not 7.2*100/60 = 12 kWh
        res = self._run([veh("e1", 1500, 115, "E1", 12.0, accept_power=3.6)])
        f = res["features"]
        self.assertAlmostEqual(f["D_mobile_kwh"], 6.0, places=9)
        v = [x for x in res["mobile_timeline"] if x.get("kind") != "recharge"][0]
        self.assertAlmostEqual(v["power_kw"], 3.6, places=9)
        self.assertAlmostEqual(v["delivered_kwh"], 6.0, places=6)
        self.assertAlmostEqual(v["t_charge_end"] - v["t_connect"], 100.0, places=6)
        self.assertTrue(all(c["ok"] for c in res["checks"]),
                        [c for c in res["checks"] if not c["ok"]])

    def test_accept_power_equal_or_above_device_output(self):
        for ap, expected in ((7.2, 12.0), (11.0, 12.0), (None, 12.0)):
            res = self._run([veh("e1", 1500, 115, "E1", 12.0, accept_power=ap)])
            self.assertAlmostEqual(res["features"]["D_mobile_kwh"], expected, places=9,
                                   msg="accept_power=%r" % (ap,))
            v = [x for x in res["mobile_timeline"] if x.get("kind") != "recharge"][0]
            self.assertLessEqual(v["power_kw"], 7.2 + 1e-9)

    def test_missing_accept_power_uses_declared_assumption(self):
        res = self._run([veh("e1", 1500, 115, "E1", 12.0, accept_power=None)],
                        mobile_kw={"assumed_accept_power_kw": 3.6})
        f = res["features"]
        self.assertAlmostEqual(f["D_mobile_kwh"], 6.0, places=9)
        self.assertEqual(f["accept_power_assumption_kw"], 3.6)
        self.assertEqual(f["accept_power_missing_vehicles"], 1)
        v = [x for x in res["mobile_timeline"] if x.get("kind") != "recharge"][0]
        self.assertAlmostEqual(v["power_kw"], 3.6, places=9)
        self.assertTrue(all(c["ok"] for c in res["checks"]),
                        [c for c in res["checks"] if not c["ok"]])

    def test_delivery_at_H_is_not_erased_by_late_release(self):
        # dep = H = 1440, charge ends exactly at 1440, device releases at 1442
        res = self._run([veh("e1", 1400, 40, "E1", 7.2)], T=1440)
        f = res["features"]
        self.assertAlmostEqual(f["D_mobile_kwh"], 3.0, places=9)
        self.assertAlmostEqual(f["D_mobile_by_H_kwh"], 3.0, places=9)
        v = [x for x in res["mobile_timeline"] if x.get("kind") != "recharge"][0]
        self.assertAlmostEqual(v["t_charge_end"], 1440.0, places=6)
        self.assertAlmostEqual(v["t_release"], 1442.0, places=6)
        self.assertTrue(v["credited"])
        checks = {c["name"]: c for c in res["checks"]}
        self.assertTrue(checks["mobile_delivery_by_H_is_credited"]["ok"], checks)
        self.assertTrue(checks["mobile_timeline_matches_ledger"]["ok"], checks)
        self.assertTrue(checks["mobile_vehicle_ledger_matches_agg"]["ok"], checks)
        self.assertTrue(checks["mobile_delivery_not_after_departure"]["ok"], checks)
        rows = [r for r in res["vehicles"] if r["session_id"] == "e1"]
        self.assertAlmostEqual(rows[0]["delivered_kwh"], 3.0, places=6)

    def test_active_minutes_clipped_at_H(self):
        res = self._run([veh("e1", 1400, 40, "E1", 7.2)], T=1440)
        # travel 10 + connect 5 + charge 25 + release 0 (release 1442 > H)
        self.assertAlmostEqual(res["features"]["mobile_active_min"], 40.0, places=6)

    def test_return_travel_clipped_at_H(self):
        # F8: release at t=1435 <= H=1443, the 10-min return leg 1435..1445
        # crosses H, so only 8 of its minutes are inside the accounting window.
        res = self._run([veh("e1", 1400, 43, "E1", 2.16)], N=1, W=0, T=1440,
                        mobile_kw={"recharge_threshold": 0.99})
        f = res["features"]
        self.assertEqual(f["H"], 1443)
        self.assertAlmostEqual(f["D_mobile_kwh"], 2.16, places=9)
        # outbound travel 10 + clipped return travel 8
        self.assertAlmostEqual(f["mobile_travel_min"], 18.0, places=6)
        # 10 travel + 5 connect + 18 charge + 2 release + 8 return = 43
        self.assertAlmostEqual(f["mobile_active_min"], 43.0, places=6)
        recharge = [x for x in res["mobile_timeline"] if x.get("kind") == "recharge"][0]
        # the physical schedule is kept: the return leg still arrives after H
        self.assertAlmostEqual(recharge["t_arrive"], 1445.0, places=6)
        self.assertGreater(recharge["t_arrive"], f["H"])
        self.assertTrue(all(c["ok"] for c in res["checks"]),
                        [c for c in res["checks"] if not c["ok"]])

    def test_no_charge_after_departure_and_power_limit(self):
        res = self._run([veh("e1", 1300, 200, "E1", 10.0, accept_power=1.0)])
        v = [x for x in res["mobile_timeline"] if x.get("kind") != "recharge"][0]
        self.assertLessEqual(v["t_charge_end"], 1500 + 1e-9)
        self.assertAlmostEqual(v["delivered_kwh"],
                               1.0 * (v["t_charge_end"] - v["t_connect"]) / 60.0, places=6)
        self.assertTrue(all(c["ok"] for c in res["checks"]),
                        [c for c in res["checks"] if not c["ok"]])

    def test_multi_device_same_minute_edf_with_accept_power(self):
        vehicles = [veh("a", 1500, 200, "E1", 10.0, accept_power=3.6),
                    veh("b", 1500, 200, "E1", 10.0, accept_power=7.2)]
        res = self._run(vehicles, m=2)
        f = res["features"]
        self.assertEqual(f["mobile_services"], 2)
        self.assertAlmostEqual(f["D_mobile_kwh"],
                               sum(x["delivered_kwh"] for x in res["mobile_timeline"]
                                   if x.get("kind") != "recharge"), places=6)
        self.assertTrue(all(c["ok"] for c in res["checks"]),
                        [c for c in res["checks"] if not c["ok"]])

    def test_export_consistency_for_mobile_boundary(self):
        stream = tiny_stream([veh("e1", 1400, 40, "E1", 7.2)], W=0, T=1440)
        scheme_service._STREAMS[stream.stream_id] = stream
        payload = scheme_service.run_payload(stream.stream_id, "S3", {"n": 0, "m": 1},
                                             params=PARAMS)
        run_id = payload["run_id"]
        body, _, _ = scheme_service.export_run(run_id, "csv")
        rows = body.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(rows) - 1, 1)
        js, _, _ = scheme_service.export_run(run_id, "json")
        doc = json.loads(js.decode("utf-8"))
        self.assertAlmostEqual(doc["features"]["D_mobile_kwh"], 3.0, places=9)
        mob, _, _ = scheme_service.export_run(run_id, "mobile_csv")
        mrows = mob.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(mrows) - 1, 1)
