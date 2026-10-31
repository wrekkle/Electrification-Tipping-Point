# -*- coding: utf-8 -*-
"""Traceable charge-probability source scenarios (round 4).

The module does not estimate p_EV or q_need. It loads a curated catalogue whose every
scenario carries its source, event definition, numerator/denominator, region/period,
vehicle type, location type, transfer assumption and limitations, then exposes the pair
plus a provenance block for the formal runner.

Hard rules enforced here:
  * p_EV and q_need are separate inputs; q_need is never derived from a product.
  * a q_use value may be used as a q_need *scenario* only when the record explicitly
    declares a hypothetical transfer (transfer.type == "hypothetical_transfer") with a
    non-empty statement; it is still not a target-scenario identified value.
  * q_location_share / device_time_utilization / vehicle-stock shares are rejected as
    q_need/q_use scenarios (different denominator).
  * finite values only, 0 < p_ev <= 1, 0 <= q_need <= 1, no clipping, no averaging.
  * every scenario records the catalogue sha256 and its own canonical record sha256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

SCHEMA_VERSION = "charge_probability_sources/v1"
ALLOWED_PROBABILITY_OBJECTS = ("q_use", "q_need", "potential_demand")
REJECTED_PROBABILITY_OBJECTS = ("q_location_share", "device_time_utilization", "vehicle_stock_share")
REQUIRED_FIELDS = (
    "scenario_id", "source_id", "version", "probability_object", "numerator",
    "denominator", "event_definition", "region", "period", "vehicle_type",
    "location_type", "p_ev", "q_need", "transfer", "limitations", "source_class",
    "source_ids",
)
SOURCE_CLASSES = ("official", "peer_reviewed", "institutional_report", "scenario", "derived")


class SourceScenarioError(ValueError):
    """A source scenario is incomplete, non-finite, out of range or mislabelled."""


def _finite(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SourceScenarioError("%s 必须是有限数值，收到 %r" % (name, value))
    return float(value)


def _canonical_sha(payload):
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _require_text(record, field):
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SourceScenarioError("%s 缺失或不是非空字符串" % field)
    return value.strip()


def validate_scenario(record):
    if not isinstance(record, dict):
        raise SourceScenarioError("scenario 记录必须是 JSON 对象")
    for field in REQUIRED_FIELDS:
        if field not in record:
            raise SourceScenarioError("scenario 缺少字段 %s" % field)
    scenario_id = _require_text(record, "scenario_id")
    _require_text(record, "source_id")
    _require_text(record, "version")
    probability_object = record["probability_object"]
    if probability_object in REJECTED_PROBABILITY_OBJECTS:
        raise SourceScenarioError(
            "%s: %s 的分母不是停车事件，不能作为 p_EV/q_need 情景"
            % (scenario_id, probability_object))
    if probability_object not in ALLOWED_PROBABILITY_OBJECTS:
        raise SourceScenarioError("%s: probability_object 非法 %r" % (scenario_id, probability_object))
    for field in ("numerator", "denominator", "event_definition", "region", "period",
                  "vehicle_type", "location_type", "limitations"):
        _require_text(record, field)
    if not isinstance(record.get("source_ids"), list) or not record["source_ids"]:
        raise SourceScenarioError("%s: source_ids 必须是非空列表" % scenario_id)
    source_class = record.get("source_class")
    if source_class not in SOURCE_CLASSES:
        raise SourceScenarioError("%s: source_class 非法 %r" % (scenario_id, source_class))
    transfer = record.get("transfer")
    if not isinstance(transfer, dict):
        raise SourceScenarioError("%s: transfer 必须是对象" % scenario_id)
    transfer_type = transfer.get("type")
    statement = transfer.get("statement")
    if transfer_type not in ("direct", "hypothetical_transfer"):
        raise SourceScenarioError("%s: transfer.type 必须是 direct 或 hypothetical_transfer" % scenario_id)
    if transfer_type == "hypothetical_transfer" and not (isinstance(statement, str) and statement.strip()):
        raise SourceScenarioError("%s: 假设性迁移必须写明 transfer.statement" % scenario_id)
    if probability_object == "q_use":
        if transfer_type != "hypothetical_transfer":
            raise SourceScenarioError(
                "%s: q_use 不是潜在需求 q_need；必须显式标 hypothetical_transfer 才能用于情景" % scenario_id)
        if "假设性迁移" not in statement:
            raise SourceScenarioError(
                "%s: q_use→q_need 的 transfer.statement 必须含“假设性迁移”字样" % scenario_id)
    p_ev = _finite("p_ev", record["p_ev"])
    q_need = _finite("q_need", record["q_need"])
    if not 0.0 < p_ev <= 1.0:
        raise SourceScenarioError("%s: p_ev 必须在 (0,1]，收到 %r" % (scenario_id, p_ev))
    if not 0.0 <= q_need <= 1.0:
        raise SourceScenarioError("%s: q_need 必须在 [0,1]，收到 %r" % (scenario_id, q_need))
    return True


def load_catalog(path):
    path = Path(path)
    raw = path.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceScenarioError("来源情景目录不是合法 UTF-8 JSON：%s" % exc) from exc
    if not isinstance(document, dict):
        raise SourceScenarioError("来源情景目录顶层必须是对象")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise SourceScenarioError("schema_version 必须是 %s" % SCHEMA_VERSION)
    scenarios = document.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise SourceScenarioError("scenarios 必须是非空列表")
    seen = set()
    for record in scenarios:
        validate_scenario(record)
        sid = record["scenario_id"]
        if sid in seen:
            raise SourceScenarioError("重复 scenario_id：%s" % sid)
        seen.add(sid)
    return document, hashlib.sha256(raw).hexdigest()


def resolve(catalog_path, scenario_id):
    document, catalog_sha = load_catalog(catalog_path)
    match = [r for r in document["scenarios"] if r["scenario_id"] == scenario_id]
    if not match:
        raise SourceScenarioError("未知 scenario_id：%s（可选 %s）"
                                  % (scenario_id, ", ".join(r["scenario_id"] for r in document["scenarios"])))
    record = match[0]
    q_use_as_q_need = record["probability_object"] == "q_use"
    transfer = dict(record["transfer"])
    if q_use_as_q_need:
        identification = "hypothetical_scenario_transfer_not_target_identified"
    elif record["scenario_id"].upper().startswith("REF"):
        identification = "historical_reference_not_identified"
    else:
        identification = "scenario_value_not_target_identified"
    provenance = {
        "catalog_path": str(Path(catalog_path)),
        "catalog_sha256": catalog_sha,
        "record_sha256": _canonical_sha(record),
        "schema_version": document.get("schema_version"),
        "scenario_id": record["scenario_id"],
        "source_id": record["source_id"],
        "version": record["version"],
        "probability_object": record["probability_object"],
        "numerator": record["numerator"],
        "denominator": record["denominator"],
        "event_definition": record["event_definition"],
        "region": record["region"],
        "period": record["period"],
        "vehicle_type": record["vehicle_type"],
        "location_type": record["location_type"],
        "unit": record.get("unit", "probability"),
        "value": record.get("value", record["q_need"]),
        "p_ev": record["p_ev"],
        "q_need": record["q_need"],
        "source_class": record["source_class"],
        "source_ids": list(record["source_ids"]),
        "transfer": transfer,
        "limitations": record["limitations"],
        "identification_status": identification,
        "q_use_as_q_need": q_use_as_q_need,
        "hypothetical_transfer": transfer.get("type") == "hypothetical_transfer",
        "note": record.get("note"),
    }
    return {
        "p_ev": record["p_ev"],
        "q_need": record["q_need"],
        "scenario_id": record["scenario_id"],
        "provenance": provenance,
    }


def scenario_ids(path):
    document, _ = load_catalog(path)
    return [r["scenario_id"] for r in document["scenarios"]]


def main(argv=None):
    parser = argparse.ArgumentParser(description="列出/解析充电概率来源情景")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.scenario:
            payload = resolve(args.catalog, args.scenario)
        else:
            payload = {"scenario_ids": scenario_ids(args.catalog)}
    except SourceScenarioError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
