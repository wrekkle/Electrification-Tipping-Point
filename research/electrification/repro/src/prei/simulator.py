# -*- coding: utf-8 -*-
"""Discrete-event simulation of one day: arrivals, admission, connection,
charging, departure (t_a / t_c / t_d / t_r), with a heapq release timeline.

Independent Python re-implementation, not a port of the original MATLAB code.
The same demand day is replayed for every design and rule (common random
numbers).  Feeder and device constraints are checked against the service
ledger at the instant a session starts.
"""
from __future__ import annotations

import heapq

import numpy as np

from . import capacity, demand, rules


def _coverage_berths(device, m, coverage, n_spaces):
    return capacity.device_berths(device, m, coverage, n_spaces)


def simulate_day(cfg, cost_model, design, day):
    """Simulate one day for one design (m, rule, mode) and one demand day."""
    N = int(cfg["lot"]["n_spaces"])
    mode = design["mode"]
    m = int(design["m"])
    rule = design["rule"]
    theta = float(design.get("theta", 0.0))
    coverage = int(design.get("coverage", 1))
    reposition_h = float(design.get("reposition_min", 0.0)) / 60.0
    power_kw = float(design["power_kw"])
    feeder_kw = float(design["feeder_kw"])

    times = np.asarray(day["times"], dtype=float)
    classes = np.asarray(day["classes"], dtype=object)
    n = len(times)
    if n > 1 and np.any(np.diff(times) < -1e-12):
        raise ValueError("arrival times must be sorted ascending")
    dwell_min = np.asarray(day["dwell_min"], dtype=float)
    energy_req = np.asarray(day["energy_req"], dtype=float)

    ledger = capacity.ServiceLedger(N, m, power_kw, feeder_kw)
    berth_free = np.zeros(N, dtype=float)
    device_free = np.zeros(m, dtype=float)
    device_last_berth = [-1] * m
    end_heap = []  # (session end time, power) heapq release timeline
    clock = 0.0  # latest connection start: keeps session starts chronological
    reserved = rules.reserved_berths(m, theta) if rule == "pi_theta" else 0
    timeline = []

    def active_power(t):
        return sum(s[2] for s in ledger.sessions if s[0] <= t < s[1])

    def next_release(t):
        while end_heap and end_heap[0][0] <= t:
            heapq.heappop(end_heap)
        return end_heap[0][0] if end_heap else None

    def berth_is_open_charging(b):
        return (rule != "pi_theta") or (b >= reserved)

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
            timeline.append({"vehicle": i, "class": cls, "t_a": t, "t_c": None,
                             "t_d": None, "t_r": t_r, "berth": None, "device": None,
                             "energy_requested_kwh": req,
                             "energy_delivered_kwh": 0.0, "blocked": True})
            continue

        berth = chosen
        berth_free[berth] = t_r
        ledger.record_admission(i, berth, t, t_r)
        ledger.record_request(i, req)
        t_c = t_d = None
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
                t_ready = float(device_free[best])
                if mode == "overhead" and device_last_berth[best] not in (berth, -1):
                    t_ready += reposition_h
                t_c = max(t, t_ready, clock)
                # wait for feeder headroom at the session start instant
                guard = 0
                while True:
                    guard += 1
                    if active_power(t_c) + power_kw <= feeder_kw + 1e-9:
                        break
                    nxt = next_release(t_c)
                    if nxt is None or nxt >= t_r or guard > n + 2:
                        t_c = float("inf")
                        break
                    t_c = nxt
                if np.isfinite(t_c) and t_c < t_r - 1e-12:
                    energy = min(req, power_kw * (t_r - t_c) / 60.0)
                    t_d = t_c + energy / power_kw * 60.0
                    device_used = best
                    device_free[best] = t_d
                    device_last_berth[best] = berth
                    heapq.heappush(end_heap, (t_d, power_kw))
                    ledger.record_session(i, best, t_c, t_d, energy, power_kw)
                    clock = t_c
                else:
                    ledger.waiting_events += 1
                    t_c = None
                    t_d = None
            else:
                ledger.waiting_events += 1

        timeline.append({"vehicle": i, "class": cls, "t_a": t, "t_c": t_c,
                         "t_d": t_d, "t_r": t_r, "berth": berth,
                         "device": device_used,
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
    shortfall_kwh = ledger.energy_requested - ledger.energy_delivered
    loss += shortfall_kwh * penalty
    metrics = {
        "arrivals_A": int(n),
        "counts_ev_charge": int(counts["ev_charge"]),
        "counts_ev_park": int(counts["ev_park"]),
        "counts_icev": int(counts["icev"]),
        "blocked_ev_charge": blocked_ev_charge,
        "blocked_ev_park": blocked_ev_park,
        "blocked_icev": blocked_icev,
        "blocked_total": blocked_ev_charge + blocked_ev_park + blocked_icev,
        "admitted": ledger.admitted,
        "sessions": len(ledger.sessions),
        "energy_requested_kwh": ledger.energy_requested,
        "energy_delivered_kwh": ledger.energy_delivered,
        "shortfall_kwh": shortfall_kwh,
        "shortfall_rate": (shortfall_kwh / ledger.energy_requested
                           if ledger.energy_requested > 0 else 0.0),
        "peak_concurrency": peaks["peak_concurrency"],
        "peak_power_kw": peaks["peak_power_kw"],
        "daily_loss_rmb": float(loss),
        "r_draw": float(day["r_draw"]),
        "rule": rule,
        "mode": mode,
        "m": m,
    }
    return {"metrics": metrics, "timeline": timeline, "ledger": ledger}
