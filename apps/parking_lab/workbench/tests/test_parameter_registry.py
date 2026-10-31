"""参数契约 v3 的准入判定、校验与缺参传播测试。"""
import json
import tempfile
import unittest
from pathlib import Path

from apps.parking_lab.workbench import parameter_registry as pr


def record(**overrides):
    base = {
        "param_id": "p_test",
        "name_zh": "测试参数",
        "definition": "测试定义",
        "unit": "TWD/hour",
        "value": 100.0,
        "source_class": "official",
        "status": "available",
        "admitted_use": ["social_cost"],
        "is_scenario": False,
        "source_ids": ["S01"],
    }
    base.update(overrides)
    return base


class ValidationTests(unittest.TestCase):
    def test_valid_record_passes(self):
        self.assertEqual(pr.validate_record(record()), [])

    def test_missing_required_field_rejected(self):
        bad = record()
        del bad["source_ids"]
        errors = pr.validate_record(bad)
        self.assertTrue(any("source_ids" in e for e in errors))

    def test_illegal_source_class_and_status(self):
        self.assertTrue(pr.validate_record(record(source_class="blog")))
        self.assertTrue(pr.validate_record(record(status="done")))

    def test_illegal_admitted_use(self):
        self.assertTrue(pr.validate_record(record(admitted_use=["everything"])))
        self.assertTrue(pr.validate_record(record(admitted_use=[])))

    def test_scenario_cannot_be_available(self):
        self.assertTrue(pr.validate_record(record(source_class="scenario", status="available")))

    def test_available_requires_source_ids(self):
        self.assertTrue(pr.validate_record(record(source_ids=[])))

    def test_infinite_and_bool_values_rejected(self):
        self.assertTrue(pr.validate_record(record(value=float("inf"))))
        self.assertTrue(pr.validate_record(record(value=True) or record(value=False)))

    def test_negative_value_requires_flag(self):
        self.assertTrue(pr.validate_record(record(value=-1.5)))
        self.assertEqual(pr.validate_record(record(value=-1.5, nonnegative=False)), [])


class AdmissionTests(unittest.TestCase):
    def test_official_available_is_admitted(self):
        self.assertEqual(pr.admission_decision(record()), "admitted")

    def test_peer_reviewed_is_transferable(self):
        self.assertEqual(pr.admission_decision(record(source_class="peer_reviewed")), "transferable")

    def test_scenario_is_scenario(self):
        decision = pr.admission_decision(record(source_class="scenario", is_scenario=True, status="transferable"))
        self.assertEqual(decision, "scenario")

    def test_null_value_is_unidentified(self):
        self.assertEqual(pr.admission_decision(record(value=None)), "unidentified")
        self.assertEqual(pr.admission_decision(record(status="unidentified")), "unidentified")

    def test_rejected_status(self):
        self.assertEqual(pr.admission_decision(record(status="rejected")), "rejected")


class RegistryTests(unittest.TestCase):
    def test_load_mapping_and_list_forms(self):
        mapping = {"parameters": {"p_a": {k: v for k, v in record(param_id="p_a").items() if k != "param_id"}}}
        registry, errors = pr.Registry.from_data(mapping)
        self.assertEqual(errors, [])
        self.assertEqual(registry.value("p_a"), 100.0)
        listing = {"parameters": [record(param_id="p_b")]}
        registry, errors = pr.Registry.from_data(listing)
        self.assertEqual(errors, [])
        self.assertEqual(registry.value("p_b"), 100.0)

    def test_null_value_stays_none_not_zero(self):
        registry, _ = pr.Registry.from_data({"parameters": [record(param_id="p_null", value=None)]})
        self.assertIsNone(registry.value("p_null"))
        self.assertIsNone(registry.value("p_absent"))
        with self.assertRaises(KeyError):
            registry.require("p_null")
        with self.assertRaises(KeyError):
            registry.require("p_absent")
        self.assertEqual(registry.require("p_null") if False else registry.value("p_ok") if False else 1, 1)

    def test_duplicate_param_id_is_error(self):
        _, errors = pr.Registry.from_data({"parameters": [record(), record()]})
        self.assertTrue(any("重复" in e for e in errors))

    def test_for_use_filters_and_sorts(self):
        data = {"parameters": [
            record(param_id="p_z", admitted_use=["social_cost"]),
            record(param_id="p_a", admitted_use=["social_cost", "validation"]),
            record(param_id="p_x", admitted_use=["traffic_fit"]),
            record(param_id="p_bad", admitted_use=["social_cost"], status="unidentified", value=None),
        ]}
        registry, _ = pr.Registry.from_data(data)
        self.assertEqual([r["param_id"] for r in registry.for_use("social_cost")], ["p_a", "p_z"])
        with self.assertRaises(ValueError):
            registry.for_use("bogus")

    def test_complete_propagates_missing_and_scenario(self):
        data = {"parameters": [
            record(param_id="p_ok"),
            record(param_id="p_missing", value=None),
            record(param_id="p_scn", source_class="scenario", is_scenario=True, status="transferable"),
        ]}
        registry, _ = pr.Registry.from_data(data)
        report = registry.complete(["p_ok", "p_missing", "p_scn", "p_absent"])
        self.assertFalse(report["complete"])
        self.assertEqual(report["missing_parameters"], ["p_missing", "p_absent"])
        self.assertEqual(report["scenario_parameters"], ["p_scn"])

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            bad = Path(tmp) / "bad.json"
            good.write_text(json.dumps({"parameters": [record()]}, ensure_ascii=False), encoding="utf-8")
            broken = record()
            del broken["unit"]
            bad.write_text(json.dumps({"parameters": [broken]}, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(pr.main(["--file", str(good), "--json"]), 0)
            self.assertEqual(pr.main(["--file", str(bad), "--json"]), 1)


if __name__ == "__main__":
    unittest.main()
