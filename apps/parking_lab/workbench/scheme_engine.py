# -*- coding: utf-8 -*-
"""Event-driven engine for the three T64 service schemes (S1/S2/S3).

The engine consumes a frozen exogenous stream (schemes.FrozenStream) and a
declared SchemeSpec, replays one configuration (n, m) and returns the physical
ledger.  It contains no cost aggregation; see social_cost for that.  The
accounting window, cohort, horizon and tie-breaking rules follow
docs/methods/THREE-SCHEME-MODEL.md and MODEL_V3 section 6.

Simultaneous events: departures and device events are processed before
arrivals at the same minute; arrivals are then processed in stable
(arrival, session_id) order.
"""
import heapq

try:  # package import (python -m apps.parking_lab.workbench ...)
    from .schemes import (CLASSES, ENGINE_VERSION, MATH_VERSION, SCHEMA, SchemeError,
                          validate_config)
except ImportError:  # direct module import (tests, standalone verification)
    from schemes import (CLASSES, ENGINE_VERSION, MATH_VERSION, SCHEMA, SchemeError,
                         validate_config)

INF = float("inf")
_PRIO_DEP = 0
_PRIO_DEV = 1


class EngineError(ValueError):
    pass


def effective_power(stream, vehicle):
    p = float(stream.station_kw)
    if vehicle.get("accept_power") is not None:
        p = min(p, float(vehicle["accept_power"]))
    return p


def mobile_effective_power(rule, vehicle):
    """Effective mobile charging power: min(device output, vehicle acceptance).

    A missing accept_power is an unknown, not a measurement: the declared
    assumption in rule.assumed_accept_power_kw is used and reported, never
    silently treated as observed.  When the assumption is also None the
    effective power is the device output (declared 'no cap' assumption).
    """
    p = float(rule.output_kw)
    accept = vehicle.get("accept_power")
    if accept is None:
        accept = getattr(rule, "assumed_accept_power_kw", None)
    if accept is not None:
        p = min(p, float(accept))
    return p


def _delivered(rec):
    """Fixed-connector delivery, identical to reference_model_v3.delivered_energy."""
    if rec.get("charge_start") is None or rec.get("rate", 0.0) <= 0:
        return 0.0
    e = float(rec["energy"])
    p = float(rec["rate"])
    if e <= 0 or p <= 0:
        return 0.0
    s = 60.0 * e / p
    end = min(rec["dep"], rec["charge_start"] + s)
    return max(0.0, min(e, p * (end - rec["charge_start"]) / 60.0))


def _delivered_between(rec, t0, t1):
    if rec.get("charge_start") is None or rec.get("rate", 0.0) <= 0:
        return 0.0
    e = float(rec["energy"])
    p = float(rec["rate"])
    if e <= 0 or p <= 0:
        return 0.0
    end = min(rec["dep"], rec["charge_start"] + 60.0 * e / p)
    lo, hi = max(rec["charge_start"], t0), min(end, t1)
    return max(0.0, hi - lo) * p / 60.0


def _empty_agg():
    return {
        "R_I": 0, "R_E0": 0, "R_EP": 0,
        "attempts_I": 0, "attempts_E0": 0, "attempts_E1": 0,
        "admitted_I": 0, "admitted_E0": 0, "admitted_E1": 0,
        "admitted_E1_charge": 0, "admitted_E1_ordinary": 0,
        "requested_E1_kwh": 0.0, "D_fixed_kwh": 0.0, "D_mobile_kwh": 0.0,
        "S_kwh": 0.0, "moves": 0, "opened": 0, "open_attempts": 0,
        "mobile_services": 0, "mobile_expired_jobs": 0, "mobile_energy_limited": 0,
        "mobile_active_min": 0.0, "mobile_travel_min": 0.0, "mobile_connect_min": 0.0,
        "mobile_charge_min": 0.0, "mobile_release_min": 0.0, "mobile_grid_kwh": 0.0,
        "mobile_loss_kwh": 0.0, "mobile_unserved_kwh": 0.0,
        "warmup_memo_delivered_kwh": 0.0,
        "max_charge_occupied": 0, "max_ordinary_occupied": 0,
        "cohort_n": 0, "rejections_total": 0,
    }


class _Device:
    __slots__ = ("idx", "state", "soc", "job", "visit", "stats")

    def __init__(self, idx, soc):
        self.idx = idx
        self.state = "idle"       # idle | busy | returning | recharging
        self.soc = float(soc)
        self.job = None
        self.visit = None
        self.stats = {"services": 0, "delivered_kwh": 0.0, "grid_kwh": 0.0,
                      "active_min": 0.0, "travel_min": 0.0, "connect_min": 0.0,
                      "charge_min": 0.0, "release_min": 0.0, "recharges": 0}


class _Run:
    def __init__(self, stream, spec, config):
        self.stream = stream
        self.spec = spec
        self.n = config["n"]
        self.m = config["m"]
        self.N = stream.N
        self.ordinary_cap = max(0, self.N - self.n)
        self.W, self.T, self.H = stream.W, stream.T, stream.H
        self.days = (self.T - self.W) / 1440.0
        self.charge_occ = {}     # slot -> occupant
        self.ordinary_occ = {}
        self.veh_heap = []       # (release, prio, seq, occ)
        self.dev_heap = []       # (time, prio, seq, dev_idx, kind)
        self.seq = 0
        self.records = []
        self.by_sid = {}
        self.agg = _empty_agg()
        self.mobile_jobs = []
        self.mobile_timeline = []
        self.moves_log = []
        self.e1_past = []        # (arrival, energy) of observed E1 arrivals
        self.devices = []
        self.mobile_on = spec.scheme == "S3" and self.m > 0
        self.init_charge = sum(1 for i in stream.initial if i["release"] > 0 and i["kind"] == "charge")
        self.init_ordinary = sum(1 for i in stream.initial if i["release"] > 0 and i["kind"] != "charge")
        self.params = None       # injected for the opening rule
        self.checks = []

    # -- helpers -----------------------------------------------------------
    def _next_seq(self):
        self.seq += 1
        return self.seq

    def _free_charge_slot(self):
        for i in range(self.n):
            if i not in self.charge_occ:
                return i
        return None

    def _free_ordinary_slot(self):
        for i in range(self.ordinary_cap):
            if i not in self.ordinary_occ:
                return i
        return None

    def _forecast(self, t):
        rule = self.spec.open
        window = float(rule.forecast_window_min)
        lo = t - window
        recent = [e for (a, e) in self.e1_past if lo <= a < t]
        lam = len(recent) * 60.0 / window if window > 0 else 0.0
        if not recent:
            lam = float(rule.fallback_e1_per_hour)
            e_hat = float(rule.fallback_unmet_kwh)
        else:
            e_hat = sum(recent) / len(recent)
        # declared forecast error: only rescales the estimate, never uses future data
        lam *= float(rule.forecast_bias)
        e_hat *= float(rule.forecast_bias)
        return lam, e_hat

    def _open_test(self, vehicle, t):
        """Incremental opportunity cost of opening one charging bay."""
        p = self.params
        rule = self.spec.open
        cls = vehicle["cls"]
        loss_now = p.b_I if cls == "I" else p.b_E0
        if loss_now is None:
            raise EngineError("S2/S3 开放规则需要完整的 b_I/b_E0 成本参数")
        lam, e_hat = self._forecast(t)
        l_e1 = None
        if p.b_E1 is not None and p.c_E is not None:
            l_e1 = p.b_E1 + p.c_E * e_hat
        if l_e1 is None:
            raise EngineError("S2/S3 开放规则需要完整的 b_E1/c_E 成本参数")
        oc = float(rule.kappa) * lam * (vehicle["dwell"] * float(rule.dwell_bias) / 60.0) * l_e1
        return loss_now >= oc, {"lambda_per_h": lam, "unmet_kwh_hat": e_hat,
                                "loss_if_rejected": loss_now,
                                "marginal_loss_blocked_E1": l_e1,
                                "incremental_opportunity_cost": oc}

    # -- admission ---------------------------------------------------------
    def _admit(self, v, t):
        rec = {
            "session_id": v["session_id"], "vehicle_id": v["vehicle_id"],
            "cls": v["cls"], "arrival": v["arrival"], "dwell": v["dwell"],
            "dep": v["arrival"] + v["dwell"], "energy": float(v["energy"]),
            "accept_power": v.get("accept_power"), "origin": v.get("origin") or "",
            "in_cohort": self.W <= v["arrival"] < self.T,
            "outcome": None, "bay": None, "service": None,
            "charge_start": None, "rate": 0.0,
            "delivered_fixed": 0.0, "delivered_mobile": 0.0,
            "rejected": False, "moved": False, "opened": False,
            "slot": None, "bay_kind": None,
        }
        self.records.append(rec)
        self.by_sid[rec["session_id"]] = rec
        cls = rec["cls"]
        if cls == "E1":
            self.e1_past.append((rec["arrival"], float(rec["energy"])))
        if rec["in_cohort"]:
            if cls == "E1":
                self.agg["attempts_E1"] += 1
            elif cls == "E0":
                self.agg["attempts_E0"] += 1
            else:
                self.agg["attempts_I"] += 1

        if cls == "E1":
            slot = self._free_charge_slot()
            if slot is not None:
                self._place_charge(rec, slot, t)
            else:
                swapped = self._try_recall(t)
                if swapped is not None:
                    start = t + float(self.spec.open.move_minutes)
                    if start < rec["dep"]:
                        self._place_charge(rec, swapped, start)
                    else:
                        self._reject(rec)
                elif self.spec.rule == "fallback" and self._free_ordinary_slot() is not None:
                    self._place_ordinary(rec)
                    if self.mobile_on and rec["in_cohort"]:
                        self._queue_mobile(rec, t)
                else:
                    self._reject(rec)
        else:
            if self._free_ordinary_slot() is not None:
                self._place_ordinary(rec)
            else:
                opened = False
                if (self.spec.open.open_rule == "opportunity" and self.n > 0
                        and self._free_charge_slot() is not None):
                    if rec["in_cohort"]:
                        self.agg["open_attempts"] += 1
                    opened, diag = self._open_test(v, t)
                    if opened:
                        slot = self._free_charge_slot()
                        rec["opened"] = True
                        rec["bay"] = "charge"
                        rec["bay_kind"] = "charge"
                        rec["slot"] = slot
                        rec["open_diag"] = diag
                        self.charge_occ[slot] = rec
                        if rec["in_cohort"]:
                            self.agg["opened"] += 1
                        self._track_occupancy()
                        self._schedule_departure(rec)
                if not opened:
                    self._reject(rec)
        return rec

    def _place_charge(self, rec, slot, start):
        rec["bay"] = "charge"
        rec["bay_kind"] = "charge"
        rec["slot"] = slot
        rec["service"] = "fixed"
        rec["charge_start"] = start
        rec["rate"] = effective_power(self.stream, rec)
        self.charge_occ[slot] = rec
        if rec["in_cohort"]:
            self.agg["admitted_E1_charge"] += 1
            self.agg["admitted_E1"] += 1
        self._track_occupancy()
        self._schedule_departure(rec)

    def _place_ordinary(self, rec):
        slot = self._free_ordinary_slot()
        rec["bay"] = "ordinary"
        rec["bay_kind"] = "ordinary"
        rec["slot"] = slot
        rec["service"] = "mobile" if (rec["cls"] == "E1" and self.mobile_on) else "none"
        self.ordinary_occ[slot] = rec
        if rec["in_cohort"]:
            if rec["cls"] == "E1":
                self.agg["admitted_E1_ordinary"] += 1
                self.agg["admitted_E1"] += 1
            elif rec["cls"] == "E0":
                self.agg["admitted_E0"] += 1
            else:
                self.agg["admitted_I"] += 1
        self._track_occupancy()
        self._schedule_departure(rec)

    def _reject(self, rec):
        rec["outcome"] = "rejected"
        rec["rejected"] = True
        if not rec["in_cohort"]:
            return
        if rec["cls"] == "E1":
            self.agg["R_EP"] += 1
        elif rec["cls"] == "E0":
            self.agg["R_E0"] += 1
        else:
            self.agg["R_I"] += 1
        self.agg["rejections_total"] += 1

    def _schedule_departure(self, rec):
        heapq.heappush(self.veh_heap, (rec["dep"], _PRIO_DEP, self._next_seq(), rec))

    def _track_occupancy(self):
        if len(self.charge_occ) > self.agg["max_charge_occupied"]:
            self.agg["max_charge_occupied"] = len(self.charge_occ)
        if len(self.ordinary_occ) > self.agg["max_ordinary_occupied"]:
            self.agg["max_ordinary_occupied"] = len(self.ordinary_occ)

    def _try_recall(self, t):
        """Free one charging bay held by an opened non-E1 (declared recall rule)."""
        if self.spec.open.open_rule != "opportunity":
            return None
        free_ord = self._free_ordinary_slot()
        if free_ord is None:
            return None
        lead = float(self.spec.open.recall_lead_min)
        best = None
        for slot, occ in self.charge_occ.items():
            if not occ.get("opened"):
                continue
            remaining = occ["dep"] - t
            if 0 <= remaining <= lead and (best is None or remaining < best[0]):
                best = (remaining, slot, occ)
        if best is None:
            return None
        _, slot, occ = best
        del self.charge_occ[slot]
        rec = occ
        rec["bay"] = "ordinary"
        rec["bay_kind"] = "ordinary"
        rec["slot"] = free_ord
        rec["moved"] = True
        self.ordinary_occ[free_ord] = rec
        self.agg["moves"] += 1
        self.moves_log.append({"session_id": rec["session_id"], "time": t,
                               "from_slot": slot, "to_slot": free_ord,
                               "remaining_min": best[0]})
        return slot

    # -- mobile ------------------------------------------------------------
    def _queue_mobile(self, rec, t):
        job = {"job_id": "J%05d" % (len(self.mobile_jobs) + 1),
               "session_id": rec["session_id"], "arrival": t,
               "dep": rec["dep"], "remaining_kwh": float(rec["energy"]),
               "state": "pending", "created_at": t}
        self.mobile_jobs.append(job)
        self.by_sid[rec["session_id"]]["mobile_job_id"] = job["job_id"]

    def _job_feasible(self, dev, job, t):
        rule = self.spec.mobile
        rec = self.by_sid.get(job["session_id"]) or {}
        p_eff = mobile_effective_power(rule, rec)
        arrive = t + float(rule.travel_min)
        connect = arrive + float(rule.connect_min)
        available = job["dep"] - connect
        if available < float(rule.min_service_min):
            return None
        usable = max(0.0, (dev.soc - float(rule.soc_reserve_kwh)) * float(rule.discharge_efficiency))
        deliver = min(job["remaining_kwh"], p_eff * available / 60.0, usable)
        if deliver < float(rule.min_deliver_kwh):
            return None
        charge_min = deliver / p_eff * 60.0
        charge_end = connect + charge_min
        if charge_end > job["dep"] + 1e-9:
            return None
        return {"arrive": arrive, "connect": connect, "available_min": available,
                "deliver_kwh": deliver, "power_kw": p_eff,
                "charge_min": charge_min, "charge_end": charge_end}

    def _dispatch(self, t):
        if not self.mobile_on:
            return
        while True:
            idle = [d for d in self.devices if d.state == "idle"]
            pending = [j for j in self.mobile_jobs if j["state"] == "pending"]
            if not idle or not pending:
                break
            pending.sort(key=lambda j: (j["dep"], j["session_id"]))
            chosen = None
            for job in pending:
                if job["dep"] <= t:
                    job["state"] = "expired"
                    self.agg["mobile_expired_jobs"] += 1
                    self.agg["mobile_unserved_kwh"] += job["remaining_kwh"]
                    continue
                for dev in idle:
                    plan = self._job_feasible(dev, job, t)
                    if plan is not None:
                        chosen = (dev, job, plan)
                        break
                if chosen:
                    break
                # no device can serve this job now: expire it if time is exhausted
                if job["dep"] - (t + float(self.spec.mobile.travel_min)
                                 + float(self.spec.mobile.connect_min)) < float(self.spec.mobile.min_service_min):
                    job["state"] = "expired"
                    self.agg["mobile_expired_jobs"] += 1
                    self.agg["mobile_unserved_kwh"] += job["remaining_kwh"]
            if not chosen:
                break
            dev, job, plan = chosen
            self._assign(dev, job, plan, t)

    def _assign(self, dev, job, plan, t):
        rule = self.spec.mobile
        charge_min = plan["charge_min"]
        charge_end = plan["charge_end"]
        release = charge_end + float(rule.release_min)
        job["state"] = "assigned"
        job["delivered_kwh"] = job.get("delivered_kwh", 0.0) + plan["deliver_kwh"]
        job["remaining_kwh"] = max(0.0, job["remaining_kwh"] - plan["deliver_kwh"])
        dev.state = "busy"
        dev.job = job
        dev.stats["services"] += 1
        self.agg["mobile_services"] += 1
        # component minutes are clipped to the accounting horizon H; the visit may
        # end after H but it must not extend the window or the facility days.
        arrive = plan["arrive"]
        connect = plan["connect"]
        comps = (
            ("travel_min", t, arrive),
            ("connect_min", arrive, connect),
            ("charge_min", connect, charge_end),
            ("release_min", charge_end, release),
        )
        active = 0.0
        for name, a, b in comps:
            minutes = max(0.0, min(b, self.H) - a)
            dev.stats[name] += minutes
            self.agg["mobile_" + name] += minutes
            active += minutes
        dev.stats["active_min"] += active
        self.agg["mobile_active_min"] += active
        heapq.heappush(self.dev_heap, (charge_end, _PRIO_DEV, self._next_seq(),
                                       dev.idx, "charge_done"))
        heapq.heappush(self.dev_heap, (release, _PRIO_DEV, self._next_seq(), dev.idx, "release"))
        visit = {
            "device_id": dev.idx, "vehicle": job["session_id"], "job_id": job["job_id"],
            "t_assign": t, "t_arrive": arrive, "t_connect": connect,
            "t_charge_end": charge_end, "t_release": release,
            "delivered_kwh": round(plan["deliver_kwh"], 6),
            "power_kw": round(plan["power_kw"], 6),
            "charge_min": round(charge_min, 6),
            "available_min": round(plan["available_min"], 3),
            "accept_power_used": self.by_sid.get(job["session_id"], {}).get("accept_power"),
            "credited": False}
        dev.visit = visit
        self.mobile_timeline.append(visit)

    def _device_charge_done(self, dev_idx, t):
        """Credit the energy at the minute charging actually ends.

        Delivery happens in [t_connect, t_charge_end]; the device release can be
        later than H, but that must never erase a delivery made before H.
        """
        dev = self.devices[dev_idx]
        visit = dev.visit
        if visit is None or visit.get("credited"):
            return
        rule = self.spec.mobile
        delivered = float(visit["delivered_kwh"])
        drawn = delivered / float(rule.discharge_efficiency)
        dev.soc = max(0.0, dev.soc - drawn)
        dev.stats["delivered_kwh"] += delivered
        dev.stats["grid_kwh"] += drawn
        self.agg["D_mobile_kwh"] += delivered
        self.agg["mobile_grid_kwh"] += drawn
        self.agg["mobile_loss_kwh"] += drawn - delivered
        rec = self.by_sid.get(visit["vehicle"])
        if rec is not None:
            rec["delivered_mobile"] += delivered
        visit["credited"] = True
        visit["t_charge_end"] = t

    def _device_release(self, dev_idx, t):
        rule = self.spec.mobile
        dev = self.devices[dev_idx]
        job = dev.job
        visit = dev.visit
        if visit is not None and not visit.get("credited"):
            # safety: a delivery planned before H must be booked even if the
            # release event is the first device event after the charging window
            self._device_charge_done(dev_idx, float(visit.get("t_charge_end", t)))
        dev.visit = None
        if job is not None and job["remaining_kwh"] <= 1e-9:
            job["state"] = "done"
        elif job is not None:
            job["state"] = "pending"
        dev.job = None
        if dev.soc < float(rule.capacity_kwh) * float(rule.recharge_threshold):
            dev.state = "returning"
            # F8: the return leg is device active time as well and is accounted
            # only up to the horizon H (the physical schedule may cross H), the
            # same way _assign clips the outbound travel/connect/charge/release.
            turn = float(rule.travel_min)
            travel = min(turn, max(0.0, self.H - t))
            recharge_min = (float(rule.capacity_kwh) - dev.soc) / float(rule.recharge_kw) * 60.0
            dev.stats["travel_min"] += travel
            dev.stats["active_min"] += travel
            self.agg["mobile_travel_min"] += travel
            self.agg["mobile_active_min"] += travel
            heapq.heappush(self.dev_heap, (t + turn + recharge_min, _PRIO_DEV,
                                           self._next_seq(), dev.idx, "recharge_done"))
            self.mobile_timeline.append({
                "device_id": dev.idx, "vehicle": None, "job_id": None,
                "t_assign": t, "t_arrive": t + turn,
                "t_connect": t + turn + recharge_min, "t_release": t + turn + recharge_min,
                "delivered_kwh": 0.0, "available_min": 0.0, "kind": "recharge"})
            # F4: another idle device must be able to take the job that just went pending
            self._dispatch(t)
        else:
            dev.state = "idle"
            self._dispatch(t)

    def _device_recharge_done(self, dev_idx, t):
        dev = self.devices[dev_idx]
        dev.soc = float(self.spec.mobile.capacity_kwh)
        dev.state = "idle"
        dev.stats["recharges"] += 1
        self._dispatch(t)

    # -- main loop ---------------------------------------------------------
    def run(self):
        self.devices = [_Device(i, self.spec.mobile.initial_soc_kwh) for i in range(self.m)] if self.mobile_on else []
        self._place_initial()
        arrivals = sorted([v for v in self.stream.vehicles if v["arrival"] < self.T],
                          key=lambda v: (v["arrival"], v["session_id"]))
        ai = 0
        while True:
            next_arr = arrivals[ai]["arrival"] if ai < len(arrivals) else INF
            next_dep = self.veh_heap[0][0] if self.veh_heap else INF
            next_dev = self.dev_heap[0][0] if self.dev_heap else INF
            t = min(next_arr, next_dep, next_dev)
            if t == INF or t > self.H:
                break
            if next_dep <= t:
                _, _, _, rec = heapq.heappop(self.veh_heap)
                self._depart(rec)
                continue
            if next_dev <= t:
                _, _, _, dev_idx, kind = heapq.heappop(self.dev_heap)
                if kind == "release":
                    self._device_release(dev_idx, t)
                elif kind == "charge_done":
                    self._device_charge_done(dev_idx, t)
                else:
                    self._device_recharge_done(dev_idx, t)
                continue
            v = arrivals[ai]
            ai += 1
            self._arrive(v, t)
            nxt = arrivals[ai]["arrival"] if ai < len(arrivals) else INF
            if nxt != t:
                # all events of this minute are processed before dispatching (§3/§4)
                self._dispatch(t)
        self._finalize()
        return self._result()

    def _arrive(self, v, t):
        if v["arrival"] < self.W:
            # warm-up: shape the state only, never counted, no mobile jobs
            self._admit(v, t)
            return
        self._arrive_cohort(v, t)

    def _place_initial(self):
        charge_used, ordinary_used = set(), set()
        for idx, init in enumerate(self.stream.initial):
            release = init["release"]
            if release <= 0:
                continue
            kind = init["kind"]
            if kind == "charge":
                slot = next((i for i in range(self.n) if i not in charge_used), None)
                if slot is None:
                    raise EngineError("初始充电占用 %d 个超过固定充电位数 n=%d" % (idx + 1, self.n))
                charge_used.add(slot)
            else:
                slot = next((i for i in range(self.ordinary_cap) if i not in ordinary_used), None)
                if slot is None:
                    raise EngineError("初始普通占用超过普通位容量 %d" % self.ordinary_cap)
                ordinary_used.add(slot)
            rec = {"session_id": "init#%d" % idx, "vehicle_id": "init#%d" % idx,
                   "cls": "init", "arrival": 0, "dwell": release, "dep": release,
                   "energy": 0.0, "accept_power": None, "origin": "initial",
                   "in_cohort": False, "outcome": None, "bay": kind, "service": "none",
                   "charge_start": None, "rate": 0.0, "delivered_fixed": 0.0,
                   "delivered_mobile": 0.0, "rejected": False, "moved": False,
                   "opened": False, "slot": slot, "bay_kind": kind}
            self.records.append(rec)
            if kind == "charge":
                self.charge_occ[rec["slot"]] = rec
            else:
                self.ordinary_occ[rec["slot"]] = rec
            self._schedule_departure(rec)
        self._track_occupancy()

    def _arrive_cohort(self, v, t):
        self._admit(v, t)

    def _depart(self, rec):
        if rec.get("bay_kind") == "charge":
            self.charge_occ.pop(rec.get("slot"), None)
        elif rec.get("bay_kind") == "ordinary":
            self.ordinary_occ.pop(rec.get("slot"), None)
        rec["outcome"] = "departed"
        self._dispatch(rec["dep"]) if self.mobile_on else None
        delivered = _delivered(rec)
        rec["delivered_fixed"] = delivered
        if rec["in_cohort"] and rec["cls"] == "E1":
            self.agg["D_fixed_kwh"] += delivered
        elif not rec["in_cohort"] and rec["cls"] == "E1" and delivered > 0:
            self.agg["warmup_memo_delivered_kwh"] += _delivered_between(rec, self.W, min(rec["dep"], self.H))

    def _finalize(self):
        for dev in self.devices:
            visit = dev.visit
            if (visit is not None and not visit.get("credited")
                    and float(visit.get("t_charge_end", INF)) <= self.H + 1e-9):
                self._device_charge_done(dev.idx, float(visit["t_charge_end"]))
        for rec in self.records:
            if rec["outcome"] is not None:
                continue
            # still present at H: cohort members cannot be here by the H contract
            if rec.get("bay_kind") == "charge":
                rec["delivered_fixed"] = _delivered(rec)
            rec["outcome"] = "present_at_H"
            if not rec["in_cohort"] and rec["cls"] == "E1":
                self.agg["warmup_memo_delivered_kwh"] += _delivered_between(rec, self.W, min(rec["dep"], self.H))
        self._aggregate_cohort()

    def _aggregate_cohort(self):
        agg = self.agg
        for rec in self.records:
            if not rec["in_cohort"] or rec["cls"] != "E1":
                continue
            req = float(rec["energy"])
            got = rec["delivered_fixed"] + rec["delivered_mobile"]
            agg["requested_E1_kwh"] += req
            agg["S_kwh"] += max(0.0, req - got)
            agg["cohort_n"] += 1
        for job in self.mobile_jobs:
            if job["state"] in ("pending", "assigned"):
                self.agg["mobile_unserved_kwh"] += job["remaining_kwh"]
                job["state"] = "unserved_at_H"
        agg["cohort_n"] = sum(1 for r in self.records if r["in_cohort"])
        agg["delivered_E1_kwh"] = agg["D_fixed_kwh"] + agg["D_mobile_kwh"]
        agg["D_mobile_by_H_kwh"] = agg["D_mobile_kwh"]
        agg["accept_power_missing_vehicles"] = sum(
            1 for r in self.records if r["in_cohort"] and r.get("accept_power") is None
            and r["cls"] == "E1")
        agg["accept_power_assumption_kw"] = getattr(
            self.spec.mobile, "assumed_accept_power_kw", None)
        agg["accept_power_assumption_applied"] = sum(
            1 for v in self.mobile_timeline
            if v.get("kind") != "recharge" and v.get("accept_power_used") is None)
        agg["mobile_charge_min_at_H"] = sum(
            float(v.get("charge_min", 0.0)) for v in self.mobile_timeline
            if v.get("kind") != "recharge"
            and float(v.get("t_charge_end", INF)) <= self.H + 1e-9)

    def _result(self):
        agg = dict(self.agg)
        agg.update({"n": self.n, "m": self.m, "days": self.days,
                    "W": self.W, "T": self.T, "H": self.H, "N": self.N,
                    "station_kw": self.stream.station_kw})
        checks = self._checks(agg)
        return {
            "scheme": self.spec.scheme, "rule": self.spec.rule,
            "config": {"n": self.n, "m": self.m},
            "features": agg,
            "vehicles": self._vehicle_rows(),
            "mobile_timeline": self.mobile_timeline,
            "mobile_jobs": [dict(j) for j in self.mobile_jobs],
            "moves": self.moves_log,
            "checks": checks,
            "versions": {"math": MATH_VERSION, "engine": ENGINE_VERSION, "schema": SCHEMA},
        }

    def _vehicle_rows(self):
        rows = []
        for rec in self.records:
            if not rec["in_cohort"]:
                continue
            requested = float(rec["energy"]) if rec["cls"] == "E1" else 0.0
            got = rec["delivered_fixed"] + rec["delivered_mobile"]
            rows.append({
                "session_id": rec["session_id"], "vehicle_id": rec["vehicle_id"],
                "cls": rec["cls"], "arrival": rec["arrival"], "dwell": rec["dwell"],
                "departure": rec["dep"], "bay": rec["bay"], "service": rec["service"],
                "rejected": rec["rejected"], "moved": rec["moved"], "opened": rec["opened"],
                "requested_kwh": round(requested, 6),
                "delivered_kwh": round(got, 6),
                "unmet_kwh": round(max(0.0, requested - got), 6),
            })
        return rows

    def _checks(self, agg):
        checks = []

        def add(name, ok, detail=""):
            checks.append({"name": name, "ok": bool(ok), "detail": detail})

        bad = [r["session_id"] for r in self.records
               if r["in_cohort"] and r["cls"] == "E1"
               and abs((r["delivered_fixed"] + r["delivered_mobile"])
                       - max(0.0, min(float(r["energy"]),
                                      r["delivered_fixed"] + r["delivered_mobile"]))) > 1e-6]
        add("demand_equals_delivered_plus_gap", not bad, ",".join(bad[:5]))
        add("no_delivery_after_departure",
            all((r["charge_start"] is None) or (r["charge_start"] < r["dep"])
                for r in self.records))
        add("charge_bays_not_oversold",
            agg["max_charge_occupied"] <= self.n,
            "max=%d n=%d init=%d" % (agg["max_charge_occupied"], self.n, self.init_charge))
        add("ordinary_bays_not_oversold",
            agg["max_ordinary_occupied"] <= self.ordinary_cap,
            "max=%d cap=%d init=%d" % (agg["max_ordinary_occupied"], self.ordinary_cap,
                                       self.init_ordinary))
        overlap = False
        for i in range(self.m):
            spans = sorted((e["t_assign"], e["t_release"]) for e in self.mobile_timeline
                           if e["device_id"] == i and e.get("kind") != "recharge")
            for a, b in zip(spans, spans[1:]):
                if b[0] < a[1] - 1e-9:
                    overlap = True
        add("devices_not_double_booked", not overlap)
        eta = float(self.spec.mobile.discharge_efficiency) if self.m > 0 else 1.0
        add("mobile_energy_conservation",
            abs(agg["D_mobile_kwh"] - agg["mobile_grid_kwh"] * eta) <= 1e-6,
            "delivered=%.6f grid=%.6f eta=%.4f" % (agg["D_mobile_kwh"],
                                                   agg["mobile_grid_kwh"], eta))
        visits = [v for v in self.mobile_timeline if v.get("kind") != "recharge"]
        after_dep = [v["vehicle"] for v in visits
                     if v.get("t_charge_end") is not None
                     and v["t_charge_end"] > float(
                         (self.by_sid.get(v["vehicle"]) or {}).get("dep", INF)) + 1e-9]
        add("mobile_delivery_not_after_departure", not after_dep, ",".join(after_dep[:5]))
        credited = [v for v in visits if v.get("credited")]
        by_h = [v for v in visits if float(v.get("t_charge_end", INF)) <= self.H + 1e-9]
        add("mobile_delivery_by_H_is_credited",
            len(credited) == len(by_h) and
            abs(sum(float(v["delivered_kwh"]) for v in by_h) - agg["D_mobile_kwh"]) <= 1e-6,
            "visits=%d credited=%d by_H=%d ledger=%.6f" % (
                len(visits), len(credited), len(by_h), agg["D_mobile_kwh"]))
        timeline_kwh = sum(float(v["delivered_kwh"]) for v in credited)
        add("mobile_timeline_matches_ledger",
            abs(timeline_kwh - agg["D_mobile_kwh"]) <= 1e-6,
            "timeline=%.6f ledger=%.6f" % (timeline_kwh, agg["D_mobile_kwh"]))
        vehicle_kwh = sum(float(r["delivered_mobile"]) for r in self.records)
        add("mobile_vehicle_ledger_matches_agg",
            abs(vehicle_kwh - agg["D_mobile_kwh"]) <= 1e-6,
            "vehicles=%.6f agg=%.6f" % (vehicle_kwh, agg["D_mobile_kwh"]))
        power_bad = [v["vehicle"] for v in credited
                     if float(v["delivered_kwh"])
                     > float(v["power_kw"]) * max(0.0, float(v["t_charge_end"]) - float(v["t_connect"]))
                     / 60.0 + 1e-6]
        add("mobile_power_cap_respected", not power_bad, ",".join(power_bad[:5]))
        accept_bad = []
        for v in credited:
            rec = self.by_sid.get(v["vehicle"]) or {}
            p_max = float(self.spec.mobile.output_kw)
            if rec.get("accept_power") is not None:
                p_max = min(p_max, float(rec["accept_power"]))
            elif getattr(self.spec.mobile, "assumed_accept_power_kw", None) is not None:
                p_max = min(p_max, float(self.spec.mobile.assumed_accept_power_kw))
            if float(v["power_kw"]) > p_max + 1e-9:
                accept_bad.append(v["vehicle"])
        add("mobile_accept_power_respected", not accept_bad, ",".join(accept_bad[:5]))
        ordered = all(
            float(v["t_assign"]) <= float(v["t_arrive"]) <= float(v["t_connect"])
            <= float(v["t_charge_end"]) <= float(v["t_release"])
            for v in visits)
        add("mobile_timeline_ordered", ordered)
        add("mobile_charge_inside_horizon",
            all(float(v["t_charge_end"]) <= self.H + 1e-9 for v in visits))
        add("mobile_active_minutes_within_window",
            all(float(v.get("t_assign", 0)) >= 0
                and float(v.get("t_release", 0)) - float(v.get("t_assign", 0))
                >= -1e-9 for v in visits))
        add("fleet_size_respected", self.m == len(self.devices))
        add("all_cohort_vehicles_have_outcome",
            all(r["outcome"] in ("rejected", "departed") for r in self.records if r["in_cohort"]))
        return checks


def run_scheme(stream, spec, config, params=None):
    """Replay one configuration of one scheme on a frozen stream."""
    if not stream.validate():
        raise EngineError("stream 校验失败")
    if not spec.validate():
        raise EngineError("scheme 校验失败")
    cfg = validate_config(stream, spec.scheme, config)
    if spec.scheme in ("S2", "S3") and spec.open.open_rule == "opportunity":
        if params is None:
            raise EngineError("S2/S3 开放规则需要成本参数（增量机会成本阈值）")
        params.validate()
        missing = [k for k in ("b_I", "b_E0", "b_E1", "c_E") if getattr(params, k) is None]
        if missing:
            raise EngineError("S2/S3 开放规则缺少成本参数: %s" % ",".join(missing))
    run = _Run(stream, spec, cfg)
    run.params = params
    return run.run()