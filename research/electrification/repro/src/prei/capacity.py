# -*- coding: utf-8 -*-
"""Resource accounting: devices, reachable berths, concurrency, power,
feeder limits and delivered energy, with hard invariant assertions.

The rule enforced here is the one stated in the v2 draft: a vehicle connects
to at most one device, a device serves at most one vehicle at a time, the
number of simultaneous sessions is bounded by the devices and by the feeder,
and a session is served only if the delivered energy covers the request.
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
        self.energy_requested = 0.0
        self.energy_delivered = 0.0
        self.energy_shortfall = 0.0
        self.waiting_events = 0

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
        if energy_kwh < 0:
            raise CapacityError("negative energy request")
        self.vehicle_request[vehicle] = float(energy_kwh)
        self.energy_requested += float(energy_kwh)

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

    # -- invariants -------------------------------------------------------
    def assert_invariants(self):
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
            raise CapacityError("total delivered energy exceeds requested energy")
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
            "energy_delivered_kwh": self.energy_delivered,
            "undelivered_kwh": self.energy_requested - self.energy_delivered,
            "energy_shortfall_rate": (
                (self.energy_requested - self.energy_delivered) / self.energy_requested
                if self.energy_requested > 0 else 0.0),
            "waiting_events": self.waiting_events,
        }