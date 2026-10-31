"""service_metrics.summarise 的单测：六项指标手工核对与边界（零分母/期初/删失/拒车/缺字段）。

只手工构造 visit dict，不跑仿真；口径见 workbench/service_metrics.py 模块 docstring。
"""
import copy
import unittest
from types import SimpleNamespace

from apps.parking_lab.workbench.service_metrics import RATE_NAMES, METRIC_NAMES, summarise


def visit(vid, t, ev=True, need=None, admitted=True, departed=None,
          energy=10.0, delivered=10.0, departure=None):
    """构造一个最小 visit；rejected 默认未离场（仿真里拒绝车辆不入 active）。"""
    if need is None:
        need = ev
    if departed is None:
        departed = admitted
    if departure is None:
        departure = t + 60 if departed else 300
    return {"vehicle_id": vid, "time_min": t, "is_ev": ev, "needs_charge": need,
            "admitted": admitted, "departed": departed, "departure_min": departure,
            "energy_kwh": energy, "delivered_kwh": delivered}


class TestSummarise(unittest.TestCase):
    def test_fixed_field_names(self):
        out = summarise([])
        for name in METRIC_NAMES:
            self.assertIn(name, out["numerators"] if name in (
                "capacity_unmet_requests", "ev_parking_failures",
                "ice_parking_failures", "departed_shortfall_kwh") else
                out["denominators"] if name in (
                "exogenous_charge_requests", "exogenous_ev_visits",
                "exogenous_ice_visits", "departed_requested_kwh") else out["levels"])
        for name in RATE_NAMES:
            self.assertIn(name, out["rates"])
        self.assertEqual(set(out), {"numerators", "denominators", "rates", "levels",
                                    "missing", "window", "visit_count", "policy"})

    def test_mixed_window(self):
        visits = [
            visit(1, 10, energy=10, delivered=10),                    # 充满并离场
            visit(2, 20, energy=20, delivered=14),                    # 离场缺电 6
            visit(3, 30, admitted=False, departed=False),             # 充电请求被拒
            visit(4, 40, need=False, admitted=False, departed=False),  # 无充电需求被拒
            visit(5, 50, ev=False, admitted=False, departed=False),   # ICE 被拒
            visit(6, 60, ev=False, energy=0, delivered=0),            # ICE 入园离场
            visit(7, 100, energy=15, delivered=5, departed=False,
                  departure=200),                                     # 期末仍在场（窗口 120）
            visit(8, 110, need=False, energy=0, delivered=0, departed=False,
                  departure=180),                                     # 无需求但删失
            visit(900, -5, energy=12, delivered=0, departed=False,
                  departure=150),                                     # 期初已在场（id 声明）
            visit(10, 200, energy=9, delivered=9),                    # 窗口外新到访：完全排除
        ]
        before = copy.deepcopy(visits)
        out = summarise(visits, horizon_min=120, initial_ids={900})
        n, d, r, lv = out["numerators"], out["denominators"], out["rates"], out["levels"]

        self.assertEqual(d["exogenous_ev_visits"], 6)          # 1,2,3,4,7,8
        self.assertEqual(d["exogenous_ice_visits"], 2)          # 5,6
        self.assertEqual(d["exogenous_charge_requests"], 4)     # 1,2,3,7
        self.assertEqual(n["capacity_unmet_requests"], 2)       # 3 被拒 + 2 缺电
        self.assertEqual(n["ev_parking_failures"], 2)           # 3,4
        self.assertEqual(n["ice_parking_failures"], 1)          # 5
        self.assertAlmostEqual(n["departed_shortfall_kwh"], 6.0)
        self.assertAlmostEqual(d["departed_requested_kwh"], 30.0)
        self.assertAlmostEqual(r["capacity_unmet_rate"], 0.5)
        self.assertAlmostEqual(r["ev_parking_failure_rate"], 2 / 6)
        self.assertAlmostEqual(r["ice_parking_failure_rate"], 0.5)
        self.assertAlmostEqual(r["departed_shortfall_energy_rate"], 0.2)
        self.assertEqual(lv["pending_count"], 2)          # 7 与期初 900 期末仍在场
        self.assertAlmostEqual(lv["pending_energy_kwh"], 22.0)  # (15-5) + (12-0)
        self.assertEqual(lv["initial_occupancy_n"], 1)
        self.assertEqual(lv["censored_sessions"], 3)            # 7,8,900
        self.assertEqual(out["missing"], [])
        self.assertEqual(visits, before, "summarise 不得修改 visits")

    def test_zero_denominators_are_none_not_zero(self):
        out = summarise([], horizon_min=60)
        self.assertEqual(out["rates"], {name: None for name in RATE_NAMES})
        self.assertEqual(out["levels"]["pending_count"], 0)
        self.assertEqual(out["levels"]["censored_sessions"], 0)
        self.assertEqual(out["denominators"]["exogenous_charge_requests"], 0)
        self.assertEqual(out["window"], {"horizon_min": 60.0, "exogenous_only": True})

    def test_all_rejected(self):
        visits = [
            visit(1, 0, admitted=False, departed=False, energy=10, delivered=0),
            visit(2, 5, need=False, admitted=False, departed=False, energy=0, delivered=0),
        ]
        out = summarise(visits)
        self.assertEqual(out["denominators"]["exogenous_ev_visits"], 2)
        self.assertEqual(out["numerators"]["ev_parking_failures"], 2)
        self.assertAlmostEqual(out["rates"]["ev_parking_failure_rate"], 1.0)
        self.assertAlmostEqual(out["rates"]["capacity_unmet_rate"], 1.0)
        self.assertIsNone(out["rates"]["ice_parking_failure_rate"])       # 0/0
        self.assertIsNone(out["rates"]["departed_shortfall_energy_rate"])  # 0/0
        self.assertEqual(out["levels"]["censored_sessions"], 0)            # 拒绝不算入园会话

    def test_pending_not_failure(self):
        out = summarise([visit(1, 0, energy=20, delivered=8, departed=False, departure=300)])
        self.assertEqual(out["levels"]["pending_count"], 1)
        self.assertAlmostEqual(out["levels"]["pending_energy_kwh"], 12.0)
        self.assertEqual(out["levels"]["censored_sessions"], 1)
        self.assertEqual(out["numerators"]["capacity_unmet_requests"], 0)
        self.assertEqual(out["numerators"]["departed_shortfall_kwh"], 0.0)
        self.assertAlmostEqual(out["rates"]["capacity_unmet_rate"], 0.0)
        self.assertIsNone(out["rates"]["departed_shortfall_energy_rate"])  # 分母 0

    def test_missing_fields_tolerated(self):
        visits = [
            visit(1, 0, energy=10, delivered=10),
            {**visit(2, 5, energy=8, delivered=8), "delivered_kwh": None},
            {"vehicle_id": 3, "time_min": 1, "needs_charge": True, "admitted": True,
             "departed": True, "departure_min": 40, "energy_kwh": 5, "delivered_kwh": 5},
            {**visit(4, 10, departed=False, departure=300), "energy_kwh": None,
             "delivered_kwh": None},
        ]
        out = summarise(visits)
        self.assertEqual(out["missing"], ["delivered_kwh", "energy_kwh", "is_ev"])
        self.assertEqual(out["denominators"]["exogenous_charge_requests"], 3)  # 2 与 4 计入请求
        self.assertAlmostEqual(out["denominators"]["departed_requested_kwh"], 10.0)
        self.assertAlmostEqual(out["numerators"]["departed_shortfall_kwh"], 0.0)
        self.assertEqual(out["levels"]["pending_count"], 1)
        self.assertAlmostEqual(out["levels"]["pending_energy_kwh"], 0.0)

    def test_initial_occupancy(self):
        pre = visit(900, -5, energy=12, delivered=0, departed=False, departure=150)
        normal = visit(901, 10, energy=8, delivered=6)
        out = summarise([pre, normal], horizon_min=120, initial_ids={900})
        self.assertEqual(out["levels"]["initial_occupancy_n"], 1)
        self.assertEqual(out["denominators"]["exogenous_ev_visits"], 1)   # 期初不计
        self.assertEqual(out["numerators"]["capacity_unmet_requests"], 1)  # 901 缺 2 kWh
        self.assertEqual(out["levels"]["censored_sessions"], 1)            # 期初会话删失

        declared = summarise([normal], initial_ids=2)  # 只声明数量
        self.assertEqual(declared["levels"]["initial_occupancy_n"], 2)
        self.assertEqual(declared["denominators"]["exogenous_ev_visits"], 1)

    def test_horizon_from_config_and_override(self):
        cfg = SimpleNamespace(duration_hours=1, policy="dedicated_by_type")
        visits = [visit(1, 10), visit(2, 70)]
        out = summarise(visits, config=cfg)
        self.assertEqual(out["window"]["horizon_min"], 60.0)
        self.assertEqual(out["denominators"]["exogenous_ev_visits"], 1)
        self.assertEqual(out["policy"], "dedicated_by_type")
        wider = summarise(visits, config=cfg, horizon_min=200)
        self.assertEqual(wider["denominators"]["exogenous_ev_visits"], 2)
        unbounded = summarise(visits)
        self.assertIsNone(unbounded["window"]["horizon_min"])
        self.assertEqual(unbounded["denominators"]["exogenous_ev_visits"], 2)

    def test_no_charge_requests_energy_rate_none(self):
        out = summarise([visit(1, 0, ev=False, energy=0, delivered=0)])
        self.assertEqual(out["rates"]["capacity_unmet_rate"], None)
        self.assertEqual(out["numerators"]["departed_shortfall_kwh"], 0.0)
        self.assertEqual(out["numerators"]["ice_parking_failures"], 0)

    def test_bad_initial_ids(self):
        with self.assertRaises(TypeError):
            summarise([], initial_ids=True)
        with self.assertRaises(ValueError):
            summarise([], initial_ids=-1)


if __name__ == "__main__":
    unittest.main()
