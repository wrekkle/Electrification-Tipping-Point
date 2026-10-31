# -*- coding: utf-8 -*-
"""Resource accounting: devices, reachable berths, concurrency, power,
feeder limits and delivered energy, with hard invariant assertions.

The rule enforced here is the one stated in the v2 draft: a vehicle connects
to at most one device, a device serves at most one vehicle at a time, the
number of simultaneous sessions is bounded by the devices and by the feeder,
and a session is served only if the delivered energy covers the request.

Energy accounting keeps two denominators apart (2026-10-29 revision):
    energy_requested          admitted vehicles only (charging request ledger)
    energy_requested_rejected charging requests refused at admission
    energy_requested_all      admitted + rejected
    energy_delivered          energy actually delivered
so "shortfall rate" and "unserved share of all requests" are never confused.

All times are minutes after opening (see simulator.py).
"""
from __future__ import annotations

import math


class CapacityError(AssertionError):
    pass


def reachable_berths(mode, m, n_spaces, coverage=1):
    """Berths a charger/device can physically reach."""
    if mode == "fixed":
        return min(int(m), int(n_spaces))
    if mode == "overhead":
        return min(int(n_spaces), int(m) * int(coverage))
    raise ValueError("unknown mode %r" % mode)


def max_sessions(power_kw, feeder_kw, devices):
    """Simultaneous sessions allowed by devices and by the feeder."""
    if power_kw <= 0:
        raise ValueError("power_kw must be positive")
    return int(min(int(devices), math.floor(float(feeder_kw) / float(power_kw) + 1e-12)))


def device_berths(device, m, coverage, n_spaces):
    """Berths reachable by one overhead device (fixed assignment, no two-at-once)."""
    out = []
    for k in range(int(coverage)):
        b = int(device) + k * int(m)
        if b < int(n_spaces):
            out.append(b)
    return out


def design_capacity(design, n_spaces):
    m = int(design["m"])
    mode = design["mode"]
    return {
        "devices": m,
        "berths_reachable": reachable_berths(
            mode, m, n_spaces, design.get("coverage", 1)),
        "max_sessions": max_sessions(design["power_kw"], design["feeder_kw"], m),
        "rated_power_kw": float(design["power_kw"]),
        "feeder_kw": float(design["feeder_kw"]),
        "mode": mode,
    }


def sweep_peaks(sessions):
    """Peak concurrency and peak power from session intervals.

    sessions: iterable of (t_start, t_end, power_kw, energy_kwh)
    """
    events = []
    for t0, t1, pw, _ in sessions:
        if t1 > t0:
            events.append((float(t0), 1, float(pw)))
            events.append((float(t1), -1, float(pw)))
    # ends before starts at the same timestamp (no overlap counted)
    events.sort(key=lambda e: (e[0], e[1]))
    current = 0
    peak_conc = 0
    current_pw = 0.0
    peak_pw = 0.0
    for _, delta, pw in events:
        current += delta
        current_pw += delta * pw
        peak_conc = max(peak_conc, current)
        peak_pw = max(peak_pw, current_pw + 0.0)
    return peak_conc, peak_pw


class ServiceLedger:
    """Per-run service ledger with invariant assertions."""

    def __init__(self, n_spaces, n_devices, power_kw, feeder_kw):
        self.n_spaces = int(n_spaces)
        self.n_devices = int(n_devices)
        self.power_kw = float(power_kw)
        self.feeder_kw = float(feeder_kw)
        self.vehicle_device = {}
        self.device_sessions = {}
        self.vehicle_request = {}
        self.vehicle_delivered = {}
        self.vehicle_berth = {}
        self.berth_intervals = {}
        self.sessions = []
        self.admitted = 0
        self.blocked = {}
        self.rejected_requests = {}
        self.rejected_by_class = {}
        self.energy_requested = 0.0
        self.energy_requested_rejected = 0.0
        self.energy_delivered = 0.0
        self.energy_shortfall = 0.0
        self.waiting_events = 0
        # device repositioning records (T14 round 2): only moves that actually
        # happened are recorded as intervals; cancelled moves are counted but
        # never occupy the device timeline.
        self.device_moves = {}
        self.vehicle_moves = {}
        self.moves_executed = 0
        self.moves_cancelled = 0

    # -- records ----------------------------------------------------------
    def record_block(self, demand_class):
        self.blocked[demand_class] = self.blocked.get(demand_class, 0) + 1

    def record_admission(self, vehicle, berth, t_start, t_end):
        if vehicle in self.vehicle_berth:
            raise CapacityError("vehicle %r admitted twice" % (vehicle,))
        self.vehicle_berth[vehicle] = berth
        self.berth_intervals.setdefault(berth, []).append(
            (float(t_start), float(t_end)))
        self.admitted += 1

    def record_request(self, vehicle, energy_kwh):
        """Energy request of an admitted vehicle (admitted denominator)."""
        if energy_kwh < 0:
            raise CapacityError("negative energy request")
        self.vehicle_request[vehicle] = float(energy_kwh)
        self.energy_requested += float(energy_kwh)

    def record_rejected_request(self, vehicle, energy_kwh, demand_class):
        """Energy request refused at admission (all-request denominator)."""
        if energy_kwh < 0:
            raise CapacityError("negative energy request")
        if vehicle in self.rejected_requests:
            raise CapacityError("vehicle %r rejected twice" % (vehicle,))
        self.rejected_requests[vehicle] = float(energy_kwh)
        self.rejected_by_class[demand_class] = (
            self.rejected_by_class.get(demand_class, 0) + 1)
        self.energy_requested_rejected += float(energy_kwh)

    def record_session(self, vehicle, device, t_start, t_end, energy_kwh, power_kw):
        if energy_kwh < -1e-12:
            raise CapacityError("negative delivered energy")
        if vehicle in self.vehicle_device:
            raise CapacityError("vehicle %r uses two devices" % (vehicle,))
        if power_kw > self.power_kw + 1e-9:
            raise CapacityError("session power %.6f exceeds device rating %.6f"
                                % (power_kw, self.power_kw))
        req = self.vehicle_request.get(vehicle, 0.0)
        if energy_kwh > req + 1e-9:
            raise CapacityError(
                "delivered %.9f > requested %.9f for vehicle %r"
                % (energy_kwh, req, vehicle))
        prior = self.vehicle_delivered.get(vehicle, 0.0)
        if prior + energy_kwh > req + 1e-9:
            raise CapacityError("cumulative delivery above request")
        for (a, b) in self.device_sessions.get(device, []):
            if t_start < b - 1e-9 and a < t_end - 1e-9:
                raise CapacityError(
                    "device %r serves two vehicles: [%.6f,%.6f) overlaps [%.6f,%.6f)"
                    % (device, a, b, t_start, t_end))
        self.vehicle_device[vehicle] = device
        self.device_sessions.setdefault(device, []).append(
            (float(t_start), float(t_end)))
        self.vehicle_delivered[vehicle] = prior + energy_kwh
        self.energy_delivered += energy_kwh
        self.sessions.append((float(t_start), float(t_end), float(power_kw), float(energy_kwh)))

    def record_move(self, vehicle, device, t_start, t_end, status="executed"):
        """Record the repositioning of a mobile device.

        status="executed": the move really happened (t_start/t_end set) and it
        occupies the device timeline; status="cancelled": the vehicle left
        before a connection could be scheduled, so no move took place, the
        device stays where it was and only a counter is incremented.  A
        half-executed move is deliberately not modelled; recording it would
        leave an interval that the next request has to respect even though no
        service ever started (review section 6 counterexample).
        """
        if status not in ("executed", "cancelled"):
            raise CapacityError("unknown move status %r" % (status,))
        if status == "cancelled":
            if vehicle in self.vehicle_moves:
                raise CapacityError("vehicle %r has a move and a cancellation"
                                    % (vehicle,))
            self.moves_cancelled += 1
            return
        if t_start is None or t_end is None:
            raise CapacityError("executed move needs t_start and t_end")
        if float(t_end) < float(t_start) - 1e-12:
            raise CapacityError("move ends before it starts")
        if vehicle in self.vehicle_moves:
            raise CapacityError("vehicle %r moves twice" % (vehicle,))
        self.vehicle_moves[vehicle] = int(device)
        self.device_moves.setdefault(int(device), []).append(
            (float(t_start), float(t_end), vehicle))
        self.moves_executed += 1

    # -- derived denominators --------------------------------------------
    @property
    def energy_requested_all(self):
        return self.energy_requested + self.energy_requested_rejected

    @property
    def unserved_energy(self):
        return self.energy_requested_all - self.energy_delivered

    def device_move_conflicts(self):
        """Overlaps between one device's moves, sessions and service starts."""
        out = []
        devices = sorted(set(self.device_sessions) | set(self.device_moves))
        for device in devices:
            spans = [(a, b, "session", None)
                     for (a, b) in self.device_sessions.get(device, [])]
            spans += [(a, b, "move", v)
                      for (a, b, v) in self.device_moves.get(device, [])]
            spans.sort()
            for left, right in zip(spans, spans[1:]):
                if right[0] < left[1] - 1e-9:
                    out.append({"device": device, "left": left, "right": right})
        return out

    # -- invariants -------------------------------------------------------
    def assert_invariants(self):
        conflicts = self.device_move_conflicts()
        if conflicts:
            first = conflicts[0]
            raise CapacityError(
                "device %r timeline conflict: %s [%.6f,%.6f) overlaps %s [%.6f,%.6f)"
                % (first["device"], first["left"][2], first["left"][0],
                   first["left"][1], first["right"][2], first["right"][0],
                   first["right"][1]))
        for device, intervals in self.device_sessions.items():
            intervals = sorted(intervals)
            for (a0, b0), (a1, b1) in zip(intervals, intervals[1:]):
                if a1 < b0 - 1e-9:
                    raise CapacityError(
                        "device %r serves two vehicles at once: [%.6f,%.6f) and [%.6f,%.6f)"
                        % (device, a0, b0, a1, b1))
        for berth, intervals in self.berth_intervals.items():
            intervals = sorted(intervals)
            for (a0, b0), (a1, b1) in zip(intervals, intervals[1:]):
                if a1 < b0 - 1e-9:
                    raise CapacityError(
                        "berth %r double-booked: [%.6f,%.6f) overlaps [%.6f,%.6f)"
                        % (berth, a0, b0, a1, b1))
        peak_conc, peak_pw = sweep_peaks(self.sessions)
        if peak_conc > self.n_devices:
            raise CapacityError("concurrent sessions %d > devices %d"
                                % (peak_conc, self.n_devices))
        if peak_pw > self.feeder_kw + 1e-6:
            raise CapacityError("peak power %.6f kW > feeder %.6f kW"
                                % (peak_pw, self.feeder_kw))
        if self.energy_delivered > self.energy_requested + 1e-6:
            raise CapacityError("total delivered energy exceeds admitted requests")
        if self.energy_delivered > self.energy_requested_all + 1e-6:
            raise CapacityError("total delivered energy exceeds all requests")
        if abs(sum(self.vehicle_delivered.values()) - self.energy_delivered) > 1e-6:
            raise CapacityError("ledger energy total mismatch")
        for vehicle, delivered in self.vehicle_delivered.items():
            req = self.vehicle_request.get(vehicle, 0.0)
            if delivered > req + 1e-9:
                raise CapacityError("vehicle %r delivered above request" % (vehicle,))
        return {"peak_concurrency": peak_conc, "peak_power_kw": peak_pw}

    def summary(self):
        return {
            "admitted": self.admitted,
            "blocked": dict(self.blocked),
            "blocked_total": sum(self.blocked.values()),
            "energy_requested_kwh": self.energy_requested,
            "energy_requested_admitted_kwh": self.energy_requested,
            "energy_requested_rejected_kwh": self.energy_requested_rejected,
            "energy_requested_all_kwh": self.energy_requested_all,
            "energy_delivered_kwh": self.energy_delivered,
            "undelivered_admitted_kwh": self.energy_requested - self.energy_delivered,
            "unserved_all_kwh": self.unserved_energy,
            "energy_shortfall_rate_admitted": (
                (self.energy_requested - self.energy_delivered) / self.energy_requested
                if self.energy_requested > 0 else 0.0),
            "unserved_rate_all": (
                self.unserved_energy / self.energy_requested_all
                if self.energy_requested_all > 0 else 0.0),
            "waiting_events": self.waiting_events,
        }
