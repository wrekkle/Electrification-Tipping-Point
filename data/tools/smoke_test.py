#!/usr/bin/env python3
"""Smoke test: prove the delivered panel is directly consumable by the v7 math layer.

Uses the manuscript definitions (research/charger_sizing_v7_20261102):
  n_opt(c) = min({n<N : c*T(n) <= a} U {N}),  T(n)=Pr(D>n)
  I(n_obs) = (a/T(n_obs-1), a/T(n_obs)]
  Prop.10: p_n = mean(W_d>n), d_m = sqrt(log(1/alpha)/(2m))  [one-sided, v7], U_m(n)=min(1,p_n+d_m)

D is taken as the daily peak overlap W_d (sampling unit = day, as in Prop.10),
under the P0 default convention D: calendar-day peak, sessions clipped into both
days when they cross midnight, and m = span (zero-event days enter as W_d = 0).
Capital cost a is NOT yet sourced (report section 2), so the n_opt ladder is
reported in the scale-free ratio c/a.
"""
import json, math, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALPHA = 0.05
SITES = ["nyc-csq", "nyc-qbo", "nyc-des", "nyc-jon"]

def load(sid):
    q = json.load(open(os.path.join(ROOT, "data", "demand", sid, "quality.json"), encoding="utf-8"))
    return q, list(q["peak_overlap_values"].values())

def ladder(peaks, ratios):
    m = len(peaks); out = []
    for r in ratios:
        thr = 1.0 / r
        for n in range(0, max(peaks) + 200):
            t = sum(1 for w in peaks if w > n) / m
            if t <= thr:
                out.append((r, n)); break
    return out

def certified(peaks, rho):
    m = len(peaks); dm = math.sqrt(math.log(1 / ALPHA) / (2 * m))
    for n in range(0, max(peaks) + 200):
        phat = sum(1 for w in peaks if w > n) / m
        if min(1.0, phat + dm) <= rho: return n, dm
    return None, dm

lines = ["# Smoke test: panel -> v7 math layer", "", "类型: 研究报告", "状态: 生效", "负责人: tho25", "日期: 2026-11-02", "用途: 数据面板能被 v7 数学层直接消费的实跑证据", "",
         "Formulas: n_opt(c)=min({n<N: c*T(n)<=a} U {N}); I(n_obs)=(a/T(n_obs-1), a/T(n_obs)];",
         "U_m(n)=min{1, p_hat_n + d_m}; d_m=sqrt(ln(1/alpha)/(2m)) [one-sided]; alpha=0.05.", "",
         "D := daily peak overlap W_d (day is the sampling unit, as in Prop. 10).",
         "Convention P0-D (default): W_d is the calendar-day peak; a session crossing midnight is clipped into both days, and m = span with zero-event days entering as W_d = 0.",
         "Sensitivity convention A (arrival-day peak, event days only): see data/demand/peak_definition_sensitivity.json.", ""]
sites = [json.loads(l) for l in open(os.path.join(ROOT, "data", "charger_sites", "nyc_v1", "sites.jsonl"), encoding="utf-8")]
for sid in SITES:
    try:
        q, peaks = load(sid)
    except FileNotFoundError:
        lines += ["## " + sid + " -- SKIPPED: no quality.json"]; continue
    m = len(peaks)
    if m < 67:
        lines += ["## " + sid + " -- SKIPPED: " + str(m) + " days < 67 needed for rho=0.15"]; continue
    rec = next((s for s in sites if s["site_id"] == sid), None)
    n_obs = rec["service_points"] if rec else None
    lines += ["## " + sid + "  (m=" + str(m) + " days, max W=" + str(max(peaks)) + ", service_points n_obs=" + str(n_obs) + ")", "",
              "| c/a | n_opt(c/a) | T(n_opt) | T(n_opt-1) |", "|---|---|---|---|"]
    for r, n in ladder(peaks, [10, 20, 50, 100, 200, 500]):
        t_n = sum(1 for w in peaks if w > n) / m
        t_n1 = sum(1 for w in peaks if w > n - 1) / m if n > 0 else 1.0
        lines.append("| " + str(r) + " | " + str(n) + " | " + format(t_n, ".4f") + " | " + format(t_n1, ".4f") + " |")
    lines.append("")
    if n_obs:
        tlo = sum(1 for w in peaks if w > n_obs - 1) / m
        thi = sum(1 for w in peaks if w > n_obs) / m
        if tlo == 0:
            lines.append("- identification set for n_obs=" + str(n_obs) + ": EMPTY. No day has W>" + str(n_obs - 1)
                         + ", so n_obs is never the smallest optimizer for any c>=0: installed capacity exceeds every observed daily peak.")
        else:
            lo = 1.0 / tlo
            if thi > 0:
                lines.append("- identification set for n_obs=" + str(n_obs) + " in c/a units: ("
                             + format(lo, ".3f") + ", " + format(1.0 / thi, ".3f") + "]")
            else:
                lines.append("- identification set for n_obs=" + str(n_obs) + " in c/a units: ("
                             + format(lo, ".3f") + ", +inf)")
    for rho in (0.15, 0.10):
        n, dm = certified(peaks, rho)
        lines.append("- rho=" + str(rho) + ": certified capacity n=" + str(n) + ", d_m=" + format(dm, ".4f") + ", days needed=" + str(math.ceil(math.log(1/ALPHA)/(2*rho*rho))))
    lines.append("")

out = os.path.join(ROOT, "docs", "reports", "smoke_test_nyc_v1.md")
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("\n".join(lines))