"""车位状态展示字段回归：bay_state / bay_frames / occupied / history.energy_kwh。

这些字段只服务前端可视化（车位点阵、状态热力图、累计电量曲线与回放帧），
不参与准入判定、指标口径与成本模型；本测试锁定以下约束：

* 点阵严格对应真实车位数量，不补齐、不伪造，状态编码只取 0–4；
* 热力图帧覆盖整个已运行区间，帧内车位数量与配置一致，帧数有上限；
* 占用清单与 metrics.occupancy 一致，每条都指向合法车位与真实车辆；
* history 的 energy_kwh / charged 与指标同源且电量单调不减；
* export() 的 state 携带同样的展示字段（导出与快照口径一致）。
"""
import unittest

from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.simulation import Simulation

VARIANTS = ((0, 0, 0), (1, 1, 1), (7, 3, 2), (60, 18, 12), (300, 40, 20))
FRAME_LIMIT_MAX = 240
STATE_CHARS = set("01234")


def run_snapshot(n_spaces, charging_bays, chargers, hours=3.0):
    config = Config.parse({
        "n_spaces": n_spaces,
        "charging_bays": charging_bays,
        "chargers": chargers,
        "reserve_fixed": 0,
        "duration_hours": hours,
        "scenario": "steady",
        "seed": 42,
    })
    simulation = Simulation(config)
    simulation.run()
    return simulation, simulation.snapshot()


class SnapshotDisplayFieldsTests(unittest.TestCase):
    def test_bay_state_matches_real_space_count(self):
        for n_spaces, charging_bays, chargers in VARIANTS:
            with self.subTest(n=n_spaces):
                _, snapshot = run_snapshot(n_spaces, charging_bays, chargers)
                self.assertEqual(len(snapshot["bay_state"]), n_spaces)
                self.assertTrue(set(snapshot["bay_state"]) <= STATE_CHARS)
                self.assertEqual(snapshot["bays_total"], n_spaces)
                # 兼容旧的逐位明细只透出前 300 个车位，但不影响 bay_state 的全量覆盖。
                self.assertEqual(len(snapshot["bays"]), min(n_spaces, 300))

    def test_bay_frames_cover_run_span_without_fabricating(self):
        for n_spaces, charging_bays, chargers in VARIANTS:
            with self.subTest(n=n_spaces):
                simulation, snapshot = run_snapshot(n_spaces, charging_bays, chargers)
                frames = snapshot["bay_frames"]
                self.assertLessEqual(len(frames), FRAME_LIMIT_MAX)
                if n_spaces == 0:
                    self.assertTrue(all(frame["s"] == "" for frame in frames))
                    continue
                self.assertGreater(len(frames), 0)
                times = [frame["t"] for frame in frames]
                self.assertEqual(times[0], 0.0)
                self.assertEqual(times, sorted(times))
                self.assertEqual(len(times), len(set(times)))
                self.assertLessEqual(times[-1], snapshot["horizon_min"] + 1e-9)
                self.assertGreaterEqual(times[-1], snapshot["time_min"] - 10.0)
                for frame in frames:
                    self.assertEqual(len(frame["s"]), n_spaces)
                self.assertTrue(set("".join(frame["s"] for frame in frames)) <= STATE_CHARS)

    def test_occupied_matches_metrics_and_real_bays(self):
        for n_spaces, charging_bays, chargers in VARIANTS:
            with self.subTest(n=n_spaces):
                _, snapshot = run_snapshot(n_spaces, charging_bays, chargers)
                occupied = snapshot["occupied"]
                self.assertEqual(len(occupied), snapshot["metrics"]["occupancy"])
                for item in occupied:
                    self.assertGreaterEqual(item["bay"], 0)
                    self.assertLess(item["bay"], n_spaces)
                    self.assertGreaterEqual(item["power_kw"], 0.0)
                    vehicle = item["vehicle"]
                    self.assertIsInstance(vehicle, dict)
                    for key in ("is_ev", "needs_charge", "departure_min"):
                        self.assertIn(key, vehicle)

    def test_history_energy_fields_share_metric_source(self):
        for n_spaces, charging_bays, chargers in VARIANTS:
            with self.subTest(n=n_spaces):
                _, snapshot = run_snapshot(n_spaces, charging_bays, chargers)
                history = snapshot["history"]
                self.assertGreater(len(history), 0)
                energies = [row["energy_kwh"] for row in history]
                self.assertEqual(energies, sorted(energies))
                last = history[-1]
                self.assertAlmostEqual(last["energy_kwh"],
                                       snapshot["metrics"]["energy_delivered_kwh"], places=6)
                self.assertEqual(last["charged"], snapshot["metrics"]["charge_completed"])

    def test_export_state_carries_display_fields(self):
        simulation, snapshot = run_snapshot(60, 18, 12)
        state = simulation.export()["state"]
        for key in ("bay_state", "bay_frames", "occupied"):
            self.assertIn(key, state)
        self.assertEqual(state["bay_state"], snapshot["bay_state"])
        self.assertEqual(len(state["bay_frames"]), len(snapshot["bay_frames"]))


if __name__ == "__main__":
    unittest.main()
