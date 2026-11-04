# -*- coding: utf-8 -*-
"""T64 backend service: freeze streams, run S1/S2/S3, compare and search.

The service is a thin, importable layer over schemes / scheme_engine /
social_cost.  It owns the in-memory registries, the declared feasible grids,
background jobs and the export payloads.  Every number it returns comes from a
real engine run on the requested stream and parameters; nothing is precomputed.
"""
import csv
import io
import json
import os
import threading
import time
import uuid

try:  # package import (python -m apps.parking_lab.workbench ...)
    from . import scheme_engine, social_cost
    from .schemes import (ADMISSION_RULES, CLASSES, CostParams, ENGINE_VERSION,
                          FeasibleDomain, FrozenStream, MATH_VERSION, MODES,
                          MODE_EVALUABLE_SCHEMES, MOBILE_DEVICE_KIND, SCHEMA, SCHEMES,
                          SchemeError, SchemeSpec, canonical_hash, cost_anchor,
                          default_m_max, mobile_anchor, validate_config, PARAM_SPECS)
except ImportError:  # direct module import (tests, standalone verification)
    import scheme_engine
    import social_cost
    from schemes import (ADMISSION_RULES, CLASSES, CostParams, ENGINE_VERSION,
                         FeasibleDomain, FrozenStream, MATH_VERSION, MODES,
                         MODE_EVALUABLE_SCHEMES, MOBILE_DEVICE_KIND, SCHEMA, SCHEMES,
                         SchemeError, SchemeSpec, canonical_hash, cost_anchor,
                         default_m_max, mobile_anchor, validate_config, PARAM_SPECS)

SCHEMA_T64 = SCHEMA
STREAM_DIR_NAME = os.path.join("research", "t64_three_schemes_20261103", "streams")
WORLD_DIRS = (
    os.path.join("research", "nyc_semisynthetic_20261103", "v3_t63", "viewer", "world"),
    os.path.join("research", "nyc_semisynthetic_20261103", "v2", "results", "worlds"),
)
MAX_STREAMS = 16
MAX_RUNS = 64
MAX_SEARCHES = 64
MAX_COMPARES = 64
MAX_GRID_POINTS = 41


def repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


REPO = repo_root()
STREAM_DIR = os.path.join(REPO, STREAM_DIR_NAME)

_LOCK = threading.RLock()
_STREAMS = {}
_RUNS = {}
_SEARCHES = {}
_COMPARES = {}
_JOBS = {}
_JOB_ORDER = []


# --------------------------------------------------------------------- helpers
def _new_id(prefix):
    return prefix + uuid.uuid4().hex[:12]


def _rel(path):
    try:
        return os.path.relpath(path, REPO).replace(os.sep, "/")
    except ValueError:
        return path


def _evidence_label(mode):
    return {
        "R0": "R0 观测重放：只输出观测占用/交付，不输出方案成本或最优配置",
        "R1": "R1 充电会话半合成：无普通停车竞争，仅评价充电服务侧",
        "R2": "R2 三类车半合成：纽约锚定情景，不是纽约实测需求",
    }.get(mode, mode)


def _warnings_for(stream, spec):
    warns = []
    if stream.mode == "R1":
        counts = stream.summary()["cohort_by_class"]
        if counts.get("I", 0) == 0 and counts.get("E0", 0) == 0:
            warns.append("R1 流中没有 I/E0 车辆：S2 开放机制在本流上不可观测；S3 仅在 fallback 下服务停普通位的 E1。")
    if spec.scheme == "S3" and spec.rule == "strict":
        warns.append("strict 准入下 E1 不会被接纳到普通位，移动设备无可服务对象（m>0 不产生交付）。")
    if spec.scheme == "S3" and spec.mobile.count == 0:
        warns.append("m=0：S3 退化为 S2（应逐车账本相同）。")
    if spec.scheme == "S2" and spec.open.open_rule == "never":
        warns.append("open_rule=never：S2 退化为 S1（应逐车账本相同）。")
    return warns


def _check_mode_evaluable(stream, scheme):
    if stream.mode == "R0":
        raise SchemeError("R0 为观测重放模式，不输出方案成本或最优配置；请使用 R1/R2 流")
    allowed = MODE_EVALUABLE_SCHEMES.get(stream.mode, ())
    if scheme not in allowed:
        raise SchemeError("%s 模式下不能评价 %s" % (stream.mode, scheme))


# --------------------------------------------------------------------- streams
def _world_files():
    out = []
    for rel_dir in WORLD_DIRS:
        d = os.path.join(REPO, rel_dir)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".json") and name.startswith("world_"):
                out.append(os.path.join(d, name))
    return out


def list_world_candidates(limit=80):
    items = []
    for path in _world_files()[:limit]:
        name = os.path.basename(path)
        items.append({"path": _rel(path), "name": name,
                      "size_bytes": os.path.getsize(path)})
    return items


def load_world_stream(path, stream_id=None):
    """Load a registered frozen-world JSON (nyc_frozen_world/v2 or /t63)."""
    full = path if os.path.isabs(path) else os.path.join(REPO, path)
    if not os.path.isfile(full):
        raise KeyError("冻结世界文件不存在: %s" % path)
    if os.path.getsize(full) > 64 * 1024 * 1024:
        raise ValueError("冻结世界文件过大（>64MB），拒绝载入")
    with open(full, encoding="utf-8") as fh:
        doc = json.load(fh)
    schema = doc.get("schema_version")
    if schema not in ("nyc_frozen_world/v2", "nyc_frozen_world/t63"):
        raise ValueError("未登记的冻结世界 schema: %r" % schema)
    raw = doc.get("vehicles")
    if not isinstance(raw, list) or not raw:
        raise ValueError("冻结世界没有 vehicles 列表")
    vehicles = []
    for v in raw:
        cls = v.get("cls")
        vehicles.append({
            "session_id": str(v.get("session_id")),
            "vehicle_id": str(v.get("synthetic_driver_id") or v.get("session_id")),
            "arrival": int(v.get("arrival_min")),
            "dwell": int(v.get("dwell_min")),
            "cls": cls,
            "energy": 0.0 if cls != "E1" else float(v.get("requested_kwh") or 0.0),
            "accept_power": (None if v.get("accept_power") is None
                             else float(v.get("accept_power"))),
            "origin": v.get("origin") or "unknown",
        })
    vehicles.sort(key=lambda x: (x["arrival"], x["session_id"]))
    stream = FrozenStream(
        stream_id=stream_id or ("w_" + str(doc.get("world_hash", ""))[7:23]),
        site_id=doc.get("site_id") or "unknown",
        mode=doc.get("mode") or "R2",
        scenario_id=doc.get("scenario_id") or "unknown",
        N=doc.get("N"), station_kw=doc.get("station_kw"),
        W=doc.get("W"), T=doc.get("T"), H=doc.get("H"),
        vehicles=vehicles,
        initial=doc.get("initial") or [],
        source="registered_world",
        provenance={
            "path": _rel(full), "schema_version": schema,
            "generator_version": doc.get("generator_version"),
            "world_hash": doc.get("world_hash"), "phi": doc.get("phi"),
            "assumptions": doc.get("assumptions"),
            "block_date": doc.get("block_date"), "stage": doc.get("stage"),
            "replicate": doc.get("replicate"),
        },
        world_hash=doc.get("world_hash"))
    stream.validate()
    return _register_stream(stream)


def create_synthetic_stream(site_id="synthetic", mode="R2", scenario_id="synthetic_demo",
                            seed=20261103, days=7, N=40, station_kw=7.2,
                            arrivals_per_hour=24.0, p_EV=0.30, p_need_given_EV=0.50,
                            warmup_days=2):
    """Declared synthetic demo stream (scenario only; never NYC evidence)."""
    import random
    rng = random.Random(int(seed))
    days = int(days)
    warmup_days = int(warmup_days)
    if days <= 0 or warmup_days < 0:
        raise ValueError("days 必须 >0，warmup_days 必须 >=0")
    if N < 1:
        raise ValueError("N 必须 >=1")
    W = warmup_days * 1440
    T = W + days * 1440
    vehicles = []
    t = 0
    rate = float(arrivals_per_hour) / 60.0
    idx = 0
    while True:
        t += int(rng.expovariate(rate)) if rate > 0 else 10 ** 9
        if t >= T:
            break
        dwell = int(min(600, max(20, rng.lognormvariate(4.6, 0.55))))
        u = rng.random()
        if u < p_EV:
            cls = "E1" if rng.random() < p_need_given_EV else "E0"
        else:
            cls = "I"
        energy = 0.0
        if cls == "E1":
            energy = round(min(60.0, max(3.0, rng.gauss(18.0, 8.0))), 3)
        vehicles.append({
            "session_id": "syn-%06d" % idx,
            "vehicle_id": "syn-acct-%06d" % (idx // 2),
            "arrival": t, "dwell": dwell, "cls": cls, "energy": energy,
            "accept_power": None, "origin": "generated_synthetic",
        })
        idx += 1
    H = max([T] + [v["arrival"] + v["dwell"] for v in vehicles
                   if W <= v["arrival"] < T])
    stream = FrozenStream(
        stream_id=_new_id("syn_"), site_id=site_id, mode=mode, scenario_id=scenario_id,
        N=N, station_kw=station_kw, W=W, T=T, H=H, vehicles=vehicles,
        initial=[], source="synthetic_demo",
        provenance={
            "kind": "declared_synthetic_demo",
            "seed": int(seed), "days": days, "warmup_days": warmup_days,
            "arrivals_per_hour": arrivals_per_hour, "p_EV": p_EV,
            "p_need_given_EV": p_need_given_EV,
            "note": "纯声明情景，仅用于演示与回归；不是纽约或任何真实场站的需求证据",
        })
    stream.validate()
    return _register_stream(stream)


def _register_stream(stream):
    with _LOCK:
        if len(_STREAMS) >= MAX_STREAMS:
            oldest = next(iter(_STREAMS))
            _STREAMS.pop(oldest, None)
        _STREAMS[stream.stream_id] = stream
        if stream.source == "registered_world":
            os.makedirs(STREAM_DIR, exist_ok=True)
            path = os.path.join(STREAM_DIR, stream.stream_id + ".json")
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(stream.to_dict(), fh, ensure_ascii=False, indent=1)
    return stream


def _stream_file(stream_id):
    if not isinstance(stream_id, str) or not stream_id:
        return None
    if not all(ch.isalnum() or ch in "_-" for ch in stream_id):
        return None
    return os.path.join(STREAM_DIR, stream_id + ".json")


def _rehydrate(stream_id):
    """Reload a frozen stream registered earlier from its on-disk copy."""
    path = _stream_file(stream_id)
    if path is None or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        stream = FrozenStream.from_dict(doc)
    except Exception:
        return None
    return _register_stream(stream)


def get_stream(stream_id):
    with _LOCK:
        stream = _STREAMS.get(stream_id)
    if stream is None:
        stream = _rehydrate(stream_id)
    if stream is None:
        raise KeyError("未知车辆流: %s（请先创建或载入）" % stream_id)
    return stream


def stream_list():
    with _LOCK:
        streams = list(_STREAMS.values())
    known = set(s.stream_id for s in streams)
    if os.path.isdir(STREAM_DIR):
        for name in sorted(os.listdir(STREAM_DIR)):
            if not name.endswith(".json"):
                continue
            stream_id = name[:-5]
            if stream_id in known:
                continue
            stream = _rehydrate(stream_id)
            if stream is not None:
                streams.append(stream)
                known.add(stream_id)
    return [s.summary() for s in streams]


# --------------------------------------------------------------------- config/params
def parse_params(data, base=None):
    params = CostParams.parse(data or {}, base=base)
    params.validate()
    return params


def build_spec(payload, stream):
    scheme = payload.get("scheme") or "S1"
    rule = payload.get("rule") or "fallback"
    if rule not in ADMISSION_RULES:
        raise SchemeError("rule 必须为 strict|fallback")
    if scheme not in SCHEMES:
        raise SchemeError("scheme 必须为 S1/S2/S3")
    open_data = dict(payload.get("open_rule") or {})
    mobile_data = dict(payload.get("mobile") or {})
    if scheme == "S1":
        open_data["open_rule"] = "never"
        mobile_data["count"] = 0
    elif scheme == "S2":
        mobile_data["count"] = 0
        open_data.setdefault("open_rule", "opportunity")
    else:
        open_data.setdefault("open_rule", "opportunity")
        mobile_data.setdefault("count", 1)
    spec = SchemeSpec.parse({"scheme": scheme, "rule": rule,
                             "open_rule": open_data, "mobile": mobile_data})
    spec.validate()
    return spec


def _domain_for(stream, scheme, payload):
    n_grid = payload.get("n_grid")
    m_grid = payload.get("m_grid")
    m_max = payload.get("m_max")
    if isinstance(n_grid, str):
        n_grid = [int(v) for v in n_grid.replace(" ", "").split(",") if v != ""]
    if isinstance(m_grid, str):
        m_grid = [int(v) for v in m_grid.replace(" ", "").split(",") if v != ""]
    if scheme != "S3":
        m_grid = [0]
    domain = FeasibleDomain(stream.N, n_grid=n_grid, m_grid=m_grid, m_max=m_max)
    domain.validate(scheme)
    return domain


def _cap_grid(values, cap=MAX_GRID_POINTS):
    values = sorted(set(int(v) for v in values))
    if len(values) <= cap:
        return values
    step = max(1, int(round(len(values) / float(cap))))
    out = values[::step]
    if values[-1] not in out:
        out.append(values[-1])
    return sorted(set(out))


def default_domain(stream, scheme):
    n_grid = _cap_grid(range(0, stream.N + 1))
    m_max = default_m_max(stream.N)
    m_grid = list(range(0, m_max + 1)) if scheme == "S3" else [0]
    domain = FeasibleDomain(stream.N, n_grid=n_grid, m_grid=m_grid, m_max=m_max)
    domain.validate(scheme)
    return domain


# --------------------------------------------------------------------- run payload
def _mobile_block(result, spec):
    features = result["features"]
    timeline = result["mobile_timeline"]
    return {
        "device_kind": MOBILE_DEVICE_KIND,
        "devices": spec.mobile.count,
        "services": features["mobile_services"],
        "delivered_kwh": round(features["D_mobile_kwh"], 6),
        "grid_kwh": round(features["mobile_grid_kwh"], 6),
        "loss_kwh": round(features["mobile_loss_kwh"], 6),
        "active_min": round(features["mobile_active_min"], 3),
        "travel_min": round(features["mobile_travel_min"], 3),
        "connect_min": round(features["mobile_connect_min"], 3),
        "charge_min": round(features["mobile_charge_min"], 3),
        "expired_jobs": features["mobile_expired_jobs"],
        "unserved_kwh": round(features["mobile_unserved_kwh"], 6),
        "timeline_sample": timeline[:200],
        "timeline_total": len(timeline),
        "jobs": [
            {k: j[k] for k in ("job_id", "session_id", "arrival", "dep",
                               "remaining_kwh", "state")}
            for j in result["mobile_jobs"][:200]
        ],
        "fleet": spec.mobile.to_dict(),
        "power_definition": "P_eff = min(output_kw, accept_power); missing accept_power uses assumed_accept_power_kw (declared)",
        "assumed_accept_power_kw": spec.mobile.assumed_accept_power_kw,
        "accept_power_missing_vehicles": features.get("accept_power_missing_vehicles"),
        "accept_power_assumption_applied": features.get("accept_power_assumption_applied"),
        "delivery_time_definition": "energy is booked at t_charge_end; t_release may exceed H without erasing it",
    }


def run_payload(stream_id, scheme, config, params=None, rule=None, open_rule=None,
                mobile=None, spec=None):
    stream = get_stream(stream_id)
    _check_mode_evaluable(stream, scheme)
    if spec is None:
        spec = build_spec({"scheme": scheme, "rule": rule or "fallback",
                           "open_rule": open_rule, "mobile": mobile}, stream)
    params = params or CostParams.theta_center()
    result = scheme_engine.run_scheme(stream, spec, config, params)
    features = result["features"]
    cost = social_cost.cost(features, params)
    run_id = _new_id("run_")
    warnings = _warnings_for(stream, spec)
    cohort_counts = stream.summary()["cohort_by_class"]
    payload = {
        "schema": SCHEMA, "run_id": run_id, "stream_id": stream.stream_id,
        "stream_hash": stream.world_hash, "site_id": stream.site_id,
        "mode": stream.mode, "scenario_id": stream.scenario_id,
        "scheme": spec.scheme, "rule": spec.rule, "spec": spec.to_dict(),
        "config": result["config"], "features": features,
        "cost": cost,
        "per_class": {
            "attempts": {c: features["attempts_" + c] for c in CLASSES},
            "admitted": {c: features["admitted_" + c] for c in CLASSES},
            "rejected": {"I": features["R_I"], "E0": features["R_E0"], "E1": features["R_EP"]},
            "cohort": cohort_counts,
            "E1_admitted_fixed": features["admitted_E1_charge"],
            "E1_admitted_ordinary": features["admitted_E1_ordinary"],
        },
        "energy": {
            "requested_kwh": round(features["requested_E1_kwh"], 6),
            "delivered_fixed_kwh": round(features["D_fixed_kwh"], 6),
            "delivered_mobile_kwh": round(features["D_mobile_kwh"], 6),
            "delivered_mobile_by_H_kwh": round(features.get("D_mobile_by_H_kwh",
                                                            features["D_mobile_kwh"]), 6),
            "accept_power_missing_vehicles": features.get("accept_power_missing_vehicles"),
            "unmet_kwh": round(features["S_kwh"], 6),
            "delivered_rate": (round((features["D_fixed_kwh"] + features["D_mobile_kwh"])
                                     / features["requested_E1_kwh"], 6)
                               if features["requested_E1_kwh"] > 0 else None),
            "demand_identity_ok": all(c["ok"] for c in result["checks"]
                                      if c["name"] == "demand_equals_delivered_plus_gap"),
        },
        "mobile": _mobile_block(result, spec),
        "accounting": {
            "W": stream.W, "T": stream.T, "H": stream.H,
            "window_days": (stream.T - stream.W) / 1440.0,
            "cohort_n": features.get("cohort_n"),
            "cohort_by_class": cohort_counts,
            "accept_power": stream.summary()["accept_power"],
            "mobile_assumption": {
                "assumed_accept_power_kw": spec.mobile.assumed_accept_power_kw,
                "source": ("declared_assumption" if spec.mobile.assumed_accept_power_kw is not None
                           else "declared_default: no cap beyond device output"),
            },
            "cost_basis": "USD per accounting window; per-day = total / window_days",
        },
        "moves": result["moves"][:100],
        "checks": result["checks"],
        "vehicles_sample": result["vehicles"][:50],
        "ledger_rows": len(result["vehicles"]),
        "evidence_label": _evidence_label(stream.mode),
        "warnings": warnings,
        "versions": {"math": MATH_VERSION, "engine": ENGINE_VERSION, "schema": SCHEMA},
        "total_social_cost": cost["total"],
        "total_social_cost_per_day": cost["total_per_day"],
        "cost_breakdown": {name: item["value"] for name, item in cost["items"].items()},
        "cost_complete": cost["complete"],
        "data_mode": stream.mode,
        "math_version": MATH_VERSION, "engine_version": ENGINE_VERSION,
        "world_hash": stream.world_hash, "n": result["config"]["n"],
        "m": result["config"]["m"],
        "parking_outcomes": {
            c: {"attempted": features["attempts_" + c],
                "admitted": features["admitted_" + c],
                "denied": features["R_I"] if c == "I" else (features["R_E0"] if c == "E0"
                                                             else features["R_EP"])}
            for c in CLASSES},
        "e1": {"required_kwh": round(features["requested_E1_kwh"], 6),
               "delivered_kwh": round(features["D_fixed_kwh"] + features["D_mobile_kwh"], 6),
               "unmet_kwh": round(features["S_kwh"], 6)},
        "timeline_sample": [{**e, "t_start": e.get("t_assign"), "t_end": e.get("t_release")}
                            for e in result["mobile_timeline"][:200]],
        "input_hash": canonical_hash({"stream": stream.world_hash,
                                      "spec": spec.to_dict(), "config": result["config"],
                                      "params": params.to_dict()["params"]}),
    }
    with _LOCK:
        if len(_RUNS) >= MAX_RUNS:
            _RUNS.pop(next(iter(_RUNS)), None)
        _RUNS[run_id] = {"payload": payload, "vehicles": result["vehicles"],
                         "mobile_timeline": result["mobile_timeline"]}
    return payload


def compare_payload(stream_id, configs=None, params=None, rule=None, schemes=None,
                    open_rule=None, mobile=None):
    stream = get_stream(stream_id)
    schemes = schemes or ["S1", "S2", "S3"]
    params = params or CostParams.theta_center()
    configs = dict(configs or {})
    base_n = None
    for sid in schemes:
        cfg = configs.get(sid) or {}
        if cfg.get("n") is not None:
            base_n = int(cfg["n"])
            break
    if base_n is None:
        base_n = min(stream.N, max(1, int(round(stream.N * 0.25))))
    rows = []
    for sid in schemes:
        cfg = dict(configs.get(sid) or {})
        cfg.setdefault("n", base_n)
        if sid == "S3":
            cfg.setdefault("m", int(cfg.get("m", 1)))
        else:
            cfg["m"] = 0
        spec = build_spec({"scheme": sid, "rule": rule or "fallback",
                           "open_rule": open_rule, "mobile": mobile}, stream)
        payload = run_payload(stream_id, sid, cfg, params=params, spec=spec)
        rows.append(payload)
    base = rows[0]
    for row in rows:
        row["delta_vs_S1"] = {
            "total": None if (row["cost"]["total"] is None or base["cost"]["total"] is None)
            else round(row["cost"]["total"] - base["cost"]["total"], 6),
            "total_per_day": None if (row["cost"]["total_per_day"] is None
                                      or base["cost"]["total_per_day"] is None)
            else round(row["cost"]["total_per_day"] - base["cost"]["total_per_day"], 6),
        }
    compare_id = _new_id("cmp_")
    out = {
        "schema": SCHEMA, "compare_id": compare_id,
        "stream_id": stream.stream_id, "stream_hash": stream.world_hash,
        "mode": stream.mode, "evidence_label": _evidence_label(stream.mode),
        "layer": "same_facilities_and_demand" if len({r["config"]["n"] for r in rows}) == 1
        else "different_facilities",
        "rows": rows, "versions": {"math": MATH_VERSION, "engine": ENGINE_VERSION},
        "same_stream": True,
    }
    with _LOCK:
        if len(_COMPARES) >= MAX_COMPARES:
            _COMPARES.pop(next(iter(_COMPARES)), None)
        _COMPARES[compare_id] = {"payload": out}
    return out


def search_payload(stream_id, scheme, payload, params=None, rule=None,
                   open_rule=None, mobile=None, progress=None):
    stream = get_stream(stream_id)
    _check_mode_evaluable(stream, scheme)
    params = params or CostParams.theta_center()
    domain = _domain_for(stream, scheme, payload)
    configs = domain.configs(scheme)
    spec = build_spec({"scheme": scheme, "rule": rule or "fallback",
                       "open_rule": open_rule, "mobile": mobile}, stream)
    curve = []
    for i, cfg in enumerate(configs):
        result = scheme_engine.run_scheme(stream, spec, cfg, params)
        cost = social_cost.cost(result["features"], params)
        curve.append({
            "n": cfg["n"], "m": cfg["m"],
            "J": cost["total"], "J_per_day": cost["total_per_day"],
            "complete": cost["complete"],
            "delivered_rate": (round((result["features"]["D_fixed_kwh"]
                                      + result["features"]["D_mobile_kwh"])
                                     / result["features"]["requested_E1_kwh"], 6)
                               if result["features"]["requested_E1_kwh"] > 0 else None),
            "unmet_kwh": round(result["features"]["S_kwh"], 6),
            "rejections": {"I": result["features"]["R_I"],
                           "E0": result["features"]["R_E0"],
                           "E1": result["features"]["R_EP"]},
        })
        if progress:
            progress((i + 1) / float(len(configs)))
    complete = [row for row in curve if row["complete"] and row["J"] is not None]
    best = min(complete, key=lambda r: (r["J"], r["n"], r["m"])) if complete else None
    near = []
    if best:
        best = {**best, "total_social_cost": best["J"], "total_cost": best["J"]}
        for row in complete:
            if row["J"] <= best["J"] * 1.01 + 1e-9:
                near.append({"n": row["n"], "m": row["m"], "J": row["J"],
                             "total_social_cost": row["J"]})
    search_id = _new_id("search_")
    out = {
        "schema": SCHEMA, "search_id": search_id,
        "stream_id": stream.stream_id, "stream_hash": stream.world_hash,
        "scheme": scheme, "rule": spec.rule, "spec": spec.to_dict(),
        "declared_domain": domain.to_dict(),
        "n_grid": domain.n_grid, "m_grid": domain.m_grid,
        "points": [{**row, "total_social_cost": row["J"], "total_cost": row["J"]}
                   for row in curve],
        "grid_points": len(configs),
        "curve": curve,
        "best": best,
        "near_optimal": near,
        "note": "声明网格内枚举；best 仅限声明可行域，不是无条件全局最优",
        "versions": {"math": MATH_VERSION, "engine": ENGINE_VERSION},
        "params": params.to_dict(),
    }
    with _LOCK:
        if len(_SEARCHES) >= MAX_SEARCHES:
            _SEARCHES.pop(next(iter(_SEARCHES)), None)
        _SEARCHES[search_id] = {"payload": out}
    return out


def validate_payload(payload):
    stream = get_stream(payload.get("stream_id"))
    scheme = payload.get("scheme") or "S1"
    _check_mode_evaluable(stream, scheme)
    spec = build_spec(payload, stream)
    cfg = payload.get("config") or {}
    config = validate_config(stream, scheme, cfg)
    params = parse_params(payload.get("params"))
    warnings = _warnings_for(stream, spec)
    if scheme in ("S2", "S3") and spec.open.open_rule == "opportunity":
        missing = [k for k in ("b_I", "b_E0", "b_E1", "c_E") if getattr(params, k) is None]
        if missing:
            raise SchemeError("开放规则缺少成本参数: %s" % ",".join(missing))
    return {
        "schema": SCHEMA, "ok": True, "stream_id": stream.stream_id,
        "stream_summary": stream.summary(), "scheme": scheme, "spec": spec.to_dict(),
        "config": config,
        "feasible_domain": default_domain(stream, scheme).to_dict(),
        "feasible_region": default_domain(stream, scheme).to_dict(),
        "errors": [], "limits": {"n_max": stream.N,
                                 "m_max": default_m_max(stream.N)},
        "params": params.to_dict(), "warnings": warnings,
        "evidence_label": _evidence_label(stream.mode),
        "versions": {"math": MATH_VERSION, "engine": ENGINE_VERSION},
    }


# --------------------------------------------------------------------- jobs
def _job_run(kind, fn, payload):
    job_id = _new_id("job_")
    job = {"job_id": job_id, "kind": kind, "status": "queued", "progress": 0.0,
           "created_at": time.time(), "result": None, "error": None}
    with _LOCK:
        _JOBS[job_id] = job
        _JOB_ORDER.append(job_id)
        while len(_JOB_ORDER) > 32:
            old = _JOB_ORDER.pop(0)
            if _JOBS.get(old, {}).get("status") in ("done", "failed", "cancelled"):
                _JOBS.pop(old, None)

    def progress(frac):
        job["progress"] = round(min(1.0, max(0.0, float(frac))), 4)

    def target():
        job["status"] = "running"
        try:
            job["result"] = fn(kind, payload, progress)
            job["status"] = "done"
            job["progress"] = 1.0
        except Exception as exc:  # noqa: BLE001 - surfaced to the client
            job["error"] = "%s: %s" % (type(exc).__name__, exc)
            job["status"] = "failed"
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return {"job_id": job_id, "status": job["status"]}


def job_payload(job_id):
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise KeyError("未知任务: %s" % job_id)
    out = {k: job[k] for k in ("job_id", "kind", "status", "progress", "error")}
    if job["status"] == "done":
        out["result"] = job["result"]
    return out


def cancel_job(job_id):
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise KeyError("未知任务: %s" % job_id)
    if job["status"] in ("queued", "running"):
        job["status"] = "cancelled"
        job["error"] = "客户端取消"
    return {"job_id": job_id, "status": job["status"]}


def _run_job(kind, data, progress):
    if kind == "run":
        return run_payload(data.get("stream_id"), data.get("scheme") or "S1",
                           data.get("config") or {}, params=parse_params(data.get("params")),
                           rule=data.get("rule"), open_rule=data.get("open_rule"),
                           mobile=data.get("mobile"))
    if kind == "compare":
        return compare_payload(data.get("stream_id"), configs=data.get("configs"),
                               params=parse_params(data.get("params")),
                               rule=data.get("rule"), schemes=data.get("schemes"),
                               open_rule=data.get("open_rule"), mobile=data.get("mobile"))
    if kind == "search":
        return search_payload(data.get("stream_id"), data.get("scheme") or "S3", data,
                              params=parse_params(data.get("params")),
                              rule=data.get("rule"), open_rule=data.get("open_rule"),
                              mobile=data.get("mobile"), progress=progress)
    raise ValueError("未知任务类型: %s" % kind)


# --------------------------------------------------------------------- exports
def _csv_bytes(columns, rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in columns})
    return out.getvalue().encode("utf-8-sig")


def export_run(run_id, fmt):
    with _LOCK:
        entry = _RUNS.get(run_id)
    if entry is None:
        raise KeyError("未知运行: %s" % run_id)
    payload = entry["payload"]
    if fmt == "json":
        doc = dict(payload)
        doc["vehicles"] = entry["vehicles"]
        doc["mobile_timeline"] = entry["mobile_timeline"]
        return (json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8"),
                "application/json; charset=utf-8", "t64-run-%s.json" % run_id)
    if fmt == "csv":
        columns = ["session_id", "vehicle_id", "cls", "arrival", "dwell", "departure",
                   "bay", "service", "rejected", "moved", "opened", "requested_kwh",
                   "delivered_kwh", "unmet_kwh"]
        return (_csv_bytes(columns, entry["vehicles"]), "text/csv; charset=utf-8",
                "t64-ledger-%s.csv" % run_id)
    if fmt == "mobile_csv":
        columns = ["device_id", "vehicle", "job_id", "t_assign", "t_arrive", "t_connect",
                   "t_release", "delivered_kwh", "available_min", "kind"]
        return (_csv_bytes(columns, entry["mobile_timeline"]), "text/csv; charset=utf-8",
                "t64-mobile-%s.csv" % run_id)
    raise ValueError("导出格式必须为 json、csv 或 mobile_csv")


def export_compare(compare_id, fmt):
    with _LOCK:
        entry = _COMPARES.get(compare_id)
    if entry is None:
        raise KeyError("未知对比: %s" % compare_id)
    payload = entry["payload"]
    if fmt == "json":
        return (json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"),
                "application/json; charset=utf-8", "t64-compare-%s.json" % compare_id)
    if fmt == "csv":
        columns = ["scheme", "run_id", "n", "m", "total", "total_per_day", "delta_total"]
        rows = []
        for row in payload.get("rows") or []:
            delta = row.get("delta_vs_S1") or {}
            rows.append({"scheme": row.get("scheme"), "run_id": row.get("run_id"),
                         "n": (row.get("config") or {}).get("n"),
                         "m": (row.get("config") or {}).get("m"),
                         "total": (row.get("cost") or {}).get("total"),
                         "total_per_day": (row.get("cost") or {}).get("total_per_day"),
                         "delta_total": delta.get("total")})
        return (_csv_bytes(columns, rows), "text/csv; charset=utf-8",
                "t64-compare-%s.csv" % compare_id)
    raise ValueError("导出格式必须为 json 或 csv")


def export_search(search_id, fmt):
    with _LOCK:
        entry = _SEARCHES.get(search_id)
    if entry is None:
        raise KeyError("未知搜索: %s" % search_id)
    payload = entry["payload"]
    if fmt == "json":
        return (json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8"),
                "application/json; charset=utf-8", "t64-search-%s.json" % search_id)
    if fmt == "csv":
        columns = ["n", "m", "J", "J_per_day", "complete", "delivered_rate",
                   "unmet_kwh", "rejections"]
        rows = []
        for row in payload.get("curve") or []:
            item = dict(row)
            item["rejections"] = json.dumps(item.get("rejections"), ensure_ascii=False)
            rows.append(item)
        return (_csv_bytes(columns, rows), "text/csv; charset=utf-8",
                "t64-search-%s.csv" % search_id)
    raise ValueError("导出格式必须为 json 或 csv")


def export_stream(stream_id, fmt):
    stream = get_stream(stream_id)
    if fmt == "json":
        return (json.dumps(stream.to_dict(), ensure_ascii=False, indent=1).encode("utf-8"),
                "application/json; charset=utf-8", "t64-stream-%s.json" % stream_id)
    if fmt == "csv":
        columns = ["session_id", "vehicle_id", "arrival", "dwell", "cls", "energy",
                   "accept_power", "origin"]
        return (_csv_bytes(columns, stream.vehicles), "text/csv; charset=utf-8",
                "t64-stream-%s.csv" % stream_id)
    raise ValueError("导出格式必须为 json 或 csv")


# --------------------------------------------------------------------- evidence
def evidence_payload():
    root = os.path.join(REPO, "research", "t64_three_schemes_20261103")
    items = []
    for rel in ("VERIFICATION.json", "REPORT.md", "PROTOCOL.json"):
        path = os.path.join(root, rel)
        items.append({"name": rel, "exists": os.path.exists(path),
                      "path": _rel(path) if os.path.exists(path) else None})
    verification = None
    vpath = os.path.join(root, "VERIFICATION.json")
    if os.path.exists(vpath):
        try:
            with open(vpath, encoding="utf-8") as fh:
                verification = json.load(fh)
        except (OSError, ValueError):
            verification = None
    return {
        "schema": SCHEMA, "math_version": MATH_VERSION, "engine_version": ENGINE_VERSION,
        "cost_anchor": cost_anchor(), "mobile_anchor": mobile_anchor(),
        "mobile_device_kind": MOBILE_DEVICE_KIND,
        "modes": list(MODES), "schemes": list(SCHEMES),
        "streams_available": len(stream_list()),
        "artifacts": items, "verification": verification,
        "verification_status": "verified" if verification else "UNVERIFIED（见 research/t64_three_schemes_20261103）",
        "contract": "docs/methods/THREE-SCHEME-MODEL.md",
    }


# --------------------------------------------------------------------- HTTP layer


# ------------------------------------------------------- cross-site evidence
CROSS_SITE_DIR = os.path.join(REPO, "research", "t64_followup_20261103", "cross_site")


def _csv_rows(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _cross_site_read(name):
    path = os.path.join(CROSS_SITE_DIR, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def cross_site_payload():
    results = _cross_site_read("results.json")
    protocol = _cross_site_read("PROTOCOL.json")
    rows = _csv_rows(os.path.join(CROSS_SITE_DIR, "tables", "evaluation.csv"))
    if results is None or not rows:
        return {"schema": SCHEMA, "available": False,
                "status": "missing",
                "message": "跨站点独立评价结果尚未生成（运行 research/t64_followup_20261103/cross_site.py）",
                "dir": "research/t64_followup_20261103/cross_site"}
    by_key = {}
    for r in rows:
        key = (r["site_id"], r["mechanism"], r["scenario_id"])
        rec = by_key.setdefault(key, {"site_id": key[0], "mechanism": key[1],
                                      "scenario_id": key[2], "worlds": 0,
                                      "schemes": {}})
        rec.setdefault("_wids", set()).add(r["world_id"])
        rec["schemes"].setdefault(r["scheme"], []).append(r)
    strata = []
    for key in sorted(by_key):
        rec = by_key[key]
        out = {"site_id": rec["site_id"], "mechanism": rec["mechanism"],
               "scenario_id": rec["scenario_id"],
               "worlds": len(rec.get("_wids") or ())}
        for scheme in ("S1", "S2", "S3"):
            items = rec["schemes"].get(scheme) or []
            if not items:
                continue
            js = [float(x["J"]) for x in items]
            mean = sum(js) / len(js)
            var = (sum((j - mean) ** 2 for j in js) / (len(js) - 1)) if len(js) > 1 else 0.0
            se = (var / len(js)) ** 0.5
            out[scheme] = {
                "n": items[0]["n"], "m": items[0]["m"],
                "J_mean": round(mean, 6), "J_per_day": round(mean / 7.0, 6),
                "J_se": round(se, 6), "replicates": len(items),
                "D_mobile_kwh": round(sum(float(x["D_mobile_kwh"]) for x in items) / len(items), 6),
            }
        if "S1" in out and "S2" in out:
            d = [float(b["J"]) - float(a["J"])
                 for a, b in zip(rec["schemes"]["S1"], rec["schemes"]["S2"])]
            out["delta_S2_S1"] = {"mean": round(sum(d) / len(d), 6),
                                  "se": round(_se(d), 6), "n": len(d),
                                  "positive": sum(1 for x in d if x > 0)}
        if "S2" in out and "S3" in out:
            d = [float(b["J"]) - float(a["J"])
                 for a, b in zip(rec["schemes"]["S2"], rec["schemes"]["S3"])]
            out["delta_S3_S2"] = {"mean": round(sum(d) / len(d), 6),
                                  "se": round(_se(d), 6), "n": len(d),
                                  "positive": sum(1 for x in d if x > 0)}
        strata.append(out)
    selected = _csv_rows(os.path.join(CROSS_SITE_DIR, "tables", "selection_best.csv"))
    per_block = {}
    for r in rows:
        b = per_block.setdefault(r["block_id"], {})
        b.setdefault(r["scheme"], []).append(float(r["J"]))
    block_rows = []
    for block in sorted(per_block):
        item = {"block_id": block}
        for scheme in ("S1", "S2", "S3"):
            js = per_block[block].get(scheme) or []
            if js:
                item[scheme + "_J_mean"] = round(sum(js) / len(js), 6)
        block_rows.append(item)
    return {
        "schema": SCHEMA,
        "available": True,
        "dir": "research/t64_followup_20261103/cross_site",
        "protocol": protocol,
        "summary": results,
        "selection": selected,
        "evaluation_strata": strata,
        "evaluation_blocks": block_rows,
        "data_mode": "R2 semi-synthetic (T63 v3 worlds)",
        "notes": [
            "selection 与 evaluation 是 T63 的独立阶段：选择集上选配置，评价集只评价冻结配置",
            "窗口 7 天；每窗口总额与每日值分列，不把不同长度窗口的平均值混用",
            "S2−S1 与 S3−S2 分开报告；S3 在声明域内重新选择 (n,m)",
            "hindsight 逐世界最优仅为诊断，不作为可选策略",
            "冻结世界不含 accept_power：移动交付按声明假设（默认设备输出）计算，属情景上界",
        ],
        "tables": [{"name": "selection.csv", "rows": len(_csv_rows(
                        os.path.join(CROSS_SITE_DIR, "tables", "selection.csv")))},
                   {"name": "selection_best.csv", "rows": len(selected)},
                   {"name": "evaluation.csv", "rows": len(rows)}],
    }


def _se(values):
    n = len(values)
    if n <= 1:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / (n - 1) / n) ** 0.5


def export_cross_site(fmt="json"):
    payload = cross_site_payload()
    if fmt == "csv":
        rows = _csv_rows(os.path.join(CROSS_SITE_DIR, "tables", "evaluation.csv"))
        keys = list(rows[0]) if rows else ["site_id"]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
        body = buf.getvalue().encode("utf-8-sig")
        return body, "text/csv; charset=utf-8", "t64_cross_site_evaluation.csv"
    body = json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")
    return body, "application/json; charset=utf-8", "t64_cross_site.json"


def handle_get(path, query):
    q = lambda name, default=None: (query.get(name) or [default])[0]
    if path == "/api/t64/health":
        fleet = SchemeSpec.s3(m=1).mobile.to_dict()
        return 200, {
            "ok": True, "status": "ok", "schema": SCHEMA, "contract_version": SCHEMA,
            "math_version": MATH_VERSION, "engine_version": ENGINE_VERSION,
            "schemes": list(SCHEMES),
            "limits": {"n_max": None, "m_max": default_m_max(200), "note": "n 上限随所选车辆流的 N 变化，见 /api/t64/validate"},
            "mobile_defaults": {k: v for k, v in fleet.items() if not isinstance(v, str)},
            "cost_defaults": {k: {"value": v, "source": PARAM_SPECS[k]["source"],
                                  "status": PARAM_SPECS[k]["status"], "unit": PARAM_SPECS[k]["unit"]}
                              for k, v in CostParams.theta_center().to_dict()["params"].items()},
            "modes": list(MODES), "device_kind": MOBILE_DEVICE_KIND,
            "cost_anchor": cost_anchor(), "mobile_anchor": mobile_anchor(),
            "param_provenance": social_cost.PARAM_SPECS if hasattr(social_cost, "PARAM_SPECS") else None,
            "defaults": {
                "rule": "fallback",
                "open_rule": SchemeSpec.s2().open.to_dict(),
                "mobile": SchemeSpec.s3(m=1).mobile.to_dict(),
                "params": CostParams.theta_center().to_dict(),
            },
            "streams": len(stream_list()),
        }
    if path == "/api/t64/cross-site":
        return 200, cross_site_payload()
    if path == "/api/t64/cross-site/export":
        body, ct, fn = export_cross_site(q("format", "json"))
        return 200, (body, ct, fn)
    if path == "/api/t64/streams":
        items = []
        for summary in stream_list():
            item = dict(summary)
            item["vehicles"] = summary["n_vehicles"]
            item["vehicle_count"] = summary["n_vehicles"]
            item["hash"] = summary["world_hash"]
            item["scenario"] = summary["scenario_id"]
            item["site"] = summary["site_id"]
            items.append(item)
        return 200, {"schema": SCHEMA, "streams": items,
                     "world_candidates": list_world_candidates()}
    if path.startswith("/api/t64/streams/") and path.endswith("/export"):
        sid = path[len("/api/t64/streams/"):-len("/export")]
        body, ct, fn = export_stream(sid, q("format", "json"))
        return 200, (body, ct, fn)
    if path.startswith("/api/t64/streams/"):
        sid = path[len("/api/t64/streams/"):]
        return 200, get_stream(sid).summary()
    if path.startswith("/api/t64/compares/") and path.endswith("/export"):
        compare_id = path[len("/api/t64/compares/"):-len("/export")]
        body, ct, fn = export_compare(compare_id, q("format", "json"))
        return 200, (body, ct, fn)
    if path.startswith("/api/t64/searches/") and path.endswith("/export"):
        search_id = path[len("/api/t64/searches/"):-len("/export")]
        body, ct, fn = export_search(search_id, q("format", "json"))
        return 200, (body, ct, fn)
    if path.startswith("/api/t64/searches/"):
        search_id = path[len("/api/t64/searches/"):]
        with _LOCK:
            entry = _SEARCHES.get(search_id)
        if entry is None:
            raise KeyError("未知搜索: %s" % search_id)
        return 200, entry["payload"]
    if path.startswith("/api/t64/runs/") and path.endswith("/export"):
        rid = path[len("/api/t64/runs/"):-len("/export")]
        body, ct, fn = export_run(rid, q("format", "json"))
        return 200, (body, ct, fn)
    if path.startswith("/api/t64/runs/"):
        rid = path[len("/api/t64/runs/"):]
        with _LOCK:
            entry = _RUNS.get(rid)
        if entry is None:
            raise KeyError("未知运行: %s" % rid)
        return 200, entry["payload"]
    if path.startswith("/api/t64/jobs/"):
        return 200, job_payload(path[len("/api/t64/jobs/"):])
    if path == "/api/t64/evidence":
        return 200, evidence_payload()
    raise KeyError("接口不存在")


def _stream_payload(stream):
    summary = stream.summary()
    payload = {"schema": SCHEMA, "stream": summary}
    for key, value in summary.items():
        payload.setdefault(key, value)
    payload["vehicles"] = summary["n_vehicles"]
    payload["vehicle_count"] = summary["n_vehicles"]
    payload["hash"] = summary["world_hash"]
    payload["scenario"] = summary["scenario_id"]
    payload["site"] = summary["site_id"]
    return payload


def _normalize_request(data):
    """Accept both the nested contract body and the flat browser form."""
    data = dict(data or {})
    payload = data.pop("payload", None)
    if isinstance(payload, dict):
        merged = dict(payload)
        merged.update(data)
        data = merged
    if "config" not in data and (data.get("n") is not None or data.get("m") is not None):
        data["config"] = {"n": data.get("n"), "m": data.get("m", 0)}
    if data.get("rule") is None and data.get("admission"):
        data["rule"] = data.get("admission")
    open_rule = data.get("open_rule")
    if isinstance(open_rule, str):
        rule = {"open_rule": open_rule}
        for key in ("kappa", "recall_lead_min", "forecast_window_min",
                    "fallback_e1_per_hour", "fallback_unmet_kwh", "move_minutes"):
            if data.get(key) is not None:
                rule[key] = data[key]
        data["open_rule"] = rule
    mobile = data.get("mobile")
    if not isinstance(mobile, dict):
        mobile = {}
    if data.get("m") is not None and data.get("scheme") == "S3":
        mobile.setdefault("count", data["m"])
    if mobile:
        data["mobile"] = mobile
    return data


def handle_post(path, data):
    data = _normalize_request(data)
    if path == "/api/t64/streams/create":
        stream = create_synthetic_stream(**{k: data[k] for k in (
            "site_id", "mode", "scenario_id", "seed", "days", "N", "station_kw",
            "arrivals_per_hour", "p_EV", "p_need_given_EV", "warmup_days") if k in data})
        return 200, _stream_payload(stream)
    if path == "/api/t64/streams/load":
        path_in = data.get("path")
        if not path_in:
            raise ValueError("必须提供冻结世界文件 path")
        stream = load_world_stream(path_in, stream_id=data.get("stream_id"))
        return 200, _stream_payload(stream)
    if path == "/api/t64/validate":
        return 200, validate_payload(data)
    if path == "/api/t64/run":
        return 200, run_payload(data.get("stream_id"), data.get("scheme") or "S1",
                                data.get("config") or {},
                                params=parse_params(data.get("params")),
                                rule=data.get("rule"), open_rule=data.get("open_rule"),
                                mobile=data.get("mobile"))
    if path == "/api/t64/compare":
        configs = data.get("configs")
        if not configs:
            cfg = data.get("config") or {}
            if cfg.get("n") is not None:
                configs = {"S1": {"n": cfg["n"]}, "S2": {"n": cfg["n"]},
                           "S3": {"n": cfg["n"], "m": cfg.get("m") or 0}}
        return 200, compare_payload(data.get("stream_id"), configs=configs,
                                    params=parse_params(data.get("params")),
                                    rule=data.get("rule"), schemes=data.get("schemes"),
                                    open_rule=data.get("open_rule"),
                                    mobile=data.get("mobile"))
    if path == "/api/t64/search":
        return 200, search_payload(data.get("stream_id"), data.get("scheme") or "S3", data,
                                   params=parse_params(data.get("params")),
                                   rule=data.get("rule"), open_rule=data.get("open_rule"),
                                   mobile=data.get("mobile"))
    if path == "/api/t64/jobs":
        kind = data.get("kind")
        if kind not in ("run", "compare", "search"):
            raise ValueError("kind 必须为 run|compare|search")
        return 200, _job_run(kind, _run_job, data)
    if path.startswith("/api/t64/jobs/") and path.endswith("/cancel"):
        return 200, cancel_job(path[len("/api/t64/jobs/"):-len("/cancel")])
    raise KeyError("接口不存在")