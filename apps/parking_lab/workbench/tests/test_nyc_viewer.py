# -*- coding: utf-8 -*-
"""NYC 半合成结果查看器后端测试：进程内 HTTP，沿用 test_http.py 的方式。"""
import csv
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from apps.parking_lab.workbench.server import make_server

REPO_ROOT = Path(__file__).resolve().parents[4]
SAMPLE_DIR = REPO_ROOT / "research" / "nyc_semisynthetic_20261103" / "v1" / "viewer_sample"
if not SAMPLE_DIR.is_dir():
    raise unittest.SkipTest(
        "viewer sample fixture is not part of the public repository")
R0_RUN = "R0__nyc-bri__observed"
R1_RUN = "R1__nyc-bri__R1__slack25__h0__strict__rep0"
R2_RUN = "R2__nyc-bri__R2__bg060__h0__strict__rep0"


class _NycHTTPCase(unittest.TestCase):
    """起一个真实 HTTP 服务；NYC_VIEWER_DIR 指向 v1 数据目录，NYC_VIEWER_DIR_V2 可另指 v2。"""

    viewer_dir = None
    viewer_dir_v2 = None
    dataset_env = None

    _ENV_KEYS = ("NYC_VIEWER_DIR", "NYC_VIEWER_DIR_V2", "NYC_VIEWER_DIR_V3",
                 "NYC_VIEWER_DATASET")

    @classmethod
    def setUpClass(cls):
        cls._previous_env = {key: os.environ.get(key) for key in cls._ENV_KEYS}
        if cls.viewer_dir is None:
            os.environ.pop("NYC_VIEWER_DIR", None)
        else:
            os.environ["NYC_VIEWER_DIR"] = str(cls.viewer_dir)
        if cls.viewer_dir_v2 is None:
            os.environ.pop("NYC_VIEWER_DIR_V2", None)
        else:
            os.environ["NYC_VIEWER_DIR_V2"] = str(cls.viewer_dir_v2)
        if cls.dataset_env is None:
            os.environ.pop("NYC_VIEWER_DATASET", None)
        else:
            os.environ["NYC_VIEWER_DATASET"] = str(cls.dataset_env)
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        for key, value in cls._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def get(self, path):
        request = Request(self.base + path, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=20) as response:
                return response.status, response.read(), dict(response.headers)
        except HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def get_json(self, path):
        status, raw, headers = self.get(path)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            self.fail(path + " 未返回 JSON：" + repr(raw[:300]))
        return status, payload, headers

    def assert_json_error(self, status, payload, expected_status):
        self.assertEqual(status, expected_status, payload)
        self.assertIsInstance(payload, dict)
        self.assertIn("error", payload)
        self.assertIsInstance(payload["error"], str)
        self.assertTrue(payload["error"])


class SampleViewerTests(_NycHTTPCase):
    viewer_dir = SAMPLE_DIR

    def test_health_reports_sample_data(self):
        status, payload, _ = self.get_json("/api/nyc/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "nyc-viewer")
        self.assertTrue(payload["exists"])
        self.assertTrue(payload["index_present"])
        self.assertEqual(payload["status"], "sample")
        self.assertEqual(payload["runs"], 3)
        self.assertEqual(Path(payload["data_dir"]), SAMPLE_DIR.resolve())

    def test_index_contract_and_sample_status(self):
        status, payload, _ = self.get_json("/api/nyc/index")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "sample")
        self.assertIn("不是研究结果", payload["warning"])
        self.assertEqual(payload["schema_version"], "nyc_semisynthetic_viewer/v1")
        self.assertEqual(set(payload["mode_labels"]), {"R0", "R1", "R2"})
        self.assertEqual(len(payload["sites"]), 1)
        self.assertEqual(payload["sites"][0]["site_id"], "nyc-bri")
        run_ids = [run["run_id"] for run in payload["runs"]]
        for run_id in (R0_RUN, R1_RUN, R2_RUN):
            self.assertIn(run_id, run_ids)
        self.assertEqual(payload["provenance"]["root_seed"], 20261103)

    def test_r1_run_payload(self):
        status, payload, _ = self.get_json("/api/nyc/run/" + R1_RUN)
        self.assertEqual(status, 200)
        self.assertEqual(payload["run_id"], R1_RUN)
        self.assertEqual(payload["mode"], "R1")
        self.assertEqual(payload["series"]["bin_minutes"], 15)
        self.assertEqual(len(payload["series"]["bins"]), 672)
        self.assertEqual(len(payload["rows"]), 5)
        self.assertEqual(payload["summary"]["best_n"], 3)
        self.assertEqual(len(payload["selected"]["vehicles"]), 2)
        self.assertEqual(payload["provenance"]["seed_registry"]["root_seed"], 20261103)

    def test_r0_run_payload_has_observed_and_no_rows(self):
        status, payload, _ = self.get_json("/api/nyc/run/" + R0_RUN)
        self.assertEqual(status, 200)
        self.assertEqual(payload["mode"], "R0")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(len(payload["observed"]["sessions"]), 2)
        self.assertEqual(payload["observed"]["registered_bays"], 5)

    def test_r2_run_payload(self):
        status, payload, _ = self.get_json("/api/nyc/run/" + R2_RUN)
        self.assertEqual(status, 200)
        self.assertEqual(payload["mode"], "R2")
        self.assertEqual(payload["cohort"]["n_I"], 4200)

    def test_missing_run_and_world_return_404_json(self):
        for path in ("/api/nyc/run/does-not-exist", "/api/nyc/world/no-such-world"):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, 404)

    def test_exports(self):
        status, raw, headers = self.get("/api/nyc/export/" + R1_RUN + "?format=json")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn(".json", headers["Content-Disposition"])
        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(payload["run_id"], R1_RUN)

        status, raw, headers = self.get("/api/nyc/export/" + R1_RUN + "?format=curve_csv")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers["Content-Type"])
        text = raw.decode("utf-8-sig")
        header = text.splitlines()[0]
        self.assertIn("n", header)
        self.assertIn("J", header)
        self.assertIn("capital", header)
        self.assertIn("R_EP", header)
        self.assertGreater(len(text.splitlines()), 3)

        status, raw, _ = self.get("/api/nyc/export/" + R1_RUN + "?format=outcomes_csv")
        self.assertEqual(status, 200)
        text = raw.decode("utf-8-sig")
        self.assertIn("session_id", text.splitlines()[0])
        self.assertIn("sample-0001", text)

    def test_export_missing_objects_return_404(self):
        cases = (
            "/api/nyc/export/" + R0_RUN + "?format=curve_csv",       # R0 无 rows
            "/api/nyc/export/" + R0_RUN + "?format=outcomes_csv",    # R0 无 selected
            "/api/nyc/export/" + R1_RUN + "?format=world_json",      # 样例无 world 文件
            "/api/nyc/export/no-such-run?format=json",
        )
        for path in cases:
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, 404)

    def test_bad_export_format_returns_400(self):
        for path in ("/api/nyc/export/" + R1_RUN + "?format=xml",
                     "/api/nyc/export/" + R1_RUN + "?format=jso"):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, 400)

    def test_export_defaults_to_json(self):
        status, payload, headers = self.get_json("/api/nyc/export/" + R1_RUN)
        self.assertEqual(status, 200)
        self.assertEqual(payload["run_id"], R1_RUN)
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_traversal_ids_are_rejected(self):
        paths = (
            "/api/nyc/run/..",
            "/api/nyc/run/../config.py",
            "/api/nyc/run/%2e%2e%2f%2e%2e%2fserver.py",
            "/api/nyc/run/a%2fb",
            "/api/nyc/run/bad!name",
            "/api/nyc/world/..%2f..%2fserver.py",
            "/api/nyc/export/..%2f..%2fserver.py?format=json",
        )
        for path in paths:
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, 400)
        # 确认没有把仓库文件当结果返回
        status, raw, _ = self.get("/api/nyc/run/%2e%2e%2f%2e%2e%2fserver.py")
        self.assertNotIn(b"ThreadingHTTPServer", raw)

    def test_static_nyc_page_and_assets(self):
        cases = (
            ("/nyc/", "text/html", "NYC 半合成研究结果"),
            ("/nyc/index.html", "text/html", "/nyc/app.js"),
            ("/nyc/app.js", "text/javascript", "/api/nyc/index"),
            ("/nyc/style.css", "text/css", "--brand"),
        )
        for path, content_type, needle in cases:
            with self.subTest(path=path):
                status, raw, headers = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(content_type, headers["Content-Type"])
                self.assertIn(needle, raw.decode("utf-8"))

    def test_main_lab_page_links_to_nyc_viewer(self):
        status, raw, headers = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b'href="/nyc/"', raw)

    def test_static_whitelist_blocks_traversal(self):
        for path in ("/nyc/../workbench/server.py", "/nyc/%2e%2e/%2e%2e/config.py",
                     "/nyc/nope.js"):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, 404)

    def test_unknown_nyc_route_returns_404_json(self):
        status, payload, _ = self.get_json("/api/nyc/nope")
        self.assert_json_error(status, payload, 404)

    def test_existing_lab_endpoints_unchanged(self):
        for path in ("/api/health", "/api/presets"):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assertEqual(status, 200)
        status, payload, _ = self.get_json("/api/health")
        self.assertTrue(payload["ok"])


class EmptyViewerTests(_NycHTTPCase):
    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.viewer_dir = Path(cls._temp.name) / "missing-viewer"
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._temp.cleanup()

    def test_index_returns_empty_status_not_500(self):
        status, payload, _ = self.get_json("/api/nyc/index")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "empty")
        self.assertIn("尚未生成", payload["message"])
        self.assertEqual(payload["runs"], [])
        self.assertEqual(set(payload["mode_labels"]), {"R0", "R1", "R2"})

    def test_health_works_without_data_dir(self):
        status, payload, _ = self.get_json("/api/nyc/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["exists"])
        self.assertFalse(payload["index_present"])
        self.assertEqual(payload["status"], "empty")
        self.assertTrue(payload["detail"])

    def test_run_and_export_return_404_without_data(self):
        for path in ("/api/nyc/run/anything", "/api/nyc/world/anything",
                     "/api/nyc/export/anything?format=json"):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, 404)

    def test_static_page_still_served_without_data(self):
        status, raw, _ = self.get("/nyc/")
        self.assertEqual(status, 200)
        self.assertIn(b"/nyc/app.js", raw)


class CustomViewerTests(_NycHTTPCase):
    """临时目录构造 ready 数据，覆盖 world、导出与恶意索引引用。"""

    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        root = Path(cls._temp.name)
        viewer = root / "viewer"
        viewer.mkdir()
        cls.viewer_dir = viewer
        # 放在 viewer 之外，用于验证 index 中的 ../ 引用不会被读取。
        (root / "outside.json").write_text(json.dumps({"leaked": True}), encoding="utf-8")
        index = {
            "schema_version": "nyc_semisynthetic_viewer/v1",
            "generated_at": "2026-11-03T12:00:00+08:00",
            "status": "ready",
            "mode_labels": {
                "R0": {"label": "R0 观测重放", "provenance": "observed", "note": "观测"},
                "R1": {"label": "R1 充电会话半合成", "provenance": "scenario", "note": "情景"},
            },
            "sites": [{"site_id": "s1", "label": "Site One", "registered": {"total_spaces": 10}}],
            "scenarios": [{"scenario_id": "sc1", "mode": "R1", "label": "Scenario One"}],
            "runs": [
                {"run_id": "good_run", "mode": "R1", "site_id": "s1", "scenario_id": "sc1",
                 "result_file": "run_good_run.json", "world_file": "world_w1.json"},
                {"run_id": "plain_run", "mode": "R1", "site_id": "s1", "scenario_id": "sc1",
                 "result_file": "run_plain_run.json", "world_file": None},
                {"run_id": "bad_path", "mode": "R1", "site_id": "s1", "scenario_id": "sc1",
                 "result_file": "../outside.json", "world_file": None},
            ],
            "provenance": {"code_version": "test", "root_seed": 7},
        }
        run_good = {
            "run_id": "good_run", "mode": "R1", "site_id": "s1", "scenario_id": "sc1",
            "rule": "strict", "replicate": 0, "station_power_kw": 7.2,
            "rows": [
                {"n": 0, "features": {"R_EP": 2, "shortfall_kwh": 3.5},
                 "capital": 0.0, "service_loss": 4.0, "J": 4.0,
                 "rejected_total": 2, "delivered_share": 0.1},
                {"n": 1, "features": {"R_EP": 0, "shortfall_kwh": 0.0},
                 "capital": 2.0, "service_loss": 1.0, "J": 3.0,
                 "rejected_total": 0, "delivered_share": 1.0},
            ],
            "summary": {"best_n": 1, "argmin": [1], "near_optimal": [0]},
            "series": {"bin_minutes": 15, "bins": [
                {"t_local": "2026-07-20T00:00:00-04:00", "charge_bays_used": 0,
                 "ordinary_bays_used": 1, "charging_kw": 0.0, "arrivals": 1,
                 "rejected": 0, "delivered_kwh": 0.5},
            ]},
            "selected": {"n": 1, "vehicles": [
                {"session_id": "sess-1", "cls": "E1", "delivered_kwh": 4.0,
                 "rejected": False, "origin": "observed_anchor"},
            ]},
            "export": {"world_file": "world_w1.json", "curve_csv": None,
                       "outcomes_csv": None},
        }
        run_plain = {
            "run_id": "plain_run", "mode": "R1", "site_id": "s1", "scenario_id": "sc1",
            "rows": [{"n": 0, "capital": 0.0, "service_loss": 1.0, "J": 1.0}],
            "series": {"bin_minutes": 15, "bins": []},
            "selected": None,
            "export": {"world_file": None},
        }
        world = {"world_id": "w1", "seed": 7, "vehicles": [{"id": 1}], "time_contract": {}}
        (viewer / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        (viewer / "run_good_run.json").write_text(json.dumps(run_good, ensure_ascii=False), encoding="utf-8")
        (viewer / "run_plain_run.json").write_text(json.dumps(run_plain, ensure_ascii=False), encoding="utf-8")
        (viewer / "world_w1.json").write_text(json.dumps(world, ensure_ascii=False), encoding="utf-8")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._temp.cleanup()

    def test_ready_index(self):
        status, payload, _ = self.get_json("/api/nyc/index")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(len(payload["runs"]), 3)

    def test_run_uses_index_result_file(self):
        status, payload, _ = self.get_json("/api/nyc/run/good_run")
        self.assertEqual(status, 200)
        self.assertEqual(payload["run_id"], "good_run")
        self.assertEqual(len(payload["rows"]), 2)

    def test_world_endpoint(self):
        status, payload, _ = self.get_json("/api/nyc/world/w1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["world_id"], "w1")
        status, payload, _ = self.get_json("/api/nyc/world/w2")
        self.assert_json_error(status, payload, 404)

    def test_world_export_follows_run_export_block(self):
        status, raw, headers = self.get("/api/nyc/export/good_run?format=world_json")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(json.loads(raw.decode("utf-8"))["world_id"], "w1")
        status, payload, _ = self.get_json("/api/nyc/export/plain_run?format=world_json")
        self.assert_json_error(status, payload, 404)

    def test_curve_and_outcome_csv(self):
        status, raw, _ = self.get("/api/nyc/export/good_run?format=curve_csv")
        self.assertEqual(status, 200)
        text = raw.decode("utf-8-sig")
        lines = text.splitlines()
        self.assertIn("R_EP", lines[0])
        self.assertIn("shortfall_kwh", lines[0])
        self.assertEqual(len(lines), 3)
        status, raw, _ = self.get("/api/nyc/export/good_run?format=outcomes_csv")
        self.assertEqual(status, 200)
        self.assertIn("sess-1", raw.decode("utf-8-sig"))
        status, payload, _ = self.get_json("/api/nyc/export/plain_run?format=outcomes_csv")
        self.assert_json_error(status, payload, 404)

    def test_malicious_index_reference_is_not_read(self):
        # index 里 result_file=../outside.json；后端必须忽略并因默认文件名不存在返回 404。
        status, payload, _ = self.get_json("/api/nyc/run/bad_path")
        self.assert_json_error(status, payload, 404)
        status, raw, _ = self.get("/api/nyc/run/bad_path")
        self.assertNotIn(b"leaked", raw)


class DefaultPathTests(unittest.TestCase):
    def test_default_data_dir_is_contract_location(self):
        from apps.parking_lab.workbench import nyc_viewer

        previous = os.environ.pop("NYC_VIEWER_DIR", None)
        try:
            expected = REPO_ROOT / "research" / "nyc_semisynthetic_20261103" / "v1" / "viewer"
            self.assertEqual(nyc_viewer.data_dir(), expected.resolve())
        finally:
            if previous is not None:
                os.environ["NYC_VIEWER_DIR"] = previous

    def test_relative_override_resolves_against_cwd(self):
        from apps.parking_lab.workbench import nyc_viewer

        previous = os.environ.get("NYC_VIEWER_DIR")
        os.environ["NYC_VIEWER_DIR"] = "research/nyc_semisynthetic_20261103/v1/viewer_sample"
        try:
            self.assertEqual(nyc_viewer.data_dir(),
                             (Path.cwd() / "research" / "nyc_semisynthetic_20261103" / "v1" / "viewer_sample").resolve())
        finally:
            if previous is None:
                os.environ.pop("NYC_VIEWER_DIR", None)
            else:
                os.environ["NYC_VIEWER_DIR"] = previous


# --------------------------------------------------------------------- v2 数据契约
V2_EXP_RUN = "exp__s1__R1_base"
V2_R2_RUN = "exp__s1__R2_base"
V2_R0_RUN = "r0__s1"
V2_WORLD_ID = "ab12cd34ef567890"
V2_CURVE_COLUMNS = ("n", "J", "capital", "refusal", "energy", "resource", "R_I",
                    "R_E0", "R_EP", "shortfall_kwh", "delivered_kwh")


def _v2_curve_arrays():
    """构造最小的期望成本曲线：J 在 n=3 取最小，供导出与页面数值一致性测试。"""
    n = list(range(0, 9))
    capital = [float(4 * i * i) for i in n]
    refusal = [max(0.0, 100.0 - 11.0 * i) for i in n]
    energy = [max(0.0, 80.0 - 8.0 * i) for i in n]
    resource = [max(0.0, 40.0 - 4.0 * i) for i in n]
    total = [round(capital[i] + refusal[i] + energy[i] + resource[i], 6) for i in n]
    return {
        "n": n,
        "J": total,
        "capital": [round(v, 6) for v in capital],
        "refusal": [round(v, 6) for v in refusal],
        "energy": [round(v, 6) for v in energy],
        "resource": [round(v, 6) for v in resource],
        "R_I": [round(0.1 * i, 3) for i in n],
        "R_E0": [round(0.2 * i, 3) for i in n],
        "R_EP": [round(0.3 * i, 3) for i in n],
        "shortfall_kwh": [round(10.0 - i, 3) for i in n],
        "delivered_kwh": [round(50.0 + 5.0 * i, 3) for i in n],
        "days": 7.0,
    }


V2_CURVE = _v2_curve_arrays()
V2_STAR = int(V2_CURVE["J"].index(min(V2_CURVE["J"])))


def _v2_exp_run(site_id, scenario_id, mode, world_file=None):
    curve = {key: (list(value) if isinstance(value, list) else value)
             for key, value in V2_CURVE.items()}
    run_id = "exp__" + site_id + "__" + scenario_id
    return {
        "run_id": run_id, "site_id": site_id, "mode": mode,
        "mode_label": {"R1": "充电会话半合成 R1", "R2": "三类车半合成 R2"}[mode],
        "evidence_kind": "expected_cost", "scenario_id": scenario_id,
        "stage": "select", "block_id": "week0", "block_date": "2026-01-05",
        "theta_id": "theta_center", "rule": "strict",
        "n_choice": int(curve["n"][V2_STAR]), "n_registered_ev": 5,
        "n_envelope": 8 if mode == "R1" else None, "n_worlds": 4,
        "J_choice": curve["J"][V2_STAR], "J_at_0": curve["J"][0],
        "J_at_registered_ev": curve["J"][curve["n"].index(5)],
        "curve": curve,
        "curve_file": "export/" + run_id + "_curve.csv",
        "world_file": world_file,
        "labels": {"simulated": True, "observed_anchor": True,
                   "note": "expected over selection replicates; the implementable choice"},
        "coverage": {"site": site_id, "scenario": scenario_id, "stage": "select",
                     "block": "week0", "replicates": 4, "theta": "theta_center",
                     "rule": "strict"},
        "unknown": ["true latent demand", "unobserved parking flow", "real cost weights"],
    }


def _v2_r0_run(site_id="s1"):
    return {
        "run_id": "r0__" + site_id, "site_id": site_id, "mode": "R0",
        "mode_label": "观测重放 R0", "evidence_kind": "observed_replay",
        "scenario_id": None, "stage": "observed", "block_id": "week0",
        "block_date": "2026-01-05", "theta_id": None, "rule": None,
        "labels": {"observed": True, "simulated": False,
                   "note": "observed replay only; no J(n), no refusal rate, no simulated delivery"},
        "realized": None, "curve": None,
        "days": [
            {"date": "2026-01-05", "sessions": 3, "connected_min": 120.5,
             "observed_kwh": 40.25, "day_status": "open"},
            {"date": "2026-01-06", "sessions": 3, "connected_min": 95.0,
             "observed_kwh": 31.5, "day_status": "open"},
        ],
        "coverage": {"sessions_in_week": 6, "days": 2},
        "unknown": ["requested energy", "unserved demand", "true parking arrivals"],
    }


def _write_v2_fixture(root):
    """按 v2 契约与 viewer_export.py 的实际字段写最小只读数据集，返回目录。"""
    viewer = Path(root) / "v2viewer"
    (viewer / "export").mkdir(parents=True)
    r0 = _v2_r0_run()
    r1 = _v2_exp_run("s1", "R1_base", "R1", world_file="world_" + V2_WORLD_ID + ".json")
    r2 = _v2_exp_run("s1", "R2_base", "R2")
    fixed_eval = [
        {"site_id": "s1", "scenario_id": "R1_base", "mode": "R1", "stage": "evaluation",
         "block_id": "week3", "block_date": "2026-01-26", "theta_id": "theta_center",
         "rule": "strict", "n_selected_on_select_block": V2_STAR, "n_worlds": 5,
         "deterministic_worlds": False, "J_mean_fixed": 195.5, "J_se_fixed": 1.25,
         "J_hindsight_mean": 190.0, "hindsight_gap": -5.5, "J_mean_at_0": 210.0,
         "registered_ev_bays": 5, "J_mean_registered_ev": 201.0,
         "paired_diff_EF_minus_registered_ev": -5.5, "declared_envelope_N": 8,
         "J_mean_declared_envelope": 199.0, "paired_diff_EF_minus_envelope": -3.5,
         "delivered_kwh_at_selected": 120.5, "refusals_at_selected": 2.5},
        {"site_id": "s1", "scenario_id": "R2_base", "mode": "R2", "stage": "evaluation",
         "block_id": "week6", "block_date": "2026-02-16", "theta_id": "theta_center",
         "rule": "strict", "n_selected_on_select_block": V2_STAR, "n_worlds": 4,
         "deterministic_worlds": False, "J_mean_fixed": 205.0, "J_se_fixed": 2.0,
         "J_hindsight_mean": 198.0, "hindsight_gap": -7.0, "J_mean_at_0": 220.0,
         "registered_ev_bays": 5, "J_mean_registered_ev": 212.0,
         "paired_diff_EF_minus_registered_ev": -7.0, "declared_envelope_N": None,
         "J_mean_declared_envelope": None, "paired_diff_EF_minus_envelope": None,
         "delivered_kwh_at_selected": 118.0, "refusals_at_selected": 4.0},
    ]
    robust = [
        {"site_id": "s1", "mode": "R1", "object": "robust_A",
         "definition": "argmin_n max_(phi,theta) regret of Jbar",
         "n_robust": 3, "worst_case_regret": 12.5, "n_scenarios": 2,
         "n_theta": 3, "coverage": "select block, 2 declared scenarios x 3 theta grid points"},
        {"site_id": "s1", "mode": "R2", "object": "robust_A",
         "definition": "argmin_n max_(phi,theta) regret of Jbar",
         "n_robust": 4, "worst_case_regret": 15.0, "n_scenarios": 2,
         "n_theta": 3, "coverage": "select block, 2 declared scenarios x 3 theta grid points"},
        {"site_id": "s1", "mode": "R1", "object": "robust_B",
         "definition": "argmin_n max_(phi,theta,omega) regret of a single realization",
         "n_robust_stress": 4, "worst_case_regret_stress": 30.0,
         "n_realizations": 5, "n_theta": 3,
         "coverage": "select block, 5 worlds x 3 theta points"},
        {"site_id": "s1", "mode": "R2", "object": "robust_B",
         "definition": "argmin_n max_(phi,theta,omega) regret of a single realization",
         "n_robust_stress": 5, "worst_case_regret_stress": 33.0,
         "n_realizations": 4, "n_theta": 3,
         "coverage": "select block, 4 worlds x 3 theta points"},
    ]
    index = {
        "schema_version": "nyc_viewer_v2/1",
        "generated_at": "2026-11-03T20:00:00+08:00",
        "code_version": "test-code-v2",
        "registration": {"design_sha256": "d" * 64, "code_sha256": "c" * 64},
        "counts": {"worlds": 6, "runs": 3, "fixed_eval_rows": len(fixed_eval),
                   "robust_rows": len(robust)},
        "mode_labels": {"R0": "观测重放 R0", "R1": "充电会话半合成 R1",
                        "R2": "三类车半合成 R2"},
        "sites": [{"site_id": "s1", "registered_ev_bays": 5,
                   "registered_total_spaces": 100, "N_R1": 8, "N_R2": 9}],
        "scenarios": [
            {"scenario_id": "R1_base", "mode": "R1", "label": "R1 基准",
             "deterministic": False},
            {"scenario_id": "R2_base", "mode": "R2", "label": "R2 基准",
             "deterministic": False},
        ],
        "runs": [r0, r1, r2],
        "fixed_eval": fixed_eval,
        "robust": robust,
        "sources": [
            {"path": "v1/canonical/sessions.csv.gz", "provenance": "observed"},
            {"path": "v2/fit/s1.json", "provenance": "derived from observed training block"},
        ],
        "limits": [
            "R1/R2 are conditional semi-synthetic scenarios, not recovered NYC demand",
            "evaluation blocks were inspected in this round (retrospective, not blind)",
            "theta weights are uncalibrated; optimal n is only conditional on the declared set",
        ],
        "labels_rule": "evidence_kind must be visible on every run; robust_A and robust_B are "
                       "different objects and must not share a name",
    }
    (viewer / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    for run in (r0, r1, r2):
        (viewer / ("run_" + run["run_id"] + ".json")).write_text(
            json.dumps(run, ensure_ascii=False), encoding="utf-8")
    world = {
        "schema_version": "nyc_viewer_v2/1", "site_id": "s1", "mode": "R1",
        "scenario_id": "R1_base", "stage": "select", "block_id": "week0",
        "replicate": 0, "N": 9, "station_kw": 7.2, "seed": 20261103,
        "world_hash": "sha256:" + V2_WORLD_ID,
        "phi": {"request_slack_mean": 0.25}, "counts": {"vehicles": 2},
        "realized": {"served": 1}, "assumptions": [{"field": "requested_kwh",
                                                     "provenance": "scenario"}],
        "vehicles": [
            {"session_id": "v-1", "synthetic_driver_id": "drv-1", "arrival_min": 0,
             "dwell_min": 60, "cls": "E1", "requested_kwh": 10.0,
             "origin": "observed_anchor", "bay": 0, "delivered_kwh": 9.5},
        ],
    }
    (viewer / ("world_" + V2_WORLD_ID + ".json")).write_text(
        json.dumps(world, ensure_ascii=False), encoding="utf-8")
    for run in (r1, r2):
        path = viewer / "export" / (run["run_id"] + "_curve.csv")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["run_id", "site_id", "scenario_id"] + list(V2_CURVE_COLUMNS))
            curve = run["curve"]
            for row_index in range(len(curve["n"])):
                writer.writerow([run["run_id"], "s1", run["scenario_id"]] +
                                [curve[column][row_index] for column in V2_CURVE_COLUMNS])
    return viewer


class V2ViewerTests(_NycHTTPCase):
    """v1 与 v2 同时挂在一个服务上：默认 v1 保持不变，?dataset=v2 走 v2 契约。"""

    viewer_dir = SAMPLE_DIR

    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.viewer_dir_v2 = _write_v2_fixture(cls._temp.name)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._temp.cleanup()

    def get_v2(self, path):
        joiner = "&" if "?" in path else "?"
        return self.get_json(path + joiner + "dataset=v2")

    def test_v2_index_schema_and_four_evidence_objects(self):
        status, payload, _ = self.get_v2("/api/nyc/index")
        self.assertEqual(status, 200)
        self.assertEqual(payload["dataset"], "v2")
        self.assertEqual(payload["schema_kind"], "v2")
        self.assertEqual(payload["schema_version"], "nyc_viewer_v2/1")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["counts"]["runs"], 3)
        self.assertEqual(len(payload["runs"]), 3)
        self.assertTrue(any(run["evidence_kind"] == "expected_cost"
                            for run in payload["runs"]))
        self.assertTrue(any(run["evidence_kind"] == "observed_replay"
                            for run in payload["runs"]))
        self.assertEqual(len(payload["fixed_eval"]), 2)
        self.assertEqual(len(payload["robust"]), 4)
        self.assertGreaterEqual(len(payload["sources"]), 1)
        self.assertGreaterEqual(len(payload["limits"]), 3)
        self.assertEqual(payload["code_version"], "test-code-v2")
        self.assertIn("registration", payload)

    def test_v1_index_unchanged_and_no_v2_tables(self):
        status, payload, _ = self.get_json("/api/nyc/index")
        self.assertEqual(status, 200)
        self.assertEqual(payload["dataset"], "v1")
        self.assertEqual(payload["schema_version"], "nyc_semisynthetic_viewer/v1")
        self.assertNotIn("fixed_eval", payload)
        self.assertNotIn("robust", payload)
        self.assertEqual(payload["status"], "sample")

    def test_v2_expected_cost_run_carries_required_labels(self):
        status, payload, _ = self.get_v2("/api/nyc/run/" + V2_EXP_RUN)
        self.assertEqual(status, 200)
        for key in ("mode_label", "evidence_kind", "stage", "block_id", "theta_id",
                    "rule", "coverage", "unknown", "curve", "labels"):
            self.assertIn(key, payload)
        self.assertEqual(payload["evidence_kind"], "expected_cost")
        self.assertEqual(payload["mode_label"], "充电会话半合成 R1")
        self.assertEqual(payload["stage"], "select")
        self.assertEqual(payload["block_id"], "week0")
        self.assertEqual(payload["theta_id"], "theta_center")
        self.assertEqual(payload["rule"], "strict")
        self.assertEqual(payload["n_choice"], V2_CURVE["n"][V2_STAR])
        self.assertEqual(payload["J_choice"], V2_CURVE["J"][V2_STAR])
        self.assertEqual(payload["curve"]["n"], V2_CURVE["n"])
        self.assertEqual(len(payload["curve"]["J"]), len(V2_CURVE["n"]))
        self.assertIn("true latent demand", payload["unknown"])

    def test_v2_r0_run_has_no_j_or_curve(self):
        status, payload, _ = self.get_v2("/api/nyc/run/" + V2_R0_RUN)
        self.assertEqual(status, 200)
        self.assertEqual(payload["evidence_kind"], "observed_replay")
        self.assertEqual(payload["mode"], "R0")
        self.assertIsNone(payload["curve"])
        for key in ("n_choice", "J_choice", "n_registered_ev"):
            self.assertNotIn(key, payload)
        self.assertEqual(len(payload["days"]), 2)
        self.assertEqual(payload["coverage"]["sessions_in_week"], 6)

    def test_fixed_eval_endpoint_returns_v2_rows_and_v1_is_unavailable(self):
        status, payload, _ = self.get_v2("/api/nyc/fixed_eval")
        self.assertEqual(status, 200)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["schema_kind"], "v2")
        self.assertEqual(payload["count"], 2)
        row = payload["rows"][0]
        for key in ("site_id", "scenario_id", "block_id", "n_selected_on_select_block",
                    "n_worlds", "J_mean_fixed", "J_hindsight_mean", "hindsight_gap",
                    "paired_diff_EF_minus_registered_ev"):
            self.assertIn(key, row)
        self.assertIn("block_id", payload["note"])
        status, payload, _ = self.get_json("/api/nyc/fixed_eval")
        self.assertEqual(status, 200)
        self.assertFalse(payload["available"])
        self.assertEqual(payload["rows"], [])

    def test_robust_endpoint_keeps_a_and_b_separate(self):
        status, payload, _ = self.get_v2("/api/nyc/robust")
        self.assertEqual(status, 200)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["counts"], {"A": 2, "B": 2})
        self.assertEqual([row["object"] for row in payload["A"]], ["robust_A", "robust_A"])
        self.assertEqual([row["object"] for row in payload["B"]], ["robust_B", "robust_B"])
        self.assertIn("n_robust", payload["A"][0])
        self.assertIn("n_robust_stress", payload["B"][0])
        self.assertNotIn("n_robust_stress", payload["A"][0])
        self.assertNotEqual(payload["objects"]["A"]["name"],
                            payload["objects"]["B"]["name"])
        self.assertIn("robust_A", payload["note"])
        status, payload, _ = self.get_json("/api/nyc/robust")
        self.assertFalse(payload["available"])

    def test_world_endpoint_v2(self):
        status, payload, _ = self.get_v2("/api/nyc/world/" + V2_WORLD_ID)
        self.assertEqual(status, 200)
        self.assertEqual(payload["world_hash"], "sha256:" + V2_WORLD_ID)
        self.assertEqual(payload["site_id"], "s1")
        self.assertEqual(payload["vehicles"][0]["synthetic_driver_id"], "drv-1")
        status, payload, _ = self.get_v2("/api/nyc/world/no-such-world")
        self.assert_json_error(status, payload, 404)

    def test_export_json_v2_matches_page_values(self):
        status, raw, headers = self.get(
            "/api/nyc/export/" + V2_EXP_RUN + "?format=json&dataset=v2")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn(V2_EXP_RUN + ".json", headers["Content-Disposition"])
        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(payload["run_id"], V2_EXP_RUN)
        self.assertEqual(payload["n_choice"], V2_CURVE["n"][V2_STAR])
        self.assertEqual(payload["J_choice"], V2_CURVE["J"][V2_STAR])
        self.assertEqual(len(payload["curve"]["n"]), len(V2_CURVE["n"]))

    def test_export_curve_csv_v2_matches_curve_arrays(self):
        status, raw, headers = self.get(
            "/api/nyc/export/" + V2_EXP_RUN + "?format=curve_csv&dataset=v2")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers["Content-Type"])
        self.assertIn("-curve.csv", headers["Content-Disposition"])
        text = raw.decode("utf-8")
        rows = list(csv.DictReader(text.splitlines()))
        self.assertEqual(len(rows), len(V2_CURVE["n"]))
        header = text.splitlines()[0]
        for column in V2_CURVE_COLUMNS:
            self.assertIn(column, header)
        for index, row in enumerate(rows):
            self.assertEqual(int(row["n"]), V2_CURVE["n"][index])
            self.assertAlmostEqual(float(row["J"]), V2_CURVE["J"][index], places=6)

    def test_download_values_equal_index_values(self):
        # 页面用的索引 run 与下载的 run JSON / CSV 必须是同一组数值。
        status, index_payload, _ = self.get_v2("/api/nyc/index")
        self.assertEqual(status, 200)
        indexed = {run["run_id"]: run for run in index_payload["runs"]}[V2_EXP_RUN]
        _, raw_json, _ = self.get("/api/nyc/export/" + V2_EXP_RUN + "?format=json&dataset=v2")
        downloaded = json.loads(raw_json.decode("utf-8"))
        self.assertEqual(downloaded["n_choice"], indexed["n_choice"])
        self.assertEqual(downloaded["J_choice"], indexed["J_choice"])
        _, raw_csv, _ = self.get(
            "/api/nyc/export/" + V2_EXP_RUN + "?format=curve_csv&dataset=v2")
        csv_rows = list(csv.DictReader(raw_csv.decode("utf-8").splitlines()))
        self.assertEqual(len(csv_rows), len(indexed["curve"]["n"]))
        self.assertAlmostEqual(float(csv_rows[V2_STAR]["J"]),
                               indexed["curve"]["J"][V2_STAR], places=6)

    def test_export_world_json_v2(self):
        status, raw, headers = self.get(
            "/api/nyc/export/" + V2_EXP_RUN + "?format=world_json&dataset=v2")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(payload["world_hash"], "sha256:" + V2_WORLD_ID)
        status, payload, _ = self.get_v2(
            "/api/nyc/export/" + V2_R2_RUN + "?format=world_json")
        self.assert_json_error(status, payload, 404)

    def test_export_outcomes_csv_rejected_for_v2(self):
        status, payload, _ = self.get_v2(
            "/api/nyc/export/" + V2_EXP_RUN + "?format=outcomes_csv")
        self.assert_json_error(status, payload, 400)
        self.assertIn("v2", payload["error"])
        status, payload, _ = self.get_v2("/api/nyc/export/" + V2_EXP_RUN + "?format=xml")
        self.assert_json_error(status, payload, 400)

    def test_invalid_dataset_returns_400(self):
        for path in ("/api/nyc/index?dataset=v9", "/api/nyc/health?dataset=v2x",
                     "/api/nyc/run/" + V2_EXP_RUN + "?dataset=../v1"):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, 400)

    def test_v2_bad_ids_and_unknown_objects(self):
        cases = (
            ("/api/nyc/run/..?dataset=v2", 400),
            ("/api/nyc/run/unknown-run?dataset=v2", 404),
            ("/api/nyc/world/..%2f..%2fserver.py?dataset=v2", 400),
            ("/api/nyc/export/..%2f..%2fserver.py?format=json&dataset=v2", 400),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, expected)
        status, raw, _ = self.get("/api/nyc/run/unknown-run?dataset=v2")
        self.assertNotIn(b"Traceback", raw)

    def test_env_dataset_selects_v2(self):
        previous = os.environ.get("NYC_VIEWER_DATASET")
        os.environ["NYC_VIEWER_DATASET"] = "v2"
        try:
            status, payload, _ = self.get_json("/api/nyc/index")
            self.assertEqual(status, 200)
            self.assertEqual(payload["dataset"], "v2")
            self.assertEqual(payload["schema_kind"], "v2")
        finally:
            if previous is None:
                os.environ.pop("NYC_VIEWER_DATASET", None)
            else:
                os.environ["NYC_VIEWER_DATASET"] = previous

    def test_health_v2_reports_schema_and_counts(self):
        status, payload, _ = self.get_v2("/api/nyc/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["dataset"], "v2")
        self.assertEqual(payload["schema_kind"], "v2")
        self.assertEqual(payload["schema_version"], "nyc_viewer_v2/1")
        self.assertTrue(payload["exists"])
        self.assertEqual(payload["runs"], 3)
        self.assertEqual(payload["counts"]["worlds"], 6)

    def test_static_page_contains_v2_ui_markers(self):
        status, raw, _ = self.get("/nyc/")
        self.assertEqual(status, 200)
        page = raw.decode("utf-8")
        for marker in ('id="dataset-switch"', 'id="v2-content"', "期望成本",
                       "固定配置评价", "稳健", "仅诊断", "证据"):
            self.assertIn(marker, page)
        status, raw, _ = self.get("/nyc/app.js")
        self.assertEqual(status, 200)
        script = raw.decode("utf-8")
        for marker in ("expected_cost", "fixed_config_eval", "robust_A", "robust_B",
                       "observed_replay", "single_world_hindsight", "dataset=v2"):
            self.assertIn(marker, script)
        status, raw, _ = self.get("/nyc/style.css")
        self.assertEqual(status, 200)
        self.assertIn(".evidence-badge", raw.decode("utf-8"))


class V2EmptyViewerTests(_NycHTTPCase):
    viewer_dir = SAMPLE_DIR

    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.viewer_dir_v2 = Path(cls._temp.name) / "missing-v2"
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._temp.cleanup()

    def test_v2_index_returns_empty_not_500(self):
        status, payload, _ = self.get_json("/api/nyc/index?dataset=v2")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["dataset"], "v2")
        self.assertIsNone(payload["schema_kind"])
        self.assertIn("v2", payload["message"])
        self.assertEqual(payload["runs"], [])

    def test_v2_health_without_dir(self):
        status, payload, _ = self.get_json("/api/nyc/health?dataset=v2")
        self.assertEqual(status, 200)
        self.assertFalse(payload["exists"])
        self.assertEqual(payload["dataset"], "v2")

    def test_v2_run_and_export_404(self):
        for path in ("/api/nyc/run/anything?dataset=v2",
                     "/api/nyc/export/anything?format=json&dataset=v2",
                     "/api/nyc/world/anything?dataset=v2"):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, 404)

    def test_v2_fixed_and_robust_unavailable(self):
        for path in ("/api/nyc/fixed_eval?dataset=v2", "/api/nyc/robust?dataset=v2"):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assertEqual(status, 200)
                self.assertFalse(payload["available"])


class V2DefaultPathTests(unittest.TestCase):
    _KEYS = ("NYC_VIEWER_DIR", "NYC_VIEWER_DIR_V2", "NYC_VIEWER_DIR_V3",
             "NYC_VIEWER_DATASET")

    def _clear_env(self):
        previous = {key: os.environ.pop(key, None) for key in self._KEYS}
        self.addCleanup(lambda: [os.environ.__setitem__(key, value) if value is not None
                                 else os.environ.pop(key, None)
                                 for key, value in previous.items()])

    def test_default_v2_data_dir_is_contract_location(self):
        from apps.parking_lab.workbench import nyc_viewer

        self._clear_env()
        expected = REPO_ROOT / "research" / "nyc_semisynthetic_20261103" / "v2" / "viewer"
        self.assertEqual(nyc_viewer.data_dir("v2"), expected.resolve())
        self.assertEqual(nyc_viewer.DEFAULT_VIEWER_DIR_V2.resolve(), expected.resolve())

    def test_dataset_name_defaults_and_validation(self):
        from apps.parking_lab.workbench import nyc_viewer

        self._clear_env()
        self.assertEqual(nyc_viewer.dataset_name(None), "v1")
        self.assertEqual(nyc_viewer.dataset_name("v2"), "v2")
        self.assertEqual(nyc_viewer.dataset_name(" V1 "), "v1")
        self.assertEqual(nyc_viewer.dataset_name("v3"), "v3")
        with self.assertRaises(ValueError):
            nyc_viewer.dataset_name("v4")

    def test_relative_v2_override_resolves_against_cwd(self):
        from apps.parking_lab.workbench import nyc_viewer

        self._clear_env()
        os.environ["NYC_VIEWER_DIR_V2"] = "tmp/v2fixture"
        self.assertEqual(nyc_viewer.data_dir("v2"),
                         (Path.cwd() / "tmp" / "v2fixture").resolve())


if __name__ == "__main__":
    unittest.main()
