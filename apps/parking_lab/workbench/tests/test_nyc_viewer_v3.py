# -*- coding: utf-8 -*-
"""T63 v3 查看器契约测试：用最小伪造 index/runs/world/export 样本走真实 HTTP。

只依赖进程内 HTTP 与临时目录，不依赖 research/ 下的真实 v3 产物；
v1/v2 的既有行为由 test_nyc_viewer.py 覆盖。
"""
import csv
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    from apps.parking_lab.workbench.server import make_server
except Exception as exc:  # pragma: no cover - public repository without research tree
    raise unittest.SkipTest("workbench server is not importable here: %s" % exc)

REPO_ROOT = Path(__file__).resolve().parents[4]
CURVE_KEYS = ("n", "total", "capital", "refusal", "energy", "shortfall", "resource",
              "R_I", "R_E0", "R_EP", "shortfall_kwh", "delivered_kwh")
CURVE_VALUES = {
    "n": [0, 1, 2, 3],
    "total": [100.0, 80.5, 70.25, 72.0],
    "capital": [0.0, 10.0, 20.0, 30.0],
    "refusal": [40.0, 25.0, 5.0, 2.0],
    "energy": [30.0, 25.0, 25.0, 25.0],
    "shortfall": [20.0, 10.0, 0.0, 0.0],
    "resource": [10.0, 10.5, 20.25, 15.0],
    "R_I": [0.0, 0.1, 0.2, 0.3],
    "R_E0": [0.0, 0.0, 0.0, 0.0],
    "R_EP": [40.0, 20.0, 5.0, 2.0],
    "shortfall_kwh": [12.0, 6.0, 0.0, 0.0],
    "delivered_kwh": [150.0, 200.0, 210.0, 210.0],
}
RUN_IDS = ("t63_s1_R1_base_M0", "t63_s1_R1_base_M1", "t63_s1_R1_base_M2")
FIXED_COLUMNS = ["site_id", "scenario_id", "mode", "block_id", "eval_mechanism",
                 "n_source_mechanism", "n_selected", "n_worlds", "J_mean_fixed",
                 "J_se_fixed", "J_hindsight_mean", "hindsight_gap_mean",
                 "hindsight_gap_median", "J_mean_at_0", "registered_ev_bays",
                 "J_mean_registered_ev", "paired_diff_fixed_minus_registered",
                 "delivered_kwh_mean", "refusals_mean"]
ROBUST_COLUMNS = ["site_id", "mode", "object", "definition", "n_robust", "n_robust_stress",
                  "worst_case_regret", "worst_case_regret_stress", "n_mechanisms",
                  "n_scenarios", "n_realizations", "n_theta", "coverage"]
HINDSIGHT_COLUMNS = ["site_id", "scenario_id", "block_id", "eval_mechanism",
                     "n_source_mechanism", "n_selected", "world_id", "replicate",
                     "J_fixed", "J_hindsight_min", "n_hindsight", "hindsight_gap",
                     "hindsight_gap_definition"]
HOLDOUT_COLUMNS = ["table", "site_id", "holdout_week", "mechanism", "metric",
                   "repeat_mean", "repeat_sd", "n_observed", "n_generated_mean",
                   "noise_floor_mean", "missing_reason"]
ATTR_COLUMNS = ["record", "site_id", "variant", "contrast", "variant_a", "variant_b",
                "metric", "value", "sd", "ci_low", "ci_high", "n_sites",
                "sign_positive", "sign_negative", "missing_reason"]
SELECTION_COLUMNS = ["site_id", "mode", "registered_ev_bays", "observed_peak_median",
                     "observed_peak_q90", "observed_saturated_days_share",
                     "unconstrained_generated_peak_median", "note"]


def _write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _fixed_row(mech, block="week0"):
    return {
        "site_id": "s1", "scenario_id": "R1_base", "mode": "R1", "block_id": block,
        "eval_mechanism": mech, "n_source_mechanism": "M0", "n_selected": 2,
        "n_worlds": 8, "J_mean_fixed": 71.5, "J_se_fixed": 1.25,
        "J_hindsight_mean": 68.0, "hindsight_gap_mean": 3.5,
        "hindsight_gap_median": 3.0, "J_mean_at_0": 100.0, "registered_ev_bays": 5,
        "J_mean_registered_ev": 76.0, "paired_diff_fixed_minus_registered": -4.5,
        "delivered_kwh_mean": 205.0, "refusals_mean": 2.0,
    }


def _hindsight_row(block, world, gap, n_hindsight=3):
    return {
        "site_id": "s1", "scenario_id": "R1_base", "block_id": block,
        "eval_mechanism": "M0", "n_source_mechanism": "M0", "n_selected": 2,
        "world_id": world, "replicate": 0, "J_fixed": 70.25,
        "J_hindsight_min": 70.25 - gap, "n_hindsight": n_hindsight,
        "hindsight_gap": gap,
        "hindsight_gap_definition": "fixed minus per-world minimum; >= 0",
    }


def _write_v3_fixture(root):
    """写最小 nyc_viewer_v3/1 数据集：3 个 expected run、2 个 world、面板 CSV。"""
    root = Path(root)
    (root / "runs").mkdir(parents=True, exist_ok=True)
    (root / "world").mkdir(parents=True, exist_ok=True)
    (root / "export").mkdir(parents=True, exist_ok=True)

    curve_csv = "export/" + RUN_IDS[0] + "_curve.csv"
    runs = []
    for index, run_id in enumerate(RUN_IDS):
        mech = "M" + str(index)
        pivot = 2 + (0 if index == 0 else index)
        payload = {
            "run_id": run_id,
            "schema_version": "nyc_viewer_v3/1",
            "meta": {"site_id": "s1", "scenario_id": "R1_base", "mode": "R1",
                     "mechanism": mech, "stage": "select", "block_id": "calib_last",
                     "n_worlds": 4, "theta_id": "theta_center",
                     "protocol_design_fingerprint": "design-fingerprint-0001",
                     "protocol_code_fingerprint": "code-fingerprint-0001"},
            "curve": {key: list(CURVE_VALUES[key]) for key in CURVE_KEYS},
            "choice": {"n_star": pivot, "Jbar_at_n_star": 70.25 + index,
                       "Jbar_min": 70.25 + index, "Jbar_minus_chosen": 0.0,
                       "argmin_set": [pivot], "near_optimal_set": [pivot]},
            "fixed_eval": [_fixed_row(mech)],
            "exports": {"curve_csv": "export/" + run_id + "_curve.csv",
                        "fixed_eval_csv": "export/t63_fixed_cross_mechanism.csv",
                        "per_world_hindsight_csv": "export/t63_per_world_hindsight.csv"},
            "labels": {"mechanism": mech, "scenario": "R1 base"},
            "coverage": {"n_grid_length": 4, "candidate_rows_strict": 16,
                         "rule": "strict primary; fallback exported separately"},
        }
        with open(root / "runs" / ("run_" + run_id + ".json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        with open(root / curve_csv.replace(RUN_IDS[0], run_id).replace("export/", "export/"),
                  "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(list(CURVE_KEYS))
            for row_index in range(len(CURVE_VALUES["n"])):
                writer.writerow([CURVE_VALUES[key][row_index] for key in CURVE_KEYS])
        runs.append({"run_id": run_id, "site_id": "s1", "scenario_id": "R1_base",
                     "mode": "R1", "mechanism": mech, "n_star": pivot,
                     "Jbar_at_n_star": 70.25 + index,
                     "run_json": "runs/run_" + run_id + ".json",
                     "curve_csv": "export/" + run_id + "_curve.csv"})
    world_payload = {"world_id": "w_m0", "site_id": "s1", "scenario_id": "R1_base",
                     "mechanism": "M0", "vehicles": [{"session_id": "v1"}, {"session_id": "v2"}]}
    with open(root / "world" / "world_w_m0.json", "w", encoding="utf-8") as handle:
        json.dump(world_payload, handle, ensure_ascii=False)
    r0_world = {"world_id": "w_r0", "site_id": "s1", "scenario_id": "R1_base",
                "mode": "R1", "observed": [{"session_id": "obs-1"}]}
    with open(root / "world" / "world_w_r0.json", "w", encoding="utf-8") as handle:
        json.dump(r0_world, handle, ensure_ascii=False)

    _write_csv(root / "export" / "t63_table_a.csv", HOLDOUT_COLUMNS, [
        {"table": "A", "site_id": "s1", "holdout_week": 0, "mechanism": "M0",
         "metric": "peak", "repeat_mean": 0.5, "repeat_sd": 0.1, "n_observed": 100,
         "n_generated_mean": 101.0, "noise_floor_mean": 0.2, "missing_reason": None},
        {"table": "A", "site_id": "s1", "holdout_week": 1, "mechanism": "M1",
         "metric": "peak", "repeat_mean": 0.4, "repeat_sd": 0.08, "n_observed": 100,
         "n_generated_mean": 99.0, "noise_floor_mean": None, "missing_reason": None},
        {"table": "A", "site_id": "s1", "holdout_week": 1, "mechanism": "M2",
         "metric": "weekday_count_tvd", "repeat_mean": None, "repeat_sd": None,
         "n_observed": 100, "n_generated_mean": None, "noise_floor_mean": None,
         "missing_reason": "undefined_metric"},
    ])
    _write_csv(root / "export" / "t63_table_b.csv", HOLDOUT_COLUMNS, [
        {"table": "B", "site_id": "s1", "holdout_week": "ALL", "mechanism": "M0",
         "metric": "peak", "repeat_mean": 0.55, "repeat_sd": 0.12, "n_observed": 1400,
         "n_generated_mean": 1400.0, "noise_floor_mean": 0.3, "missing_reason": None},
        {"table": "B", "site_id": "s1", "holdout_week": "ALL", "mechanism": "M1",
         "metric": "peak", "repeat_mean": 0.45, "repeat_sd": 0.09, "n_observed": 1400,
         "n_generated_mean": 1398.0, "noise_floor_mean": 0.3, "missing_reason": None},
    ])
    _write_csv(root / "export" / "t63_noise_floor.csv",
               ["site_id", "holdout_week", "metric", "noise_floor_mean", "noise_floor_sd"], [
                   {"site_id": "s1", "holdout_week": 0, "metric": "peak",
                    "noise_floor_mean": 0.2, "noise_floor_sd": 0.01},
                   {"site_id": "s1", "holdout_week": "ALL", "metric": "peak",
                    "noise_floor_mean": 0.3, "noise_floor_sd": 0.02},
               ])
    _write_csv(root / "export" / "t63_drift_reference.csv",
               ["site_id", "metric", "value", "reference", "missing_reason"], [
                   {"site_id": "s1", "metric": "peak", "value": 0.7, "reference": 0.6,
                    "missing_reason": None},
               ])
    _write_csv(root / "export" / "t63_attribution.csv", ATTR_COLUMNS, [
        {"record": "contrast", "site_id": "ALL", "contrast": "M1_minus_M0",
         "variant_a": "obs_count_M1", "variant_b": "obs_count_M0", "metric": "peak",
         "value": -0.1, "sd": 0.02, "ci_low": -0.13, "ci_high": -0.07, "n_sites": 1,
         "sign_positive": 0, "sign_negative": 1, "missing_reason": None},
        {"record": "level", "site_id": "s1", "variant": "obs_count_M0",
         "metric": "peak", "value": 0.6, "sd": 0.05, "n_sites": 1},
    ])
    _write_csv(root / "export" / "t63_selection_diagnostic.csv", SELECTION_COLUMNS, [
        {"site_id": "s1", "mode": "R1", "registered_ev_bays": 5,
         "observed_peak_median": 4.0, "observed_peak_q90": 5.0,
         "observed_saturated_days_share": 0.2,
         "unconstrained_generated_peak_median": 6.0,
         "note": "observed sessions are served samples"},
    ])
    _write_csv(root / "export" / "t63_per_world_hindsight.csv", HINDSIGHT_COLUMNS, [
        _hindsight_row("week0", "w0", 0.5),
        _hindsight_row("week0", "w1", 0.0),
        _hindsight_row("week3", "w2", 2.25, n_hindsight=2),
        _hindsight_row("week3", "w3", 1.0, n_hindsight=3),
    ])
    _write_csv(root / "export" / "t63_fixed_cross_mechanism.csv", FIXED_COLUMNS,
               [_fixed_row("M0"), _fixed_row("M1"), _fixed_row("M2")])
    robust_rows = [
        {"site_id": "s1", "mode": "R1", "object": "A",
         "definition": "expectation over omega, then worst over (mechanism, scenario, theta)",
         "n_robust": 2, "n_robust_stress": None, "worst_case_regret": 0.5,
         "worst_case_regret_stress": None, "n_mechanisms": 3, "n_scenarios": 2,
         "n_realizations": None, "n_theta": 4, "coverage": 0.75},
        {"site_id": "s1", "mode": "R1", "object": "B",
         "definition": "worst over individual omega, then worst over (mechanism, scenario, theta)",
         "n_robust": None, "n_robust_stress": 3, "worst_case_regret": None,
         "worst_case_regret_stress": 1.25, "n_mechanisms": 3, "n_scenarios": 2,
         "n_realizations": 120, "n_theta": 4, "coverage": None},
    ]
    _write_csv(root / "export" / "t63_robust.csv", ROBUST_COLUMNS, robust_rows)
    _write_csv(root / "export" / "t63_expected_choice.csv",
               ["site_id", "scenario_id", "mode", "mechanism", "n_worlds", "n_star",
                "Jbar_at_n_star", "Jbar_min", "Jbar_minus_chosen", "argmin_set",
                "near_optimal_set", "n_grid_length"],
               [{"site_id": "s1", "scenario_id": "R1_base", "mode": "R1", "mechanism": mech,
                 "n_worlds": 4, "n_star": pivot, "Jbar_at_n_star": 70.25,
                 "Jbar_min": 70.25, "Jbar_minus_chosen": 0.0, "argmin_set": "[%d]" % pivot,
                 "near_optimal_set": "[%d]" % pivot, "n_grid_length": 4}
                for mech, pivot in zip(("M0", "M1", "M2"), (2, 2, 2))])
    _write_csv(root / "export" / "t63_stability.csv",
               ["site_id", "mode", "n_star_values", "n_distinct", "stable",
                "mechanism_choices", "scenario_span", "robust_A", "robust_B"],
               [{"site_id": "s1", "mode": "R1", "n_star_values": "[2]", "n_distinct": 1,
                 "stable": True, "mechanism_choices": "{}", "scenario_span": 0,
                 "robust_A": 2, "robust_B": 3}])
    tables = ["export/t63_table_a.csv", "export/t63_table_b.csv",
              "export/t63_noise_floor.csv", "export/t63_drift_reference.csv",
              "export/t63_expected_choice.csv", "export/t63_fixed_cross_mechanism.csv",
              "export/t63_robust.csv", "export/t63_stability.csv",
              "export/t63_attribution.csv", "export/t63_selection_diagnostic.csv",
              "export/t63_per_world_hindsight.csv"]

    fixed_index = [_fixed_row("M0"), _fixed_row("M1"), _fixed_row("M2")]
    index = {
        "schema_version": "nyc_viewer_v3/1",
        "code_version": "nyc_semisynthetic_t63",
        "generated_at": "2026-11-04T00:00:00+00:00",
        "registration": {"design_fingerprint": "design-fingerprint-0001",
                         "code_fingerprint": "code-fingerprint-0001",
                         "protocol": "research/.../results/protocol.json"},
        "counts": {"runs": 3, "worlds": 2, "runs_json": 3, "expected_rows": 3,
                   "fixed_rows": 3, "hindsight_rows": 4,
                   "holdout_table_a_rows": 3, "holdout_table_b_rows": 2,
                   "attribution_rows": 2},
        "sites": ["s1"],
        "scenarios": ["R1_base"],
        "runs": runs,
        "worlds": [
            {"world_id": "w_m0", "site_id": "s1", "scenario_id": "R1_base", "mode": "R1",
             "mechanism": "M0", "stage": "select", "block_id": "calib_last",
             "replicate": 0, "world_json": "world/world_w_m0.json",
             "world_hash": "sha256:abc", "sha256": "abc"},
            {"world_id": "w_r0", "site_id": "s1", "scenario_id": "R1_base", "mode": "R1",
             "mechanism": "R0", "stage": "select", "block_id": "calib_last",
             "replicate": 0, "world_json": "world/world_w_r0.json",
             "world_hash": "sha256:def", "sha256": "def",
             "label": "R0 real-anchor replay (observed sessions only)"},
        ],
        "panels": {
            "holdout": {"summary": {"table_summary": {}},
                        "table_a_csv": "export/t63_table_a.csv",
                        "table_b_csv": "export/t63_table_b.csv",
                        "noise_floor_csv": "export/t63_noise_floor.csv",
                        "drift_csv": "export/t63_drift_reference.csv",
                        "table_a_vs_b_note": "A imposes the hold-out week count and scores shape only; B predicts count+shape from train-only information. Never report A as B."},
            "attribution": {"csv": "export/t63_attribution.csv",
                            "rows": [{"record": "contrast", "site_id": "ALL",
                                      "contrast": "M1_minus_M0", "metric": "peak",
                                      "value": -0.1, "n_sites": 1,
                                      "sign_positive": 0, "sign_negative": 1}],
                            "selection_csv": "export/t63_selection_diagnostic.csv",
                            "note": "grouped controls change one mechanism at a time"},
            "decision": {"expected": [dict(run) for run in runs],
                         "fixed_eval": fixed_index,
                         "robust": robust_rows,
                         "stability": [],
                         "note": "expected-cost choice n*; fixed config evaluated on disjoint blocks"},
            "hindsight": {"csv": "export/t63_per_world_hindsight.csv", "rows": 4,
                          "definition": "fixed cost minus per-world hindsight minimum, >= 0",
                          "fields": list(HINDSIGHT_COLUMNS),
                          "sample": [_hindsight_row("week0", "w0", 0.5)]},
        },
        "limits": ["no queueing, no SOC curves", "scenario/theta grids carry no real-world probabilities"],
        "sources": {"protocol": "research/.../results/protocol.json",
                    "v2_registration": "research/.../v2/results/registration.json"},
        "downloads": {"tables": tables, "protocol": "research/.../results/protocol.json"},
    }
    with open(root / "index.json", "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False)
    return root


class _V3HTTPCase(unittest.TestCase):
    viewer_dir_v3 = None

    _ENV_KEYS = ("NYC_VIEWER_DIR", "NYC_VIEWER_DIR_V2", "NYC_VIEWER_DIR_V3",
                 "NYC_VIEWER_DATASET")

    @classmethod
    def setUpClass(cls):
        cls._previous_env = {key: os.environ.get(key) for key in cls._ENV_KEYS}
        base = Path(cls.viewer_dir_v3)
        os.environ["NYC_VIEWER_DIR"] = str(base.parent / "no-v1-viewer")
        os.environ["NYC_VIEWER_DIR_V2"] = str(base.parent / "no-v2-viewer")
        os.environ.pop("NYC_VIEWER_DATASET", None)
        os.environ["NYC_VIEWER_DIR_V3"] = str(cls.viewer_dir_v3)
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


class V3ViewerTests(_V3HTTPCase):
    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.viewer_dir_v3 = _write_v3_fixture(Path(cls._temp.name) / "viewer")
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._temp.cleanup()

    def test_health_reports_v3_dataset(self):
        status, payload, _ = self.get_json("/api/nyc/health?dataset=v3")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["dataset"], "v3")
        self.assertEqual(payload["schema_version"], "nyc_viewer_v3/1")
        self.assertEqual(payload["schema_kind"], "v3")
        self.assertTrue(payload["exists"])
        self.assertTrue(payload["index_present"])
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["runs"], 3)
        self.assertEqual(payload["worlds"], 2)

    def test_index_contract_and_panels(self):
        status, payload, _ = self.get_json("/api/nyc/index?dataset=v3")
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema_version"], "nyc_viewer_v3/1")
        self.assertEqual(payload["schema_kind"], "v3")
        self.assertEqual(payload["dataset"], "v3")
        self.assertIn("panels", payload)
        for name in ("holdout", "attribution", "decision", "hindsight"):
            self.assertIn(name, payload["panels"])
        self.assertEqual(payload["counts"]["runs"], 3)
        runs = {run["run_id"]: run for run in payload["runs"]}
        self.assertEqual(set(runs), set(RUN_IDS))
        for run in runs.values():
            self.assertTrue(run["run_json"].startswith("runs/"))
            self.assertTrue(run["curve_csv"].startswith("export/"))
            self.assertIn("n_star", run)
        worlds = {world["world_id"]: world for world in payload["worlds"]}
        self.assertEqual(worlds["w_r0"]["mechanism"], "R0")
        self.assertIn("label", worlds["w_r0"])
        self.assertEqual(payload["panels"]["hindsight"]["csv"],
                         "export/t63_per_world_hindsight.csv")
        self.assertEqual(len(payload["downloads"]["tables"]), 11)

    def test_run_payload_from_runs_dir(self):
        status, payload, _ = self.get_json(
            "/api/nyc/run/t63_s1_R1_base_M0?dataset=v3")
        self.assertEqual(status, 200)
        self.assertEqual(payload["run_id"], "t63_s1_R1_base_M0")
        self.assertEqual(payload["meta"]["mechanism"], "M0")
        self.assertEqual(payload["curve"]["n"], [0, 1, 2, 3])
        self.assertEqual(payload["choice"]["n_star"], 2)
        self.assertEqual(len(payload["fixed_eval"]), 1)
        self.assertEqual(payload["fixed_eval"][0]["registered_ev_bays"], 5)

    def test_world_payloads_include_r0(self):
        for world_id, mechanism in (("w_m0", "M0"), ("w_r0", "R0")):
            with self.subTest(world_id=world_id):
                status, payload, _ = self.get_json(
                    "/api/nyc/world/" + world_id + "?dataset=v3")
                self.assertEqual(status, 200)
                self.assertEqual(payload["world_id"], world_id)
                if mechanism == "M0":
                    self.assertEqual(payload["mechanism"], "M0")

    def test_export_json_is_real_run_file(self):
        status, raw, headers = self.get(
            "/api/nyc/export/t63_s1_R1_base_M0?format=json&dataset=v3")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn(".json", headers["Content-Disposition"])
        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(payload["run_id"], "t63_s1_R1_base_M0")

    def test_export_curve_csv_parses_as_csv(self):
        status, raw, headers = self.get(
            "/api/nyc/export/t63_s1_R1_base_M0?format=curve_csv&dataset=v3")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers["Content-Type"])
        text = raw.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(rows), 4)
        for key in ("n", "total", "capital", "refusal", "energy", "shortfall"):
            self.assertIn(key, rows[0])
        self.assertEqual([int(row["n"]) for row in rows], [0, 1, 2, 3])
        self.assertAlmostEqual(float(rows[2]["total"]), 70.25)

    def test_export_world_json(self):
        status, raw, headers = self.get(
            "/api/nyc/export/t63_s1_R1_base_M0?format=world_json&dataset=v3")
        self.assertEqual(status, 200)
        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(payload["world_id"], "w_m0")

    def test_bad_ids_and_formats(self):
        cases = (
            ("/api/nyc/run/unknown?dataset=v3", 404),
            ("/api/nyc/world/unknown?dataset=v3", 404),
            ("/api/nyc/export/unknown?format=json&dataset=v3", 404),
            ("/api/nyc/export/t63_s1_R1_base_M0?format=outcomes_csv&dataset=v3", 400),
            ("/api/nyc/export/t63_s1_R1_base_M0?format=xml&dataset=v3", 400),
            ("/api/nyc/run/..?dataset=v3", 400),
            ("/api/nyc/index?dataset=v9", 400),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, expected)

    def test_table_downloads_are_real_csv(self):
        status, raw, headers = self.get(
            "/api/nyc/table/t63_table_a.csv?dataset=v3")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers["Content-Type"])
        self.assertIn("t63_table_a.csv", headers["Content-Disposition"])
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["table"], "A")
        self.assertEqual(rows[2]["missing_reason"], "undefined_metric")

    def test_hindsight_table_comes_from_csv_file(self):
        status, raw, headers = self.get(
            "/api/nyc/table/t63_per_world_hindsight.csv?dataset=v3")
        self.assertEqual(status, 200)
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 4)
        self.assertEqual([row["world_id"] for row in rows], ["w0", "w1", "w2", "w3"])
        self.assertEqual([float(row["hindsight_gap"]) for row in rows], [0.5, 0.0, 2.25, 1.0])
        for key in ("n_selected", "J_fixed", "J_hindsight_min", "n_hindsight"):
            self.assertIn(key, rows[0])
        fixture_file = Path(self.viewer_dir_v3) / "export" / "t63_per_world_hindsight.csv"
        self.assertEqual(raw, fixture_file.read_bytes())

    def test_table_rejects_unknown_and_traversal_names(self):
        for path, expected in (
                ("/api/nyc/table/nope.csv?dataset=v3", 404),
                ("/api/nyc/table/t63_table_a.csv?dataset=v2", 404),
                ("/api/nyc/table/..%2findex.json?dataset=v3", 400),
                ("/api/nyc/table/t63_table_a.txt?dataset=v3", 400)):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, expected)

    def test_fixed_eval_and_robust_v3(self):
        status, fixed, _ = self.get_json("/api/nyc/fixed_eval?dataset=v3")
        self.assertEqual(status, 200)
        self.assertTrue(fixed["available"])
        self.assertEqual(fixed["count"], 3)
        status, robust, _ = self.get_json("/api/nyc/robust?dataset=v3")
        self.assertEqual(status, 200)
        self.assertTrue(robust["available"])
        self.assertEqual(robust["counts"], {"A": 1, "B": 1})
        self.assertEqual(robust["A"][0]["object"], "robust_A")
        self.assertEqual(robust["B"][0]["object"], "robust_B")
        self.assertEqual(robust["A"][0]["n_robust"], 2)
        self.assertIsNone(robust["A"][0]["n_robust_stress"])
        self.assertEqual(robust["B"][0]["n_robust_stress"], 3)
        self.assertIsNone(robust["B"][0]["n_robust"])

    def test_v3_static_page_and_assets(self):
        status, raw, _ = self.get("/nyc/")
        self.assertEqual(status, 200)
        text = raw.decode("utf-8")
        self.assertIn('data-dataset="v3"', text)
        self.assertIn('id="v3-content"', text)
        self.assertIn("逐世界事后最优", text)
        status, raw, _ = self.get("/nyc/app.js")
        self.assertEqual(status, 200)
        js = raw.decode("utf-8")
        self.assertIn("/api/nyc/table/", js)
        self.assertIn("v3-hindsight-table", js)
        self.assertIn("未定义", js)


class MissingV3ViewerTests(_V3HTTPCase):
    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.viewer_dir_v3 = Path(cls._temp.name) / "missing-v3-viewer"
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._temp.cleanup()

    def test_health_reports_missing_v3_without_500(self):
        status, payload, _ = self.get_json("/api/nyc/health?dataset=v3")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["exists"])
        self.assertFalse(payload["index_present"])
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["runs"], 0)

    def test_index_empty_payload_mentions_v3(self):
        status, payload, _ = self.get_json("/api/nyc/index?dataset=v3")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["schema_version"], "nyc_viewer_v3/1")
        self.assertIn("v3", payload["message"])
        self.assertEqual(payload["runs"], [])
        self.assertEqual(payload["panels"], {})

    def test_run_world_export_table_return_404_not_500(self):
        for path in ("/api/nyc/run/anything?dataset=v3",
                     "/api/nyc/world/anything?dataset=v3",
                     "/api/nyc/export/anything?format=json&dataset=v3",
                     "/api/nyc/table/t63_table_a.csv?dataset=v3"):
            with self.subTest(path=path):
                status, payload, _ = self.get_json(path)
                self.assert_json_error(status, payload, 404)


if __name__ == "__main__":
    unittest.main()
