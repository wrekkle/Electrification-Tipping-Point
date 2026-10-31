"""Contract, conservation, component, endpoint and original-formula checks."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True  # keep the read-only audit tree unchanged

import numpy as np

HERE = Path(__file__).resolve().parent
PREI = HERE.parent
ROOT = PREI.parent.parent
sys.path.insert(0, str(PREI))

import compare_with_matlab as compare  # noqa: E402
import reference  # noqa: E402
from reference import ContractError, allocate, evaluate, load_config, load_fixture  # noqa: E402

AUDIT = ROOT / "research" / "electrification" / "matlab_audit_20261029"


def audit_module():
    spec = importlib.util.spec_from_file_location("audit_numeric", AUDIT / "audit_numeric.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.configs = {}
        for path in sorted((PREI / "configs").glob("*.json")):
            cls.configs[path.stem] = load_config(path)
        cls.audit = audit_module()

    def test_both_model_variants_are_runnable(self):
        for case, cfg in self.configs.items():
            days = load_fixture(cfg)
            rows = evaluate(cfg, days)
            self.assertEqual(len(rows), len(days) * len(cfg["pile_ratios"]), case)
            self.assertEqual(cfg["model_variant"] in ("legacy_reference", "corrected_baseline"), True)

    def test_schema_rejects_unknown_key_and_bad_ratio(self):
        cfg = copy.deepcopy(self.configs["final_tvr_n40_legacy"])
        cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
        cfg["unexpected"] = 1
        with self.assertRaises(ContractError):
            reference.validate_config(cfg, PREI / "configs")
        cfg = copy.deepcopy(self.configs["final_tvr_n40_legacy"])
        cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
        cfg["pile_ratios"] = [0.5, 0.2, 1]
        with self.assertRaises(ContractError):
            reference.validate_config(cfg, PREI / "configs")

    def test_contract_rejects_incomplete_or_variable_day(self):
        columns = [
            "scenario_id", "hour", "ev_share_target", "total_arrivals",
            "ev_share_actual", "ev_fuel_cost", "ice_fuel_cost",
            "ev_time_cost", "ice_time_cost", "ev_complaint_cost",
            "ice_complaint_cost",
        ]
        base = {
            "schema_version": 1, "model_variant": "corrected_baseline",
            "source_case": "synthetic_contract_check", "n_spaces": 10,
            "installation_cost_rmb_per_pile": 100.0, "amortization_years": 5.0,
            "partial_shared_fraction": 0.0, "full_install_open_to_all": True,
            "pile_ratios": [0.0, 0.5, 1.0], "ev_share_targets": [0.4],
            "fixture_file": "fixture.csv",
        }
        rows = [["day", h, 0.4, 100.0, 0.4, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
                for h in range(24)]
        cases = [
            ("missing_hour", rows[:-1], "hours 0..23"),
            ("out_of_day_hour", rows[:-1] + [["day", 24, 0.4, 100.0, 0.4,
                                              1.0, 1.0, 1.0, 1.0, 1.0, 1.0]],
             "0..23"),
            ("variable_daily_unit_rate",
             rows[:-1] + [["day", 23, 0.4, 100.0, 0.4, 2.0, 1.0, 1.0,
                           1.0, 1.0, 1.0]], "changes inside day"),
        ]
        for name, values, pattern in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                (directory / "fixture.csv").write_text(
                    "\n".join(",".join(map(str, row)) for row in [columns] + values) + "\n",
                    "utf-8")
                (directory / "config.json").write_text(
                    json.dumps(base), "utf-8")
                with self.assertRaises(ContractError) as raised:
                    load_fixture(load_config(directory / "config.json"))
                self.assertIn(pattern, str(raised.exception))

    def test_legacy_policy_outside_default_is_rejected(self):
        base = {
            "schema_version": 1, "model_variant": "legacy_reference",
            "source_case": "synthetic_contract_check", "n_spaces": 10,
            "installation_cost_rmb_per_pile": 100.0, "amortization_years": 5.0,
            "partial_shared_fraction": 0.0, "full_install_open_to_all": True,
            "pile_ratios": [0.0, 0.5, 1.0], "ev_share_targets": [0.4],
            "fixture_file": "fixture.csv",
        }
        rows = [["day", h, 0.4, 100.0, 0.4, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
                for h in range(24)]
        columns = [
            "scenario_id", "hour", "ev_share_target", "total_arrivals",
            "ev_share_actual", "ev_fuel_cost", "ice_fuel_cost",
            "ev_time_cost", "ice_time_cost", "ev_complaint_cost",
            "ice_complaint_cost",
        ]
        cases = {
            "legacy_positive_sharing": {"partial_shared_fraction": 0.4},
            "legacy_closed_full": {"full_install_open_to_all": False},
        }
        for name, override in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                (directory / "fixture.csv").write_text(
                    "\n".join(",".join(map(str, row)) for row in [columns] + rows) + "\n",
                    "utf-8")
                config = dict(base)
                config.update(override)
                (directory / "config.json").write_text(
                    json.dumps(config), "utf-8")
                with self.assertRaises(ContractError) as raised:
                    load_config(directory / "config.json")
                self.assertIn("config schema error", str(raised.exception))

    def test_v2_parameters_match_audit(self):
        cfg = self.configs["v2_n10786_corrected"]
        p, q = self.audit.parameters()
        self.assertEqual(cfg["n_spaces"], int(q["n"]))
        self.assertEqual(cfg["installation_cost_rmb_per_pile"], q["installation"])
        self.assertEqual(cfg["amortization_years"], q["years"])
        self.assertEqual(q["od_arr_min"], 42)
        self.assertEqual(q["rho_nev_min"], .09)
        self.assertEqual(cfg["n_spaces"], 10786)
        self.assertEqual(cfg["installation_cost_rmb_per_pile"], 60000)

    def test_final_tvr_parameters_match_audit(self):
        cfg = self.configs["final_tvr_n40_legacy"]
        p, _ = self.audit.parameters()
        self.assertEqual(cfg["n_spaces"], int(p["n"]))
        self.assertEqual(cfg["installation_cost_rmb_per_pile"], p["installation"])
        self.assertEqual(p["installation"], 70100)
        self.assertEqual(cfg["amortization_years"], 8)

    def test_deterministic_legacy_matches_audit_oracle_all_441_cells(self):
        cfg = self.configs["final_tvr_n40_legacy"]
        days = load_fixture(cfg)
        rows = evaluate(cfg, days)
        p, _ = self.audit.parameters()
        cost, ev, ice = self.audit.deterministic_formula(p)
        n_r, n_t = len(cfg["pile_ratios"]), len(cfg["ev_share_targets"])
        matrix = np.array([r["total_daily_cost"] for r in rows]).reshape(n_t, n_r).T
        ev_m = np.array([r["ev_rejected"] for r in rows]).reshape(n_t, n_r).T
        ice_m = np.array([r["ice_rejected"] for r in rows]).reshape(n_t, n_r).T
        # audit cost rows are r; columns are ICE share u, so reverse to EV share.
        np.testing.assert_allclose(matrix, cost[:, ::-1], rtol=0, atol=1e-9)
        np.testing.assert_allclose(ev_m, ev[:, ::-1], rtol=0, atol=1e-9)
        np.testing.assert_allclose(ice_m, ice[:, ::-1], rtol=0, atol=1e-9)
        self.assertEqual(matrix.shape, (21, 21))

    def test_legacy_full_install_omits_ev_complaint_only_there(self):
        legacy = self.configs["final_tvr_n40_legacy"]
        corrected = self.configs["final_tvr_n40_corrected"]
        rows_l = evaluate(legacy, load_fixture(legacy))
        rows_c = evaluate(corrected, load_fixture(corrected))
        full = [r for r in rows_l if r["pile_ratio"] == 1.0]
        self.assertTrue(all(r["ev_complaint_cost"] == 0 for r in full))
        self.assertTrue(any(r["ev_rejected"] > 0 for r in full))
        partial_l = [r for r in rows_l if r["pile_ratio"] < 1.0]
        partial_c = [r for r in rows_c if r["pile_ratio"] < 1.0]
        self.assertEqual([r["total_daily_cost"] for r in partial_l],
                         [r["total_daily_cost"] for r in partial_c])

    def test_capital_charged_once_per_day(self):
        cfg = self.configs["final_tvr_n40_corrected"]
        rows = evaluate(cfg, load_fixture(cfg))
        for row in rows:
            expected = cfg["n_spaces"] * row["pile_ratio"] * cfg["installation_cost_rmb_per_pile"] / (
                365.0 * cfg["amortization_years"])
            self.assertAlmostEqual(row["capital_daily_cost"], expected, places=12)

    def test_component_identity_and_nonnegative(self):
        for cfg in self.configs.values():
            for row in evaluate(cfg, load_fixture(cfg)):
                parts = sum(row[name] for name in (
                    "capital_daily_cost", "ev_fuel_cost", "ice_fuel_cost",
                    "ev_time_cost", "ice_time_cost", "ev_complaint_cost",
                    "ice_complaint_cost"))
                self.assertAlmostEqual(parts, row["total_daily_cost"], delta=1e-6)
                self.assertGreaterEqual(row["ev_rejected"], 0)
                self.assertGreaterEqual(row["ice_rejected"], 0)

    def test_gaps_are_signed_differences(self):
        cfg = self.configs["final_tvr_n40_corrected"]
        rows = evaluate(cfg, load_fixture(cfg))
        for day, group in __import__("itertools").groupby(
                sorted(rows, key=lambda r: (r["scenario_id"], r["ev_share_target"])),
                key=lambda r: (r["scenario_id"], r["ev_share_target"])):
            group = list(group)
            full = next(r for r in group if r["pile_ratio"] == 1.0)
            partial_best = min(r["total_daily_cost"] for r in group
                               if r["pile_ratio"] < 1.0)
            for row in group:
                self.assertAlmostEqual(row["delta_candidate_minus_full"],
                                       row["total_daily_cost"] - full["total_daily_cost"], places=10)
                self.assertAlmostEqual(row["g_full_minus_best_partial"],
                                       full["total_daily_cost"] - partial_best, places=10)


class AllocationTests(unittest.TestCase):
    def test_partial_sharing_counterexample(self):
        ev_rej, ice_rej, _, _ = allocate(total_arrivals=105, ev_share_actual=.4,
                                         n_spaces=100, pile_ratio=.5,
                                         shared_fraction=.4, open_to_all=False)
        self.assertAlmostEqual(ev_rej, 5.0)
        self.assertAlmostEqual(ice_rej, 0.0)

    def test_h0_is_strict_partition(self):
        ev_rej, ice_rej, _, _ = allocate(200, .7, 100, .5, 0.0, False)
        self.assertAlmostEqual(ev_rej, 140 - 50)
        self.assertAlmostEqual(ice_rej, 60 - 50)

    def test_full_install_open_to_all_splits_total_overflow(self):
        ev_rej, ice_rej, ev_acc, ice_acc = allocate(120, .25, 100, 1.0, 0.0, True)
        self.assertAlmostEqual(ev_rej, 20 * .25)
        self.assertAlmostEqual(ice_rej, 20 * .75)
        self.assertAlmostEqual(ev_acc + ice_acc, 100)

    def test_conservation_and_capacity(self):
        for total in (0, 37, 100, 105, 260):
            for ev_share in (0, .2, .4, .7, 1):
                for ratio in (0, .5, 1):
                    for h in (0, .4, 1):
                        ev_rej, ice_rej, ev_acc, ice_acc = allocate(
                            total, ev_share, 100, ratio, h, True)
                        ev_d, ice_d = total * ev_share, total * (1 - ev_share)
                        self.assertLessEqual(ev_acc, ev_d + 1e-9)
                        self.assertLessEqual(ice_acc, ice_d + 1e-9)
                        self.assertLessEqual(ev_acc + ice_acc, 100 + 1e-9)
                        self.assertGreaterEqual(ev_acc, -1e-9)
                        self.assertGreaterEqual(ice_acc, -1e-9)


class ComparatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_dir = PREI / "runs" / "run2_v1_legacy"
        if not (cls.run_dir / "raw_cost_matrix.csv").is_file():
            raise unittest.SkipTest(f"missing {cls.run_dir}; generate the Python baselines first")
        cls.meta = json.loads((cls.run_dir / "metadata.json").read_text("utf-8"))
        cls.config_hash = cls.meta["input"]["config_sha256"]
        cls.fixture_hash = cls.meta["input"]["fixture_sha256"]

    def _copy(self, tmp):
        import shutil
        dst = Path(tmp) / "candidate"
        shutil.copytree(self.run_dir, dst)
        return dst

    def test_real_output_flags_and_ties_use_true_false(self):
        text = (self.run_dir / "raw_cost_matrix.csv").read_text("utf-8")
        self.assertIn("True", text)
        self.assertIn("False", text)
        _, rows = compare.read_csv(self.run_dir / "raw_cost_matrix.csv",
                                   list(compare.KEY_COLUMNS)
                                   + list(compare.NUMERIC_COLUMNS) + ["is_optimal"])
        indexed = compare.index_rows(rows, True)
        ties, errors, mismatches = compare.optimal_sets(indexed, True)
        self.assertEqual(errors, [])
        self.assertEqual(mismatches, [])
        self.assertEqual(len(ties), 21)
        self.assertTrue(all(tie for tie in ties.values()))
        self.assertEqual(compare.parse_flag("True"), True)
        self.assertEqual(compare.parse_flag("False"), False)
        self.assertEqual(compare.parse_flag("1"), True)
        self.assertEqual(compare.parse_flag("0"), False)

    def test_near_tie_within_tolerance_is_tied(self):
        base = {
            ("d", 0.0, 0.0): {"total_daily_cost": "100.0", "is_optimal": "True"},
            ("d", 0.0, 0.05): {"total_daily_cost": "100.000000005", "is_optimal": "True"},
        }
        ties, errors, mismatches = compare.optimal_sets(base, True)
        self.assertEqual(ties[("d", 0.0)], {0.0, 0.05})
        self.assertEqual(errors, [])
        self.assertEqual(mismatches, [])
        base[("d", 0.0, 0.05)]["is_optimal"] = "False"
        _, _, mismatches = compare.optimal_sets(base, True)
        self.assertEqual(len(mismatches), 1)

    def test_same_path_is_not_a_cross_language_pass(self):
        code, report = compare.compare(self.run_dir, self.run_dir)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "self_comparison")

    def test_copied_run_with_same_hashes_passes_logic(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dst = self._copy(tmp)
            code, report = compare.compare_safe(self.run_dir, dst)
        self.assertEqual(code, 0, json.dumps(report, indent=2)[:2000])
        self.assertTrue(report["input_identity"]["same_fixed_input"])
        self.assertTrue(report["optimal_set_compared"])

    def test_m_style_metadata_hash_aliases(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dst = self._copy(tmp)
            (dst / "metadata.json").unlink()
            (dst / "run_metadata.json").write_text(json.dumps({
                "inputs": {"config_sha": self.config_hash,
                           "fixture_hash": self.fixture_hash}
            }), "utf-8")
            code, report = compare.compare_safe(self.run_dir, dst)
        self.assertEqual(code, 0, json.dumps(report, indent=2)[:2000])

    def test_missing_candidate_hash_is_unverified_not_pass(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dst = self._copy(tmp)
            (dst / "metadata.json").write_text(json.dumps({
                "inputs": {"config_sha": self.config_hash}
            }), "utf-8")
            code, report = compare.compare_safe(self.run_dir, dst)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "unverified")
        self.assertFalse(report["input_identity"]["same_fixed_input"])

    def test_hash_mismatch_fails_even_when_numbers_match(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dst = self._copy(tmp)
            data = json.loads((dst / "metadata.json").read_text("utf-8"))
            data["input"]["fixture_sha256"] = "0" * 64
            (dst / "metadata.json").write_text(json.dumps(data), "utf-8")
            code, report = compare.compare_safe(self.run_dir, dst)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "unverified")
        self.assertFalse(report["input_identity"]["same_fixed_input"])

    def test_duplicate_result_key_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dst = self._copy(tmp)
            lines = (dst / "raw_cost_matrix.csv").read_text("utf-8").splitlines()
            (dst / "raw_cost_matrix.csv").write_text("\n".join(
                [lines[0], lines[1], lines[1]] + lines[2:]) + "\n", "utf-8")
            code, report = compare.compare_safe(self.run_dir, dst)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "contract_error")
        self.assertIn("duplicate", report["reason"])

    def test_empty_matrix_and_missing_column_are_clear_failures(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dst = self._copy(tmp)
            lines = (dst / "raw_cost_matrix.csv").read_text("utf-8").splitlines()
            (dst / "raw_cost_matrix.csv").write_text(lines[0] + "\n", "utf-8")
            code, report = compare.compare_safe(self.run_dir, dst)
            self.assertEqual((code, report["status"]), (1, "contract_error"))
            self.assertIn("no data rows", report["reason"])
            header = lines[0].replace("ev_fuel_cost", "ev_fuel_cost_typo")
            (dst / "raw_cost_matrix.csv").write_text(
                header + "\n" + "\n".join(lines[1:]) + "\n", "utf-8")
            code, report = compare.compare_safe(self.run_dir, dst)
            self.assertEqual((code, report["status"]), (1, "contract_error"))
            self.assertIn("missing required columns", report["reason"])

    def test_daily_optimal_only_is_partial_not_full_pass(self):
        code, report = compare.compare(self.run_dir, self.run_dir / "daily_optimal.csv")
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "partial_daily_optimal_only")
        self.assertFalse(report["optimal_set_compared"])
        self.assertIn("NOT a full", report["verdict"])

    def test_missing_candidate_is_pending_not_pass(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            code, report = compare.compare(self.run_dir, Path(tmp))
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "pending_matlab_output")

    def test_actual_m_output_if_present(self):
        pairs = [
            ("run2_v1_legacy", "m2_final_tvr_n40_legacy"),
            ("run2_v1_corrected", "m2_final_tvr_n40_corrected"),
            ("run2_v2_legacy", "m2_v2_n10786_legacy"),
            ("run2_v2_corrected", "m2_v2_n10786_corrected"),
        ]
        tested = 0
        for ref_name, cand_name in pairs:
            candidate = ROOT / "matlab" / "prei" / "runs" / cand_name
            if not (candidate / "raw_cost_matrix.csv").is_file():
                continue
            code, report = compare.compare(PREI / "runs" / ref_name, candidate)
            self.assertEqual(code, 0, json.dumps(report, indent=2)[:3000])
            self.assertTrue(report["input_identity"]["same_fixed_input"])
            self.assertEqual(report["tie_mismatches"], [])
            tested += 1
        if tested == 0:
            self.skipTest("M output not delivered yet")


if __name__ == "__main__":
    unittest.main(verbosity=2)


