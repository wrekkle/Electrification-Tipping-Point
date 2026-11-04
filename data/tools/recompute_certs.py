#!/usr/bin/env python3
"""Recompute certificate fields with the v7 one-sided Massart radius.

Why: build_panel.py was written against the v6 two-sided DKW radius
d = sqrt(ln(2/alpha)/(2m)).  v7 Prop.10 uses the one-sided radius
d^+ = sqrt(ln(1/alpha)/(2m)), which is 1.1097x tighter at alpha=.05.
This script rewrites only *derived* fields (certificates, radii, sample-size
thresholds, identification status); raw counts are untouched.

Also recomputes the two-sided reference certificate (audit only) and the
inverse-optimality form under both capacity conventions.

Capacity convention: service_points = sum of max connector_id per box is the
physical simultaneous capacity.  W_d can exceed charger_units (nyc-sge:
max W=5 > units=4), so the box-count convention is not a valid n_obs; it is
reported only as a counterexample.

W_d convention (P0): default is D = calendar-day peak, sessions clipped into
every calendar day they overlap, m = span with zero-event days included as 0.
The A variant (arrival-day peak, event days only) is recomputed here as the
sensitivity convention and stored under *_arrival_day keys.

Run: python data/tools/recompute_certs.py
"""
import json, math, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALPHA = 0.05
RHO_STD = (0.10, 0.15, 0.20)


def radius_one_sided(m):
    return math.sqrt(math.log(1.0 / ALPHA) / (2 * m))


def radius_two_sided(m):
    return math.sqrt(math.log(2.0 / ALPHA) / (2 * m))


def days_needed(rho):
    return math.ceil(math.log(1.0 / ALPHA) / (2 * rho * rho))


def tail(vals, n):
    return sum(1 for w in vals if w > n) / len(vals)


def certify(vals, d, rho):
    """Smallest n with min(1, T(n)+d) <= rho; None if no capacity certifies."""
    hi = max(vals) if vals else 0
    for n in range(0, hi + 1):
        if min(1.0, tail(vals, n) + d) <= rho + 1e-12:
            return n
    return None


def ident(vals, n_obs):
    """Prop.2/2a form, with the M4 censoring case split made explicit."""
    if n_obs <= 0:
        return {"n_obs": n_obs, "T_at_n_obs_minus_1": None, "T_at_n_obs": None,
                "form": "undefined"}
    t_lo = tail(vals, n_obs - 1)
    t_hi = tail(vals, n_obs)
    if t_lo == 0:
        form = "empty"
    elif t_hi == 0:
        form = "one_sided"
    else:
        form = "two_sided"
    return {
        "n_obs": n_obs,
        "T_at_n_obs_minus_1": round(t_lo, 6),
        "T_at_n_obs": round(t_hi, 6),
        "form": form,
        "identified_c_over_a_lower": (round(1.0 / t_lo, 6) if t_lo > 0 else None),
        "identified_c_over_a_upper": (round(1.0 / t_hi, 6) if t_hi > 0 else None),
    }


def main():
    sp = os.path.join(ROOT, "data", "charger_sites", "nyc_v1", "sites.jsonl")
    sites = [json.loads(l) for l in open(sp, encoding="utf-8") if l.strip()]
    thr15, thr10 = days_needed(0.15), days_needed(0.10)
    out = []
    for s in sites:
        sid = s["site_id"]
        qp = os.path.join(ROOT, "data", "demand", sid, "quality.json")
        q = json.load(open(qp, encoding="utf-8"))
        pv = {k: int(v) for k, v in q["peak_overlap_values"].items()}
        m = len(pv)
        vals = list(pv.values())
        d1, d2 = radius_one_sided(m), radius_two_sided(m)

        # sensitivity convention A: arrival-day peak over event days only
        pv_a = {k: int(v) for k, v in q.get("peak_overlap_values_arrival_day", pv).items()}
        m_a = len(pv_a)
        vals_a = list(pv_a.values())
        d1_a = radius_one_sided(m_a)

        cert = {str(r): certify(vals, d1, r) for r in RHO_STD}
        cert_two = {str(r): certify(vals, d2, r) for r in RHO_STD}
        cert_a = {str(r): certify(vals_a, d1_a, r) for r in RHO_STD}

        nobs = s["service_points"]
        units = s["charger_units"]
        ident_sp = ident(vals, nobs)
        ident_sp["n_obs_convention"] = "service_points"
        ident_sp["censoring_note"] = (
            "T(n_obs)=0 is structural: served occupancy cannot exceed installed capacity")
        ident_a = ident(vals_a, nobs)
        ident_a["n_obs_convention"] = "service_points"
        ident_u = ident(vals, units)
        ident_u["n_obs_convention"] = "charger_units"
        ident_u["note"] = (
            "box count is not the physical capacity; W can exceed it (nyc-sge: max W=5 > units=4), "
            "so a two_sided label here is an artefact, not evidence against M4")
        ident_sp["with_charger_units"] = ident_u

        q["dkw_radius_dm"] = round(d1, 6)
        q["certificate_bound"] = "one-sided Massart d+=sqrt(ln(1/alpha)/(2m)) (v7 Prop.10); alpha=0.05"
        q["two_sided_dkw_radius_reference"] = round(d2, 6)
        q["certified_capacity_by_rho"] = cert
        q["certified_capacity_by_rho_two_sided_reference"] = cert_two
        q["min_certifiable_rho"] = round(d1, 6)
        q["days_needed"] = {f"rho_{r:.2f}": days_needed(r) for r in (0.05, 0.10, 0.15, 0.20)}
        q["identification"] = ident_sp
        q["certified_capacity_by_rho_arrival_day"] = cert_a
        q["dkw_radius_dm_arrival_day"] = round(d1_a, 6)
        q["min_certifiable_rho_arrival_day"] = round(d1_a, 6)
        q["identification_arrival_day"] = ident_a
        q["peak_definition"] = (
            "W_d = calendar-day peak overlap: each session is clipped into every calendar day "
            "it overlaps, so a session crossing midnight counts on both days")
        q["peak_definition_default"] = "D (calendar-day peak; m = span, zero-event days included as W_d = 0)"
        q["peak_definition_sensitivity"] = (
            "A = arrival-day peak over event days only; certified_capacity_by_rho_arrival_day "
            "and identification_arrival_day report it, it is not the default")
        q["certificate_sample"] = (
            "m = days in span, zero-event days included (calendar-day convention)")
        json.dump(q, open(qp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

        s["analysis_eligible"] = m >= thr15
        s["eligibility_reason"] = (
            f"{m} days with events: rho=0.15 and rho=0.10 feasible" if m >= thr10
            else f"{m} days with events: rho=0.15 feasible" if m >= thr15
            else f"{m} days with events: below the {thr15}-day minimum for rho=0.15")
        out.append(s)
        print(f"{sid:9s} m={m:3d} d+={d1:.4f} cert(.10)={cert['0.1']} cert(.15)={cert['0.15']} "
              f"ident={ident_sp['form']:9s} units={ident_u['form']:9s} "
              f"| A: m={m_a:3d} cert(.10)={cert_a['0.1']} cert(.15)={cert_a['0.15']} "
              f"ident={ident_a['form']:9s}")

    with open(sp, "w", encoding="utf-8") as f:
        for s in out:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print("thresholds: rho=.15 ->", thr15, "days; rho=.10 ->", thr10, "days")


if __name__ == "__main__":
    main()
