# -*- coding: utf-8 -*-
"""Reproducible traffic generator calibrated on the Taipei 372-site 5-min panel.

Pure standard library. Parameters come from
research/traffic_generation_20261031/fitted_parameters.json (schema traffic_gen_params/v1).

What the calibration actually identifies (do not claim more):
  - lambda(t) per 100 spaces per hour from 5-min net-occupancy increments;
  - mean dwell from Little's identity, short/long mixture split partly scenario;
  - charging session starts from connector idle->charging transitions;
  - only the product p_EV*q_need is identified, never the factors separately;
  - charger power is a scenario, so energy is capped by power*dwell.

Normalised output (CONTRACT section 6):
  meta{seed, params_hash, generator_version, split, horizon_min, n_spaces}
  arrivals[{vehicle_id, time_min, is_ev, needs_charge, dwell_min, energy_kwh}]
  stream hash = the same canonical SHA-256 used by workbench.demand.stream_hash
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass

GENERATOR_VERSION = "traffic_gen-1.1.0"
PARAMS_SCHEMA = "traffic_gen_params/v1"


@dataclass(frozen=True)
class Arrival:
    vehicle_id: int
    time_min: float
    is_ev: bool
    needs_charge: bool
    dwell_min: float
    energy_kwh: float

    def to_dict(self):
        return asdict(self)


def stream_hash(arrivals):
    """Canonical stream hash: identical normalisation to workbench.demand.stream_hash."""
    raw = json.dumps([a.to_dict() if hasattr(a, "to_dict") else dict(a) for a in arrivals],
                     sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def params_hash(params):
    payload = {k: v for k, v in params.items() if k != "generated_utc"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_params(path):
    with open(path, encoding="utf-8") as fh:
        params = json.load(fh)
    if params.get("schema_version") != PARAMS_SCHEMA:
        raise ValueError("unsupported parameter schema: %r" % params.get("schema_version"))
    return params


def _weighted_hour_profile(hours, values, minutes):
    """Merge calibration bins that share a clock hour, weighting each by its observed minutes."""
    num = [0.0] * 24
    den = [0.0] * 24
    for idx, hour in enumerate(hours):
        if idx >= len(values) or values[idx] is None:
            continue
        w = minutes[idx] if idx < len(minutes) else 60.0
        num[hour % 24] += float(values[idx]) * w
        den[hour % 24] += w
    missing = [h for h in range(24) if den[h] <= 0]
    if missing:
        raise ValueError("parameter file has no arrival rate for local hours %r" % missing)
    return [num[h] / den[h] for h in range(24)]


def _hour_profile(params, split):
    hours = params["bins"]["local_hour"]
    minutes = params["bins"]["minutes_observed"]
    fit = params["traffic_fit"]
    if split == "train":
        values = fit["train"]["arrival_rate_per_100_spaces_hour"]
    elif split == "cohort":
        values = fit["cohort_reference"]["arrival_rate_per_100_spaces_hour"]
    else:
        raise ValueError("unknown split %r (expected train or cohort)" % (split,))
    return _weighted_hour_profile(hours, values, minutes)


def _components(dwell):
    comps = dwell.get("components") or []
    if not comps:
        raise ValueError("fitted dwell_dist carries no mixture components")
    total = sum(float(c.get("weight") or 0.0) for c in comps)
    if total <= 0:
        raise ValueError("dwell component weights sum to zero")
    return [dict(c, weight=float(c["weight"]) / total) for c in comps]


def _sample_component(comps, rng):
    u, acc = rng.random(), 0.0
    chosen = comps[-1]
    for c in comps:
        acc += c["weight"]
        if u <= acc:
            chosen = c
            break
    return chosen


def _sample_dwell(comps, rng):
    chosen = _sample_component(comps, rng)
    params = chosen.get("params") or []
    if len(params) >= 2 and params[0] is not None and params[1] is not None:
        return rng.lognormvariate(float(params[0]), float(params[1]))
    return rng.expovariate(1.0 / max(1.0, float(chosen.get("mean_min") or 60.0)))


def _poisson(rng, mean):
    if mean <= 0:
        return 0
    if mean > 30:
        return max(0, int(round(rng.gauss(mean, math.sqrt(mean)))))
    limit = math.exp(-mean)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _duration_sampler(entry, params):
    """Draw a charging session duration (minutes) from an observed 5-min histogram."""
    hist = (entry or {}).get("charge_duration_hist_5min")
    if not hist:
        hist = ((params.get("charging") or {}).get("charge_duration_dist") or {}).get("hist_5min")
    if not hist:
        return None
    items = sorted((float(k), int(v)) for k, v in hist.items() if int(v) > 0)
    total = sum(v for _, v in items)
    if total <= 0:
        return None
    cdf = []
    acc = 0
    for minutes, count in items:
        acc += count
        cdf.append((acc / total, minutes))

    def draw(rng):
        u = rng.random()
        for prob, minutes in cdf:
            if u <= prob:
                return minutes + rng.random() * 5.0
        return cdf[-1][1] + rng.random() * 5.0

    return draw


def _charge_energy(need, dwell, sampler, rng, power, eff, comps, dmean, dsd, clip):
    """Return (energy_kwh, shortfall) for one arrival: duration is capped by the stay."""
    if not need:
        return 0.0, False
    if sampler is not None:
        wanted = max(1.0, sampler(rng))
    else:
        wanted = min(float(clip[1]), max(float(clip[0]), rng.gauss(dmean, dsd))) / (power * eff) * 60.0
    usable = min(wanted, dwell)
    return power * eff * usable / 60.0, bool(wanted > dwell + 1.0)


def _energy_block(params):
    e = params["energy"]
    return (float(e["charger_power_kw"]), float(e["efficiency"]), float(e["deficit_mean_kwh"]),
            float(e["deficit_sd_kwh"]), e["deficit_clip_kwh"])


def _finalise(rows, meta, params, power, eff):
    rows.sort(key=lambda r: r[0])
    arrivals = tuple(Arrival(i, round(r[0], 6), bool(r[1]), bool(r[2]), round(r[3], 6),
                             round(r[4], 6)) for i, r in enumerate(rows))
    n_need = sum(1 for r in rows if r[2])
    n_short = sum(1 for r in rows if r[2] and r[4] < power * eff * r[3] / 60.0 - 1e-9)
    meta.update({
        "n_arrivals": len(arrivals),
        "n_ev": sum(1 for a in arrivals if a.is_ev),
        "n_needs_charge": n_need,
        "mean_dwell_min": (sum(a.dwell_min for a in arrivals) / len(arrivals)) if arrivals else None,
        "mean_energy_kwh": (sum(a.energy_kwh for a in arrivals) / n_need) if n_need else None,
        "charge_shortfall_sessions": meta.get("charge_shortfall_sessions", n_short),
        "stream_hash": stream_hash(arrivals),
        "params_hash": params_hash(params),
        "generator_version": GENERATOR_VERSION,
    })
    return arrivals, meta


def generate(params, seed, horizon_min=None, n_spaces=None, split="train"):
    """Generate a full-day traffic stream for a reference lot of n_spaces parking spaces."""
    gen = params.get("generator") or {}
    horizon = float(horizon_min if horizon_min is not None else gen.get("horizon_min", 1440))
    spaces = float(n_spaces if n_spaces is not None else gen.get("default_n_spaces", 100.0))
    if spaces <= 0 or horizon <= 0:
        raise ValueError("n_spaces and horizon_min must be positive")
    profile = _hour_profile(params, split)
    comps = _components(params["traffic_fit"]["train"]["dwell"])
    power, eff, dmean, dsd, (lo, hi) = _energy_block(params)
    min_dwell = float(gen.get("min_dwell_min", 1.0))
    max_dwell = float(gen.get("max_dwell_min", 1440.0))
    max_arrivals = int(gen.get("max_arrivals", 40000))
    step = float(gen.get("minute_step_min", 1.0))
    ref = float(gen.get("reference_spaces", 100.0))
    sampler = _duration_sampler(None, params)
    ev = params.get("ev") or {}
    p_ev = float(ev.get("p_ev_default", 0.30))
    product = ev.get("product_required_mean")
    if product is None:
        raise ValueError("fitted parameters carry no p_EV*q_need product")
    q_need = min(0.99, max(0.0, float(product) / p_ev)) if p_ev > 0 else 0.0
    rng_time = random.Random(seed * 1000003 + 101)
    rng_type = random.Random(seed * 1000003 + 202)
    rng_service = random.Random(seed * 1000003 + 303)
    rng_energy = random.Random(seed * 1000003 + 404)
    scale = spaces / ref
    shortfalls = 0
    sampler = _duration_sampler(None, params)
    rows = []
    for k in range(int(math.ceil(horizon / step))):
        minute = k * step
        if minute >= horizon:
            break
        lam = profile[int(minute // 60) % 24] * scale
        if lam <= 0:
            continue
        for _ in range(_poisson(rng_time, lam * step / 60.0)):
            t = minute + rng_time.random() * step
            is_ev = rng_type.random() < p_ev
            need = bool(is_ev and rng_type.random() < q_need)
            dwell = min(max_dwell, max(min_dwell, _sample_dwell(comps, rng_service)))
            delivered, short = _charge_energy(need, dwell, sampler, rng_energy, power, eff,
                                              comps, dmean, dsd, (lo, hi))
            shortfalls += short
            rows.append((t, is_ev, need, dwell, delivered))
            if len(rows) > max_arrivals:
                raise ValueError("generated arrivals exceed the %d hard cap" % max_arrivals)
    meta = {"charge_shortfall_sessions": shortfalls,
            "seed": int(seed), "split": split, "horizon_min": horizon, "n_spaces": spaces,
            "lot_id": None, "minute_step_min": step, "p_ev": p_ev, "q_need": q_need,
            "demand_scale": 1.0, "identification_conflict": False,
            "initial_occupancy_n": 0, "initial_occupancy_vehicles": 0.0, "warm_start": False}
    return _finalise(rows, meta, params, power, eff)


def generate_for_lot(params, lot_id, seed, horizon_min=None, p_ev=None, q_need=None,
                     demand_scale=None):
    """Generate a full-day stream for one calibrated lot, including a warm start.

    Warm start: round(mean_occupancy_vehicles) vehicles are present at t=0. Their residual
    dwell is drawn as U(0, D) with D from the fitted dwell mixture, i.e. the residual-life
    distribution of a random observer at t=0. This is what makes t=0 occupancy match the
    observed mean instead of starting from an empty lot.

    p_ev / q_need / demand_scale:
      default (demand_scale=1) reproduces the observed charging arrival rate;
      give p_ev to obtain q_need = observed_product/p_ev (clipped at 1, flagged on conflict);
      give demand_scale (e.g. 2 or 5) to scale charging demand for growth scenarios.
    """
    entry = None
    for candidate in params.get("per_lot") or []:
        if candidate.get("lot_id") == lot_id:
            entry = candidate
            break
    if entry is None:
        raise KeyError("lot_id %r is not present in the fitted per_lot array" % (lot_id,))
    gen = params.get("generator") or {}
    horizon = float(horizon_min if horizon_min is not None else gen.get("horizon_min", 1440))
    spaces = float(entry["n_spaces"])
    hours = params["bins"]["local_hour"]
    minutes = params["bins"]["minutes_observed"]
    lam_by_bin = entry["lambda_hour_by_bin"]
    profile = _weighted_hour_profile(hours, lam_by_bin, minutes)
    comps = _components(entry["dwell_dist"])
    power, eff, dmean, dsd, (lo, hi) = _energy_block(params)
    min_dwell = float(gen.get("min_dwell_min", 1.0))
    max_dwell = float(gen.get("max_dwell_min", 1440.0))
    max_arrivals = int(gen.get("max_arrivals", 40000))
    step = float(gen.get("minute_step_min", 1.0))
    ev = params.get("ev") or {}
    obs_rate = entry.get("charge_session_rate_mean_hour")
    if obs_rate is None:
        bins = entry.get("charge_session_rate_hour_by_bin") or []
        obs_rate = (sum(v for v in bins if v) / max(1, sum(1 for v in bins if v))) if bins else 0.0
    lam_bar = float(entry.get("lambda_bar_veh_per_hour") or 0.0)
    observed_product = (float(obs_rate) / lam_bar) if lam_bar > 0 else None
    dscale = float(demand_scale if demand_scale is not None else 1.0)
    if dscale <= 0:
        raise ValueError("demand_scale must be positive")
    p_ev_used = float(p_ev if p_ev is not None else ev.get("p_ev_default", 0.30))
    if not 0.0 < p_ev_used <= 1.0:
        raise ValueError("p_ev must be in (0, 1]")
    expected_arrivals = sum(profile) * horizon / 1440.0
    target_sessions = float(obs_rate) * dscale * horizon / 60.0
    conflict = False
    if q_need is not None:
        q_need_used = min(1.0, max(0.0, float(q_need)))
        if observed_product is not None and p_ev_used > 0:
            implied = q_need_used * p_ev_used
            conflict = implied > observed_product + 1e-9 or implied < observed_product - 1e-9
        target_sessions = expected_arrivals * p_ev_used * q_need_used
    else:
        raw_q = (target_sessions / (expected_arrivals * p_ev_used)) if (expected_arrivals > 0) else 0.0
        q_need_used = min(1.0, max(0.0, raw_q))
        if raw_q > 1.0:
            conflict = True
    rng_time = random.Random(seed * 1000003 + 101)
    rng_type = random.Random(seed * 1000003 + 202)
    rng_service = random.Random(seed * 1000003 + 303)
    rng_energy = random.Random(seed * 1000003 + 404)
    rng_warm = random.Random(seed * 1000003 + 505)
    rng_charge = random.Random(seed * 1000003 + 606)
    sampler = _duration_sampler(entry, params)
    rows = []
    shortfalls = 0
    warm_n = int(round(float(entry.get("mean_occupancy_vehicles") or 0.0)))
    for _ in range(warm_n):
        is_ev = rng_warm.random() < p_ev_used
        need = bool(is_ev and rng_warm.random() < q_need_used)
        full_dwell = min(max_dwell, max(min_dwell, _sample_dwell(comps, rng_warm)))
        residual = rng_warm.random() * full_dwell
        residual = min(max_dwell, max(1e-6, residual))
        delivered, short = _charge_energy(need, residual, sampler, rng_charge, power, eff,
                                          comps, dmean, dsd, (lo, hi))
        shortfalls += short
        rows.append((0.0, is_ev, need, residual, delivered))
    for k in range(int(math.ceil(horizon / step))):
        minute = k * step
        if minute >= horizon:
            break
        lam = profile[int(minute // 60) % 24]
        if lam <= 0:
            continue
        for _ in range(_poisson(rng_time, lam * step / 60.0)):
            t = minute + rng_time.random() * step
            is_ev = rng_type.random() < p_ev_used
            need = bool(is_ev and rng_type.random() < q_need_used)
            dwell = min(max_dwell, max(min_dwell, _sample_dwell(comps, rng_service)))
            delivered, short = _charge_energy(need, dwell, sampler, rng_energy, power, eff,
                                              comps, dmean, dsd, (lo, hi))
            shortfalls += short
            rows.append((t, is_ev, need, dwell, delivered))
            if len(rows) > max_arrivals:
                raise ValueError("generated arrivals exceed the %d hard cap" % max_arrivals)
    meta = {"charge_shortfall_sessions": shortfalls,
            "seed": int(seed), "split": entry.get("fit_split"), "horizon_min": horizon,
            "n_spaces": spaces, "lot_id": lot_id, "minute_step_min": step,
            "p_ev": p_ev_used, "q_need": q_need_used, "demand_scale": dscale,
            "observed_product_p_ev_q_need": observed_product,
            "observed_sessions_per_day": float(obs_rate) * 24.0,
            "observed_charge_session_per_hour": float(obs_rate),
            "target_charge_arrivals": target_sessions,
            "expected_charge_sessions": target_sessions,
            "p_ev_times_q_need_used": p_ev_used * q_need_used,
            "identification_conflict": conflict,
            "initial_occupancy_n": warm_n,
            "initial_occupancy_vehicles": float(entry.get("mean_occupancy_vehicles") or 0.0),
            "warm_start": True,
            "dwell_component_names": [c.get("name") for c in comps]}
    return _finalise(rows, meta, params, power, eff)


def save_traffic(path, arrivals, meta):
    payload = {"meta": dict(meta), "arrivals": [a.to_dict() for a in arrivals],
               "stream_hash": stream_hash(arrivals)}
    payload["meta"]["stream_hash"] = payload["stream_hash"]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, allow_nan=False)
        fh.write("\n")
    return payload["stream_hash"]


def load_traffic(path):
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    for key in ("meta", "arrivals", "stream_hash"):
        if key not in payload:
            raise ValueError("traffic file is missing %r" % key)
    arrivals = tuple(Arrival(int(r["vehicle_id"]), float(r["time_min"]), bool(r["is_ev"]),
                             bool(r["needs_charge"]), float(r["dwell_min"]),
                             float(r["energy_kwh"])) for r in payload["arrivals"])
    recomputed = stream_hash(arrivals)
    if recomputed != payload["stream_hash"]:
        raise ValueError("stream hash mismatch: file %s recomputed %s"
                         % (payload["stream_hash"], recomputed))
    meta = dict(payload["meta"])
    meta["stream_hash"] = recomputed
    return arrivals, meta
