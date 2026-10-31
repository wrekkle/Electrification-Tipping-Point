"""publicdata（契约适配层）单元测试：校验 / 场站-日切分 / 经验重采样 / 覆盖度。

只用手写小契约，不依赖数据文件；口径见 apps/parking_lab/workbench/publicdata.py docstring。
"""
import copy
import json
import random
import unittest

from apps.parking_lab.workbench import publicdata

SCHEMA = publicdata.CONTRACT_SCHEMA_VERSION


def event(event_id, site_id, ts, dwell, is_ev, needs=None, energy=None):
    record = {"event_id": event_id, "site_id": site_id, "arrival_ts": ts,
              "dwell_min": dwell, "is_ev": is_ev}
    if needs is not None:
        record["needs_charge"] = needs
    if energy is not None:
        record["energy_kwh"] = energy
    return record


def payload(days=("2024-03-04", "2024-03-05")):
    sites = [
        {"site_id": "S1", "n_spaces": 10, "charging_bays": 4, "connectors": 2,
         "connector_kw": 7.0, "feeder_kw": 14.0},
        {"site_id": "S2", "n_spaces": 8, "charging_bays": 3, "connectors": 2,
         "connector_kw": 7.0, "feeder_kw": 14.0},
    ]
    events = []
    for day in days:
        events.append(event("S1-%s-a" % day, "S1", day + "T08:00:00+08:00", 60, True, True, 8.0))
        events.append(event("S1-%s-b" % day, "S1", day + "T09:30:00+08:00", 45, False, False, 0.0))
        events.append(event("S2-%s-a" % day, "S2", day + "T10:00:00+08:00", 90, True, False))
        events.append(event("S2-%s-b" % day, "S2", day + "T11:15:00+08:00", 30, False, False, 0.0))
    return {"schema_version": SCHEMA, "dataset_id": "unit-test",
            "sites": sites, "events": events}


class ValidateTests(unittest.TestCase):
    def test_valid_payload(self):
        report = publicdata.validate_contract(payload())
        self.assertTrue(report["ok"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["counts"]["sites"], 2)
        self.assertEqual(report["counts"]["events_accepted"], 8)
        self.assertEqual(report["counts"]["events_rejected"], 0)
        normalised = report["normalised"]
        self.assertEqual(sorted(normalised["sites"]), ["S1", "S2"])

    def test_schema_version_mismatch(self):
        bad = payload()
        bad["schema_version"] = "unknown/v9"
        report = publicdata.validate_contract(bad)
        self.assertFalse(report["ok"])
        self.assertIn("schema", {item["kind"] for item in report["errors"]})
        with self.assertRaises(publicdata.ContractError):
            publicdata.normalise_contract(bad)

    def _error_kinds(self, mutate):
        bad = payload()
        mutate(bad)
        report = publicdata.validate_contract(bad)
        return {item["kind"] for item in report["errors"]}, report

    def test_missing_dwell(self):
        def mutate(bad):
            del bad["events"][0]["dwell_min"]
        kinds, report = self._error_kinds(mutate)
        self.assertIn("missing_field", kinds)
        self.assertEqual(report["counts"]["events_rejected"], 1)

    def test_zero_dwell_out_of_range(self):
        def mutate(bad):
            bad["events"][0]["dwell_min"] = 0
        kinds, _ = self._error_kinds(mutate)
        self.assertIn("out_of_range", kinds)

    def test_duplicate_event_id_exact_duplicate_rejected(self):
        # 完全相同的记录（同一场站/到达/停留/能量）判 duplicate_id
        def mutate(bad):
            clone = dict(bad["events"][0])
            clone["arrival_ts"] = bad["events"][2]["arrival_ts"]  # 不同到达，先构造非重复
            bad["events"].append({**bad["events"][0]})  # 与第 0 条完全相同
        kinds, report = self._error_kinds(mutate)
        self.assertIn("duplicate_id", kinds)
        self.assertEqual(report["counts"]["events_rejected"], 1)

    def test_reused_event_id_is_rekeyed_not_dropped(self):
        # 来源行号型 id 在多个日期复用（命名空间问题）：重编号并记 warning，不丢事件
        def mutate(bad):
            bad["events"][1]["event_id"] = bad["events"][0]["event_id"]
        bad = payload()
        mutate(bad)
        report = publicdata.validate_contract(bad)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["counts"]["events_accepted"], 8)
        self.assertTrue(any(item["kind"] == "duplicate_id_rekeyed" for item in report["warnings"]))
        ids = [row["event_id"] for row in report["normalised"]["events"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_unknown_site(self):
        def mutate(bad):
            bad["events"][0]["site_id"] = "S9"
        kinds, _ = self._error_kinds(mutate)
        self.assertIn("unknown_site", kinds)

    def test_naive_timestamp_rejected(self):
        def mutate(bad):
            bad["events"][0]["arrival_ts"] = "2024-03-04T08:00:00"
        kinds, _ = self._error_kinds(mutate)
        self.assertIn("bad_timestamp", kinds)

    def test_charge_on_ice_rejected(self):
        def mutate(bad):
            bad["events"][1]["needs_charge"] = True
            bad["events"][1]["energy_kwh"] = 5.0
        kinds, _ = self._error_kinds(mutate)
        self.assertIn("illegal_value", kinds)

    def test_missing_is_ev(self):
        def mutate(bad):
            del bad["events"][0]["is_ev"]
        kinds, _ = self._error_kinds(mutate)
        self.assertIn("missing_field", kinds)

    def test_field_aliases_accepted(self):
        bad = payload()
        bad["events"][0] = {"id": "alias-1", "lot_id": "S1",
                            "arrival_time": "2024-03-04T07:00:00+08:00",
                            "duration_min": 30, "electric": "yes",
                            "charge_request": "true", "kwh": 6.0}
        report = publicdata.validate_contract(bad)
        self.assertTrue(report["ok"], report["errors"])
        row = report["normalised"]["events"][0]
        self.assertEqual(row["event_id"], "alias-1")
        self.assertEqual(row["dwell_min"], 30.0)
        self.assertTrue(row["is_ev"])
        self.assertEqual(row["energy_kwh"], 6.0)

    def test_parse_ts_offsets(self):
        epoch, day, minute = publicdata.parse_ts("2024-03-04T08:15:00+08:00")
        self.assertEqual(day, "2024-03-04")
        self.assertAlmostEqual(minute, 8 * 60 + 15)
        epoch_utc, day_utc, minute_utc = publicdata.parse_ts("2024-03-04T00:15:00Z")
        self.assertEqual(day_utc, "2024-03-04")
        self.assertAlmostEqual(epoch, epoch_utc)
        self.assertAlmostEqual(minute_utc, 15)
        with self.assertRaises(ValueError):
            publicdata.parse_ts("2024-03-04T08:15:00")


class SplitTests(unittest.TestCase):
    def _blocks(self, data=None):
        normalised = publicdata.normalise_contract(data or payload())
        return publicdata.site_day_blocks(normalised)

    def test_blocks_unit_and_order(self):
        blocks = self._blocks()
        self.assertEqual(len(blocks), 4)  # 2 场站 x 2 日
        for block in blocks:
            times = [row["arrival_min"] for row in block["events"]]
            self.assertEqual(times, sorted(times))
            self.assertEqual(block["n_events"], 2)

    def test_split_no_overlap(self):
        blocks = self._blocks()
        split = publicdata.split_site_days(blocks, seed=7, holdout_site_fraction=0.5,
                                           holdout_day_fraction=0.5)
        cal = {(b["site_id"], b["day_key"]) for b in split["calibration"]}
        test = {(b["site_id"], b["day_key"]) for b in split["test"]}
        self.assertFalse(cal & test)
        self.assertEqual(len(cal) + len(test), len(blocks))
        self.assertTrue(split["test_site_ids"])
        for block in split["test"]:
            self.assertTrue(block["site_id"] in split["test_site_ids"]
                            or block["day_key"] in split["test_day_keys"])
        for block in split["calibration"]:
            self.assertNotIn(block["site_id"], split["test_site_ids"])
            self.assertNotIn(block["day_key"], split["test_day_keys"])

    def test_split_deterministic(self):
        blocks = self._blocks()
        first = publicdata.split_site_days(blocks, seed=11)
        second = publicdata.split_site_days(blocks, seed=11)
        self.assertEqual([(b["site_id"], b["day_key"]) for b in first["test"]],
                         [(b["site_id"], b["day_key"]) for b in second["test"]])

    def test_single_site_split_degrades_honestly(self):
        data = payload()
        data["sites"] = data["sites"][:1]
        data["events"] = [row for row in data["events"] if row["site_id"] == "S1"]
        blocks = self._blocks(data)
        split = publicdata.split_site_days(blocks, seed=3)
        self.assertEqual(split["test_site_ids"], [])
        self.assertTrue(any(item["path"] == "split.site_holdout" for item in split["warnings"]))
        self.assertTrue(split["test"])


class ResamplingTests(unittest.TestCase):
    def _blocks(self):
        return publicdata.site_day_blocks(publicdata.normalise_contract(payload()))

    def test_dwell_model_summary(self):
        model = publicdata.EmpiricalDwellModel.from_blocks(self._blocks())
        summary = model.summary()
        self.assertEqual(summary["all"]["n"], 8)
        self.assertEqual(summary["ev"]["n"], 4)
        self.assertEqual(summary["ice"]["n"], 4)

    def test_dwell_sampling_reproducible(self):
        model = publicdata.EmpiricalDwellModel.from_blocks(self._blocks())
        first = [model.sample(random.Random(5), "ev") for _ in range(10)]
        second = [model.sample(random.Random(5), "ev") for _ in range(10)]
        self.assertEqual(first, second)

    def test_empty_category_raises(self):
        model = publicdata.EmpiricalDwellModel({"all": [10.0], "ev": [], "ice": []})
        with self.assertRaises(ValueError):
            model.sample(random.Random(0), "ev")

    def test_block_resampler_deterministic(self):
        blocks = self._blocks()
        first = publicdata.BlockResampler(blocks, seed=13).streams(3)
        second = publicdata.BlockResampler(blocks, seed=13).streams(3)
        self.assertEqual([s["stream_hash"] for s in first], [s["stream_hash"] for s in second])
        self.assertEqual([s["stream_id"] for s in first], [s["stream_id"] for s in second])
        for stream in first:
            self.assertIn(stream["source_block"],
                          {"%s:%s" % (b["site_id"], b["day_key"]) for b in blocks})

    def test_resample_dwell_mode_keeps_arrivals(self):
        blocks = self._blocks()
        replay = publicdata.BlockResampler(blocks, seed=2, dwell_mode="block").stream(0)
        resampled = publicdata.BlockResampler(blocks, seed=2, dwell_mode="resample").stream(0)
        self.assertEqual([e["time_min"] for e in replay["events"]],
                         [e["time_min"] for e in resampled["events"]])
        self.assertEqual(replay["stream_hash"] != resampled["stream_hash"] or
                         [e["dwell_min"] for e in replay["events"]] ==
                         [e["dwell_min"] for e in resampled["events"]], True)

    def test_to_traffic_arrivals(self):
        blocks = self._blocks()
        stream = publicdata.BlockResampler(blocks, seed=4).stream(0)
        arrivals = publicdata.to_traffic_arrivals(stream, horizon_min=1000)
        self.assertEqual(len(arrivals), stream["n_events"])
        for arrival in arrivals:
            if not arrival.needs_charge:
                self.assertEqual(arrival.energy_kwh, 0.0)
        limited = publicdata.to_traffic_arrivals(stream, horizon_min=1)
        self.assertLessEqual(len(limited), len(arrivals))

    def test_needs_charge_without_energy_raises(self):
        stream = {"stream_id": "bad", "events": [{"vehicle_id": 0, "time_min": 0.0,
                                                  "is_ev": True, "needs_charge": True,
                                                  "dwell_min": 30.0, "energy_kwh": None,
                                                  "source_event_id": "x"}]}
        with self.assertRaises(publicdata.ContractError):
            publicdata.to_traffic_arrivals(stream)


class CoverageTests(unittest.TestCase):
    def test_coverage_unverified_without_complete_days(self):
        normalised = publicdata.normalise_contract(payload())
        report = publicdata.coverage_report(normalised)
        criteria = {item["id"]: item for item in report["criteria"]}
        self.assertEqual(criteria["P3_complete_days_ge_4"]["status"], "unverified")
        self.assertEqual(report["n_site_days"], 4)
        self.assertEqual(criteria["charge_fields"]["status"], "missing_data")

    def test_coverage_pass_with_declared_complete_days(self):
        data = payload(days=("2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07"))
        for row in data["events"]:
            row["needs_charge"] = bool(row.get("needs_charge"))
            row["energy_kwh"] = float(row.get("energy_kwh") or 0.0)
        data["coverage"] = {"complete_days": {"S1": ["2024-03-04", "2024-03-05"]}}
        normalised = publicdata.normalise_contract(data)
        report = publicdata.coverage_report(normalised)
        criteria = {item["id"]: item for item in report["criteria"]}
        self.assertEqual(criteria["P3_complete_days_ge_4"]["status"], "fail")
        self.assertEqual(criteria["charge_fields"]["status"], "pass")
        self.assertEqual(report["complete_days_declared"], 2)


class MissingCapacityAndCsvTests(unittest.TestCase):
    def test_missing_capacity_is_missing_data_not_blocking(self):
        data = payload()
        for site in data["sites"]:
            for key in ("n_spaces", "charging_bays", "connectors"):
                del site[key]
        report = publicdata.validate_contract(data)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["blocking_errors"], 0)
        self.assertIn("missing_data", {item["kind"] for item in report["errors"]})
        coverage = publicdata.coverage_report(report["normalised"])
        criteria = {item["id"]: item for item in coverage["criteria"]}
        self.assertEqual(criteria["P4_site_capacity"]["status"], "missing_data")

    def test_csv_adapter_with_explicit_mapping(self):
        import csv as _csv
        import os
        import tempfile

        rows = [{"id": "a1", "lot": "L1", "start": "2014-02-04T10:00:00", "dur": "30"},
                {"id": "a2", "lot": "L1", "start": "2014-02-04T11:00:00", "dur": "45"}]
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "events.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = _csv.DictWriter(handle, fieldnames=["id", "lot", "start", "dur"])
            writer.writeheader()
            writer.writerows(rows)
        try:
            normalised = publicdata.load_csv_contract(
                path,
                column_map={"event_id": "id", "site_id": "lot",
                            "arrival_ts": "start", "dwell_min": "dur"},
                sites=[{"site_id": "L1", "n_spaces": 10, "charging_bays": 2,
                        "connectors": 1, "connector_kw": 7.0, "feeder_kw": 14.0}],
                dataset_id="csv-unit", tz_offset_minutes=600, default_is_ev=False)
            self.assertEqual(len(normalised["events"]), 2)
            self.assertEqual(normalised["events"][0]["dwell_min"], 30.0)
            self.assertEqual(normalised["events"][0]["day_key"], "2014-02-04")
            self.assertFalse(normalised["events"][0]["is_ev"])
            self.assertEqual(normalised["events"][0]["needs_charge"], None)
        finally:
            os.remove(path)
            os.rmdir(directory)

    def test_csv_adapter_refuses_ambiguous_offset(self):
        with self.assertRaises(ValueError):
            publicdata.payload_from_csv_rows(
                [{"id": "a", "lot": "L", "start": "2014-02-04T10:00:00+08:00", "dur": "10"}],
                column_map={"event_id": "id", "site_id": "lot",
                            "arrival_ts": "start", "dwell_min": "dur"},
                sites=[{"site_id": "L", "n_spaces": 1}], tz_offset_minutes=600)


if __name__ == "__main__":
    unittest.main()
