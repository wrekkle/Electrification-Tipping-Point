#!/usr/bin/env python3
"""Generate COVERAGE.md and a machine summary from sites.jsonl + quality.json."""
import csv, glob, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sites = [json.loads(l) for l in open(os.path.join(ROOT, "data", "charger_sites", "nyc_v1", "sites.jsonl"), encoding="utf-8")]
rows, tot_ev, tot_min, n_sess = [], 0, 0.0, 0
for s in sorted(sites, key=lambda z: z["site_id"]):
    q = json.load(open(os.path.join(ROOT, "data", "demand", s["site_id"], "quality.json"), encoding="utf-8"))
    tot_ev += q["event_count"]
    b2 = list(csv.DictReader(open(os.path.join(ROOT, "data", "demand", s["site_id"], "sessions_b2.csv"), encoding="utf-8")))
    for r in b2:
        if r["connected_minutes"]:
            tot_min += float(r["connected_minutes"]); n_sess += 1
    rows.append({
        "site_id": s["site_id"], "units": s["charger_units"], "points": s["service_points"],
        "spaces": s["total_spaces"], "events": q["event_count"], "days": q["days_with_events"],
        "span": q["days_in_span"], "missing": q["missing_days_count"],
        "m": q.get("certificate_m", q["days_with_events"]),
        "hourcov": q["hourly_coverage_mean_pct"], "full24": q["days_full_24h"],
        "full24pct": q["days_full_24h_pct"], "peak": q["peak_overlap_max"],
        "cert15": q["certified_capacity_by_rho"].get("0.15"), "cert10": q["certified_capacity_by_rho"].get("0.1"),
        "cert20": q["certified_capacity_by_rho"].get("0.2"),
        "rho_min": q["min_certifiable_rho"], "elig": s["analysis_eligible"],
    })

lines = ["# COVERAGE — NYC municipal garages, v1 (fetched 2026-11-02)", "",
         "Window: up to 365 days per site (the most recent available window; some source records are shorter).",
         "Capacity convention: charger_units = distinct charge_box_id; service_points = sum of max connector_id per box.",
         "W_d convention (P0-D, default): calendar-day peak; a session crossing midnight is clipped into both days; m = span, so zero-event days enter as W_d = 0.",
         "Sensitivity convention A (arrival-day peak, event days only): columns cert*A are written to data/demand/peak_definition_sensitivity.json.",
         "total_spaces (A2) was not obtained for any site (blocked source, see report section 2).", "",
         "| site_id | charger_units | service_points | total_spaces | events | event days | span = m | missing | hourly cov % | full-24h days | peak W | cert n (rho=.15) | cert n (rho=.10) | cert n (rho=.20) | rho_min | eligible |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    lines.append("| {site_id} | {units} | {points} | {spaces} | {events} | {days} | {m} | {missing} | {hourcov} | {full24} ({full24pct}%) | {peak} | {cert15} | {cert10} | {cert20} | {rho_min} | {elig} |".format(**r))
lines += ["", "## Totals", "",
          f"- sites: {len(rows)}; events: {tot_ev}",
          f"- eligible at rho=0.15 (>=67 span days, one-sided Massart): {sum(1 for r in rows if r['m'] >= 67)}",
          f"- eligible at rho=0.10 (>=150 span days): {sum(1 for r in rows if r['m'] >= 150)}",
          "- eligible = sample-size feasibility only; a certificate can still fail if observed exceedances are high.",
          "- certificate bound: one-sided Massart d+=sqrt(ln(1/alpha)/(2m)) (v7 Prop.10); alpha=0.05",
          "- rho_min = d+ at the site's m (smallest rho certifiable with zero exceedances).",
          f"- weighted mean dwell: {round(tot_min/n_sess/60, 2)} h over {n_sess} sessions",
          "", "## Hourly coverage definition", "",
          "For each observed date, the share of its 24 clock hours overlapped by at least one session interval,",
          "averaged over dates. Garages that close overnight cannot reach 100%; full-24h days are reported separately.", ""]
open(os.path.join(ROOT, "data", "charger_sites", "nyc_v1", "COVERAGE.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
json.dump({"rows": rows, "events": tot_ev, "mean_dwell_h": round(tot_min/n_sess/60, 2), "n_sess": n_sess},
          open(os.path.join(ROOT, "tmp", "raw", "coverage_summary.json"), "w"), indent=1)
print("\n".join(lines))
