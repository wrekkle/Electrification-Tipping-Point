import concurrent.futures
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from apps.parking_lab.workbench.server import make_server


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self, path, payload=None, raw=None, headers=None):
        data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        request = Request(self.base + path, data=data, headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urlopen(request, timeout=20) as response:
                return response.status, response.read(), dict(response.headers)
        except HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def create(self):
        status, raw, _ = self.request("/api/create", {"config": {"duration_hours": 1, "arrival_rate_hour": 10}})
        self.assertEqual(status, 200)
        return json.loads(raw)["id"]

    def test_health_static_and_whitelist(self):
        for path in ("/", "/app.js", "/style.css", "/api/health", "/api/presets"):
            with self.subTest(path=path): self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(self.request("/../config.py")[0], 404)
        self.assertEqual(self.request("/%2e%2e/config.py")[0], 404)

    def test_create_step_reset_run_and_exports(self):
        key = self.create()
        status, raw, _ = self.request("/api/step", {"id": key, "minutes": 5})
        self.assertEqual(status, 200); self.assertEqual(json.loads(raw)["time_min"], 5)
        self.assertEqual(self.request("/api/reset", {"id": key})[0], 200)
        status, raw, _ = self.request("/api/run", {"id": key})
        self.assertTrue(json.loads(raw)["finished"])
        for kind in ("json", "csv", "events_csv", "predictions_csv"):
            status, content, headers = self.request(f"/api/export?id={key}&format={kind}")
            self.assertEqual(status, 200); self.assertIn("attachment", headers["Content-Disposition"])
            if kind == "json": self.assertIn("source_sha256", json.loads(content)["provenance"])
            else: self.assertGreater(len(content), 3)
        self.assertEqual(self.request("/api/close", {"id": key})[0], 200)

    def test_http_errors_do_not_mutate_session(self):
        key = self.create()
        for payload in ({"id": key, "minutes": -1}, {"id": key, "minutes": "5"}, {"id": key, "minutes": True}):
            self.assertEqual(self.request("/api/step", payload)[0], 400)
        self.assertEqual(self.request("/api/reset", {"id": key, "config": {"n_spaces": 0}})[0], 400)
        self.assertEqual(self.request("/api/state?id=missing")[0], 404)
        self.assertEqual(self.request("/api/run", {"id": []})[0], 404)
        self.assertEqual(self.request("/api/create", raw=b'{"config":{"ev_share":NaN}}')[0], 400)
        self.assertEqual(self.request("/api/create", raw=b'[]')[0], 400)
        self.assertEqual(self.request("/api/create", raw=b'x' * 131073)[0], 413)
        self.assertEqual(json.loads(self.request(f"/api/state?id={key}")[1])["time_min"], 0)
        self.request("/api/close", {"id": key})

    def test_empty_csv_has_headers(self):
        key = self.create()
        raw = self.request(f"/api/export?id={key}&format=csv")[1].decode("utf-8-sig")
        self.assertIn("vehicle_id", raw)
        self.request("/api/close", {"id": key})

    def test_origin_and_host(self):
        self.assertEqual(self.request("/api/health", headers={"Host": "foreign.example"})[0], 403)
        self.assertEqual(self.request("/api/create", {}, headers={"Origin": "https://foreign.example"})[0], 403)

    def test_concurrent_steps_serialized(self):
        key = self.create()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.request("/api/step", {"id": key, "minutes": 1})[0], range(2)))
        self.assertEqual(results, [200, 200])
        self.assertEqual(json.loads(self.request(f"/api/state?id={key}")[1])["time_min"], 2)
        self.request("/api/close", {"id": key})

    def test_compare_paired_flow(self):
        status, raw, _ = self.request("/api/compare", {"config": {"duration_hours": 1, "arrival_rate_hour": 10}, "seeds": [3, 4, 5]})
        self.assertEqual(status, 200)
        result = json.loads(raw)
        self.assertEqual(len(result["rows"]), 4)
        self.assertEqual(len(result["runs"]), 12)


    def test_continuous_advance_pause_resume_ledger(self):
        key = self.create()
        status, raw, _ = self.request("/api/mode", {"id": key, "mode": "accelerated", "speed": 60})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["continuous"]["mode"], "accelerated")
        status, raw, _ = self.request("/api/advance", {"id": key, "elapsed_seconds": 30})
        state = json.loads(raw)
        self.assertGreater(state["time_min"], 0)
        entries = state["continuous"]["ledger"]["entries"]
        self.assertGreater(entries, 0)
        status, raw, _ = self.request("/api/pause", {"id": key})
        self.assertEqual(status, 200)
        paused_at = json.loads(raw)
        # 暂停先结算“最后一次轮询到暂停请求”的墙体时间：只允许略微前进（60x 下毫秒级），不得回退或丢弃
        self.assertGreaterEqual(paused_at["time_min"], state["time_min"])
        self.assertLess(paused_at["time_min"] - state["time_min"], 5)
        paused_entries = paused_at["continuous"]["ledger"]["entries"]
        status, raw, _ = self.request("/api/advance", {"id": key, "elapsed_seconds": 120})
        paused = json.loads(raw)
        self.assertEqual(paused["time_min"], paused_at["time_min"])            # 暂停区间不推进
        self.assertEqual(paused["continuous"]["ledger"]["entries"], paused_entries)  # 暂停不重复入账
        self.request("/api/resume", {"id": key})
        status, raw, _ = self.request("/api/advance", {"id": key, "elapsed_seconds": 30})
        resumed = json.loads(raw)
        self.assertGreater(resumed["time_min"], state["time_min"])
        ledger = resumed["continuous"]["ledger"]
        self.assertEqual(ledger["entries"], ledger["last_seq"])
        self.assertEqual(ledger["entries"], ledger["watermark"])
        status, content, headers = self.request(f"/api/export?id={key}&format=ledger_csv")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn("seq", content.decode("utf-8-sig").splitlines()[0])
        status, raw, _ = self.request(f"/api/export?id={key}&format=json")
        payload = json.loads(raw)
        self.assertEqual(payload["runtime"]["continuous"]["mode"], payload["state"]["continuous"]["mode"])
        self.assertEqual(len(payload["runtime"]["ledger"]), payload["state"]["continuous"]["ledger"]["entries"])
        self.assertEqual(payload["runtime"]["cost_model_version"], payload["state"]["cost_model_version"])
        self.request("/api/close", {"id": key})

    def test_advance_cost_block_matches_state(self):
        """推进响应的 cost 块必须与 /api/state 同源同口径（v2 分项，而非 available=false 兜底）。"""
        key = self.create()
        self.request("/api/mode", {"id": key, "mode": "accelerated", "speed": 60})
        status, raw, _ = self.request("/api/advance", {"id": key, "elapsed_seconds": 30})
        self.assertEqual(status, 200)
        advanced = json.loads(raw)["continuous"]["ledger"]["cost"]
        status, raw, _ = self.request(f"/api/state?id={key}")
        self.assertEqual(status, 200)
        state_cost = json.loads(raw)["continuous"]["ledger"]["cost"]
        self.assertTrue(advanced.get("available"), advanced)
        self.assertNotIn("reason", advanced)
        for field in ("projected", "relocation_cost", "relocation_count", "relocation_blocked"):
            self.assertIn(field, advanced)
        self.assertEqual(sorted(advanced.keys()), sorted(state_cost.keys()))
        self.assertEqual(advanced.get("total"), state_cost.get("total"))
        self.assertEqual(advanced.get("complete"), state_cost.get("complete"))
        self.request("/api/close", {"id": key})

    def test_replay_requires_explicit_label(self):
        key = self.create()
        # realtime 恒 1x：60 实时秒只推进 1 分钟；要 60 分钟需显式进入 accelerated
        self.request("/api/mode", {"id": key, "mode": "accelerated", "speed": 60})
        self.request("/api/advance", {"id": key, "elapsed_seconds": 60})
        status, raw, _ = self.request("/api/replay/start", {"id": key, "source": "synthetic"})
        state = json.loads(raw)
        self.assertEqual(state["continuous"]["mode"], "replay")
        self.assertEqual(state["continuous"]["mode_label"], "回放 replay")
        self.assertTrue(state["continuous"]["replay"]["active"])
        frozen = state["time_min"]
        status, raw, _ = self.request("/api/advance", {"id": key, "elapsed_seconds": 30})
        self.assertEqual(json.loads(raw)["time_min"], frozen)
        status, raw, _ = self.request("/api/replay/step", {"id": key, "count": 2})
        step = json.loads(raw)["replay_step"]
        self.assertEqual(step["label"], "回放 replay")
        self.assertGreaterEqual(step["cursor"], 1)
        status, raw, _ = self.request("/api/replay/exit", {"id": key})
        self.assertEqual(json.loads(raw)["continuous"]["mode"], "accelerated")  # 退回进入回放前的模式
        self.request("/api/close", {"id": key})

    def test_mode_and_speed_validation(self):
        key = self.create()
        for payload in ({"id": key, "mode": "bogus"}, {"id": key, "speed": 0}, {"id": key, "speed": "fast"}):
            with self.subTest(payload=payload):
                self.assertEqual(self.request("/api/mode", payload)[0], 400)
        self.assertEqual(self.request("/api/advance", {"id": key, "elapsed_seconds": -1})[0], 400)
        self.assertEqual(self.request("/api/replay/step", {"id": key, "count": 1})[0], 400)
        self.request("/api/close", {"id": key})

    def test_continuous_realtime_is_one_x_and_transitions_settle(self):
        key = self.create()
        state = json.loads(self.request(f"/api/state?id={key}")[1])
        self.assertEqual(state["continuous"]["mode"], "realtime")
        status, raw, _ = self.request("/api/advance", {"id": key, "elapsed_seconds": 60})
        state = json.loads(raw)
        self.assertAlmostEqual(state["time_min"], 1.0, places=6)            # realtime 恒 1x
        self.assertEqual(state["continuous"]["effective_speed"], 1.0)
        status, raw, _ = self.request("/api/pause", {"id": key})
        paused = json.loads(raw)
        self.assertGreaterEqual(paused["time_min"], state["time_min"])       # 暂停先结算上一区间
        status, raw, _ = self.request("/api/advance", {"id": key, "elapsed_seconds": 300})
        self.assertEqual(json.loads(raw)["time_min"], paused["time_min"])    # 暂停区间不推进
        self.request("/api/resume", {"id": key})
        self.request("/api/mode", {"id": key, "mode": "accelerated", "speed": 60})
        status, raw, _ = self.request("/api/advance", {"id": key, "elapsed_seconds": 30})
        fast = json.loads(raw)
        self.assertGreater(fast["time_min"], paused["time_min"] + 29)
        self.assertEqual(fast["continuous"]["effective_speed"], 60.0)
        self.request("/api/mode", {"id": key, "mode": "realtime"})
        status, raw, _ = self.request("/api/advance", {"id": key, "elapsed_seconds": 60})
        back = json.loads(raw)
        self.assertGreater(back["time_min"], fast["time_min"] + 0.9)
        self.assertLess(back["time_min"], fast["time_min"] + 1.1)
        self.assertTrue(back["continuous"]["window"]["finite"])
        self.request("/api/close", {"id": key})

if __name__ == "__main__":
    unittest.main()
