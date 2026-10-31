# -*- coding: utf-8 -*-
"""Admission rules pi_S / pi_F / pi_theta and the demand-class compatibility
matrix required by the v2 draft (Table 9 placeholder).

Demand classes: ICEV, parking-only EV, charging EV.
Berth types: ordinary (no charger), charging (charger / overhead device reach).

pi_S      strict separation: ICEV and parking-only EV may use ordinary berths
          only; charging EVs may use charging berths only.
pi_F      full flexibility: ICEV and parking-only EV may use any free
          compatible berth; charging EVs still need a charging berth.
pi_theta  protected threshold: the first round(theta*m) charging berths are
          reserved for charging EVs; the remaining charging berths are open to
          ICEV / parking-only EVs.
"""
from __future__ import annotations

CLASSES = ("icev", "ev_park", "ev_charge")
BERTH_TYPES = ("ordinary", "charging")
RULES = ("pi_S", "pi_F", "pi_theta")

ADMITTED = "admitted"
CONDITIONAL = "conditional"
RESERVED = "reserved"
NOT_ADMITTED = "not_admitted"


def reserved_berths(m, theta):
    """Number of charging berths protected under pi_theta."""
    m = int(m)
    theta = float(theta)
    if not (0.0 <= theta <= 1.0):
        raise ValueError("theta must be in [0,1]; got %r" % theta)
    return int(round(theta * m))


def is_admissible(rule, demand_class, berth_type, is_open_charging=True):
    """Single-point compatibility check used by the event simulator."""
    if demand_class not in CLASSES:
        raise ValueError("unknown demand class %r" % demand_class)
    if berth_type not in BERTH_TYPES:
        raise ValueError("unknown berth type %r" % berth_type)
    if rule not in RULES:
        raise ValueError("unknown rule %r" % rule)
    if demand_class == "ev_charge":
        return berth_type == "charging"
    if rule == "pi_S":
        return berth_type == "ordinary"
    if rule == "pi_F":
        return True
    # pi_theta: non-charging vehicles may only use open charging berths
    if berth_type == "ordinary":
        return True
    return bool(is_open_charging)


def compatibility_matrix(theta=0.4):
    """Exhaustive (rule, class, berth) matrix as plain rows (for CSV/tests)."""
    rows = []
    for rule in RULES:
        for demand_class in CLASSES:
            for berth_type in BERTH_TYPES:
                if rule == "pi_theta" and berth_type == "charging":
                    if demand_class == "ev_charge":
                        state = ADMITTED
                        cond = "reserved berths always; open berths if free"
                    else:
                        state = CONDITIONAL
                        cond = "only the %.0f%% open charging berths, never the reserved ones" % (
                            100.0 * (1.0 - float(theta)))
                else:
                    admitted = is_admissible(rule, demand_class, berth_type)
                    state = ADMITTED if admitted else NOT_ADMITTED
                    cond = ""
                rows.append({
                    "rule": rule,
                    "demand_class": demand_class,
                    "berth_type": berth_type,
                    "state": state,
                    "condition": cond,
                })
    return rows


def matrix_lookup(rows):
    return {(r["rule"], r["demand_class"], r["berth_type"]): r["state"] for r in rows}
