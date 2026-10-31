"""Piecewise-constant Poisson arrivals with separate arrival/type/service streams."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import random


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


def intensity(c, minute):
    rate, share = c.arrival_rate_hour, c.ev_share
    hour = (c.start_hour + minute / 60) % 24
    fraction = minute / (c.duration_hours * 60)
    if c.scenario == "peaks" and (7 <= hour < 10 or 17 <= hour < 20):
        rate *= c.peak_multiplier
    elif c.scenario == "burst" and .35 <= fraction < .5:
        rate *= c.burst_multiplier
    elif c.scenario == "drift" and fraction >= c.drift_at_fraction:
        rate *= c.drift_rate_multiplier
        share = c.drift_ev_share
    return rate / 60, share


def generate(c):
    clock = random.Random(c.seed + 101)
    types = random.Random(c.seed + 202)
    services = random.Random(c.seed + 303)
    end, result = c.duration_hours * 60, []
    # One-minute bins: the documented DGP is constant within each bin.
    for minute in range(math.ceil(end)):
        rate, share = intensity(c, minute)
        if rate <= 0:
            continue
        t, boundary = float(minute), min(minute + 1.0, end)
        while True:
            t += clock.expovariate(rate)
            if t >= boundary:
                break
            ev = types.random() < share
            need = (types.random() < c.charge_probability) if ev else False
            mean = c.ev_dwell_min if ev else c.ice_dwell_min
            sigma = math.sqrt(math.log1p(c.dwell_cv**2))
            dwell = services.lognormvariate(math.log(mean) - sigma**2 / 2, sigma) if sigma else mean
            # Bounded support prevents pathological generated service times.
            dwell = min(max(dwell, .1), 7 * 1440)
            energy = min(services.gammavariate(4, c.energy_mean_kwh / 4), 500) if need and c.energy_mean_kwh > 0 else 0.0
            result.append(Arrival(len(result), t, ev, need, dwell, energy))
            if len(result) > 40000:
                raise ValueError("实际到达超过40000辆硬上限，本次运行已拒绝，请降低规模")
    return tuple(result)


def stream_hash(arrivals):
    raw = json.dumps([a.to_dict() for a in arrivals], sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
