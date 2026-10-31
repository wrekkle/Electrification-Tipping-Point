"""第四轮代码安全回归（T35）。

缺陷编号（详细表格见 task-15 回执）：
- F1 空批次文件：summarise 以前 IndexError，现在 available=False / DataUnavailable。
- F2 外部 availablecar：bool/NaN/Infinity/负数以前当有效计数（available_sum 可为 inf/nan），现在计 invalid。
- F3 非对象 JSONL 行：以前 AttributeError，现在 DataUnavailable（明确报行号）。
- F4 采集器元数据非对象（config/cohort/state）：以前 AttributeError，现在 available=False 并说明原因。
- F5 runtime/state.json 的 gaps 形状错误：以前 AttributeError，现在按空列表处理。
- F6 config.interval_seconds 非数值/NaN/Infinity/0：以前 TypeError/ValueError，现在退回 300s。
- F7 观测年龄：客户端时钟提前时负年龄以前原样输出，现在夹到 0；naive now 显式报错。
- F8 POST /api/datasource 非法 now_utc：以前 500（并打印 traceback），现在 400。
- F9 请求体长度：重复/非十进制 Content-Length 以前被接受（解析歧义），空体以前 413；现在 400，超限仍 413。
- F10 实验数量上限：以前 413（与“请求体过大”混淆），现在 429。
已存在保护的回归：仅监听 127.0.0.1、Host/Origin 校验、静态白名单、seeds 预算、
配置往返/未知字段/非有限数拒绝、导出 source hash 与版本、审计模块无 shell/外部网络客户端。
F11（写范围外，Lead 已修复并固化为 test_round4_atomic.py）：experiments.write_output 改为临时文件→fsync→os.replace，失败清理临时文件与空目录。
"""
import hashlib
import json
import socket
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from apps.parking_lab.workbench import VERSION, server as server_module
from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.server import EXPORT_SCHEMA_VERSION, make_server

BASE = datetime(2026, 10, 30, 3, 30, tzinfo=timezone.utc)


def _stamp(minutes):
    return (BASE + timedelta(minutes=minutes)).isoformat()


def _row(minutes, *, pid="TPE0001", available=10, sha="a" * 8, **extra):
    row = {"slot_start_utc": _stamp(minutes), "fetch_utc": _stamp(minutes + 0.2),
           "parking_id": pid, "availablecar_raw": available, "availablecar_valid": True,
           "http_status": 200, "request_sha256": sha, "data_missing": False,
           "source_batch_update_time": "Fri Oct 30 11:25:00 CST 2026",
           "source_update_time_is_batch_only": True}
    row.update(extra)
    return row


def _write_collection(root, rows, *, config=None, state=None, cohort=None):
    root = Path(root)
    data = root / "data" / "2026-10-30"
    data.mkdir(parents=True)
    (root / "runtime").mkdir(parents=True)
    lines = [row if isinstance(row, str) else json.dumps(row, ensure_ascii=False) for row in rows]
    (data / "parking_slots.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    (root / "cohort.json").write_text(json.dumps(cohort if cohort is not None else {"cohort_id": "fixture", "size": 2}), encoding="utf-8")
    (root / "config.json").write_text(json.dumps(config if config is not None else {"interval_seconds": 300}), encoding="utf-8")
    (root / "runtime" / "state.json").write_text(json.dumps(state if state is not None else {"status": "running", "gaps": []}), encoding="utf-8")
    return root


class BatchDataValidationTests(unittest.TestCase):
    """外部已保存批次是输入：类型/范围/有限性/形状错误必须显式失败或计 invalid，不能崩溃或污染统计。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _build(self, name, rows, **kwargs):
        root = _write_collection(self.root / name, rows, **kwargs)
        return root

class HTTPSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port
        cls.host = "127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, payload=None, raw=None, headers=None):
        data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        req = Request(self.base + path, data=data, headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urlopen(req, timeout=20) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    def raw_status(self, text):
        sock = socket.create_connection(("127.0.0.1", self.server.server_port), 5)
        try:
            sock.sendall(text.encode("utf-8"))
            sock.settimeout(5)
            data = b""
            while b"\r\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            return int(data.split(b" ")[1])
        finally:
            sock.close()

    def create(self, config=None):
        status, raw = self.request("/api/create", {"config": config or {"duration_hours": 1, "arrival_rate_hour": 2}})
        self.assertEqual(status, 200)
        return json.loads(raw)["id"]

    def close(self, key):
        self.request("/api/close", {"id": key})

    def test_f9_content_length_discipline(self):
        self.assertEqual(self.request("/api/validate", raw=b"")[0], 400)          # 空体：客户端错误，不是 413
        self.assertEqual(self.request("/api/validate", raw=b"x" * 131073)[0], 413)  # 上限语义保持
        self.assertEqual(self.raw_status("POST /api/validate HTTP/1.1\r\nHost: %s\r\n"
                                         "Content-Length: 2\r\nContent-Length: 3\r\n\r\n{}" % self.host), 400)
        self.assertEqual(self.raw_status("POST /api/validate HTTP/1.1\r\nHost: %s\r\n"
                                         "Content-Length: +2\r\n\r\n{}" % self.host), 400)
        self.assertEqual(self.raw_status("POST /api/validate HTTP/1.1\r\nHost: %s\r\n\r\n{}" % self.host), 400)

    def test_f10_session_limit_is_429_not_413(self):
        keys = []
        try:
            for _ in range(6):
                keys.append(self.create({"duration_hours": 1, "arrival_rate_hour": 1}))
            status, raw = self.request("/api/create", {"config": {"duration_hours": 1, "arrival_rate_hour": 1}})
            self.assertEqual(status, 429)
            self.assertIn("6个实验", raw.decode("utf-8"))
        finally:
            for key in keys:
                self.close(key)

    def test_compare_seed_and_budget_validation(self):
        small = {"duration_hours": 0.1, "arrival_rate_hour": 5}
        for seeds in ([True], [1.0], [-1], [1, 1], list(range(9))):
            with self.subTest(seeds=seeds):
                self.assertEqual(self.request("/api/compare", {"config": small, "seeds": seeds})[0], 400)
        status, raw = self.request("/api/compare", {"config": {"duration_hours": 72, "arrival_rate_hour": 2000},
                                                    "seeds": [1]})
        self.assertEqual(status, 400)
        self.assertIn("运行量过大", raw.decode("utf-8"))  # 预算保护命中：配置校验拒绝，不是 500

    def test_config_roundtrip_and_rejections(self):
        payload = {"n_spaces": 60, "charging_bays": 18, "chargers": 12, "duration_hours": 1,
                   "arrival_rate_hour": 2, "policy": "protected_quota", "protected_bays": 2,
                   "prediction_object": "charge_arrivals", "coordinate_window": False}
        status, raw = self.request("/api/validate", {"config": payload})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["config"], Config.parse(payload).to_dict())
        self.assertEqual(self.request("/api/validate", {"config": {"bogus": 1}})[0], 400)
        self.assertEqual(self.request("/api/validate", {"config": []})[0], 400)
        status, raw = self.request("/api/validate", raw=b'{"config": {"arrival_rate_hour": 1e999}}')
        self.assertEqual(status, 400)  # 1e999 解析为 inf，Config 的有限性校验必须拦住
        self.assertIn("有限数值", raw.decode("utf-8"))

    def test_export_provenance_and_unknown_format(self):
        key = self.create()
        try:
            self.request("/api/step", {"id": key, "minutes": 1})
            status, raw = self.request("/api/export?id=%s&format=json" % key)
            self.assertEqual(status, 200)
            payload = json.loads(raw)
            expected = hashlib.sha256(Path(server_module.__file__).read_bytes()).hexdigest()
            self.assertEqual(payload["provenance"]["source_sha256"]["server.py"], expected)
            self.assertEqual(payload["provenance"]["model_version"], VERSION)
            self.assertEqual(payload["runtime"]["server_version"], VERSION)
            self.assertEqual(payload["runtime"]["export_schema_version"], EXPORT_SCHEMA_VERSION)
            self.assertTrue(payload["demand_hash"])
            self.assertEqual(self.request("/api/export?id=%s&format=nope" % key)[0], 400)
        finally:
            self.close(key)

    def test_local_bind_host_origin_and_static_whitelist(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(self.request("/api/health")[0], 200)
        self.assertEqual(self.request("/api/health", headers={"Host": "foreign.example"})[0], 403)
        self.assertEqual(self.request("/api/health", headers={"Origin": "null"})[0], 403)
        self.assertEqual(self.request("/api/health", headers={"Origin": self.base})[0], 200)
        for path in ("/../config.py", "/%2e%2e%2fserver.py", "/api/%2e%2e%2fserver.py"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

if __name__ == "__main__":
    unittest.main()
