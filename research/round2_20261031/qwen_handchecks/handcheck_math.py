"""Independent hand-check math module (pure stdlib).

These functions intentionally do NOT import anything from apps/; they are
re-derivable closed forms used to cross-check the optimizer's numbers.
"""

import math


def erlang_b_closed_form(load, servers):
    """Erlang B blocking probability via the closed-form sum.

    C(a, c) = (a^c / c!) / sum_{n=0..c} a^n / n!
    No recursion is used; each term is computed directly with factorials.
    """
    if servers < 1:
        raise ValueError("servers must be >= 1")
    denom = sum(load ** n / math.factorial(n) for n in range(servers + 1))
    return (load ** servers) / math.factorial(servers) / denom


def stationary_residual_mean(dwell_values, probs=None):
    """Length-biased stationary residual lifetime E[D^2] / (2 E[D]).

    Accepts either a dict {dwell: probability} as dwell_values, or two
    parallel sequences dwell_values/probs describing the dwell-time D.
    """
    if isinstance(dwell_values, dict):
        # dict form: dwell value -> probability; ignore the unused probs arg
        items = list(dwell_values.items())
    else:
        items = list(zip(dwell_values, probs))
    ed = sum(p * d for d, p in items)
    ed2 = sum(p * d * d for d, p in items)
    return ed2 / (2.0 * ed)


def charge_gap(demand_kwh, power_kw, dwell_min):
    """(delivered_kwh, gap_kwh): delivered = min(demand, power * dwell / 60)."""
    capacity = power_kw * dwell_min / 60.0
    delivered = min(demand_kwh, capacity)
    return delivered, demand_kwh - delivered


def facility_cost_per_window(k, capex, life_years, maintenance_per_bay_day, window_min):
    """Per-window cost of k bays: amortized capex + pro-rated daily maintenance.

    Capex is amortized over the equipment lifetime in days (life_years*365),
    then scaled to the window fraction; maintenance is per bay per day, also
    scaled by window_min/1440:

    cost = k * (capex / (life_years*365) + maintenance_per_bay_day) * window_min / 1440
    """
    daily_capex = capex / (life_years * 365.0)
    daily_maint = maintenance_per_bay_day
    return k * (daily_capex + daily_maint) * window_min / 1440.0


def service_status(baseline_unmet, curve, hard_limit=40):
    """Classify a k-sweep result.

    curve maps k -> unmet demand. Returns (status, k):
      - baseline_unmet == 0            -> ("no_demand", 0)
      - k=0 missing from curve         -> ("missing_data", None)
      - smallest k with unmet <= 0     -> ("achieved", k)
      - no such k and max(curve) >= hard_limit
                                        -> ("infeasible_upper_bound", None)
      - otherwise (budget exhausted)   -> ("budget_exhausted", None)
    """
    if baseline_unmet == 0:
        return ("no_demand", 0)
    if 0 not in curve:
        return ("missing_data", None)
    achieved = [k for k, u in curve.items() if u <= 0]
    if achieved:
        return ("achieved", min(achieved))
    if max(curve.keys()) >= hard_limit:
        return ("infeasible_upper_bound", None)
    return ("budget_exhausted", None)
