# -*- coding: utf-8 -*-
"""Round-4 tests: source-scenario provenance and q_use→q_need guardrails."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.parking_lab.workbench import charge_sources


def _record(**overrides):
    record = {
        "scenario_id": "SC-TEST", "source_id": "M08", "version": "2026-10-31",
        "probability_object": "q_use",
        "numerator": "EV parking events with charging",
        "denominator": "all EV parking events",
        "event_definition": "one EV parking episode",
        "region": "San Diego", "period": "2013", "vehicle_type": "BEV",
        "location_type": "near public EVSE",
        "p_ev": 0.10, "q_need": 0.286, "value": 0.286,
        "source_class": "peer_reviewed", "source_ids": ["M08"],
        "transfer": {"type": "hypothetical_transfer",
                     "statement": "假设性迁移：仅用于情景/敏感性，不是目标场景识别值。"},
        "limitations": "historical, non-Taipei, parking-event denominator",
    }
    record.update(overrides)
    return record


class ChargeSourcesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "catalog.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, records):
        self.path.write_text(json.dumps({"schema_version": charge_sources.SCHEMA_VERSION,
                                         "scenarios": records}, ensure_ascii=False),
                             encoding="utf-8")

    def test_valid_transfer_resolves_with_hashes_and_warning(self):
        self.write([_record()])
        out = charge_sources.resolve(self.path, "SC-TEST")
        self.assertEqual(out["p_ev"], 0.10)
        self.assertEqual(out["q_need"], 0.286)
        prov = out["provenance"]
        self.assertTrue(prov["q_use_as_q_need"])
        self.assertEqual(prov["identification_status"],
                         "hypothetical_scenario_transfer_not_target_identified")
        self.assertEqual(len(prov["catalog_sha256"]), 64)
        self.assertEqual(len(prov["record_sha256"]), 64)
        self.assertIn("假设性迁移", prov["transfer"]["statement"])

    def test_q_use_without_transfer_is_rejected(self):
        self.write([_record(transfer={"type": "direct", "statement": ""})])
        with self.assertRaises(charge_sources.SourceScenarioError):
            charge_sources.resolve(self.path, "SC-TEST")

    def test_transfer_statement_must_name_hypothetical(self):
        self.write([_record(transfer={"type": "hypothetical_transfer",
                                      "statement": "used as scenario"})])
        with self.assertRaises(charge_sources.SourceScenarioError):
            charge_sources.resolve(self.path, "SC-TEST")

    def test_rejects_location_share_or_device_utilization(self):
        for obj in ("q_location_share", "device_time_utilization"):
            self.write([_record(probability_object=obj)])
            with self.assertRaises(charge_sources.SourceScenarioError):
                charge_sources.resolve(self.path, "SC-TEST")

    def test_rejects_non_finite_and_out_of_range(self):
        for bad in (float("nan"), float("inf"), -0.1, 1.01):
            self.write([_record(q_need=bad)])
            with self.assertRaises(charge_sources.SourceScenarioError):
                charge_sources.resolve(self.path, "SC-TEST")
        self.write([_record(p_ev=0.0)])
        with self.assertRaises(charge_sources.SourceScenarioError):
            charge_sources.resolve(self.path, "SC-TEST")

    def test_rejects_duplicate_ids_and_missing_fields(self):
        self.write([_record(), _record()])
        with self.assertRaises(charge_sources.SourceScenarioError):
            charge_sources.resolve(self.path, "SC-TEST")
        missing = _record()
        del missing["numerator"]
        self.write([missing])
        with self.assertRaises(charge_sources.SourceScenarioError):
            charge_sources.resolve(self.path, "SC-TEST")

    def test_record_hash_changes_with_value_but_catalog_validates(self):
        self.write([_record()])
        h1 = charge_sources.resolve(self.path, "SC-TEST")["provenance"]["record_sha256"]
        self.write([_record(q_need=0.237, value=0.237)])
        h2 = charge_sources.resolve(self.path, "SC-TEST")["provenance"]["record_sha256"]
        self.assertNotEqual(h1, h2)

    def test_unknown_scenario_lists_choices(self):
        self.write([_record()])
        with self.assertRaises(charge_sources.SourceScenarioError) as ctx:
            charge_sources.resolve(self.path, "NOPE")
        self.assertIn("SC-TEST", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
