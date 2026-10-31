"""公开停车数据的统一事件契约适配层（R8-B）。

职责（只依赖标准库 json / datetime / hashlib / random / math）：
1. 契约校验：public_parking_events/v1。字段缺失、非法值、越界、重复 id、未知场站分列记录，
   不静默丢弃；非法记录既不进分母，也不被当作 0。
2. 场站-日切分：统计单位固定为「场站-日」（site-day）。留出场站与留出日互不重叠；
   同一场站的不同日可进训练，测试日必须整日留出。
3. 到达与停留经验重采样：停留按训练集经验分布抽样；到达按「场站-日整块」重采样
   （block bootstrap），不把 5 分钟快照当独立样本，也不把重采样次数当样本量。
4. 覆盖度报告：E1 的 coverage 输入；逐条给出 P3/P4 判定值，缺数据标 unverified / missing_data。

数据来源约束（PLAN §1）：只读本轮 data/processed/ 的契约文件；不读旧 Taipei 快照、
旧 fitted_parameters、旧车流 JSON、旧结果。

契约（v1）
----------
顶层：{"schema_version": "public_parking_events/v1", "dataset_id": str,
       "sites": [ {site_id, n_spaces, charging_bays?, connectors?, connector_kw?, feeder_kw?} ],
       "events": [ {event_id?, site_id, arrival_ts, dwell_min | departure_ts,
                    is_ev, needs_charge?, energy_kwh?} ],
       "coverage": {"complete_days": {site_id: ["YYYY-MM-DD", ...]}}   # 可选
      }
时间戳必须是带时区偏移的 ISO-8601（如 2024-03-01T08:12:00+08:00）；当地日期由该偏移推出，
不依赖 zoneinfo（Windows 无 tzdata 时仍可运行）。字段别名见 EVENT_ALIASES / SITE_ALIASES，
别名只是读取便利，不改变语义。

口径提醒
--------
- 到达是事件级记录（不是随机时刻快照），故对「到达样本」的停留抽样不产生长度偏倚；
  若数据改为定时快照，必须改用 residual-lifetime 校正，本模块不提供该默认行为。
- 重采样次数（如 bootstrap n_boot）不是样本量；样本量由独立场站-日数决定。
- 拒绝/缺失/非法分列，不互相吞并。
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import random
from pathlib import Path

CONTRACT_SCHEMA_VERSION = "public_parking_events/v1"
SUPPORTED_SCHEMA_VERSIONS = (CONTRACT_SCHEMA_VERSION,)
UNIT = "site-day"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROCESSED_DIR = REPO_ROOT / "research" / "round8_20261031" / "data" / "processed"

ERROR_KINDS = (
    "schema", "missing_field", "missing_data", "illegal_value",
    "out_of_range", "duplicate_id", "unknown_site", "bad_timestamp",
)

SITE_ALIASES = {
    "site_id": ("site_id", "site", "lot_id", "facility_id", "garage_id"),
    "n_spaces": ("n_spaces", "capacity", "total_spaces", "spaces"),
    "charging_bays": ("charging_bays", "ev_bays", "charging_spaces"),
    "connectors": ("connectors", "chargers", "n_connectors", "charger_count", "evse"),
    "connector_kw": ("connector_kw", "charger_kw", "power_kw"),
    "feeder_kw": ("feeder_kw", "feeder_capacity_kw"),
}

EVENT_ALIASES = {
    "event_id": ("event_id", "id", "session_id", "record_id"),
    "site_id": ("site_id", "site", "lot_id", "facility_id", "garage_id"),
    "arrival_ts": ("arrival_ts", "arrival_time", "arrive_ts", "start_ts", "entry_ts", "in_ts"),
    "dwell_min": ("dwell_min", "dwell_minutes", "duration_min", "stay_min", "parking_min"),
    "departure_ts": ("departure_ts", "depart_ts", "exit_ts", "out_ts", "leave_ts"),
    "is_ev": ("is_ev", "ev", "electric", "is_electric"),
    "needs_charge": ("needs_charge", "charge_request", "wants_charge", "is_charging"),
    "energy_kwh": ("energy_kwh", "requested_kwh", "energy_request_kwh", "kwh"),
}

_TRUE = {"1", "true", "yes", "y", "t", "ev", "electric"}
_FALSE = {"0", "false", "no", "n", "f", "ice", "fuel"}


class ContractError(ValueError):
    """契约不可用时抛出；错误明细同时保留在 report["errors"]。"""


# --------------------------------------------------------------------------- 基础设施
def _canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def payload_sha256(payload):
    """规范 JSON 的 SHA-256（与 traffic_gen.stream_hash 同一规范化约定）。"""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _err(errors, kind, path, message):
    assert kind in ERROR_KINDS, kind
    errors.append({"kind": kind, "path": path, "message": str(message)})


def _pick(record, aliases):
    for name in aliases:
        if name in record and record[name] is not None:
            return name, record[name]
    return None, None


def _num(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("%s 必须是有限数值，得到 %r" % (name, value))
    return float(value)


def _int(value, name, *, minimum=0):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s 必须是整数，得到 %r" % (name, value))
    if value < minimum:
        raise ValueError("%s 必须 >= %d，得到 %r" % (name, minimum, value))
    return int(value)


def _bool(value, name):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE:
            return True
        if text in _FALSE:
            return False
    raise ValueError("%s 必须是布尔值，得到 %r" % (name, value))


def parse_ts(text):
    """带时区偏移的 ISO-8601 时间戳 -> (epoch 分钟, 当地日期 YYYY-MM-DD, 当地分钟数)。

    naive 时间戳（无偏移）视为非法：P4 要求带时区时间戳，不猜时区。
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("时间戳必须是非空字符串，得到 %r" % (text,))
    raw = text.strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        moment = _dt.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("无法解析时间戳 %r：%s" % (text, exc)) from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("时间戳缺少时区偏移（P4 要求带时区）：%r" % (text,))
    epoch_min = moment.timestamp() / 60.0
    minute_of_day = moment.hour * 60.0 + moment.minute + moment.second / 60.0
    return epoch_min, moment.date().isoformat(), minute_of_day


# --------------------------------------------------------------------------- 校验 + 规范化
def _normalise_sites(payload, errors, warnings):
    sites = payload.get("sites")
    if not isinstance(sites, list) or not sites:
        _err(errors, "schema", "sites", "sites 必须是非空列表")
        return {}
    normalised = {}
    for index, record in enumerate(sites):
        path = "sites[%d]" % index
        if not isinstance(record, dict):
            _err(errors, "illegal_value", path, "场站记录必须是对象")
            continue
        _, site_id = _pick(record, SITE_ALIASES["site_id"])
        if not isinstance(site_id, str) or not site_id.strip():
            _err(errors, "missing_field", path + ".site_id", "缺少场站标识")
            continue
        site_id = site_id.strip()
        if site_id in normalised:
            _err(errors, "duplicate_id", path + ".site_id", "重复场站 %r" % site_id)
            continue
        entry = {"site_id": site_id,
                 "n_spaces": None, "charging_bays": None, "connectors": None,
                 "connector_kw": None, "feeder_kw": None}
        key, raw = _pick(record, SITE_ALIASES["n_spaces"])
        if raw is None:
            # 缺容量不阻止读取（E1 只需要到达/停留）；E3/E6 会按 missing_data 分列
            _err(errors, "missing_data", path + ".n_spaces", "缺少总车位数（P4 未满足）")
        else:
            try:
                entry["n_spaces"] = _int(raw, key)
            except ValueError as exc:
                _err(errors, "out_of_range", path + "." + str(key), exc)
        for name, minimum in (("charging_bays", 0), ("connectors", 0)):
            key, raw = _pick(record, SITE_ALIASES[name])
            if raw is None:
                _err(errors, "missing_data", path + "." + name, "缺少 %s（E6/实例构造需要）" % name)
                continue
            try:
                entry[name] = _int(raw, key, minimum=minimum)
            except ValueError as exc:
                _err(errors, "out_of_range", path + "." + str(key), exc)
        for name in ("connector_kw", "feeder_kw"):
            key, raw = _pick(record, SITE_ALIASES[name])
            if raw is None:
                _err(errors, "missing_data", path + "." + name, "缺少 %s（E6 需要）" % name)
                continue
            try:
                entry[name] = _num(raw, key)
                if entry[name] <= 0:
                    raise ValueError("%s 必须 > 0" % name)
            except ValueError as exc:
                _err(errors, "out_of_range", path + "." + str(key), exc)
        if (entry["n_spaces"] is not None and entry["charging_bays"] is not None
                and entry["n_spaces"] < entry["charging_bays"]):
            _err(errors, "illegal_value", path, "必须满足 charging_bays <= n_spaces")
        if (entry["charging_bays"] is not None and entry["connectors"] is not None
                and entry["charging_bays"] < entry["connectors"]):
            _err(errors, "illegal_value", path, "必须满足 connectors <= charging_bays")
        normalised[site_id] = entry
    return normalised


def _normalise_events(payload, sites, errors, warnings):
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        _err(errors, "schema", "events", "events 必须是非空列表")
        return []
    rows, seen = [], {}  # identity -> 规范化记录（判完全重复）
    for index, record in enumerate(events):
        path = "events[%d]" % index
        if not isinstance(record, dict):
            _err(errors, "illegal_value", path, "事件记录必须是对象")
            continue
        key, site_id = _pick(record, EVENT_ALIASES["site_id"])
        if not isinstance(site_id, str) or not site_id.strip():
            _err(errors, "missing_field", path + ".site_id", "缺少场站标识")
            continue
        site_id = site_id.strip()
        if site_id not in sites:
            _err(errors, "unknown_site", path + ".site_id", "未知场站 %r" % site_id)
            continue
        key_eid, event_id = _pick(record, EVENT_ALIASES["event_id"])
        if event_id is None:
            event_id = "%s#%d" % (site_id, index)
        else:
            event_id = str(event_id)
        key_arr, arrival_raw = _pick(record, EVENT_ALIASES["arrival_ts"])
        if arrival_raw is None:
            _err(errors, "missing_field", path + ".arrival_ts", "缺少到达时间（P2）")
            continue
        try:
            arrival_min, day_key, minute_of_day = parse_ts(arrival_raw)
        except ValueError as exc:
            _err(errors, "bad_timestamp", path + ".arrival_ts", exc)
            continue
        dwell_raw = _pick(record, EVENT_ALIASES["dwell_min"])[1]
        departure_raw = _pick(record, EVENT_ALIASES["departure_ts"])[1]
        dwell = None
        if dwell_raw is not None:
            try:
                dwell = _num(dwell_raw, "dwell_min")
            except ValueError as exc:
                _err(errors, "illegal_value", path + ".dwell_min", exc)
                continue
        elif departure_raw is not None:
            try:
                departure_min, _, _ = parse_ts(departure_raw)
                dwell = departure_min - arrival_min
            except ValueError as exc:
                _err(errors, "bad_timestamp", path + ".departure_ts", exc)
                continue
        else:
            _err(errors, "missing_field", path, "缺少停留时长：dwell_min 与 departure_ts 都没有（P2）")
            continue
        if not math.isfinite(dwell) or dwell <= 0:
            _err(errors, "out_of_range", path + ".dwell_min", "停留时长必须 > 0，得到 %r" % dwell)
            continue
        key_ev, ev_raw = _pick(record, EVENT_ALIASES["is_ev"])
        if ev_raw is None:
            _err(errors, "missing_field", path + ".is_ev", "缺少车型（EV/ICE）")
            continue
        try:
            is_ev = _bool(ev_raw, "is_ev")
        except ValueError as exc:
            _err(errors, "illegal_value", path + ".is_ev", exc)
            continue
        need_raw = _pick(record, EVENT_ALIASES["needs_charge"])[1]
        needs_charge = None
        if need_raw is not None:
            try:
                needs_charge = _bool(need_raw, "needs_charge")
            except ValueError as exc:
                _err(errors, "illegal_value", path + ".needs_charge", exc)
                continue
        energy_raw = _pick(record, EVENT_ALIASES["energy_kwh"])[1]
        energy_kwh = None
        if energy_raw is not None:
            try:
                energy_kwh = _num(energy_raw, "energy_kwh")
            except ValueError as exc:
                _err(errors, "illegal_value", path + ".energy_kwh", exc)
                continue
            if energy_kwh < 0:
                _err(errors, "out_of_range", path + ".energy_kwh", "能量需求必须 >= 0")
                continue
        if needs_charge and not is_ev:
            _err(errors, "illegal_value", path, "非电车不能有充电需求")
            continue
        if needs_charge and energy_kwh is None:
            warnings.append({"kind": "missing_data", "path": path + ".energy_kwh",
                             "message": "需要充电但缺少能量需求：E6/离场能量服务不可判定"})
        row = {"event_id": event_id, "site_id": site_id,
               "arrival_min": arrival_min, "day_key": day_key,
               "minute_of_day": minute_of_day, "dwell_min": dwell,
               "departure_min": arrival_min + dwell, "is_ev": is_ev,
               "needs_charge": needs_charge, "energy_kwh": energy_kwh,
               "source_index": index}
        # 事件 id 唯一性口径：按 (场站, 原始 id) 判重。
        # 来源数据的行号型 id 会跨多日/多场站复用（命名空间问题）：仅当两条记录完全相同
        # 才判 duplicate_id 错误；否则按复合键重新编号并记 warning，不静默丢弃。
        identity = (site_id, event_id)
        if identity in seen:
            if seen[identity] == {k: v for k, v in row.items()
                                  if k not in ("event_id", "source_index")}:
                _err(errors, "duplicate_id", path + ".event_id",
                     "完全重复的事件 id %r（同一场站同一到达/停留/能量）" % event_id)
                continue
            warnings.append({"kind": "duplicate_id_rekeyed", "path": path + ".event_id",
                             "message": "事件 id %r 在该场站被复用，已按复合键重新编号"
                                        % event_id})
            row["event_id"] = "%s#%d" % (event_id, index)
            identity = (site_id, row["event_id"])
        seen[identity] = {k: v for k, v in row.items()
                          if k not in ("event_id", "source_index")}
        rows.append(row)
    if any(item["kind"] == "duplicate_id_rekeyed" for item in warnings):
        count = sum(1 for item in warnings if item["kind"] == "duplicate_id_rekeyed")
        warnings.insert(0, {"kind": "duplicate_id_rekeyed_summary",
                            "path": "events", "message": "共用 id 重编号 %d 条" % count})
    return rows


def validate_contract(payload):
    """校验契约并返回报告；不抛异常（除非 payload 不是对象）。

    返回：{"ok": bool, "schema_version": str|None, "errors": [...], "warnings": [...],
           "counts": {...}, "normalised": {"sites": {...}, "events": [...]}}（ok 时才有 normalised）。
    """
    errors, warnings = [], []
    if not isinstance(payload, dict):
        raise ContractError("契约顶层必须是 JSON 对象")
    version = payload.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        _err(errors, "schema", "schema_version",
             "不支持的契约版本 %r；支持 %s" % (version, ", ".join(SUPPORTED_SCHEMA_VERSIONS)))
    sites = _normalise_sites(payload, errors, warnings)
    events = _normalise_events(payload, sites, errors, warnings)
    missing_needs = sum(1 for row in events if row["needs_charge"] is None)
    missing_energy = sum(1 for row in events if row["energy_kwh"] is None)
    # 只有 missing_data 级别的错误可容忍（缺容量/缺充电字段）：E1 仍可跑；
    # 结构性错误（schema/缺必填/非法/越界/重复/未知场站/坏时间戳）一律不可用。
    blocking = [item for item in errors if item["kind"] != "missing_data"]
    report = {
        "ok": not blocking,
        "blocking_errors": len(blocking),
        "schema_version": version,
        "dataset_id": payload.get("dataset_id"),
        "errors": errors,
        "warnings": warnings,
        "counts": {
            "sites": len(sites),
            "events_declared": len(payload.get("events") or []),
            "events_accepted": len(events),
            "events_rejected": len(payload.get("events") or []) - len(events),
            "events_missing_needs_charge": missing_needs,
            "events_missing_energy_kwh": missing_energy,
        },
    }
    schema_errors = [item for item in errors if item["kind"] == "schema"]
    if not schema_errors and events:
        report["normalised"] = {"sites": sites, "events": events,
                                "dataset_id": payload.get("dataset_id"),
                                "coverage": payload.get("coverage") or {},
                                "provenance": payload.get("provenance") or {},
                                "qa": {"events_declared": len(payload.get("events") or []),
                                       "events_accepted": len(events),
                                       "events_rejected": len(payload.get("events") or []) - len(events),
                                       "errors": len(errors), "warnings": len(warnings)}}
    return report


def normalise_contract(payload, *, allow_rejected_events=False):
    """校验并返回规范化契约；有硬错误时抛 ContractError（附前 5 条明细）。

    allow_rejected_events=True：允许**事件级**坏记录被计数后剔除（report.counts 与 qa 里可查），
    但结构性 schema 错误仍抛错。用于"文件可用、个别行损坏"的公开数据，剔除数必须写进输出。
    """
    report = validate_contract(payload)
    fatal = [item for item in report["errors"] if item["kind"] == "schema"]
    blocking = [item for item in report["errors"] if item["kind"] != "missing_data"]
    if fatal or (blocking and not allow_rejected_events) or "normalised" not in report:
        head = "; ".join("%s@%s: %s" % (e["kind"], e["path"], e["message"])
                         for e in report["errors"][:5])
        raise ContractError("契约校验失败（%d 条错误）：%s" % (len(report["errors"]), head))
    return report["normalised"]


def load_contract(path, *, strict=True, allow_rejected_events=False):
    """读取契约文件；strict=True 时校验失败抛 ContractError，否则返回校验报告（用于 QA 记录）。"""
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    if strict:
        return normalise_contract(payload, allow_rejected_events=allow_rejected_events)
    return validate_contract(payload)


# --------------------------------------------------------------------------- 场站-日切分
def site_day_blocks(normalised):
    """按 (site_id, 当地日期) 切块，块内按到达时间升序；返回按 (场站, 日期) 排序的列表。

    统计单位就是这些块（site-day）；事件顺序保留，供整块重采样与到达过程拟合。
    """
    buckets = {}
    for row in normalised["events"]:
        buckets.setdefault((row["site_id"], row["day_key"]), []).append(row)
    blocks = []
    for (site_id, day_key), rows in sorted(buckets.items()):
        rows.sort(key=lambda r: (r["arrival_min"], r["event_id"]))
        blocks.append({"site_id": site_id, "day_key": day_key,
                       "site": dict(normalised["sites"][site_id]),
                       "events": rows,
                       "n_events": len(rows),
                       "first_arrival_min": rows[0]["arrival_min"],
                       "last_arrival_min": rows[-1]["arrival_min"]})
    return blocks


def split_site_days(blocks, *, seed=0, holdout_site_fraction=0.25, holdout_day_fraction=0.2,
                    min_holdout_sites=1, warnings=None):
    """留出切分：测试 = 留出场站的全部日 + 其余场站上的留出整日；训练 = 其余块。

    纪律（PLAN §3.1）：场站级留出与日级留出都不与训练重叠；一个块只能属于一个集合。
    站点数 < 2 时无法做场站级留出，记 warning 并只用日级留出（如实降级，不冒充）。
    """
    warnings = [] if warnings is None else warnings
    if not blocks:
        raise ValueError("blocks 为空，无法切分")
    rng = random.Random(seed)
    site_ids = sorted({block["site_id"] for block in blocks})
    shuffled_sites = list(site_ids)
    rng.shuffle(shuffled_sites)
    n_holdout_sites = 0
    if len(site_ids) >= 2:
        n_holdout_sites = max(int(min_holdout_sites), int(round(holdout_site_fraction * len(site_ids))))
        n_holdout_sites = min(n_holdout_sites, len(site_ids) - 1)
    else:
        warnings.append({"kind": "missing_data", "path": "split.site_holdout",
                         "message": "只有 1 个场站，无法做场站级留出；本次只用日级留出"})
    test_site_ids = set(shuffled_sites[:n_holdout_sites])
    remaining_sites = [s for s in site_ids if s not in test_site_ids]
    day_keys = sorted({block["day_key"] for block in blocks
                       if block["site_id"] in remaining_sites})
    shuffled_days = list(day_keys)
    rng.shuffle(shuffled_days)
    n_holdout_days = 0
    if len(day_keys) >= 2:
        n_holdout_days = max(1, int(round(holdout_day_fraction * len(day_keys))))
        n_holdout_days = min(n_holdout_days, len(day_keys) - 1)
    else:
        warnings.append({"kind": "missing_data", "path": "split.day_holdout",
                         "message": "留出场站外的整日不足 2 天，日级留出无法独立成立"})
    test_day_keys = set(shuffled_days[:n_holdout_days])
    calibration, test = [], []
    for block in blocks:
        if block["site_id"] in test_site_ids:
            test.append(block)
        elif block["day_key"] in test_day_keys:
            test.append(block)
        else:
            calibration.append(block)
    cal_keys = {(b["site_id"], b["day_key"]) for b in calibration}
    test_keys = {(b["site_id"], b["day_key"]) for b in test}
    if cal_keys & test_keys:
        raise AssertionError("切分重叠：同一场站-日同时进入训练与测试")
    if not calibration or not test:
        raise ValueError("切分后训练集或测试集为空：场站 %d 个、日 %d 个，不足以留出"
                         % (len(site_ids), len({b["day_key"] for b in blocks})))
    return {"unit": UNIT, "seed": seed,
            "calibration": calibration, "test": test,
            "test_site_ids": sorted(test_site_ids), "test_day_keys": sorted(test_day_keys),
            "n": {"blocks": len(blocks), "calibration": len(calibration), "test": len(test),
                  "sites_total": len(site_ids),
                  "sites_calibration": len(site_ids) - len(test_site_ids)},
            "rule": ("测试块 = 留出场站的全部场站-日 + 其余场站里的留出整日；"
                     "训练块 = 其余；同一场站-日不得同时属于两者"),
            "warnings": warnings}


def select_solve_blocks(blocks, *, max_vehicles=20, connectors_cap=8, per_site=1):
    """挑代表性场站-日做小实例求解（E3 用）：每场站取需求最大的块。

    车辆数 > max_vehicles 或 connectors > connectors_cap 的块不进小实例（见 offline_opt）。
    """
    chosen = []
    by_site = {}
    for block in blocks:
        by_site.setdefault(block["site_id"], []).append(block)
    for site_id in sorted(by_site):
        blocks = list(by_site[site_id])
        small = [block for block in blocks if block["n_events"] <= max_vehicles]
        pool = small or blocks
        demand = []
        for block in pool:
            charge = sum(1 for e in block["events"]
                         if e["is_ev"] and e.get("needs_charge"))
            demand.append((charge, block["n_events"], block["day_key"], block))
        demand.sort(key=lambda item: (-item[0], -item[1], item[2]))
        for _, _, _, block in demand[:per_site]:
            # 不按 connectors 过滤：即使场站枪位 > 小实例上限，也要记录
            # budget_not_covered（枚举上限截断）而不是静默跳过。
            chosen.append(block)
    return chosen


# --------------------------------------------------------------------------- 经验重采样
class EmpiricalDwellModel:
    """停留时长经验分布（不拟合参数、不外推）。抽样单位 = 一条到达记录的停留。

    说明：到达为事件级记录时，对到达样本抽停留不会产生长度偏倚；若用随机时刻快照，
    必须做 residual-lifetime 校正（本类不提供，避免误用）。
    """

    CATEGORIES = ("all", "ev", "ice")

    def __init__(self, samples):
        pools = {}
        for name in self.CATEGORIES:
            values = [float(v) for v in samples.get(name, [])]
            if any(not math.isfinite(v) or v <= 0 for v in values):
                raise ValueError("停留样本必须是有限正数")
            pools[name] = sorted(values)
        self.pools = pools

    @classmethod
    def from_blocks(cls, blocks):
        samples = {name: [] for name in cls.CATEGORIES}
        for block in blocks:
            for row in block["events"]:
                samples["all"].append(row["dwell_min"])
                samples["ev" if row["is_ev"] else "ice"].append(row["dwell_min"])
        return cls(samples)

    def summary(self):
        out = {}
        for name, values in self.pools.items():
            if not values:
                out[name] = {"n": 0, "mean": None, "p50": None, "p90": None}
                continue
            n = len(values)
            out[name] = {"n": n, "mean": sum(values) / n,
                         "p50": values[min(n - 1, int(0.5 * (n - 1)))],
                         "p90": values[min(n - 1, int(0.9 * (n - 1)))]}
        return out

    def sample(self, rng, category="all"):
        pool = self.pools.get(category)
        if not pool:
            raise ValueError("经验停留池为空：category=%r" % category)
        return pool[rng.randrange(len(pool))]


class BlockResampler:
    """场站-日整块重采样（block bootstrap）。

    每次抽一个训练块，保留块内到达次序与间隔（这是拿不到跨日依赖时的保守做法）。
    dwell_mode="block"：用块内观测停留（保真，默认）；
    dwell_mode="resample"：到达保留、停留从训练集经验分布重抽（灵敏度用，丢失块内停留相关性）。
    重采样次数不是样本量：返回的 n_streams 只是重放条数，报告须写清独立块数。
    """

    def __init__(self, blocks, *, seed=0, dwell_mode="block"):
        if not blocks:
            raise ValueError("重采样需要非空的训练块")
        if dwell_mode not in ("block", "resample"):
            raise ValueError("dwell_mode 只能是 block 或 resample")
        self.blocks = list(blocks)
        self.seed = int(seed)
        self.dwell_mode = dwell_mode
        self.dwell_model = EmpiricalDwellModel.from_blocks(blocks)

    def stream(self, index, rng=None):
        rng = random.Random(self.seed + 100003 * index) if rng is None else rng
        block = self.blocks[rng.randrange(len(self.blocks))]
        offset = block["first_arrival_min"]
        events = []
        for position, row in enumerate(block["events"]):
            if self.dwell_mode == "block":
                dwell = row["dwell_min"]
            else:
                dwell = self.dwell_model.sample(rng, "ev" if row["is_ev"] else "ice")
            events.append({"vehicle_id": position,
                           "time_min": row["arrival_min"] - offset,
                           "is_ev": bool(row["is_ev"]),
                           "needs_charge": row["needs_charge"],
                           "dwell_min": float(dwell),
                           "energy_kwh": row["energy_kwh"],
                           "source_event_id": row["event_id"]})
        stream = {"stream_id": "%s:%s#%d" % (block["site_id"], block["day_key"], index),
                  "site_id": block["site_id"], "day_key": block["day_key"],
                  "source_block": "%s:%s" % (block["site_id"], block["day_key"]),
                  "dwell_mode": self.dwell_mode, "n_events": len(events),
                  "events": events}
        stream["stream_hash"] = payload_sha256(events)
        return stream

    def streams(self, n_streams, *, seed=None):
        if not isinstance(n_streams, int) or isinstance(n_streams, bool) or n_streams < 1:
            raise ValueError("n_streams 必须是正整数")
        base = self.seed if seed is None else int(seed)
        return [self.stream(index, random.Random(base + 7919 * index)) for index in range(n_streams)]


def to_traffic_arrivals(stream, horizon_min=None):
    """重采样流 -> workbench.traffic_gen.Arrival 序列（供现有仿真直接消费）。

    严格：时间必须落在 [0, horizon_min) 且升序；需要充电就必须有能量需求；
    不充电的车辆 energy_kwh 必须为 0（与 Simulation 的校验一致）。
    """
    from .traffic_gen import Arrival

    if horizon_min is not None:
        if not isinstance(horizon_min, (int, float)) or isinstance(horizon_min, bool) \
                or not math.isfinite(horizon_min) or horizon_min <= 0:
            raise ValueError("horizon_min 必须是有限正数")
    rows = []
    previous = -math.inf
    for event in stream["events"]:
        if horizon_min is not None and event["time_min"] >= horizon_min - 1e-9:
            continue
        if event["time_min"] < previous - 1e-9:
            raise ContractError("流内到达时间无序：%s" % stream["stream_id"])
        previous = event["time_min"]
        needs_charge = bool(event["needs_charge"]) if event["needs_charge"] is not None else False
        energy = event["energy_kwh"]
        if needs_charge:
            if energy is None:
                raise ContractError("需要充电但缺能量需求，不能编造为 0：event %r"
                                    % event.get("source_event_id"))
            energy = float(energy)
        else:
            energy = 0.0
        rows.append(Arrival(vehicle_id=len(rows), time_min=float(event["time_min"]),
                            is_ev=bool(event["is_ev"]), needs_charge=needs_charge,
                            dwell_min=float(event["dwell_min"]), energy_kwh=energy))
    if not rows:
        raise ContractError("流在时间窗口内没有车辆：%s" % stream["stream_id"])
    return rows


# --------------------------------------------------------------------------- 覆盖度
def coverage_report(normalised, blocks=None):
    """E1 覆盖度输入：逐条给出 P3/P4 判定；缺标记时写 unverified / missing_data，不猜。"""
    blocks = site_day_blocks(normalised) if blocks is None else list(blocks)
    sites = normalised["sites"]
    complete_declared = (normalised.get("coverage") or {}).get("complete_days") or {}
    events = normalised["events"]
    days = sorted({block["day_key"] for block in blocks})
    per_site = {}
    for site_id in sorted(sites):
        site_blocks = [b for b in blocks if b["site_id"] == site_id]
        complete = sorted(complete_declared.get(site_id) or [])
        per_site[site_id] = {
            "events": sum(b["n_events"] for b in site_blocks),
            "site_days": len(site_blocks),
            "days": sorted({b["day_key"] for b in site_blocks}),
            "complete_days_declared": complete,
            "n_spaces": sites[site_id]["n_spaces"],
            "charging_bays": sites[site_id]["charging_bays"],
            "connectors": sites[site_id]["connectors"],
        }
    total_complete = sum(len(v["complete_days_declared"]) for v in per_site.values())
    has_charge = sum(1 for row in events if row["needs_charge"] is not None)
    has_energy = sum(1 for row in events if row["energy_kwh"] is not None)
    criteria = [
        {"id": "P2_event_level_arrival_dwell", "requirement": "每条事件都有到达与停留",
         "value": len(events), "status": "pass" if events else "fail"},
        {"id": "P3_sites_ge_3", "requirement": ">= 3 场站",
         "value": len(sites), "status": "pass" if len(sites) >= 3 else "fail"},
        {"id": "P3_complete_days_ge_4", "requirement": ">= 4 个完整 24h 日",
         "value": total_complete,
         "status": ("pass" if total_complete >= 4 else "fail") if complete_declared
                   else "unverified",
         "reason": None if complete_declared else
                   "契约未提供 coverage.complete_days 标记；记录到的日数不能当作已核完整日"},
        {"id": "P4_site_capacity", "requirement": "每场站有总车位与充电位/枪数",
         "value": sum(1 for s in sites.values()
                      if s["n_spaces"] is not None and s["charging_bays"] is not None
                      and s["connectors"] is not None),
         "status": "pass" if all(s["n_spaces"] is not None and s["charging_bays"] is not None
                                 and s["connectors"] is not None for s in sites.values())
                   else "missing_data"},
        {"id": "charge_fields", "requirement": "needs_charge 与 energy_kwh 可用于 E6",
         "value": {"needs_charge": has_charge, "energy_kwh": has_energy, "events": len(events)},
         "status": ("missing_data" if has_energy < len(events) or has_charge < len(events)
                    else "pass")},
    ]
    return {"unit": UNIT, "dataset_id": normalised.get("dataset_id"),
            "n_sites": len(sites), "n_days": len(days), "n_site_days": len(blocks),
            "n_events": len(events), "events_per_site": {k: v["events"] for k, v in per_site.items()},
            "days_per_site": {k: len(v["days"]) for k, v in per_site.items()},
            "complete_days_declared": total_complete, "per_site": per_site,
            "criteria": criteria,
            "missing": {"needs_charge": len(events) - has_charge,
                        "energy_kwh": len(events) - has_energy}}


# --------------------------------------------------------------------------- CSV 适配
def payload_from_csv_rows(rows, *, column_map, sites, dataset_id=None,
                          tz_offset_minutes=0, default_is_ev=False):
    """CSV 行 -> v1 契约 payload。列名必须显式映射（column_map），不猜列。

    column_map 允许键：event_id / site_id / arrival_ts / dwell_min / departure_ts /
    is_ev / needs_charge / energy_kwh，值为 CSV 列名（None 表示该字段不提供）。
    时间列必须是 naive 本地时间（如 2014-02-04T10:56:29），按显式给出的固定偏移
    tz_offset_minutes 补时区；不做 DST 推断，跨夏令时切换必须由数据方给出带偏移的 UTC 列
    （否则日期/分钟口径会有 1 小时误差，属 missing_data 风险，需在 provenance 里声明）。
    is_ev 列缺省时用 default_is_ev（必须显式传入，默认 False=当作燃油车，并记录假设）。
    """
    if not isinstance(column_map, dict):
        raise ValueError("column_map 必须是 dict")
    if not isinstance(tz_offset_minutes, int) or not -14 * 60 <= tz_offset_minutes <= 14 * 60:
        raise ValueError("tz_offset_minutes 必须是 -840..840 的整数")
    if type(default_is_ev) is not bool:
        raise ValueError("default_is_ev 必须是布尔值")
    sign = "+" if tz_offset_minutes >= 0 else "-"
    offset = "%s%02d:%02d" % (sign, abs(tz_offset_minutes) // 60, abs(tz_offset_minutes) % 60)
    events = []
    for index, row in enumerate(rows):
        def cell(key):
            column = column_map.get(key)
            if column is None:
                return None
            value = row.get(column)
            if isinstance(value, str):
                value = value.strip()
            return None if value in (None, "") else value

        arrival = cell("arrival_ts")
        if arrival is None:
            raise ContractError("第 %d 行缺 arrival_ts 列值（column_map=%r）" % (index, column_map))
        arrival_text = str(arrival)
        if arrival_text.endswith(("Z", "z")) or arrival_text[-6:][:1] in ("+", "-"):
            raise ValueError("CSV 时间列必须是不带偏移的本地时间；带偏移请走 JSON 契约")
        event = {
            "event_id": cell("event_id") or ("csv-%d" % index),
            "site_id": cell("site_id"),
            "arrival_ts": arrival_text + offset,
            "is_ev": cell("is_ev") if cell("is_ev") is not None else default_is_ev,
        }
        dwell = cell("dwell_min")
        departure = cell("departure_ts")
        if dwell is not None:
            event["dwell_min"] = float(dwell)
        elif departure is not None:
            event["departure_ts"] = str(departure) + offset
        for key in ("needs_charge", "energy_kwh"):
            value = cell(key)
            if value is not None:
                event[key] = value
        events.append(event)
    payload = {"schema_version": CONTRACT_SCHEMA_VERSION, "dataset_id": dataset_id,
               "sites": [dict(site) for site in sites], "events": events,
               "provenance": {"csv_adapter": True, "tz_offset_minutes": tz_offset_minutes,
                              "tz_policy": "naive_local_fixed_offset",
                              "default_is_ev": default_is_ev,
                              "column_map": {k: v for k, v in column_map.items() if v}}}
    return payload


def load_csv_contract(path, **kwargs):
    """读取 CSV 并用显式映射得到规范化契约（字段校验复用 v1 校验器）。"""
    import csv as _csv
    delimiter = kwargs.pop("delimiter", ",")
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(_csv.DictReader(handle, delimiter=delimiter))
    if not rows:
        raise ContractError("CSV 无数据行：%s" % path)
    payload = payload_from_csv_rows(rows, **kwargs)
    payload["dataset_id"] = payload.get("dataset_id") or Path(path).stem
    return normalise_contract(payload)


def summary(blocks):
    """块集合的最小摘要（供 manifest 记录，避免把大文件塞进输出）。"""
    return {"n_blocks": len(blocks),
            "sites": sorted({b["site_id"] for b in blocks}),
            "days": sorted({b["day_key"] for b in blocks}),
            "n_events": sum(b["n_events"] for b in blocks)}
