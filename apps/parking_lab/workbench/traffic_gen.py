# -*- coding: utf-8 -*-
"""HISTORICAL generator calibrated on the retired Taipei 372-site 5-min panel.

ROUND8 (2026-10-31): the Taipei panel left the execution chain; this module and its
fitted_parameters.json stay as read-only historical evidence and are NOT a default input
for new runs. New runs must use the round8 public-data adapter (publicdata.py).

Pure standard library. Parameters come from
research/traffic_generation_20261031/fitted_parameters.json (schema traffic_gen_params/v1).

What the calibration actually identifies (do not claim more):
  - lambda(t) per 100 spaces per hour from 5-min net-occupancy increments;
  - mean dwell from Little's identity, short/long mixture split partly scenario;
  - charging session starts from connector idle->charging transitions;
  - only the product p_EV*q_need is identified, never the factors separately;
  - the observed charging duration is a scenario proxy for energy, not a direct energy measurement.

Demand energy (CONTRACT section 2, traffic_gen-2.0.0):
  Arrival.energy_kwh is the TRUE energy the parking episode needs, drawn from the calibrated
  energy-demand distribution (energy.deficit_mean_kwh / deficit_sd_kwh / deficit_clip_kwh;
  the parameter file marks the energy block is_scenario=true). It is NEVER
  min(demand, deliverable): a short stay or a low rated power appears as a power/dwell
  shortfall in the accounting, not as a smaller demand.
  Per-vehicle columns (true demand / theoretical service minutes / deliverable inside the
  stay / departed gap / pending at window end / right-censoring flag) are produced by
  demand_ledger(); their totals are copied into meta by generate()/generate_for_lot().

Warm start (CONTRACT section 2.3, traffic_gen-2.0.0):
  MIGRATION: the old "draw D from the ordinary dwell mixture, then age~U(0,D)" warm start is
  removed. It biased the initial occupancy: for a two-point dwell {1,9} min it gives
  E[remaining]=2.5 min instead of the stationary length-biased value
  E[D^2]/(2E[D])=4.1 min. The only supported warm start is stationary length bias:
  D ~ P(D) proportional to D*f(D) (mixture components weighted by weight_i*E[D_i];
  a lognormal component stays lognormal with mu+sigma^2), then age~U(0,D),
  remaining=D-age. It is exposed as the public
  warm_start_arrivals(lot_info, n, rng, dwell_dist, ...) so runners reuse one implementation.
  meta.warm_start_method="length_biased_stationary" and meta.length_biased=True mark the
  method; these rows are present at t=0, they are NOT new arrivals (meta.initial_occupancy_n).

Demand scenario model (traffic_gen-2.1.0, third round):
  generate_for_lot() and warm_start_arrivals() accept
  scenario_model="legacy_product"|"independent" and strict=False.
  - "legacy_product" (default, backward compatible): keeps the old coupling
    q_need = product/p_EV from the observed session target (an explicit q_need is still
    clipped into [0,1]); meta records scenario_model / product_coupled / clipped /
    p_ev_source / q_need_source plus the existing identification_conflict flag.
  - "independent": p_EV and q_need are separate inputs; q_need is never derived from the
    product and a small p_EV is not rejected; both must be finite with 0<=p<=1 (p>0)
    and 0<=q<=1 (out-of-range raises, independent of strict).
  With strict=True the legacy path raises ValueError instead of clipping: q>1, NaN, inf
  and out-of-range p_EV / q_need / product all raise.
  The demand energy and dwell relations keep their scenario label: meta carries
  demand_calibration_status="scenario_not_identified" (and demand_energy_is_scenario).

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

GENERATOR_VERSION = "traffic_gen-2.1.0"
PARAMS_SCHEMA = "traffic_gen_params/v1"
WARM_START_METHOD = "length_biased_stationary"
ENERGY_LEDGER_METHOD = "static_one_charger_available_for_the_whole_stay"
SCENARIO_MODELS = ("legacy_product", "independent")
DEMAND_CALIBRATION_STATUS = "scenario_not_identified"


def _check_scenario_model(scenario_model):
    """Validate the demand scenario model selector."""
    if scenario_model not in SCENARIO_MODELS:
        raise ValueError("scenario_model 必须是 %r 之一，收到 %r"
                         % (SCENARIO_MODELS, scenario_model))
    return scenario_model


def _finite_float(name, value):
    """Coerce to a finite float; NaN, inf, None and non-numeric inputs raise ValueError."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s 必须是有限数值，收到 %r" % (name, value))
    if not math.isfinite(number):
        raise ValueError("%s 必须是有限数值（NaN/inf 不接受），收到 %r" % (name, value))
    return number


def _unit_interval(name, value, *, allow_zero=True):
    """Validate a finite probability in [0,1] (or (0,1] when allow_zero=False)."""
    if not (0.0 <= value <= 1.0) or (not allow_zero and value == 0.0):
        raise ValueError("%s 必须在 %s 内，收到 %r"
                         % (name, "[0,1]" if allow_zero else "(0,1]", value))
    return value


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
    """Draw a NEW arrival's full dwell D ~ f(D) (not length biased)."""
    chosen = _sample_component(comps, rng)
    params = chosen.get("params") or []
    if len(params) >= 2 and params[0] is not None and params[1] is not None:
        return rng.lognormvariate(float(params[0]), float(params[1]))
    return rng.expovariate(1.0 / max(1.0, float(chosen.get("mean_min") or 60.0)))


def _component_mean(chosen):
    """Expected dwell (minutes) of one mixture component."""
    params = chosen.get("params") or []
    if len(params) >= 2 and params[0] is not None and params[1] is not None:
        return math.exp(float(params[0]) + 0.5 * float(params[1]) ** 2)
    return max(1.0, float(chosen.get("mean_min") or 60.0))


def _sample_length_biased_dwell(comps, rng):
    """Draw D from the stationary length-biased dwell distribution P(D) proportional to D*f(D).

    Mixture components are selected with probability proportional to weight_i*E[D_i]; inside a
    lognormal component the length-biased draw is lognormal(mu+sigma^2, sigma); for the
    mean-only fallback (assumed exponential) the length-biased mean doubles.
    """
    weighted = [(c, c["weight"] * _component_mean(c)) for c in comps]
    total = sum(w for _, w in weighted)
    if total <= 0:
        raise ValueError("dwell mixture has zero length-biased mass")
    u, acc, chosen = rng.random() * total, 0.0, weighted[-1][0]
    for comp, weight in weighted:
        acc += weight
        if u <= acc:
            chosen = comp
            break
    params = chosen.get("params") or []
    if len(params) >= 2 and params[0] is not None and params[1] is not None:
        mu, sigma = float(params[0]), float(params[1])
        return rng.lognormvariate(mu + sigma * sigma, sigma)
    mean = max(1.0, float(chosen.get("mean_min") or 60.0))
    return rng.expovariate(1.0 / (2.0 * mean))


def _norm_cdf(value):
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _length_biased_truncated_mean(mu, sigma, upper):
    """E[min(D, upper)] for D ~ length-biased lognormal(mu, sigma); upper None means no cap."""
    mean = math.exp(mu + 1.5 * sigma * sigma)
    if upper is None or sigma <= 0:
        return min(mean, upper) if upper is not None else mean
    log_m = math.log(upper)
    z1 = (log_m - mu - sigma * sigma) / sigma
    z2 = (log_m - mu - 2.0 * sigma * sigma) / sigma
    return mean * _norm_cdf(z2) + upper * (1.0 - _norm_cdf(z1))


def stationary_residual_mean(dwell_dist, max_dwell=None):
    """Stationary remaining stay of a random observer at t=0: E[D^2]/(2*E[D]) (mixture closed form).

    With max_dwell=M the generator caps the drawn D at M, so the expectation is
    E[min(D, M)]/2 for the length-biased mixture; this is the value the generator should
    actually reproduce. max_dwell=None gives the untruncated E[D^2]/(2E[D]).
    """
    comps = _components(dwell_dist)
    weighted = [(comp, comp["weight"] * _component_mean(comp)) for comp in comps]
    total = sum(weight for _, weight in weighted)
    if total <= 0:
        return None
    expected = 0.0
    for comp, weight in weighted:
        params = comp.get("params") or []
        if len(params) >= 2 and params[0] is not None and params[1] is not None:
            mu, sigma = float(params[0]), float(params[1])
            expected += (weight / total) * _length_biased_truncated_mean(mu, sigma, max_dwell)
        else:
            mean = max(1.0, float(comp.get("mean_min") or 60.0))
            if max_dwell is None:
                expected += (weight / total) * (2.0 * mean)
            else:
                expected += (weight / total) * (2.0 * mean * (1.0 - math.exp(-max_dwell / (2.0 * mean))))
    return expected / 2.0


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


def _demand_block(source):
    """Resolve the calibrated true-demand distribution: source is a params dict or the energy block."""
    block = source.get("energy") if isinstance(source, dict) and "energy" in source else source
    block = block or {}
    mean = block.get("deficit_mean_kwh")
    if mean is None:
        raise ValueError("energy.deficit_mean_kwh is required to draw true demand")
    sd = block.get("deficit_sd_kwh")
    clip = block.get("deficit_clip_kwh") or [None, None]
    return (float(mean), float(sd) if sd is not None else 0.0,
            None if clip[0] is None else float(clip[0]),
            None if clip[1] is None else float(clip[1]))


def _sample_demand_kwh(block, rng):
    """Draw the TRUE energy demand (kWh) for one charging session; independent of power and dwell."""
    mean, sd, low, high = block
    value = rng.gauss(mean, sd) if sd > 0 else mean
    if low is not None and value < low:
        value = low
    if high is not None and value > high:
        value = high
    return value


def _charger_block(params):
    """Scenario charger power/efficiency used for time/feasibility bookkeeping (never for demand)."""
    energy = params.get("energy") or {}
    power, eff = energy.get("charger_power_kw"), energy.get("efficiency")
    if power is None or eff is None or float(power) <= 0 or float(eff) <= 0:
        raise ValueError("energy.charger_power_kw and energy.efficiency must be positive")
    return float(power), float(eff)


def warm_start_arrivals(lot_info, n, rng, dwell_dist, *, p_ev=None, q_need=None,
                        energy=None, mean_energy_kwh=None, min_dwell_min=1.0,
                        max_dwell_min=1440.0, vehicle_id_start=0,
                        scenario_model="legacy_product", strict=False):
    """Draw the vehicles already parked at t=0 with the stationary length-biased method.

    D ~ P(D) proportional to D*f(D) (mixture components weighted by weight_i*E[D_i]),
    age ~ U(0, D), remaining stay = D - age. This is the residual-life distribution of a
    random observer at t=0, so the t=0 occupancy reproduces the observed mean instead of a
    uniform 0..D residual (E[remaining] = E[D^2]/(2E[D]), not E[D]/2).

    Parameters
    ----------
    lot_info : dict
        Lot record (may carry p_ev / q_need fallbacks).
    n : int
        Number of vehicles present at t=0.
    rng : random.Random
        Caller-owned stream (generators use seed*1000003+505).
    dwell_dist : dict
        Fitted dwell mixture (components / params / mean_min).
    p_ev, q_need : float or None
        EV share and charge-willingness probability; fall back to lot_info then 0.30/0.0.
    energy : dict or None
        params["energy"] block used to draw the true demand of charging vehicles.
    mean_energy_kwh : float or None
        Legacy constant-demand fallback (approximation, must be flagged in reports) used when
        energy is None.
    min_dwell_min, max_dwell_min : float
        Bounds applied to the total dwell D before the age is removed.
    vehicle_id_start : int
        First vehicle id (ids are contiguous from here).
    scenario_model : {"legacy_product", "independent"}
        "legacy_product" (default, backward compatible) keeps the historical fallbacks and
        clips q_need into [0,1] unless strict; "independent" takes p_ev/q_need as separate
        inputs (no product derivation) and requires both to be finite with 0<=p<=1 (p>0)
        and 0<=q<=1; a small p_ev is never rejected.
    strict : bool
        With strict=True an out-of-range legacy q_need raises ValueError instead of being
        clipped; NaN/inf are always rejected.

    Returns
    -------
    tuple[Arrival] with time_min=0.0; these are initial occupancy, not new arrivals.
    """
    scenario_model = _check_scenario_model(scenario_model)
    strict = bool(strict)
    info = lot_info or {}
    count = max(0, int(n))
    raw_p = p_ev if p_ev is not None else info.get("p_ev")
    p_ev = _unit_interval("p_ev", _finite_float("p_ev", 0.30 if raw_p is None else raw_p),
                          allow_zero=False)
    if q_need is None:
        if scenario_model == "independent":
            raw_q = info.get("q_need")
            if raw_q is None:
                raise ValueError("scenario_model='independent' 需要显式 q_need"
                                 "（不从 product 推导）")
        else:
            raw_q = info.get("q_need", 0.0)
    else:
        raw_q = q_need
    raw_q = _finite_float("q_need", 0.0 if raw_q is None else raw_q)
    if scenario_model == "independent":
        q_need = _unit_interval("q_need", raw_q)
    elif strict:
        q_need = _unit_interval("q_need", raw_q)
    else:
        q_need = min(1.0, max(0.0, raw_q))
    block = _demand_block(energy) if energy is not None else None
    if block is None and mean_energy_kwh is None and p_ev > 0 and q_need > 0:
        raise ValueError("warm_start_arrivals needs energy=params['energy'] "
                         "(or mean_energy_kwh) when q_need > 0")
    comps = _components(dwell_dist)
    limit_low = float(min_dwell_min)
    limit_high = float(max_dwell_min)
    out = []
    for index in range(count):
        is_ev = rng.random() < p_ev
        needs = bool(is_ev and rng.random() < q_need)
        full = _sample_length_biased_dwell(comps, rng)
        full = min(limit_high, max(limit_low, full))
        age = rng.random() * full
        remaining = min(limit_high, max(1e-6, full - age))
        if needs:
            energy_kwh = max(1e-9, _sample_demand_kwh(block, rng) if block is not None
                             else float(mean_energy_kwh))
        else:
            energy_kwh = 0.0
        out.append(Arrival(vehicle_id_start + index, 0.0, is_ev, needs,
                           round(remaining, 6), round(energy_kwh, 6)))
    return tuple(out)


def demand_ledger(arrivals, *, charger_kw, efficiency, horizon_min, initial_occupancy_n=0,
                  include_vehicles=False):
    """Split every arrival into true demand / required time / deliverable / gap / pending.

    Columns per vehicle:
      demand_energy_kwh       true demand (Arrival.energy_kwh, never pre-cut)
      required_min            demand / (charger_kw*efficiency) * 60
      deliverable_energy_kwh  min(demand, charger_kw*efficiency*stay_within_window/60)
      departed_shortfall_kwh  demand - deliverable when the vehicle leaves inside the window
      pending_energy_kwh      demand - deliverable when the stay is right-censored by the window
      censored                time_min + dwell_min > horizon_min (window truncation)

    Method note: this is a static feasibility ledger assuming one charger is free for the whole
    stay. Queueing, rule-level rejection and shared feeder power are NOT modelled here; the
    simulation metrics are authoritative for delivered kWh. Censored stays are marked and are
    never counted as departure failures (charge_shortfall_sessions excludes them).

    initial_occupancy_n splits meta totals into initial-occupancy vs new-arrival demand.
    """
    horizon = float(horizon_min)
    cap_per_hour = float(charger_kw) * float(efficiency)
    if cap_per_hour <= 0:
        raise ValueError("charger_kw and efficiency must be positive")
    cap_per_min = cap_per_hour / 60.0
    initial_n = max(0, int(initial_occupancy_n))
    vehicles = []
    demand_total = required_total = deliverable_total = 0.0
    gap_total = pending_total = 0.0
    initial_demand = 0.0
    n_charge = n_censored = n_short = 0
    for index, arrival in enumerate(arrivals):
        demand = float(arrival.energy_kwh) if arrival.needs_charge else 0.0
        required = demand / cap_per_hour * 60.0 if demand > 0 else 0.0
        departure = float(arrival.time_min) + float(arrival.dwell_min)
        censored = departure > horizon + 1e-9
        stay = float(arrival.dwell_min)
        if censored:
            stay = max(0.0, min(stay, horizon - float(arrival.time_min)))
        deliverable = min(demand, cap_per_min * stay)
        if censored:
            gap, pending = 0.0, demand - deliverable
        else:
            gap, pending = demand - deliverable, 0.0
        short = (not censored) and gap > 1e-9
        demand_total += demand
        required_total += required
        deliverable_total += deliverable
        gap_total += gap
        pending_total += pending
        if index < initial_n:
            initial_demand += demand
        if demand > 0:
            n_charge += 1
            n_censored += int(censored)
        n_short += int(short)
        if include_vehicles:
            vehicles.append({
                "vehicle_id": int(arrival.vehicle_id),
                "time_min": float(arrival.time_min),
                "dwell_min": float(arrival.dwell_min),
                "departure_min": departure,
                "needs_charge": bool(arrival.needs_charge),
                "demand_energy_kwh": demand,
                "required_min": required,
                "deliverable_energy_kwh": deliverable,
                "departed_shortfall_kwh": gap,
                "pending_energy_kwh": pending,
                "censored": bool(censored),
                "charge_shortfall": bool(short),
            })
    totals = {
        "demand_energy_kwh_total": demand_total,
        "theoretical_service_min_total": required_total,
        "deliverable_energy_kwh_total": deliverable_total,
        "departed_shortfall_kwh": gap_total,
        "pending_energy_kwh": pending_total,
        "n_charge_sessions": n_charge,
        "censored_charge_sessions": n_censored,
        "charge_shortfall_sessions": n_short,
        "charge_shortfall_energy_kwh": gap_total,
        "initial_occupancy_demand_kwh": initial_demand,
        "new_arrival_demand_kwh": demand_total - initial_demand,
        "energy_accounting_method": ENERGY_LEDGER_METHOD,
    }
    return {"totals": totals, "vehicles": vehicles if include_vehicles else []}


def _finalise(rows, meta, params, power, eff):
    rows.sort(key=lambda r: r[0])
    arrivals = tuple(Arrival(i, round(r[0], 6), bool(r[1]), bool(r[2]), round(r[3], 6),
                             round(r[4], 6)) for i, r in enumerate(rows))
    n_need = sum(1 for a in arrivals if a.needs_charge)
    initial_n = int(meta.get("initial_occupancy_n") or 0)
    ledger = demand_ledger(arrivals, charger_kw=power, efficiency=eff,
                           horizon_min=float(meta["horizon_min"]),
                           initial_occupancy_n=initial_n)
    meta.update(ledger["totals"])
    meta.update({
        "n_arrivals": len(arrivals),
        "n_new_arrivals": len(arrivals) - initial_n,
        "n_ev": sum(1 for a in arrivals if a.is_ev),
        "n_needs_charge": n_need,
        "mean_dwell_min": (sum(a.dwell_min for a in arrivals) / len(arrivals)) if arrivals else None,
        "mean_energy_kwh": (sum(a.energy_kwh for a in arrivals) / n_need) if n_need else None,
        "charger_power_kw": power,
        "efficiency": eff,
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
    power, eff = _charger_block(params)
    demand_block = _demand_block(params)
    min_dwell = float(gen.get("min_dwell_min", 1.0))
    max_dwell = float(gen.get("max_dwell_min", 1440.0))
    max_arrivals = int(gen.get("max_arrivals", 40000))
    step = float(gen.get("minute_step_min", 1.0))
    ref = float(gen.get("reference_spaces", 100.0))
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
            energy = _sample_demand_kwh(demand_block, rng_energy) if need else 0.0
            rows.append((t, is_ev, need, dwell, energy))
            if len(rows) > max_arrivals:
                raise ValueError("generated arrivals exceed the %d hard cap" % max_arrivals)
    meta = {"seed": int(seed), "split": split, "horizon_min": horizon, "n_spaces": spaces,
            "lot_id": None, "minute_step_min": step, "p_ev": p_ev, "q_need": q_need,
            "demand_scale": 1.0, "identification_conflict": False,
            "initial_occupancy_n": 0, "initial_occupancy_vehicles": 0.0,
            "warm_start": False, "warm_start_method": "none", "length_biased": False,
            "demand_energy_source": "energy.deficit_* (is_scenario=true)",
            "demand_calibration_status": DEMAND_CALIBRATION_STATUS,
            "demand_energy_is_scenario": bool((params.get("energy") or {}).get("is_scenario", False)),
            "scenario_model": "legacy_product", "strict": False, "product_coupled": True,
            "clipped": False,
            "q_need_raw": (float(product) / p_ev) if p_ev > 0 else 0.0,
            "p_ev_source": "params.ev.p_ev_default",
            "q_need_source": "product_required_mean/p_ev (clipped to 0.99)",
            "product_required_mean": float(product)}
    return _finalise(rows, meta, params, power, eff)


def generate_for_lot(params, lot_id, seed, horizon_min=None, p_ev=None, q_need=None,
                     demand_scale=None, scenario_model="legacy_product", strict=False,
                     charge_provenance=None, dwell_scale=1.0):
    """Generate a full-day stream for one calibrated lot, including a warm start.

    Warm start (stationary length bias, traffic_gen-2.0.0): round(mean_occupancy_vehicles)
    vehicles are present at t=0. Their total dwell is drawn from the length-biased mixture
    P(D) proportional to D*f(D) and the remaining stay is D-age with age~U(0,D), so the t=0
    occupancy matches the observed mean with the correct residual-life distribution
    (old uniform-residual implementation removed; see module docstring). These rows are
    initial occupancy, not t=0 new arrivals (meta.initial_occupancy_n).

    p_ev / q_need / demand_scale:
      default (demand_scale=1) reproduces the observed charging arrival rate;
      give p_ev to obtain q_need = observed_product/p_ev (clipped at 1, flagged on conflict);
      give demand_scale (e.g. 2 or 5) to scale charging demand for growth scenarios.

    scenario_model / strict:
      "legacy_product" (default, backward compatible) keeps the historical product coupling
      q_need = product/p_ev; an explicit q_need is clipped into [0,1] and meta.clipped marks
      it. "independent" takes p_ev and q_need as separate inputs, never derives q_need from
      the product and never rejects a small p_ev; both must be finite with 0<p_ev<=1 and
      0<=q_need<=1 (out-of-range raises regardless of strict). strict=True makes the legacy
      path raise ValueError instead of clipping (q>1, NaN, inf, out-of-range all raise).
      Meta always records scenario_model/product_coupled/clipped/p_ev_source/q_need_source,
      and demand_calibration_status="scenario_not_identified".
    """
    entry = None
    for candidate in params.get("per_lot") or []:
        if candidate.get("lot_id") == lot_id:
            entry = candidate
            break
    if entry is None:
        raise KeyError("lot_id %r is not present in the fitted per_lot array" % (lot_id,))
    gen = params.get("generator") or {}
    horizon = _finite_float("horizon_min",
                            horizon_min if horizon_min is not None else gen.get("horizon_min", 1440))
    if horizon <= 0:
        raise ValueError("horizon_min must be positive")
    spaces = _finite_float("n_spaces", entry["n_spaces"])
    hours = params["bins"]["local_hour"]
    minutes = params["bins"]["minutes_observed"]
    lam_by_bin = entry["lambda_hour_by_bin"]
    profile = _weighted_hour_profile(hours, lam_by_bin, minutes)
    comps = _components(entry["dwell_dist"])
    power, eff = _charger_block(params)
    demand_block = _demand_block(params)
    min_dwell = float(gen.get("min_dwell_min", 1.0))
    max_dwell = float(gen.get("max_dwell_min", 1440.0))
    max_arrivals = int(gen.get("max_arrivals", 40000))
    step = float(gen.get("minute_step_min", 1.0))
    ev = params.get("ev") or {}
    scenario_model = _check_scenario_model(scenario_model)
    strict = bool(strict)
    obs_rate = entry.get("charge_session_rate_mean_hour")
    if obs_rate is None:
        bins = entry.get("charge_session_rate_hour_by_bin") or []
        obs_rate = (sum(v for v in bins if v) / max(1, sum(1 for v in bins if v))) if bins else 0.0
    obs_rate = _finite_float("observed charge_session_rate_mean_hour", obs_rate)
    lam_bar = _finite_float("lambda_bar_veh_per_hour",
                            entry.get("lambda_bar_veh_per_hour") or 0.0)
    observed_product = (obs_rate / lam_bar) if lam_bar > 0 else None
    dscale = _finite_float("demand_scale", demand_scale if demand_scale is not None else 1.0)
    if dscale <= 0:
        raise ValueError("demand_scale must be positive")
    dwell_factor = _finite_float("dwell_scale", dwell_scale if dwell_scale is not None else 1.0)
    if dwell_factor <= 0:
        raise ValueError("dwell_scale must be positive")
    expected_arrivals = _finite_float("expected_arrivals", sum(profile) * horizon / 1440.0)
    if expected_arrivals < 0:
        raise ValueError("expected_arrivals must be non-negative")
    if p_ev is None:
        default_p = ev.get("p_ev_default")
        if default_p is None:
            p_ev_source, p_ev_value = "builtin_default", 0.30
        else:
            p_ev_source, p_ev_value = "params.ev.p_ev_default", default_p
    else:
        p_ev_source, p_ev_value = "argument", p_ev
    p_ev_used = _unit_interval("p_ev", _finite_float("p_ev", p_ev_value), allow_zero=False)
    observed_target_sessions = _finite_float(
        "observed target sessions", obs_rate * dscale * horizon / 60.0)
    conflict = False
    clipped = False
    product_used = None
    if scenario_model == "independent":
        # R3-A: p_ev and q_need are separate inputs; q is never derived from the product and
        # a small p_ev is not rejected. Both must be finite in [0,1] with p>0.
        product_coupled = False
        if q_need is None:
            q_fallback = ev.get("q_need_default")
            if q_fallback is None:
                raise ValueError("scenario_model='independent' 需要显式 q_need"
                                 "（不从 product 推导）")
            q_need_source, q_need_value = "params.ev.q_need_default", q_fallback
        else:
            q_need_source, q_need_value = "argument", q_need
        q_need_used = _unit_interval("q_need", _finite_float("q_need", q_need_value))
        q_need_raw = q_need_used
        target_sessions = expected_arrivals * p_ev_used * q_need_used
    else:
        product_coupled = True
        product = ev.get("product_required_mean")
        if product is not None:
            product_used = _finite_float("ev.product_required_mean", product)
            if strict:
                _unit_interval("ev.product_required_mean", product_used)
        if q_need is not None:
            q_need_source = "argument"
            q_need_raw = _finite_float("q_need", q_need)
            if strict:
                _unit_interval("q_need", q_need_raw)
            q_need_used = min(1.0, max(0.0, q_need_raw))
            clipped = q_need_used != q_need_raw
            if observed_product is not None and p_ev_used > 0:
                implied = q_need_used * p_ev_used
                conflict = implied > observed_product + 1e-9 or implied < observed_product - 1e-9
            target_sessions = expected_arrivals * p_ev_used * q_need_used
        else:
            q_need_source = "product/p_ev derived (observed session target)"
            raw_q = (observed_target_sessions / (expected_arrivals * p_ev_used))                 if expected_arrivals > 0 else 0.0
            q_need_raw = _finite_float("derived q_need", raw_q)
            if strict:
                _unit_interval("derived q_need (=product/p_ev)", q_need_raw)
            q_need_used = min(1.0, max(0.0, q_need_raw))
            clipped = q_need_used != q_need_raw
            if q_need_raw > 1.0:
                conflict = True
            target_sessions = observed_target_sessions
    target_sessions = _finite_float("target_charge_arrivals", target_sessions)
    rng_time = random.Random(seed * 1000003 + 101)
    rng_type = random.Random(seed * 1000003 + 202)
    rng_service = random.Random(seed * 1000003 + 303)
    rng_energy = random.Random(seed * 1000003 + 404)
    rng_warm = random.Random(seed * 1000003 + 505)
    rows = []
    warm_n = int(round(float(entry.get("mean_occupancy_vehicles") or 0.0)))
    warm = warm_start_arrivals(entry, warm_n, rng_warm, entry["dwell_dist"],
                               p_ev=p_ev_used, q_need=q_need_used, energy=params.get("energy"),
                               min_dwell_min=min_dwell, max_dwell_min=max_dwell,
                               vehicle_id_start=0, scenario_model=scenario_model,
                               strict=strict)
    for arrival in warm:
        warm_dwell = min(max_dwell, max(min_dwell, arrival.dwell_min * dwell_factor))
        rows.append((0.0, arrival.is_ev, arrival.needs_charge, warm_dwell,
                     arrival.energy_kwh))
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
            dwell = min(max_dwell, max(min_dwell, _sample_dwell(comps, rng_service) * dwell_factor))
            energy = _sample_demand_kwh(demand_block, rng_energy) if need else 0.0
            rows.append((t, is_ev, need, dwell, energy))
            if len(rows) > max_arrivals:
                raise ValueError("generated arrivals exceed the %d hard cap" % max_arrivals)
    meta = {"seed": int(seed), "split": entry.get("fit_split"), "horizon_min": horizon,
            "n_spaces": spaces, "lot_id": lot_id, "minute_step_min": step,
            "p_ev": p_ev_used, "q_need": q_need_used, "demand_scale": dscale,
            "dwell_scale": dwell_factor,
            "dwell_scale_is_scenario": bool(abs(dwell_factor - 1.0) > 1e-12),
            "observed_product_p_ev_q_need": observed_product,
            "observed_sessions_per_day": float(obs_rate) * 24.0,
            "observed_charge_session_per_hour": float(obs_rate),
            "target_charge_arrivals": target_sessions,
            "expected_charge_sessions": target_sessions,
            "p_ev_times_q_need_used": p_ev_used * q_need_used,
            "identification_conflict": conflict,
            "scenario_model": scenario_model,
            "strict": strict,
            "product_coupled": product_coupled,
            "clipped": clipped,
            "q_need_raw": q_need_raw,
            "p_ev_source": p_ev_source,
            "q_need_source": q_need_source,
            "product_required_mean": product_used,
            "demand_calibration_status": DEMAND_CALIBRATION_STATUS,
            "demand_energy_is_scenario": bool((params.get("energy") or {}).get("is_scenario", False)),
            "initial_occupancy_n": warm_n,
            "initial_occupancy_vehicles": float(entry.get("mean_occupancy_vehicles") or 0.0),
            "warm_start": True,
            "warm_start_method": WARM_START_METHOD,
            "length_biased": True,
            "expected_warm_residual_mean_min": stationary_residual_mean(entry["dwell_dist"],
                                                              max_dwell=max_dwell),
            "warm_start_note": "期初车辆为平稳长度偏置抽样，不是 t=0 新到达",
            "demand_energy_source": "energy.deficit_* (is_scenario=true)",
            "dwell_component_names": [c.get("name") for c in comps]}
    if charge_provenance is not None:
        # Only scenario provenance is attached; the default stream/meta is unchanged.
        meta["charge_provenance"] = dict(charge_provenance)
        meta["charge_provenance_is_scenario"] = True
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