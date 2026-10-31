"""参数契约 v3：数据准入判定、记录校验与加载。

口径来源：research/official_data_20261031/contract/CONTRACT.md §2 / §3。
本模块只做结构化校验与准入判定，不产生任何数值；缺值一律 None，禁止以 0 代替，
禁止为跑通补数。

用法：
    python -m apps.parking_lab.workbench.parameter_registry --file <registry.json> [--use social_cost] [--json]
退出码：0 校验通过，1 存在错误。
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

SCHEMA_VERSION = "v3-2026-10-31"

REQUIRED_FIELDS = (
    "param_id", "name_zh", "definition", "unit", "value", "source_class",
    "status", "admitted_use", "is_scenario", "source_ids",
)

SOURCE_CLASSES = ("official", "peer_reviewed", "institutional_report", "scenario", "derived")
STATUSES = ("available", "transferable", "unidentified", "rejected")
ADMITTED_USES = (
    "traffic_fit", "charging_prob", "energy_power_dwell",
    "social_cost", "validation", "sensitivity_only",
)
PROBABILITY_OBJECTS = (
    None, "q_use", "q_need", "q_day", "q_location_share",
    "device_time_utilization", "potential_demand",
)
DECISIONS = ("admitted", "admitted_derived", "transferable", "scenario", "unidentified", "rejected")


def _is_finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_record(record, index=0):
    """返回该记录的错误列表；空列表表示通过。"""
    errors = []
    if not isinstance(record, dict):
        return ["records[%d] 不是 JSON 对象" % index]
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append("records[%d].%s 缺失" % (index, field))
    param_id = record.get("param_id")
    if not isinstance(param_id, str) or not param_id.strip():
        errors.append("records[%d].param_id 必须为非空字符串" % index)
    source_class = record.get("source_class")
    if source_class is not None and source_class not in SOURCE_CLASSES:
        errors.append("records[%d].source_class 非法：%r（允许 %s）" % (index, source_class, ", ".join(SOURCE_CLASSES)))
    status = record.get("status")
    if status is not None and status not in STATUSES:
        errors.append("records[%d].status 非法：%r（允许 %s）" % (index, status, ", ".join(STATUSES)))
    uses = record.get("admitted_use")
    if uses is not None:
        if not isinstance(uses, list) or not uses:
            errors.append("records[%d].admitted_use 必须为非空列表" % index)
        else:
            bad = [u for u in uses if u not in ADMITTED_USES]
            if bad:
                errors.append("records[%d].admitted_use 含非法用途：%r" % (index, bad))
    if "is_scenario" in record and not isinstance(record["is_scenario"], bool):
        errors.append("records[%d].is_scenario 必须为布尔值" % index)
    sources = record.get("source_ids")
    if sources is not None and (not isinstance(sources, list) or any(not isinstance(s, str) for s in sources)):
        errors.append("records[%d].source_ids 必须为字符串列表" % index)
    probability_object = record.get("probability_object", "__absent__")
    if probability_object != "__absent__" and probability_object not in PROBABILITY_OBJECTS:
        errors.append("records[%d].probability_object 非法：%r" % (index, probability_object))
    unit = record.get("unit")
    if unit is not None and (not isinstance(unit, str) or not unit.strip()):
        errors.append("records[%d].unit 必须为非空字符串" % index)
    value = record.get("value")
    if _is_finite_number(value):
        if value < 0 and record.get("nonnegative", True):
            errors.append("records[%d].value 为负数且未声明 nonnegative=False" % index)
    elif value is not None and not isinstance(value, (str, dict, list)):
        errors.append("records[%d].value 必须为有限数值/字符串/对象或 null" % index)
    if status in ("available", "transferable") and record.get("source_class") == "scenario":
        errors.append("records[%d] 情景值不得标记为 %s 来源" % (index, status))
    if status in ("available", "transferable") and not sources:
        errors.append("records[%d] 状态 %s 必须给出 source_ids" % (index, status))
    price_year = record.get("price_year")
    if price_year is not None and (not isinstance(price_year, int) or isinstance(price_year, bool)):
        errors.append("records[%d].price_year 必须为整数年份或 null" % index)
    return errors


def admission_decision(record):
    """准入判定：组件可用性不等于可进入完整成本。"""
    status = record.get("status")
    if status == "rejected":
        return "rejected"
    if status == "unidentified" or record.get("value") is None:
        return "unidentified"
    if record.get("is_scenario"):
        return "scenario"
    source_class = record.get("source_class")
    if source_class == "official":
        return "admitted"
    if source_class == "derived":
        return "admitted_derived"
    return "transferable"


class Registry:
    """参数注册表：id -> 记录；提供按用途过滤与缺参传播。"""

    def __init__(self, records):
        self.records = dict(records)

    @classmethod
    def from_data(cls, data):
        records = {}
        errors = []
        raw = []
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict):
            for key in ("records", "parameters", "items"):
                if key in data:
                    container = data[key]
                    if isinstance(container, list):
                        raw = container
                    elif isinstance(container, dict):
                        for pid, rec in container.items():
                            if isinstance(rec, dict):
                                merged = {"param_id": pid}
                                merged.update(rec)
                                raw.append(merged)
                            else:
                                errors.append("parameters[%s] 不是对象" % pid)
                    break
            else:
                errors.append("顶层对象缺少 records/parameters/items 列表")
        else:
            errors.append("注册表必须是列表或对象")
        for index, rec in enumerate(raw):
            errors.extend(validate_record(rec, index))
            pid = rec.get("param_id") if isinstance(rec, dict) else None
            if isinstance(pid, str) and pid:
                if pid in records:
                    errors.append("param_id 重复：%s" % pid)
                records[pid] = rec
        return cls(records), errors

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_data(data)

    def get(self, param_id):
        return self.records.get(param_id)

    def value(self, param_id):
        """返回参数值；不可识别/拒绝/缺记录一律 None，禁止以 0 代替缺值。"""
        record = self.records.get(param_id)
        if record is None or admission_decision(record) in ("unidentified", "rejected"):
            return None
        return record.get("value")

    def require(self, param_id):
        """取已准入参数值；不可用或缺记录抛 KeyError（调用方必须显式处理缺参）。"""
        value = self.value(param_id)
        if value is None:
            raise KeyError("参数不可用：%s（decision=%s）" % (param_id, self.decision(param_id)))
        return value

    def decision(self, param_id):
        record = self.records.get(param_id)
        if record is None:
            return "missing"
        return admission_decision(record)

    def for_use(self, use):
        """返回允许用于该用途、且未被判为不可用/拒绝的记录。"""
        if use not in ADMITTED_USES:
            raise ValueError("未知用途：%r" % (use,))
        result = []
        for record in self.records.values():
            if use not in (record.get("admitted_use") or []):
                continue
            if admission_decision(record) in ("rejected", "unidentified"):
                continue
            result.append(record)
        return sorted(result, key=lambda r: r["param_id"])

    def complete(self, required_ids):
        """完整成本可用性：任一必需参数不可用即 complete=False，并列出缺失 id。"""
        missing = [pid for pid in required_ids if self.decision(pid) in ("missing", "unidentified", "rejected")]
        scenario_based = [pid for pid in required_ids if self.decision(pid) == "scenario"]
        return {"complete": not missing, "missing_parameters": missing, "scenario_parameters": scenario_based}

    def used_for(self, use):
        return [r["param_id"] for r in self.for_use(use)]


def main(argv=None):
    parser = argparse.ArgumentParser(description="参数契约 v3 校验与准入判定")
    parser.add_argument("--file", required=True)
    parser.add_argument("--use", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    registry, errors = Registry.load(args.file)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "file": args.file,
        "records": len(registry.records),
        "errors": errors,
        "decisions": {},
        "missing_parameters": [],
    }
    for pid, record in sorted(registry.records.items()):
        decision = admission_decision(record)
        summary["decisions"][pid] = decision
        if decision in ("unidentified", "rejected"):
            summary["missing_parameters"].append(pid)
    if args.use:
        summary["use"] = args.use
        summary["usable"] = registry.used_for(args.use)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("参数契约 %s：%d 条记录，错误 %d 条" % (SCHEMA_VERSION, summary["records"], len(errors)))
        for error in errors:
            print("  [错误] " + error)
        counts = {}
        for decision in summary["decisions"].values():
            counts[decision] = counts.get(decision, 0) + 1
        print("准入判定：" + ", ".join("%s=%d" % (k, counts[k]) for k in sorted(counts)))
        if args.use:
            print("可用于 %s：%d 条" % (args.use, len(summary["usable"])))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
