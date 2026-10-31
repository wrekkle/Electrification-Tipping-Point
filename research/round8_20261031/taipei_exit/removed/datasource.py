"""Read-only integration of the Taipei 372 parking collector's saved batches.

This module never fetches the network, never writes the collection directory and never
manufactures a newer observation.  It reads the files the collector already committed:

* data/<date>/parking_slots.jsonl          per-slot per-site parking availability rows
* data/<date>/connector_status_long.jsonl  per-slot per-connector raw status rows
* runtime/state.json                       collector heartbeat, last success and gap log
* cohort.json                              frozen 372-site cohort definition
* config.json                              interval and planned window of the collector

Semantics enforced here (docs/methods/COST-MODEL-V2.md section 8):

* a parking row's available-car change is a **net occupancy change**, not an arrival or a
  departure; one sampling interval can contain both;
* a connector's raw status ("待機中" / "充電中") is **not** an empty bay, not "no charging
  demand" and not "finished charging but still parked";
* batches are de-duplicated by request_sha256: the same hash appearing again means the
  upstream source did not update, so it must not be counted as a new observation;
* freshness is the age of the last REAL observation (the newest valid batch slot), not
  of the last request: a duplicate response (same request_sha256) or a failed fetch
  refreshes last_request / last_success_fetch at most, never the effective observation
  age.  When the source is stale the state says so and the last real observation is kept
  as-is - no synthetic refresh, no interpolated slot, no invented timestamp;
* the upstream batch update time (source_batch_update_time) is a batch-level raw string;
  its CST offset is not independently verified and it is NOT a per-site observation time.
"""
from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_COLLECTION = Path(__file__).resolve().parents[3] / "research" / "collection" / "taipei_372_polling_20261030"
DEFAULT_INTERVAL_SECONDS = 300
FRESH_INTERVALS = 1      # age <= 1 interval  -> fresh
STALE_INTERVALS = 6      # 1 < age <= 6      -> stale, beyond -> expired

SEMANTICS = {
    "parking_availability": "逐场 availablecar 只反映净占用变化；不等于到达或离场，同一采样间隔可能同时有进有出。",
    "connector_status": "逐枪 status_raw（待機中/充電中）不等于空位、不等于无充电需求、也不等于充完未走；只作原始状态计数。",
    "dedupe": "按 request_sha256 去重：同一哈希再次出现表示源未更新，不重复计量、不视为新观测。",
    "freshness": "新鲜度按最后真实观测（有效新批次的槽时间）与当前 UTC 计算；重复响应或抓取失败只更新 last_request/last_success_fetch，不刷新有效观测年龄。",
    "replay": "回放只按游标顺序暴露已保存批次，游标之后的数据不可见。",
    "cost_parameters": "成本参数无来源一律 null（未知／待校准），禁止填 0 或演示默认值。",
}
UNIDENTIFIABLE = ["到达率", "离场率", "停车时长分布", "车型比例", "充电意愿", "被拒绝需求"]


class DataUnavailable(RuntimeError):
    """已保存批次不可读：调用方必须显示缺失，不得生成替代数据。"""


def _utc(text):
    if text in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataUnavailable(f"时间戳无法解析：{text!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(moment):
    return moment.astimezone(timezone.utc).isoformat() if moment else None


def _iter_jsonl(path):
    with path.open(encoding="utf-8-sig") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DataUnavailable(f"{path.name} 第{lineno}行不是合法JSON：{exc}") from exc
            if not isinstance(row, dict):
                raise DataUnavailable(f"{path.name} 第{lineno}行不是JSON对象")
            yield row


def _batch_files(collection):
    data = Path(collection) / "data"
    return sorted(data.glob("*/parking_slots.jsonl")) if data.is_dir() else []


def _signature(collection):
    root = Path(collection)
    parts = []
    for path in _batch_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        parts.append((str(path), stat.st_mtime_ns, stat.st_size))
    for name in ("runtime/state.json", "cohort.json", "config.json"):
        path = root / name
        try:
            stat = path.stat()
        except OSError:
            continue
        parts.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(parts)


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise DataUnavailable(f"{Path(path).name} 无法读取：{exc}") from exc


def _load_object(path):
    """Collector metadata must be a JSON object; a non-object file is corrupt, not metadata."""
    value = _load_json(path)
    if value is None or isinstance(value, dict):
        return value
    raise DataUnavailable(f"{Path(path).name} 必须是JSON对象，实际为 {type(value).__name__}")


def load_collector_config(collection=DEFAULT_COLLECTION):
    return _load_object(Path(collection) / "config.json") or {}


def load_state(collection=DEFAULT_COLLECTION):
    return _load_object(Path(collection) / "runtime" / "state.json")


def load_cohort(collection=DEFAULT_COLLECTION):
    return _load_object(Path(collection) / "cohort.json") or {}


def _new_slot(slot_text, row):
    return {
        "slot_start_utc": slot_text,
        "slot": _utc(slot_text),
        "rows": 0,
        "sites": set(),
        "shas": set(),
        "ok_rows": 0,
        "failed_rows": 0,
        "missing_rows": 0,
        "invalid_rows": 0,
        "duplicate_flag_rows": 0,
        "available_by_site": {},
        "fetch_utc": _utc(row.get("fetch_utc")),
        "source_batch_update_time": row.get("source_batch_update_time"),
        "source_update_time_is_batch_only": bool(row.get("source_update_time_is_batch_only")),
        "error_sample": None,
    }


def _load_slots_uncached(collection):
    files = _batch_files(collection)
    if not files:
        raise DataUnavailable(f"未找到已保存批次：{Path(collection)}")
    slots = {}
    for path in files:
        for row in _iter_jsonl(path):
            slot_text = row.get("slot_start_utc")
            if not isinstance(slot_text, str) or not slot_text.strip():
                raise DataUnavailable(f"{path.name} 存在缺少或非字符串 slot_start_utc 的行")
            slot = slots.get(slot_text)
            if slot is None:
                slot = slots[slot_text] = _new_slot(slot_text, row)
            slot["rows"] += 1
            parking_id = row.get("parking_id")
            valid_id = isinstance(parking_id, str) and bool(parking_id.strip())
            if valid_id:
                slot["sites"].add(parking_id)
            sha = row.get("request_sha256")
            if isinstance(sha, str) and sha:
                slot["shas"].add(sha)
            if row.get("http_status") == 200:
                slot["ok_rows"] += 1
            else:
                slot["failed_rows"] += 1
                if slot["error_sample"] is None and row.get("error"):
                    slot["error_sample"] = str(row.get("error"))[:120]
            if row.get("data_missing"):
                slot["missing_rows"] += 1
            available = row.get("availablecar_raw")
            # 外部保存批次也是输入：bool/NaN/Infinity/负数都不是合法的车位计数，只计为 invalid，
            # 否则 available_sum 会变成 inf/nan（JSON 无法序列化或统计被污染）。
            valid_available = (isinstance(available, (int, float)) and not isinstance(available, bool)
                               and math.isfinite(available) and available >= 0)
            if valid_id and row.get("availablecar_valid") and valid_available:
                slot["available_by_site"][parking_id] = available
            else:
                slot["invalid_rows"] += 1
            if row.get("duplicate_batch"):
                slot["duplicate_flag_rows"] += 1
            fetched = _utc(row.get("fetch_utc"))
            if fetched and (slot["fetch_utc"] is None or fetched < slot["fetch_utc"]):
                slot["fetch_utc"] = fetched
    if not slots:
        raise DataUnavailable(f"已保存批次没有可用行：{Path(collection)}")
    ordered = sorted(slots.values(), key=lambda item: item["slot"])
    seen = {}
    previous_sha = None
    for slot in ordered:
        shas = {sha for sha in slot["shas"] if sha}
        slot["sha"] = shas.pop() if len(shas) == 1 else (sorted(shas)[0] if shas else None)
        slot["sites"] = len(slot["sites"])
        slot["complete_rows"] = slot["rows"] > 0 and slot["failed_rows"] == 0
        if slot["failed_rows"] and not slot["available_by_site"]:
            slot["status"] = "request_failed"
            slot["is_new_data"] = False
            slot["duplicate_of_slot_utc"] = None
            slot["consecutive_duplicate"] = False
        elif slot["sha"] is None:
            slot["status"] = "no_batch_hash"
            slot["is_new_data"] = False
            slot["duplicate_of_slot_utc"] = None
            slot["consecutive_duplicate"] = False
        elif slot["sha"] in seen:
            slot["status"] = "duplicate"
            slot["is_new_data"] = False
            slot["duplicate_of_slot_utc"] = seen[slot["sha"]]
            slot["consecutive_duplicate"] = previous_sha == slot["sha"]
        else:
            seen[slot["sha"]] = slot["slot_start_utc"]
            slot["status"] = "ok"
            slot["is_new_data"] = True
            slot["duplicate_of_slot_utc"] = None
            slot["consecutive_duplicate"] = False
        previous_sha = slot["sha"]
    return tuple(ordered)


_CACHE = {}
_CACHE_LOCK = threading.Lock()


def load_slots(collection=DEFAULT_COLLECTION):
    """Ordered saved batches; cached by file mtime/size signature (read-only)."""
    root = Path(collection)
    signature = _signature(root)
    key = str(root.resolve())
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    slots = _load_slots_uncached(root)
    with _CACHE_LOCK:
        _CACHE[key] = (signature, slots)
    return slots


def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()


def _interval_seconds(value):
    """采集器配置里的间隔必须有限且为正；坏值退回文档默认值，不让单位计算崩掉。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return DEFAULT_INTERVAL_SECONDS
    return value


def freshness(age_seconds, interval_seconds=DEFAULT_INTERVAL_SECONDS):
    interval = _interval_seconds(interval_seconds)
    if age_seconds is not None:
        age_seconds = max(0.0, float(age_seconds))  # 客户端时钟提前时年龄不为负，最多记 0
    thresholds = {"fresh_within_seconds": interval, "stale_within_seconds": interval * STALE_INTERVALS}
    if age_seconds is None:
        state = "unknown"
    elif age_seconds <= thresholds["fresh_within_seconds"]:
        state = "fresh"
    elif age_seconds <= thresholds["stale_within_seconds"]:
        state = "stale"
    else:
        state = "expired"
    return {"state": state, "age_seconds": None if age_seconds is None else round(age_seconds, 1),
            "thresholds": thresholds,
            "note": "源未更新或采集器停摆时显示 stale/expired/missing；不生成假更新。"}


def _gaps(slots, interval_seconds):
    gaps = []
    for previous, current in zip(slots, slots[1:]):
        delta = (current["slot"] - previous["slot"]).total_seconds()
        missed = int(round(delta / interval_seconds)) - 1
        if missed > 0:
            gaps.append({"after_slot_utc": previous["slot_start_utc"], "next_slot_utc": current["slot_start_utc"],
                         "missed_slots": missed, "gap_seconds": round(delta - interval_seconds, 1)})
    return gaps


def _collector_gaps(state):
    if not isinstance(state, dict):
        return []
    gaps = state.get("gaps")
    if not isinstance(gaps, list):
        return []
    return [{"from_slot_utc": item.get("from_slot_utc"), "to_slot_utc": item.get("to_slot_utc"),
             "missed_slots": item.get("missed_slots")} for item in gaps if isinstance(item, dict)]


def summarise(collection=DEFAULT_COLLECTION, now=None, interval_seconds=None, include_connectors=False):
    """Recompute the real span / valid batches / duplicates / gaps of the saved batches."""
    root = Path(collection)
    if now is not None and now.tzinfo is None:
        raise ValueError("now 必须带时区（naive datetime 会把本地时间误当 UTC）")
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        config = load_collector_config(root)
        interval = _interval_seconds(interval_seconds if interval_seconds is not None
                                     else config.get("interval_seconds"))
        cohort = load_cohort(root)
        state = load_state(root)
        slots = load_slots(root)
    except DataUnavailable as exc:
        return {"available": False, "collection_path": str(root), "reason": str(exc),
                "checked_at_utc": _iso(checked_at), "freshness": {"state": "missing", "age_seconds": None,
                                                                   "thresholds": {}, "note": "已保存批次缺失或不可读。"},
                "semantics": SEMANTICS, "unidentifiable": UNIDENTIFIABLE}
    first, last = slots[0], slots[-1]
    span_minutes = (last["slot"] - first["slot"]).total_seconds() / 60.0
    expected_slots = int(round(span_minutes / (interval / 60.0))) + 1
    recomputed_gaps = _gaps(slots, interval)
    collector_gaps = _collector_gaps(state)
    recomputed_missed = sum(item["missed_slots"] for item in recomputed_gaps)
    collector_missed = sum(item.get("missed_slots") or 0 for item in collector_gaps)
    valid = [slot for slot in slots if slot["is_new_data"]]
    duplicates = [slot for slot in slots if slot["status"] == "duplicate"]
    failed = [slot for slot in slots if slot["status"] == "request_failed"]
    # 三个时间互不替代：最近一次请求（含重复/失败）、最近一次成功且有新数据的抓取、
    # 最后真实观测（有效新批次的槽时间）。新鲜度只认最后一个。
    last_request = max((slot["fetch_utc"] for slot in slots if slot["fetch_utc"]), default=None)
    last_success_fetch = max((slot["fetch_utc"] for slot in valid if slot["fetch_utc"]), default=None)
    last_real = valid[-1]["slot"] if valid else None
    age = None if last_real is None else max(0.0, (checked_at - last_real).total_seconds())
    cohort_id = cohort.get("cohort_id")
    collection_id = cohort_id if isinstance(cohort_id, str) and cohort_id.strip() else root.name
    cohort_size = cohort.get("size")
    sites = (cohort_size if isinstance(cohort_size, int) and not isinstance(cohort_size, bool) and cohort_size > 0
             else last["sites"])
    fresh = freshness(age, interval)
    fresh["note"] = ("新鲜度按最后真实观测（有效新批次的槽时间）与当前 UTC 计算；"
                     "重复响应或抓取失败只更新 last_request/last_success_fetch，不刷新有效观测年龄。")
    payload = {
        "available": True,
        "collection_id": collection_id,
        "collection_path": str(root),
        "checked_at_utc": _iso(checked_at),
        "interval_seconds": interval,
        "planned_window": {"start_assumption_utc": config.get("start_assumption_utc"),
                           "planned_end_utc": config.get("planned_end_utc"),
                           "duration_days": config.get("duration_days")},
        "source_time_range": {"first_slot_utc": first["slot_start_utc"], "last_slot_utc": last["slot_start_utc"],
                              "span_minutes": round(span_minutes, 1), "observed_slots": len(slots)},
        "expected_slots": expected_slots,
        "coverage_ratio": round(len(slots) / expected_slots, 4) if expected_slots else None,
        "valid_batches": len(valid),
        "valid_batch_slots": {"first": valid[0]["slot_start_utc"] if valid else None,
                              "last": valid[-1]["slot_start_utc"] if valid else None},
        "duplicate_batches": {"count": len(duplicates), "slots": [
            {"slot_utc": slot["slot_start_utc"], "duplicate_of_slot_utc": slot["duplicate_of_slot_utc"],
             "consecutive": slot["consecutive_duplicate"]} for slot in duplicates]},
        "failed_batches": {"count": len(failed), "slots": [
            {"slot_utc": slot["slot_start_utc"], "rows": slot["rows"], "error_sample": slot["error_sample"]} for slot in failed]},
        "gaps": {"count": recomputed_missed, "segments": recomputed_gaps, "collector_log": collector_gaps,
                 "matches_collector_log": recomputed_missed == collector_missed,
                 "collector_logged_missed_slots": collector_missed},
        "last_real_observation_utc": valid[-1]["slot_start_utc"] if valid else None,
        "last_success_fetch_utc": _iso(last_success_fetch),
        "last_request_utc": _iso(last_request),
        "upstream_time": {"source_batch_update_time": last["source_batch_update_time"],
                          "is_batch_only": last["source_update_time_is_batch_only"],
                          "verified": False,
                          "note": "批次级上游时间（原始字符串，CST 偏移未独立核验），不代表逐场观测时间。"},
        "source_batch_update_time": last["source_batch_update_time"],
        "source_update_time_is_batch_only": last["source_update_time_is_batch_only"],
        "source_time_note": "source_batch_update_time 为批次级上游时间（原始字符串，CST 偏移未独立核验），不代表逐场观测时间。",
        "sites": sites,
        "rows": {"parking": sum(slot["rows"] for slot in slots),
                 "missing": sum(slot["missing_rows"] for slot in slots),
                 "invalid_availablecar": sum(slot["invalid_rows"] for slot in slots)},
        "freshness": {**fresh, "age_basis": "last_real_observation_utc",
                      "last_real_observation_utc": _iso(last_real),
                      "last_success_fetch_utc": _iso(last_success_fetch),
                      "last_request_utc": _iso(last_request),
                      "last_success_utc": (state or {}).get("last_success_utc"),
                      "collector_status": (state or {}).get("status"),
                      "collector_heartbeat_utc": (state or {}).get("heartbeat_utc")},
        "series": [{"slot_utc": slot["slot_start_utc"], "is_new_data": slot["is_new_data"], "status": slot["status"],
                    "valid_sites": len(slot["available_by_site"]),
                    "available_sum": sum(slot["available_by_site"].values()),
                    "missing_rows": slot["missing_rows"]} for slot in slots],
        "semantics": SEMANTICS,
        "unidentifiable": UNIDENTIFIABLE,
    }
    if include_connectors:
        payload["connector"] = connector_counts(root)
    return payload


def connector_counts(collection=DEFAULT_COLLECTION, slot_limit=None):
    """Raw per-slot connector status counts.  Not an empty-bay / demand signal."""
    files = sorted((Path(collection) / "data").glob("*/connector_status_long.jsonl"))
    if not files:
        return {"available": False, "reason": "未找到 connector_status_long.jsonl", "counts": {}}
    counts = {}
    for path in files:
        for row in _iter_jsonl(path):
            slot = row.get("slot_start_utc")
            if slot_limit and slot not in slot_limit:
                continue
            bucket = counts.setdefault(slot, {})
            status = row.get("status_raw")
            bucket[status] = bucket.get(status, 0) + 1
    ordered = {slot: counts[slot] for slot in sorted(counts)}
    return {"available": True, "counts": ordered,
            "note": "待機中/充電中为原始状态计数；不等于空位、无需求或充完未走。"}


def net_occupancy_changes(collection=DEFAULT_COLLECTION):
    """Consecutive-slot available-car changes, labelled as net occupancy, never as arrivals."""
    slots = [slot for slot in load_slots(collection) if slot["is_new_data"] and slot["available_by_site"]]
    changes = []
    for previous, current in zip(slots, slots[1:]):
        common = sorted(set(previous["available_by_site"]) & set(current["available_by_site"]))
        deltas = {site: current["available_by_site"][site] - previous["available_by_site"][site] for site in common}
        changes.append({
            "from_slot_utc": previous["slot_start_utc"], "to_slot_utc": current["slot_start_utc"],
            "sites_compared": len(common),
            "free_spaces_change_sum": sum(deltas.values()),
            "sites_with_more_free": sum(1 for value in deltas.values() if value > 0),
            "sites_with_less_free": sum(1 for value in deltas.values() if value < 0),
            "sites_unchanged": sum(1 for value in deltas.values() if value == 0),
            "note": "净占用变化：正值=净释放车位，负值=净占用增加；均不等于到达/离场车辆数。",
        })
    return {"available": True, "transitions": changes, "sites_per_slot": [slot["sites"] for slot in slots][:1],
            "note": "逐场停车余位=净占用变化，不得当作到达/离场。"}


class TaipeiReplay:
    """Cursor over saved batches; batches after the cursor are not visible."""

    def __init__(self, collection=DEFAULT_COLLECTION, interval_seconds=None):
        self.collection = Path(collection)
        self.slots = list(load_slots(self.collection))
        self.interval_seconds = interval_seconds or DEFAULT_INTERVAL_SECONDS
        self.cursor = 0

    @property
    def total(self):
        return len(self.slots)

    def status(self):
        visible = self.slots[:self.cursor]
        return {"active": True, "label": "回放 replay", "source": "taipei_saved_batches",
                "cursor": self.cursor, "total": self.total,
                "visible_until_slot_utc": visible[-1]["slot_start_utc"] if visible else None,
                "note": "回放只暴露游标之前的已保存批次；游标之后的数据不可见。"}

    @staticmethod
    def _batch(slot):
        return {"slot_utc": slot["slot_start_utc"], "status": slot["status"], "is_new_data": slot["is_new_data"],
                "duplicate_of_slot_utc": slot["duplicate_of_slot_utc"], "rows": slot["rows"],
                "valid_sites": len(slot["available_by_site"]), "missing_rows": slot["missing_rows"],
                "available_sum": sum(slot["available_by_site"].values())}

    def step(self, count=1):
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 500:
            raise ValueError("回放步数必须为1至500的整数")
        start = self.cursor
        self.cursor = min(self.total, self.cursor + count)
        return {"cursor": self.cursor, "total": self.total,
                "batches": [self._batch(slot) for slot in self.slots[start:self.cursor]]}

    def reset(self):
        self.cursor = 0
        return self.status()
