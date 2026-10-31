"""Runtime tests: backend clock, pause/resume ledger guard, explicit replay, Taipei batches."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.continuous import ContinuousEngine, ContinuousError
from apps.parking_lab.workbench.demand import generate
from apps.parking_lab.workbench.simulation import Simulation

BASE = datetime(2026, 10, 30, 3, 30, tzinfo=timezone.utc)


def _stamp(minutes):
    return (BASE + timedelta(minutes=minutes)).isoformat()


def build_collection(root, slots):
    """Write a tiny fake collector tree: each entry is a slot dict."""
    root = Path(root)
    data = root / "data" / "2026-10-30"
    data.mkdir(parents=True)
    (root / "runtime").mkdir(parents=True)
    lines = []
    for slot in slots:
        for index in range(2):
            failed = bool(slot.get("failed"))
            lines.append(json.dumps({
                "slot_start_utc": slot["slot"], "fetch_utc": slot["fetch"],
                "source_batch_update_time": "Fri Oct 30 11:25:00 CST 2026",
                "source_update_time_is_batch_only": True,
                "request_sha256": slot.get("sha"),
                "parking_id": "TPE%04d" % index,
                "baseline_totalcar": 100,
                "availablecar_raw": slot.get("available", [10, 20])[index],
                "availablecar_valid": not failed,
                "data_missing": failed,
                "missing_status": "request_failed" if failed else "ok",
                "http_status": None if failed else 200,
                "error": "IncompleteRead" if failed else None,
                "duplicate_batch": bool(slot.get("duplicate_flag")),
            }, ensure_ascii=False))
    (data / "parking_slots.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "cohort.json").write_text(json.dumps({"cohort_id": "fixture", "size": 2}), encoding="utf-8")
    (root / "config.json").write_text(json.dumps({"interval_seconds": 300}), encoding="utf-8")
    (root / "runtime" / "state.json").write_text(json.dumps({
        "status": "running", "last_success_utc": slots[-1]["fetch"], "gaps": []}), encoding="utf-8")
    return root


FIXTURE_SLOTS = [
    {"slot": _stamp(0), "fetch": _stamp(0.2), "sha": "a" * 8, "available": [10, 20]},
    {"slot": _stamp(5), "fetch": _stamp(5.2), "sha": "b" * 8, "available": [12, 20]},
    {"slot": _stamp(10), "fetch": _stamp(10.2), "sha": "b" * 8, "available": [12, 20], "duplicate_flag": True},
    {"slot": _stamp(20), "fetch": _stamp(20.2), "sha": "c" * 8, "available": [9, 25]},
    {"slot": _stamp(25), "fetch": _stamp(25.2), "sha": "d" * 8, "available": [8, 24]},
]


class DatasourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = build_collection(self.tmp.name, FIXTURE_SLOTS)

    def tearDown(self):
        self.tmp.cleanup()

class EngineTests(unittest.TestCase):
    def make(self, **overrides):
        """加速 60x 的引擎（realtime 恒 1x，需要 60x 就必须显式进入 accelerated）。"""
        raw = {"duration_hours": 1, "arrival_rate_hour": 10}
        raw.update(overrides)
        clock = {"now": 0.0}
        engine = ContinuousEngine(Simulation(Config.parse(raw)), clock=lambda: clock["now"], speed=60.0)
        engine.set_mode("accelerated", 60.0)
        return engine, clock

    def test_tick_advances_and_posts_new_events(self):
        engine, clock = self.make()
        clock["now"] = 10.0
        status = engine.tick()
        self.assertAlmostEqual(status["time_min"], 10.0, places=6)
        self.assertGreater(status["events_total"], 0)
        self.assertEqual(status["ledger"]["entries"], status["events_total"])
        clock["now"] = 25.0
        later = engine.tick()
        self.assertAlmostEqual(later["time_min"], 25.0, places=6)
        self.assertGreater(later["events_total"], status["events_total"])
        self.assertEqual(later["ledger"]["entries"], later["events_total"])

    def test_pause_resume_does_not_double_account(self):
        engine, clock = self.make()
        clock["now"] = 10.0
        first = engine.tick()
        engine.pause()
        for offset in (20.0, 40.0, 80.0):
            clock["now"] = offset
            paused = engine.tick()
            self.assertEqual(paused["time_min"], first["time_min"])
            self.assertEqual(paused["ledger"]["entries"], first["ledger"]["entries"])
        engine.resume()
        clock["now"] = 90.0
        resumed = engine.tick()
        self.assertGreater(resumed["time_min"], first["time_min"])
        seqs = [entry["seq"] for entry in engine.ledger]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))          # unique + monotonic
        self.assertEqual(len(seqs), len(engine.sim.events))            # every event exactly once
        self.assertEqual(resumed["ledger"]["watermark"], len(engine.sim.events))

    def test_rewind_guard_refuses_double_posting(self):
        engine, clock = self.make()
        clock["now"] = 10.0
        engine.tick()
        engine.watermark = len(engine.sim.events) + 5
        with self.assertRaises(ContinuousError):
            engine.post_pending()

    def test_replay_is_explicit_and_does_not_advance_clock(self):
        engine, clock = self.make()
        clock["now"] = 30.0
        engine.tick()
        ledger_before = len(engine.ledger)
        status = engine.start_replay("synthetic")
        self.assertEqual(status["mode"], "replay")
        self.assertEqual(status["mode_label"], "回放 replay")
        self.assertTrue(status["replay"]["active"])
        clock["now"] = 90.0
        frozen = engine.tick()
        self.assertEqual(frozen["time_min"], status["time_min"])       # clock frozen
        self.assertEqual(len(engine.ledger), ledger_before)            # replay not re-accounted
        step = engine.replay_step(3)
        self.assertEqual(step["label"], "回放 replay")
        self.assertEqual(step["cursor"], 3)
        self.assertEqual(len(engine.ledger), ledger_before)
        self.assertTrue(all(item["time_min"] <= engine.sim.time + 1e-9 for item in step["events"]))
        with self.assertRaises(ContinuousError):
            engine.pause()

    def test_online_algorithm_sees_only_past(self):
        config = Config.parse({"duration_hours": 1, "arrival_rate_hour": 30, "seed": 7})
        arrivals = generate(config)
        cutoff = 30.0
        full = Simulation(config, arrivals)
        full.advance(cutoff)
        past = Simulation(config, tuple(a for a in arrivals if a.time_min <= cutoff))
        past.advance(cutoff)
        self.assertEqual(full.learner.forecast(), past.learner.forecast())
        self.assertEqual(len(full.scores), len(past.scores))
        self.assertEqual(full.visits, past.visits)

    def test_cost_ledger_keeps_null(self):
        engine, clock = self.make()
        clock["now"] = 10.0
        engine.tick()
        legacy = engine.status({"total_cost": None, "cost_components": {}})
        self.assertFalse(legacy["ledger"]["cost"]["available"])
        self.assertIsNone(legacy["ledger"]["cost"]["total"])
        v2 = engine.status({"cost": {"currency": "TWD", "price_year": None, "accounting_period": "per_day",
                                     "items": {"user_time": None}, "total": None, "complete": False,
                                     "missing_parameters": ["vot_per_hour"],
                                     "projected": {"note": "预计最终值", "transfers": {"parking_fee": None}},
                                     "relocation_cost": None, "relocation_count": 2, "relocation_blocked": None},
                            "cost_model_version": "v2-2026-10-30", "total_cost": None,
                            "cost_complete": False, "cost_missing_parameters": ["vot_per_hour"]})
        self.assertTrue(v2["ledger"]["cost"]["available"])
        self.assertIsNone(v2["ledger"]["cost"]["total"])
        self.assertEqual(v2["ledger"]["cost"]["missing_parameters"], ["vot_per_hour"])
        self.assertEqual(v2["ledger"]["cost_model_version"], "v2-2026-10-30")
        # 挪车成本已计入 total，账本精选字段必须能看见它；null 不得被吞成缺失键。
        for key in ("projected", "relocation_cost", "relocation_count", "relocation_blocked"):
            self.assertIn(key, v2["ledger"]["cost"])
        self.assertIsNone(v2["ledger"]["cost"]["relocation_cost"])
        self.assertEqual(v2["ledger"]["cost"]["relocation_count"], 2)
        self.assertEqual(v2["ledger"]["cost"]["projected"]["note"], "预计最终值")

    def test_cost_ledger_exposes_relocation_and_projected_from_real_run(self):
        engine, clock = self.make()
        clock["now"] = 10.0
        engine.tick()
        metrics = engine.sim.snapshot().get("metrics") or {}
        block = engine.status(metrics)["ledger"]["cost"]
        self.assertTrue(block["available"])
        for key in ("projected", "relocation_cost", "relocation_count", "relocation_blocked"):
            self.assertIn(key, block)                     # 缺键会吞掉“这笔钱进了总额”的可见性
        self.assertIsInstance(block["projected"], dict)
        self.assertIsInstance(block["relocation_count"], int)
        self.assertTrue(block["relocation_cost"] is None or isinstance(block["relocation_cost"], (int, float)))
        self.assertTrue(block["relocation_blocked"] is None or isinstance(block["relocation_blocked"], int))


class RealtimeClockTests(unittest.TestCase):
    """realtime 恒 1x；暂停/改速/切模式先结算上一区间；恢复不补算；窗口有限。"""

    def engine(self, speed=60.0, **overrides):
        raw = {"duration_hours": 1, "arrival_rate_hour": 0}
        raw.update(overrides)
        clock = {"now": 0.0}
        return ContinuousEngine(Simulation(Config.parse(raw)), clock=lambda: clock["now"], speed=speed), clock

    def test_realtime_ignores_speed_and_is_one_x(self):
        engine, clock = self.engine(speed=60.0)
        self.assertEqual(engine.status()["effective_speed"], 1.0)
        clock["now"] = 60.0
        engine.tick()
        self.assertAlmostEqual(engine.sim.time, 1.0, places=6)

    def test_accelerated_uses_selected_speed(self):
        engine, clock = self.engine(speed=60.0)
        engine.set_mode("accelerated", 60)
        self.assertEqual(engine.status()["effective_speed"], 60.0)
        clock["now"] = 60.0
        engine.tick()
        self.assertAlmostEqual(engine.sim.time, 60.0, places=6)

    def test_realtime_is_one_x_even_after_acceleration(self):
        engine, clock = self.engine(speed=60.0)
        clock["now"] = 60.0
        engine.tick()
        self.assertAlmostEqual(engine.sim.time, 1.0, places=6)   # realtime = 1x
        engine.set_mode("accelerated", 60)
        clock["now"] = 61.0
        engine.tick()
        self.assertAlmostEqual(engine.sim.time, 2.0, places=6)   # 1 秒 × 60
        engine.set_mode("realtime")
        clock["now"] = 121.0
        engine.tick()
        self.assertAlmostEqual(engine.sim.time, 3.0, places=6)   # 回到 1x

    def test_pause_settles_last_unpolled_interval(self):
        engine, clock = self.engine(speed=1.0)
        clock["now"] = 60.0
        engine.pause()                                            # 无中间 tick
        self.assertAlmostEqual(engine.sim.time, 1.0, places=6)
        self.assertEqual(engine.status()["mode"], "paused")

    def test_resume_does_not_backfill_paused_interval(self):
        engine, clock = self.engine(speed=1.0)
        clock["now"] = 60.0
        engine.pause()
        clock["now"] = 600.0                                      # 暂停 9 分钟
        engine.tick()
        self.assertAlmostEqual(engine.sim.time, 1.0, places=6)
        engine.resume()
        clock["now"] = 660.0
        engine.tick()                                             # 只算恢复后的 60 秒
        self.assertAlmostEqual(engine.sim.time, 2.0, places=6)

    def test_set_speed_settles_previous_interval(self):
        engine, clock = self.engine(speed=60.0)
        engine.set_mode("accelerated", 60)
        clock["now"] = 30.0
        engine.set_speed(1)                                       # 60x 下 30 秒先结算成 30 分钟
        self.assertAlmostEqual(engine.sim.time, 30.0, places=6)
        clock["now"] = 90.0
        engine.tick()                                             # accelerated + 1x 的 60 秒 → 1 分钟
        self.assertAlmostEqual(engine.sim.time, 31.0, places=6)
        self.assertEqual(engine.status()["effective_speed"], 1.0)
        engine.set_mode("realtime")
        engine.set_speed(300)                                     # realtime 下记住倍速但仍 1x
        self.assertEqual(engine.status()["effective_speed"], 1.0)

    def test_mode_and_speed_transitions_never_double_account(self):
        engine, clock = self.engine(speed=60.0, arrival_rate_hour=120)
        for moment in (10.0, 20.0, 30.0, 40.0):
            clock["now"] = moment
            engine.tick()
            engine.pause()
            engine.resume()
            engine.set_speed(30)
            engine.set_mode("realtime")
            engine.set_mode("accelerated")
        seqs = [entry["seq"] for entry in engine.ledger]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        self.assertEqual(len(seqs), len(engine.sim.events))
        self.assertEqual(engine.watermark, len(engine.sim.events))

    def test_finite_window_stops_at_horizon(self):
        engine, clock = self.engine(speed=60.0, duration_hours=0.05)  # 3 分钟窗口
        engine.set_mode("accelerated", 60)
        clock["now"] = 60.0
        status = engine.tick()
        self.assertTrue(status["finished"])
        self.assertAlmostEqual(status["time_min"], 3.0, places=6)
        self.assertTrue(status["window"]["finite"])
        self.assertIn("有限窗口", status["window"]["note"])
        clock["now"] = 120.0
        self.assertAlmostEqual(engine.tick()["time_min"], 3.0, places=6)  # 到期不再推进


if __name__ == "__main__":
    unittest.main()
