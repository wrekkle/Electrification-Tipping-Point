# -*- coding: utf-8 -*-
"""Discrete-event simulation of one day: arrivals, admission, connection,
charging, departure (t_a / t_c / t_d / t_r), with a release timeline.

Independent Python re-implementation, not a port of the original MATLAB code.
The same demand day is replayed for every design and rule (common random
numbers).

Time contract (2026-10-29 revision)
----------------------------------
The whole event layer runs on ONE unit: minutes after the lot opens.

    day["times_min"]      arrival time, minutes after opening (intake field)
    day["dwell_min"]      parking dwell, minutes
    day["energy_req"]     requested energy, kWh
    design["power_kw"]    rated charging power, kW
    design["feeder_kw"]   feeder limit, kW
    design["reposition_min"] overhead reposition time, minutes
    timeline t_a/t_c/t_d/t_r   minutes; t_c/t_d may be None
    metrics["time_unit"]  "minute"

The demand layer (demand.simulate_day_arrivals) draws a non-homogeneous
Poisson process in hours and converts once at its boundary; nothing else in
the pipeline is allowed to mix hours and minutes.  Connector duration is
derived from energy and power, never from a hard-coded 60.

Scheduling: an admission keeps the parking berth for the whole dwell.  A
charging session starts as soon as its device is free and the feeder has
headroom over the whole session; it never waits for an unrelated device's
future start (the earlier global clock did that).  Only commitments already
scheduled are used, i.e. the decision uses information available at the
arrival instant.

Mobile (overhead) devices, T14/F01
----------------------------------
The target berth of an arriving vehicle is only known at its arrival, so the
reposition time cannot be paid out of idle time that elapsed before the
vehicle showed up.  The timeline of one connection is therefore:

    t_a             arrival (vehicle is parked at its berth)
    t_move_start    max(t_a, device_free[best]) if a reposition is needed
    t_move_end      t_move_start + reposition_min   (device now at the berth)
    t_c             first instant >= t_move_end with enough feeder headroom
    t_d             t_c + charged duration;  t_r = t_a + dwell

Device initial position is an explicit assumption (config
v2.device_initial_position): "home_berth" means device d rests at berth d, so
serving another berth costs reposition_min; "depot" reproduces the old
behaviour in which the first assignment is free.
"""
from __future__ import annotations

import numpy as np

from . import capacity, demand, rules


def _coverage_berths(device, m, coverage, n_spaces):
    return capacity.device_berths(device, m, coverage, n_spaces)


def _peak_power_over(sessions, t0, t1, extra_kw):
    """Peak concurrent power on [t0, t1) including one extra session."""
    events = []
    for (s0, s1, pw, _) in sessions:
        lo = max(t0, s0)
        hi = min(t1, s1)
        if hi > lo:
            events.append((lo, pw))
            events.append((hi, -pw))
    # Intervals are half-open [start, end): at a shared timestamp the END must
    # be applied before the START.  Sorting by -power put starts first and
    # counted two abutting 50 kW sessions plus a spanning 50 kW request as
    # 150 kW instead of 100 kW (T14/F01).
    events.sort(key=lambda e: (e[0], e[1]))
    cur = 0.0
    peak = 0.0
    for _, delta in events:
        cur += delta
        if cur > peak:
            peak = cur
    return peak + extra_kw


def _next_release_after(sessions, t):
    """Earliest already-scheduled session end strictly after t, or None."""
    ends = [s[1] for s in sessions if s[1] > t + 1e-12]
    return min(ends) if ends else None


def _schedule_connection(ledger, t_arrive, t_ready, t_r, req_kwh, power_kw,
                         feeder_kw):
    """Earliest feasible connected interval, or (None, 0.0, None).

    Feasibility means: rated power for the whole session stays within the
    feeder limit together with the sessions already scheduled.  Waiting is
    only for scheduled releases, never for a global clock.
    """
    t_c = max(float(t_arrive), float(t_ready))
    guard = 0
    limit = 2 * len(ledger.sessions) + 8
    while t_c < t_r - 1e-12:
        guard += 1
        if guard > limit:
            return None, 0.0, None
        duration = min(req_kwh / power_kw * 60.0, t_r - t_c)
        if duration <= 1e-12:
            return None, 0.0, None
        t_d = t_c + duration
        energy = power_kw * duration / 60.0
        if _peak_power_over(ledger.sessions, t_c, t_d, power_kw) <= feeder_kw + 1e-9:
            return t_c, energy, t_d
        nxt = _next_release_after(ledger.sessions, t_c)
        if nxt is None or nxt >= t_r - 1e-12:
            return None, 0.0, None
        t_c = nxt
    return None, 0.0, None


def simulate_day(cfg, cost_model, design, day):
    """Simulate one day for one design (m, rule, mode) and one demand day."""
    N = int(cfg["lot"]["n_spaces"])
    mode = design["mode"]
    m = int(design["m"])
    rule = design["rule"]
    theta = float(design.get("theta", 0.0))
    coverage = int(design.get("coverage", 1))
    reposition_min = float(design.get("reposition_min", 0.0))
    power_kw = float(design["power_kw"])
    feeder_kw = float(design["feeder_kw"])

    if "times_min" not in day:
        raise ValueError(
            "day['times_min'] (minutes after opening) is required; the demand "
            "layer must hand over minutes, not raw hours in a 'times' key")
    times = np.asarray(day["times_min"], dtype=float)
    classes = np.asarray(day["classes"], dtype=object)
    n = len(times)
    if n > 1 and np.any(np.diff(times) < -1e-12):
        raise ValueError("arrival times must be sorted ascending")
    dwell_min = np.asarray(day["dwell_min"], dtype=float)
    energy_req = np.asarray(day["energy_req"], dtype=float)

    ledger = capacity.ServiceLedger(N, m, power_kw, feeder_kw)
    berth_free = np.zeros(N, dtype=float)
    device_free = np.zeros(m, dtype=float)
    initial_position = str(cfg.get("v2", {}).get("device_initial_position",
                                                 "home_berth")).lower()
    if initial_position == "home_berth":
        device_last_berth = [d if d < N else -1 for d in range(m)]
    elif initial_position == "depot":
        device_last_berth = [-1] * m
    else:
        raise ValueError("unknown device_initial_position %r" % (initial_position,))
    reserved = rules.reserved_berths(m, theta) if rule == "pi_theta" else 0

    def berth_is_open_charging(b):
        return (rule != "pi_theta") or (b >= reserved)

    timeline = []
    for i in range(n):
        t = float(times[i])
        cls = str(classes[i])
        t_r = t + float(dwell_min[i])
        req = float(energy_req[i]) if cls == "ev_charge" else 0.0

        # -- choose an admissible free berth --------------------------------
        chosen = None
        for b in range(N):
            if berth_free[b] > t + 1e-12:
                continue
            if mode == "overhead":
                if cls == "ev_charge":
                    devs = [d for d in range(m)
                            if b in _coverage_berths(d, m, coverage, N)]
                    if not devs:
                        continue
                ok = True
            else:
                berth_type = "charging" if b < m else "ordinary"
                ok = rules.is_admissible(rule, cls, berth_type,
                                         berth_is_open_charging(b))
            if ok:
                chosen = b
                break
        if chosen is None:
            ledger.record_block(cls)
            if cls == "ev_charge":
                ledger.record_rejected_request(i, req, cls)
            timeline.append({"vehicle": i, "class": cls, "t_a": t, "t_c": None,
                             "t_d": None, "t_r": t_r, "berth": None, "device": None,
                             "t_move_start": None, "t_move_end": None,
                             "t_move_status": "blocked", "t_move_device": None,
                             "energy_requested_kwh": req,
                             "energy_delivered_kwh": 0.0, "blocked": True})
            continue

        berth = chosen
        berth_free[berth] = t_r
        ledger.record_admission(i, berth, t, t_r)
        ledger.record_request(i, req)
        t_c = t_d = None
        t_move_start = t_move_end = None
        t_move_status = "none"
        t_move_device = None
        energy = 0.0
        device_used = None

        if cls == "ev_charge":
            if mode == "overhead":
                devs = [d for d in range(m)
                        if berth in _coverage_berths(d, m, coverage, N)]
            else:
                devs = [berth] if berth < m else []
            if devs:
                best = min(devs, key=lambda d: (device_free[d], d))
                # the move cannot start before the vehicle has arrived: the
                # target berth is unknown until then (T14/F01)
                base = max(t, float(device_free[best]))
                needs_move = (mode == "overhead" and reposition_min > 0.0
                              and device_last_berth[best] != berth)
                if needs_move:
                    t_move_start = base
                    t_move_end = base + reposition_min
                    base = t_move_end
                t_c, energy, t_d = _schedule_connection(
                    ledger, base, 0.0, t_r, req, power_kw, feeder_kw)
                if t_c is not None:
                    device_used = best
                    if needs_move:
                        ledger.record_move(i, best, t_move_start, t_move_end,
                                           "executed")
                        t_move_status = "executed"
                        t_move_device = best
                    device_free[best] = t_d
                    device_last_berth[best] = berth
                    ledger.record_session(i, best, t_c, t_d, energy, power_kw)
                else:
                    # the vehicle leaves before a connection is possible, so
                    # the tentative move never happens: drop its interval and
                    # leave device_free/device_last_berth untouched (review
                    # section 6: no 10-20 move recorded for a failed request)
                    ledger.waiting_events += 1
                    if needs_move:
                        ledger.record_move(i, best, None, None, "cancelled")
                        t_move_status = "cancelled"
                        t_move_device = best
                    t_move_start = t_move_end = None
                    t_c = None
                    t_d = None
                    energy = 0.0
            else:
                ledger.waiting_events += 1
                t_move_status = "no_device"

        timeline.append({"vehicle": i, "class": cls, "t_a": t, "t_c": t_c,
                         "t_d": t_d, "t_r": t_r, "berth": berth,
                         "device": device_used,
                         "t_move_start": t_move_start, "t_move_end": t_move_end,
                         "t_move_status": t_move_status,
                         "t_move_device": t_move_device,
                         "energy_requested_kwh": req,
                         "energy_delivered_kwh": energy,
                         "blocked": False})

    peaks = ledger.assert_invariants()

    counts = day["counts"]
    blocked_ev_charge = ledger.blocked.get("ev_charge", 0)
    blocked_ev_park = ledger.blocked.get("ev_park", 0)
    blocked_icev = ledger.blocked.get("icev", 0)
    loss = (
        (blocked_ev_charge + blocked_ev_park) * cost_model.event_cost("ev")
        + blocked_icev * cost_model.event_cost("icev")
    )
    penalty = float(cfg["cost"].get("energy_shortfall_rmb_per_kwh", 0.0))
    shortfall_kwh = max(0.0, ledger.energy_requested - ledger.energy_delivered)
    ledger.energy_shortfall = shortfall_kwh
    loss += shortfall_kwh * penalty
    rejected_energy = ledger.energy_requested_rejected
    all_requested = ledger.energy_requested_all
    unserved = all_requested - ledger.energy_delivered
    metrics = {
        "arrivals_A": int(n),
        "counts_ev_charge": int(counts["ev_charge"]),
        "counts_ev_park": int(counts["ev_park"]),
        "counts_icev": int(counts["icev"]),
        "blocked_ev_charge": blocked_ev_charge,
        "blocked_ev_park": blocked_ev_park,
        "blocked_icev": blocked_icev,
        "blocked_total": blocked_ev_charge + blocked_ev_park + blocked_icev,
        "rejected_ev_charge": int(ledger.rejected_by_class.get("ev_charge", 0)),
        "admitted": ledger.admitted,
        "sessions": len(ledger.sessions),
        # two energy denominators, never mixed:
        "energy_requested_kwh": ledger.energy_requested,          # admitted only
        "energy_requested_admitted_kwh": ledger.energy_requested,
        "energy_requested_all_kwh": all_requested,                # incl. rejected
        "rejected_energy_kwh": rejected_energy,
        "energy_delivered_kwh": ledger.energy_delivered,
        "shortfall_kwh": shortfall_kwh,                           # admitted only
        "shortfall_rate": (shortfall_kwh / ledger.energy_requested
                           if ledger.energy_requested > 0 else 0.0),
        "unserved_energy_kwh": unserved,
        "unserved_rate_all": (unserved / all_requested
                              if all_requested > 0 else 0.0),
        # T12 label split: M06 is shortfall_rate (admitted denominator),
        # M07 is refused_rate_all (all requested energy denominator); the
        # combined unserved_rate_all above is neither and must not be quoted
        # as either metric.
        "refused_rate_all": (rejected_energy / all_requested
                             if all_requested > 0 else 0.0),
        # q denominators.  The configured q is P(charge request | EV visit),
        # so the EV-visit count has to be exposed; sessions/EV visits is the
        # realised plug rate (q_plug analogue), not q_need.
        "ev_arrivals": int(counts["ev"]),
        "ev_charge_requests": int(counts["ev_charge"]),
        "q_request_realized": (float(counts["ev_charge"]) / counts["ev"]
                               if counts["ev"] > 0 else 0.0),
        "q_plug_realized": (float(len(ledger.sessions)) / counts["ev"]
                            if counts["ev"] > 0 else 0.0),
        "peak_concurrency": peaks["peak_concurrency"],
        "peak_power_kw": peaks["peak_power_kw"],
        "daily_loss_rmb": float(loss),
        "time_unit": "minute",
        "device_initial_position": initial_position,
        "device_moves_executed": int(ledger.moves_executed),
        "device_moves_cancelled": int(ledger.moves_cancelled),
        "device_moves_planned": int(ledger.moves_executed + ledger.moves_cancelled),
        "device_move_conflicts": len(ledger.device_move_conflicts()),
        "r_draw": float(day["r_draw"]),
        "rule": rule,
        "mode": mode,
        "m": m,
    }
    return {"metrics": metrics, "timeline": timeline, "ledger": ledger}
