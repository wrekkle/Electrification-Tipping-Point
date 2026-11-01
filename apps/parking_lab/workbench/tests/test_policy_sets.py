"""策略比较版本：默认 formal=当前研究正式规则；legacy 必须显式选择并标注历史演示。"""
import json
import threading
import unittest
from urllib.request import Request, urlopen

from apps.parking_lab.workbench.config import Config, LEGACY_POLICIES, RULE_POLICIES
from apps.parking_lab.workbench.experiments import compare
from apps.parking_lab.workbench.server import make_server

CONFIG = {"duration_hours": 2, "arrival_rate_hour": 40, "n_spaces": 16,
          "charging_bays": 6, "chargers": 4}


class PolicySetTests(unittest.TestCase):
    def test_default_is_formal_rules(self):
        result = compare(Config.parse(CONFIG), [11, 12, 13])
        model = result["comparison_model"]
        self.assertEqual(result["policy_set"], "formal")
        self.assertEqual(result["policy_family"], "formal_rule")
        self.assertEqual(set(run["policy"] for run in result["runs"]), set(RULE_POLICIES))
        self.assertFalse(set(run["policy"] for run in result["runs"]) & set(LEGACY_POLICIES))
        self.assertEqual(model["baseline_policy"], "dedicated_by_type")
        self.assertEqual(model["model_version"], result["provenance"]["model_version"])
        self.assertIn("不读取 needs_charge", model["info_contract"])
        self.assertIsNone(model["legacy_notice"])
        self.assertEqual(len(result["rows"]), 4)
        self.assertEqual(sum(1 for row in result["rows"] if row["baseline"]), 1)
        self.assertEqual({row["paired_cost_baseline"] for row in result["rows"]}, {"dedicated_by_type"})
        for key in ("rejection_rate", "charge_completion_rate_all", "energy_delivered_kwh", "total_cost",
                    "mean_occupancy_rate", "brier", "interval_coverage", "interval_width_min",
                    "departed_shortfall_kwh"):
            self.assertIn(key, model["metric_definitions"])
        self.assertIn("不是置信区间", model["uncertainty"])
        self.assertIn("同一外生车辆流", model["simulation_contract"])
        for seed in result["seeds"]:
            runs = [run for run in result["runs"] if run["seed"] == seed]
            self.assertEqual(len(runs), 4)
            self.assertEqual(len({run["demand_hash"] for run in runs}), 1)
            self.assertEqual(len({run["metrics"]["arrivals"] for run in runs}), 1)

    def test_legacy_requires_explicit_flag_and_is_labeled(self):
        result = compare(Config.parse(CONFIG), [11, 12], policy_set="legacy")
        model = result["comparison_model"]
        self.assertEqual(set(run["policy"] for run in result["runs"]), set(LEGACY_POLICIES))
        self.assertFalse(set(run["policy"] for run in result["runs"]) & set(RULE_POLICIES))
        self.assertEqual(result["baseline_policy"], "open")
        self.assertTrue(model["legacy_notice"])
        self.assertIn("历史策略演示", model["legacy_notice"])
        self.assertIn("不代表当前研究模型", model["applicable_model"])
        self.assertEqual({row["paired_cost_baseline"] for row in result["rows"]}, {"open"})

    def test_unknown_policy_set_rejected(self):
        for value in ("pi0", "", "FORMAL", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare(Config.parse(CONFIG), [1], policy_set=value)


class CompareHTTPPolicySetTests(unittest.TestCase):
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
        try:
            with urlopen(req, timeout=120) as response:
                return response.status, json.loads(response.read())
        except Exception as error:
            import urllib.error
            if isinstance(error, urllib.error.HTTPError):
                return error.code, json.loads(error.read())
            raise

    def test_http_compare_policy_sets_and_presets(self):
        status, formal = self.request("/api/compare", {
            "config": {"duration_hours": 1, "arrival_rate_hour": 10},
            "seeds": [3, 4], "policy_set": "formal"})
        self.assertEqual(status, 200)
        self.assertEqual(formal["policy_set"], "formal")
        self.assertEqual(formal["comparison_model"]["policy_family"], "formal_rule")
        self.assertEqual(len(formal["rows"]), 4)
        status, legacy = self.request("/api/compare", {
            "config": {"duration_hours": 1, "arrival_rate_hour": 10},
            "seeds": [3], "policy_set": "legacy"})
        self.assertEqual(status, 200)
        self.assertTrue(legacy["comparison_model"]["legacy_notice"])
        self.assertEqual({row["policy"] for row in legacy["rows"]},
                         {"strict", "open", "fixed", "adaptive"})
        status, _ = self.request("/api/compare", {
            "config": {"duration_hours": 1, "arrival_rate_hour": 10},
            "seeds": [3], "policy_set": "pi0"})
        self.assertEqual(status, 400)
        status, presets = self.request("/api/presets")
        self.assertEqual(status, 200)
        self.assertEqual(presets["default_policy_set"], "formal")
        self.assertIn("formal", presets["policy_sets"])
        self.assertIn("legacy", presets["policy_sets"])
        self.assertTrue(presets["policy_sets"]["legacy"]["legacy_notice"])


if __name__ == "__main__":
    unittest.main()
