"""回放快照一致性：同一快照派生全部回放视图，时间与状态不跨帧错配。

回归目标（对应“顶部时钟 08:57、点阵 08:54、KPI 取另一组历史记录”的旧问题）：
- 快照时间与 history 行、点阵状态、KPI 标量、图表/热力图截止一致；
- 回放位置是后端真实状态快照，同刻多事件合并，位置严格递增、不插值；
- 快照未记录的字段显式为空/未记录，不冒用当前运行值；
- 覆盖起点、终点、来回拖动、退出回放。
"""
import json
import threading
import unittest
from urllib.request import Request, urlopen

from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.continuous import ContinuousEngine
from apps.parking_lab.workbench.server import make_server
from apps.parking_lab.workbench.simulation import Simulation

CONFIG = {"n_spaces": 16, "charging_bays": 6, "chargers": 4, "duration_hours": 4,
          "arrival_rate_hour": 80, "scenario": "peaks", "seed": 7}


def build_sim():
    sim = Simulation(Config.parse(CONFIG))
    sim.run()
    return sim


class SnapshotConsistencyTests(unittest.TestCase):
    def test_each_snapshot_internally_consistent(self):
        sim = build_sim()
        snaps = sim.replay_snapshots
        self.assertGreater(len(snaps), 10)
        self.assertEqual(snaps[0]["t"], 0)
        self.assertEqual(snaps[0]["event_seq"], 0)
        # 终点快照：事件结束后仍在充电/累计电量，末快照必须覆盖到窗口结束
        self.assertAlmostEqual(snaps[-1]["t"], sim.horizon, places=9)
        previous = None
        for index, snap in enumerate(snaps):
            with self.subTest(index=index, t=snap["t"]):
                metrics = snap["metrics"]
                states = snap["bay_state"]
                self.assertEqual(len(states), sim.config.n_spaces)
                self.assertEqual(metrics["occupancy"], sum(1 for code in states if code != "0"))
                self.assertEqual(metrics["charging_now"], states.count("3"))
                row = sim.history[snap["history_index"]]
                self.assertAlmostEqual(row["time_min"], snap["t"], places=12)
                self.assertEqual(row["occupancy"], metrics["occupancy"])
                self.assertEqual(row["charging"], metrics["charging_now"])
                self.assertAlmostEqual(row["power_kw"], metrics["current_power_kw"], places=6)
                self.assertAlmostEqual(row["energy_kwh"], metrics["energy_delivered_kwh"], places=6)
                self.assertEqual(row["charged"], metrics["charge_completed"])
                self.assertEqual(row["arrivals"], metrics["arrivals"])
                self.assertEqual(row["rejected"], metrics["rejected"])
                self.assertEqual(metrics["rejected_ev"] + metrics["rejected_ice"], metrics["rejected"])
                frames = [frame for frame in sim.bay_frames if frame["t"] <= snap["t"] + 1e-9]
                self.assertTrue(frames)
                self.assertLessEqual(frames[-1]["t"], snap["t"] + 1e-9)
                self.assertTrue(snap["roster_available"])
                self.assertEqual(len(snap["roster"]), metrics["occupancy"])
                self.assertEqual(sum(1 for item in snap["roster"] if item["power_kw"] > 0),
                                 metrics["charging_now"])
                if previous is not None:
                    # 位置严格递增：同一时刻多事件只产生一个快照，不产生插值位置。
                    # 终点快照允许 event_seq 不变（纯时长推进补记终态），但时间仍必须前进。
                    self.assertGreater(snap["t"], previous["t"])
                    if index < len(snaps) - 1:
                        self.assertGreater(snap["event_seq"], previous["event_seq"])
                    else:
                        self.assertGreaterEqual(snap["event_seq"], previous["event_seq"])
                previous = snap
        # 确实存在“同一时刻多个事件合成一个快照”的批次（seq 一次跳多）
        self.assertTrue(any(snaps[i + 1]["event_seq"] - snaps[i]["event_seq"] > 1
                            for i in range(len(snaps) - 1)))

    def test_engine_positions_and_jump_use_snapshot_times(self):
        sim = build_sim()
        engine = ContinuousEngine(sim)
        status = engine.start_replay("synthetic")
        replay = status["replay"]
        snaps = sim.replay_snapshots
        self.assertEqual(replay["basis"], "state_snapshot")
        self.assertEqual(len(replay["positions"]), len(snaps))
        self.assertEqual([position["t"] for position in replay["positions"]],
                         [snap["t"] for snap in snaps])
        last = engine.replay_jump(len(snaps) - 1)
        self.assertEqual(last["cursor"], len(snaps) - 1)
        self.assertAlmostEqual(last["t"], sim.horizon, places=9)
        back = engine.replay_jump(1)
        self.assertEqual(back["cursor"], 1)
        self.assertAlmostEqual(back["t"], snaps[1]["t"], places=12)
        clamped = engine.replay_jump(10 ** 6)
        self.assertEqual(clamped["cursor"], len(snaps) - 1)
        engine.exit_replay()
        self.assertFalse(engine.status({})["replay"]["active"])

    def test_large_lot_snapshot_omits_vehicle_roster(self):
        sim = Simulation(Config.parse({"n_spaces": 301, "charging_bays": 30, "chargers": 18,
                                       "duration_hours": 1, "arrival_rate_hour": 120, "seed": 3}))
        sim.advance(30)
        snap = sim.replay_snapshots[-1]
        self.assertFalse(snap["roster_available"])
        self.assertIsNone(snap["roster"])


class ReplayHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=60) as response:
            return json.loads(response.read())

    def test_snapshot_payload_cutoffs_and_labels(self):
        created = self.request("/api/create", {"config": {
            "duration_hours": 2, "arrival_rate_hour": 60, "n_spaces": 16,
            "charging_bays": 6, "chargers": 4, "seed": 11}})
        key = created["id"]
        try:
            self.request("/api/run", {"id": key})  # 先产生事件，回放快照才有内容
            started = self.request("/api/replay/start", {"id": key, "source": "synthetic"})
            total = started["continuous"]["replay"]["total"]
            self.assertGreater(total, 5)
            for index in (0, total // 2, total - 1, 0, total - 1):
                payload = self.request("/api/replay/snapshot", {"id": key, "index": index})
                with self.subTest(index=index):
                    self.assertEqual(payload["replay"]["index"], index)
                    self.assertEqual(payload["replay"]["total"], total)
                    # 时钟、点阵、KPI、图表截止都由同一快照派生
                    last = payload["history"][-1]
                    self.assertAlmostEqual(last["time_min"], payload["time_min"], places=9)
                    self.assertAlmostEqual(payload["replay"]["history_t"], payload["time_min"], places=9)
                    self.assertEqual(len(payload["bay_state"]), payload["metrics"]["capacity"])
                    self.assertEqual(sum(1 for code in payload["bay_state"] if code != "0"),
                                     payload["metrics"]["occupancy"])
                    self.assertEqual(payload["bay_state"].count("3"), payload["metrics"]["charging_now"])
                    self.assertEqual(last["occupancy"], payload["metrics"]["occupancy"])
                    self.assertEqual(last["charging"], payload["metrics"]["charging_now"])
                    self.assertAlmostEqual(last["power_kw"], payload["metrics"]["current_power_kw"], places=6)
                    self.assertAlmostEqual(last["energy_kwh"], payload["metrics"]["energy_delivered_kwh"], places=6)
                    self.assertTrue(all(frame["t"] <= payload["time_min"] + 1e-9
                                        for frame in payload["bay_frames"]))
                    self.assertTrue(all(event["seq"] <= payload["replay"]["event_seq"]
                                        for event in payload["events"]))
                    # 该历史时刻未整体记录的量不得冒充当前值
                    self.assertIsNone(payload["metrics"]["mean_occupancy_rate"])
                    self.assertIn("非回放时刻", payload["replay_diagnostics"]["note"])
                    self.assertTrue(payload["occupied_available"])
                    # 回放数据与当前运行诊断分开：诊断时刻是当前 sim.time
                    self.assertGreaterEqual(payload["replay_diagnostics"]["diagnostics_time_min"],
                                            payload["time_min"])
            jumped = self.request("/api/replay/jump", {"id": key, "index": 1})
            self.assertEqual(jumped["replay_jump"]["cursor"], 1)
            middle = self.request("/api/replay/jump", {"id": key, "index": total // 2})
            self.assertEqual(middle["replay_jump"]["cursor"], total // 2)
            exited = self.request("/api/replay/exit", {"id": key})
            self.assertFalse(exited["continuous"]["replay"]["active"])
            self.assertNotEqual(exited["continuous"]["mode"], "replay")
        finally:
            self.request("/api/close", {"id": key})


if __name__ == "__main__":
    unittest.main()
