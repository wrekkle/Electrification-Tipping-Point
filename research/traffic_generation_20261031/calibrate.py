# -*- coding: utf-8 -*-
"""Calibrate the reproducible traffic generator from the Taipei 372-site 5-min panel.

Read-only, streamed inputs:
  research/collection/taipei_372_polling_20261030/data/2026-10-30|31/parking_slots.jsonl
  research/collection/taipei_372_polling_20261030/data/2026-10-30|31/connector_status_long.jsonl

Method (standard library only):
  O(t) = capacity - availablecar  -> net occupancy, NOT per-vehicle arrivals
  M/G/infinity inversion O(t) = int lambda(s) S(t-s) ds -> clock-hour lambda (NNLS)
  night low-arrival occupancy decay -> survival S(tau) -> lognormal / Weibull
  connector idle/charging transitions -> charging sessions, durations, availability
  energy kept physically consistent: delivered <= power * dwell

Split rule: 12 train lots estimate every pooled parameter; 6 validation lots are
never used in estimation (they are only predicted and reported).
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = REPO / "research" / "collection" / "taipei_372_polling_20261030" / "data"
OUT_DATA = HERE / "data"
SLOT_MIN = 5
LOCAL = timezone(timedelta(hours=8))
GENERATOR_VERSION = "traffic_gen-1.0.0"
CHARGING = "\u5145\u96fb\u4e2d"
IDLE = "\u5f85\u6a5f\u4e2d"
TRAIN_LOTS = 12
VALIDATION_LOTS = 6


def parse_iso(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def local_label(dt):
    return dt.astimezone(LOCAL).strftime("%Y-%m-%d %H:%M")


def sha256_json(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cohort():
    payload = json.loads((DATA / "static" / "cohort_static.json").read_text(encoding="utf-8"))
    return {s["parking_id"]: s for s in payload["sites"]}


def load_parking_panel(caps):
    rows = []
    for day in ("2026-10-30", "2026-10-31"):
        with (DATA / day / "parking_slots.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                rows.append((r["slot_start_utc"], r["parking_id"],
                             bool(r.get("availablecar_valid")), r.get("availablecar_raw")))
    slots = sorted({r[0] for r in rows})
    index = {s: i for i, s in enumerate(slots)}
    n = len(slots)
    occ = {pid: [None] * n for pid in caps}
    for slot, pid, valid, avail in rows:
        if pid not in occ:
            continue
        i = index[slot]
        cap = caps[pid].get("baseline_totalcar")
        if valid and avail is not None and avail >= 0 and cap:
            occ[pid][i] = cap - avail
    return slots, occ


def select_window(slots, occ):
    """Keep slots that are not total request failures; merge short gaps; trim weak edges.

    Whole failed slots stay in the time axis and are linearly interpolated per lot, so the
    pooled mean keeps an identical lot composition at every slot."""
    n = len(slots)
    site_n = len(occ)
    valid = {}
    for i in range(n):
        c = 0
        for p in occ:
            if occ[p][i] is not None:
                c += 1
        valid[i] = c
    frac = [valid[i] / site_n for i in range(n)]
    runs, cur = [], []
    for i in range(n):
        if frac[i] >= 0.5:
            if cur and i - cur[-1] <= 6:
                cur.append(i)
            else:
                if cur:
                    runs.append(cur)
                cur = [i]
    if cur:
        runs.append(cur)
    main = max(runs, key=len) if runs else list(range(n))
    lo, hi = 0, len(main) - 1
    while lo < hi and frac[main[lo]] < 0.9:
        lo += 1
    while hi > lo and frac[main[hi]] < 0.9:
        hi -= 1
    return main[lo:hi + 1], valid


def build_bins(slots, keep):
    t0 = parse_iso(slots[keep[0]]).astimezone(LOCAL)
    hour_start = t0.replace(minute=0, second=0, microsecond=0)
    minutes = [(parse_iso(slots[i]).astimezone(LOCAL) - hour_start).total_seconds() / 60.0 for i in keep]
    obs_end = minutes[-1] + SLOT_MIN
    bins = []
    midnight = hour_start.replace(hour=0)
    cur = (midnight - hour_start).total_seconds() / 60.0
    while cur < -1e-9:
        nxt = min(cur + 60.0, 0.0)
        mid = hour_start + timedelta(minutes=(cur + nxt) / 2.0)
        hour = int((mid - midnight).total_seconds() // 3600) % 24
        bins.append({"start": cur, "end": nxt, "kind": "nuisance", "hour": hour,
                     "label": "pre_%02d" % hour})
        cur = nxt
    hour_cursor = hour_start
    while (hour_cursor - hour_start).total_seconds() / 60.0 < obs_end - 1e-9:
        a = (hour_cursor - hour_start).total_seconds() / 60.0
        bins.append({"start": a, "end": a + 60.0, "kind": "primary", "hour": hour_cursor.hour,
                     "label": "%02d:00" % hour_cursor.hour})
        hour_cursor = hour_cursor + timedelta(hours=1)
    for b in bins:
        b["minutes_observed"] = max(0.0, min(b["end"], obs_end) - max(b["start"], minutes[0]))
    return hour_start, minutes, obs_end, bins


def frange(a, b, step):
    out, x = [], a
    while x <= b + 1e-12:
        out.append(x)
        x += step
    return out


def surv_lognormal(tau, mu, sigma):
    if tau <= 0:
        return 1.0
    return 0.5 * math.erfc((math.log(tau) - mu) / (sigma * math.sqrt(2.0)))


def surv_weibull(tau, k, lam):
    if tau <= 0:
        return 1.0
    return math.exp(-((tau / lam) ** k))


def make_surv(fit):
    if fit["family"] == "lognormal":
        mu, sigma = fit["params"][0], fit["params"][1]
        return lambda t: surv_lognormal(t, mu, sigma)
    k, lam = fit["params"]
    return lambda t: surv_weibull(t, k, lam)


def fit_survival(taus, target, family):
    best = None
    if family == "lognormal":
        for mu in frange(1.0, 7.0, 0.05):
            for sigma in frange(0.2, 2.2, 0.05):
                sse = sum((surv_lognormal(t, mu, sigma) - y) ** 2 for t, y in zip(taus, target))
                if best is None or sse < best[0]:
                    best = (sse, [mu, sigma])
    else:
        for k in frange(0.4, 2.6, 0.02):
            for lam in frange(60.0, 900.0, 10.0):
                sse = sum((surv_weibull(t, k, lam) - y) ** 2 for t, y in zip(taus, target))
                if best is None or sse < best[0]:
                    best = (sse, [k, lam])
    return {"family": family, "params": best[1], "sse": best[0]}


def popmean(fit):
    if fit["family"] == "lognormal":
        mu, sigma = fit["params"]
        return math.exp(mu + sigma * sigma / 2.0)
    k, lam = fit["params"]
    return lam * math.gamma(1.0 + 1.0 / k)


def popquant(fit, p):
    lo, hi = 1e-6, 1e6
    surv = make_surv(fit)
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if surv(mid) > 1.0 - p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def describe_fit(fit):
    return {"family": fit["family"], "params": fit["params"],
            "mean_min": popmean(fit), "p50_min": popquant(fit, 0.5),
            "p90_min": popquant(fit, 0.9), "sse": fit["sse"]}


def pearson(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else None


def design_matrix(bins, minutes, surv):
    W = []
    for t in minutes:
        row = []
        for b in bins:
            s0, s1 = b["start"], min(b["end"], t)
            if s1 <= s0:
                row.append(0.0)
                continue
            cells = max(1, int(round((s1 - s0) / SLOT_MIN)))
            width = (s1 - s0) / cells
            acc = 0.0
            for c in range(cells):
                s = s0 + (c + 0.5) * width
                acc += surv(t - s) * width
            row.append(acc / 60.0)
        W.append(row)
    return W


def gram(W):
    m, n = len(W), len(W[0])
    WtW = [[0.0] * n for _ in range(n)]
    for k in range(m):
        row = W[k]
        for i in range(n):
            if row[i]:
                for j in range(n):
                    WtW[i][j] += row[i] * row[j]
    return WtW


def nnls_cd(WtW, y, iters=800):
    n = len(WtW)
    Wty = [sum(WtW[i][j] * y[j] for j in range(n)) for i in range(n)]
    x = [0.0] * n
    for _ in range(iters):
        delta = 0.0
        for i in range(n):
            if WtW[i][i] <= 0:
                continue
            resid = Wty[i] - sum(WtW[i][j] * x[j] for j in range(n) if j != i)
            new = max(0.0, resid / WtW[i][i])
            delta = max(delta, abs(new - x[i]))
            x[i] = new
        if delta < 1e-12:
            break
    return x


def forward(W, x):
    return [sum(r * c for r, c in zip(row, x)) for row in W]


def invert(A):
    n = len(A)
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        M[col] = [v / pv for v in M[col]]
        for r in range(n):
            if r != col and M[r][col]:
                f = M[r][col]
                M[r] = [a - f * b for a, b in zip(M[r], M[col])]
    return [row[n:] for row in M]


def param_se(WtW, var):
    inv = invert(WtW)
    if inv is None:
        return [None] * len(WtW)
    return [math.sqrt(max(0.0, var * inv[i][i])) for i in range(len(WtW))]


def lot_series(occ, pid, keep):
    """Per-lot occupancy in vehicles with linear interpolation over failed slots."""
    xs = [k for k, i in enumerate(keep) if occ[pid][i] is not None]
    out = []
    for k, i in enumerate(keep):
        v = occ[pid][i]
        if v is not None:
            out.append(float(v))
            continue
        prev = next((x for x in reversed(xs) if x < k), None)
        nxt = next((x for x in xs if x > k), None)
        if prev is None or nxt is None:
            out.append(None)
        else:
            a, b = float(occ[pid][keep[prev]]), float(occ[pid][keep[nxt]])
            out.append(a + (b - a) * (k - prev) / (nxt - prev))
    return out


def pooled(series_map, lots):
    n = len(next(iter(series_map.values())))
    out = []
    for i in range(n):
        vals = [series_map[p][i] for p in lots if series_map[p][i] is not None]
        out.append(sum(vals) / len(vals) if vals else None)
    return out


def pooled_per100(series_map, lots, cap_of, weight_by_capacity=True):
    n = len(next(iter(series_map.values())))
    out = []
    for i in range(n):
        num = den = 0.0
        for p in lots:
            v = series_map[p][i]
            if v is None:
                continue
            num += v
            den += cap_of[p]
        out.append(100.0 * num / den if den else None)
    return out


def increments(values):
    inc, dec = [], []
    prev = None
    for v in values:
        if v is None:
            inc.append(None)
            dec.append(None)
            prev = None
            continue
        if prev is None:
            inc.append(None)
            dec.append(None)
        else:
            d = v - prev
            inc.append(max(0.0, d))
            dec.append(max(0.0, -d))
        prev = v
    return inc, dec


def idx_of(dt, hour_start):
    return int(round((dt - hour_start).total_seconds() / 60.0 / SLOT_MIN))


def primary_bins(bins):
    return [b for b in bins if b["kind"] == "primary" and b["minutes_observed"] >= 25]


def bin_of_minute(pbins, t):
    for j, b in enumerate(pbins):
        if b["start"] <= t < b["end"]:
            return j
    return None


def night_decay(values, hour_start, anchors, max_tau):
    taus = list(range(5, max_tau + 1, 5))
    curves, info = [], []
    for anchor in anchors:
        i0 = idx_of(anchor, hour_start)
        if i0 < 0 or i0 >= len(values) or not values[i0]:
            continue
        base = values[i0]
        pts = []
        for tau in taus:
            i = i0 + tau // SLOT_MIN
            if i >= len(values) or values[i] is None:
                break
            pts.append(values[i] / base)
        if len(pts) < 12:
            continue
        curves.append(pts)
        info.append({"anchor_local": anchor.strftime("%H:%M"), "n_points": len(pts)})
    if not curves:
        return [], [], []
    n = min(len(c) for c in curves)
    taus = taus[:n]
    raw = [max(0.0, sum(c[k] for c in curves) / len(curves)) for k in range(n)]
    mono, low = [], 1.0
    for r in raw:
        low = min(low, r)
        mono.append(low)
    return taus, mono, info


def corrected_decay(values, hour_start, anchors, taus, pbins, lam_hour, surv):
    curves = []
    for anchor in anchors:
        i0 = idx_of(anchor, hour_start)
        if i0 < 0 or i0 >= len(values) or not values[i0]:
            continue
        base = values[i0]
        pts = []
        for tau in taus:
            i = i0 + tau // SLOT_MIN
            if i >= len(values) or values[i] is None:
                break
            arrivals = 0.0
            for j, b in enumerate(pbins):
                if lam_hour[j] is None:
                    continue
                s0, s1 = b["start"] - b["start"], min(b["end"], tau) - b["start"]
                s0 = max(0.0, -b["start"])
                s1 = min(tau, b["end"])
                if s1 <= s0:
                    continue
                cells = max(1, int(round((s1 - s0) / SLOT_MIN)))
                width = (s1 - s0) / cells
                for c in range(cells):
                    s = s0 + (c + 0.5) * width
                    arrivals += lam_hour[j] * surv(tau - s) * width / 60.0
            pts.append((values[i] - arrivals) / base)
        if len(pts) < 12:
            continue
        curves.append(pts)
    if not curves:
        return []
    n = min(len(c) for c in curves)
    out, low = [], 1.0
    for k in range(n):
        low = min(low, max(0.0, sum(c[k] for c in curves) / len(curves)))
        out.append(low)
    return out


def pick_fit(taus, target):
    best = None
    for fam in ("lognormal", "weibull"):
        fit = fit_survival(taus, target, fam)
        if best is None or fit["sse"] < best["sse"]:
            best = fit
    return best


def fit_lognormal_given_mean(taus, target, mean_min):
    best = None
    for sigma in frange(0.05, 2.0, 0.01):
        mu = math.log(max(1e-6, mean_min)) - sigma * sigma / 2.0
        sse = sum((surv_lognormal(t, mu, sigma) - y) ** 2 for t, y in zip(taus, target))
        if best is None or sse < best[0]:
            best = (sse, mu, sigma)
    sse, mu, sigma = best
    return {"family": "lognormal", "params": [mu, sigma], "sse": sse,
            "constrained_mean_min": mean_min}


RECOUNT_METHOD = (
    "dedupe by (parking_id, spot_abrv, slot_start_utc) keeping the non-duplicate_batch row; "
    "sort each connector by slot; merge 充電中 slots separated by <=5 missing/non-charging slots "
    "(25 min) into one session; duration = (last-first)+5 min span (internal gaps count as charging); "
    "sessions touching either window edge are flagged left/right censored but still counted in the "
    "session rate; duration mean/p50/p90 use all sessions, mean_complete_min uses internal-only ones"
)
MAX_GAP_SLOTS = 5


def load_connector_series(slot_index):
    raw = {}
    status_counts = {}
    for day in ("2026-10-30", "2026-10-31"):
        with (DATA / day / "connector_status_long.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                i = slot_index.get(r["slot_start_utc"])
                st = r.get("status_raw")
                status_counts[st] = status_counts.get(st, 0) + 1
                if i is None:
                    continue
                key = (r["parking_id"], r.get("spot_abrv"))
                prio = 0 if r.get("duplicate_batch") else 1
                cur = raw.setdefault(key, {}).get(i)
                if cur is None or prio >= cur[0]:
                    raw[key][i] = (prio, st)
    series = {key: {i: st for i, (prio, st) in items.items()} for key, items in raw.items()}
    return series, status_counts


def line_runs(idxs):
    runs, cur = [], []
    for i in idxs:
        if cur and i != cur[-1] + 1:
            runs.append(cur)
            cur = []
        cur.append(i)
    if cur:
        runs.append(cur)
    return runs


def connector_sessions(series, keep):
    keep_set = set(keep)
    first_slot, last_slot = keep[0], keep[-1]
    sessions = []
    censored = {"left": 0, "right": 0, "both": 0}
    for (pid, conn), items in series.items():
        idxs = sorted(i for i in items if i in keep_set)
        if not idxs:
            continue
        # charging groups, merging gaps of up to MAX_GAP_SLOTS slots
        groups, cur = [], None
        for i in idxs:
            if items[i] != CHARGING:
                if cur is not None:
                    groups.append(cur)
                    cur = None
                continue
            if cur is not None and i - cur[-1] <= (MAX_GAP_SLOTS + 1):
                cur.append(i)
            else:
                if cur is not None:
                    groups.append(cur)
                cur = [i]
        if cur is not None:
            groups.append(cur)
        for grp in groups:
            first, last = grp[0], grp[-1]
            left = first <= idxs[0]
            right = last >= idxs[-1]
            complete = (not left) and (not right)
            sessions.append({
                "lot": pid, "connector": conn,
                "start_slot": first, "end_slot": last,
                "n_charging_slots": len(grp),
                "duration_min": (last - first) * SLOT_MIN + SLOT_MIN,
                "duration_low_min": max(0, (last - first - 1) * SLOT_MIN),
                "duration_high_min": (last - first + 2) * SLOT_MIN,
                "complete": complete, "left_censored": left, "right_censored": right,
            })
            if left and right:
                censored["both"] += 1
            elif left:
                censored["left"] += 1
            elif right:
                censored["right"] += 1
    return sessions, censored


def _hist5(values):
    hist = {}
    for v in values:
        key = int(round(v / 5.0)) * 5
        hist["%d" % key] = hist.get("%d" % key, 0) + 1
    return hist


def pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    lo = int(math.floor(k))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def local_hour_fn(hour_start, minutes):
    base = hour_start.hour * 60
    return lambda k: int((base + minutes[k]) // 60) % 24


def lot_increments_profile(series_lot, keep, pbins, minutes):
    inc, dec = increments(series_lot)
    total_inc = sum(v for v in inc if v is not None)
    total_dec = sum(v for v in dec if v is not None)
    counts = [0.0] * len(pbins)
    occ_by_bin = [[] for _ in pbins]
    for k in range(len(keep)):
        t = minutes[k]
        j = bin_of_minute(pbins, t)
        if j is None:
            continue
        if inc[k] is not None:
            counts[j] += inc[k]
        if series_lot[k] is not None:
            occ_by_bin[j].append(series_lot[k])
    rates = [counts[j] / (pbins[j]["minutes_observed"] / 60.0) for j in range(len(pbins))]
    return {"inc": inc, "dec": dec, "total_inc": total_inc, "total_dec": total_dec,
            "rate_by_bin": rates, "counts_by_bin": counts,
            "mean_occ_by_bin": [sum(v) / len(v) if v else None for v in occ_by_bin]}


def fit_short_component(taus, ratio, w_long):
    if not taus or w_long >= 0.999:
        return None
    target = [max(0.0, (r - w_long) / (1.0 - w_long)) for r in ratio]
    best = None
    for mu in frange(1.0, 6.5, 0.05):
        for sigma in frange(0.10, 1.60, 0.05):
            sse = sum((surv_lognormal(t, mu, sigma) - y) ** 2 for t, y in zip(taus, target))
            if best is None or sse < best[0]:
                best = (sse, [mu, sigma])
    if best is None:
        return None
    return {"family": "lognormal", "params": best[1], "sse": best[0], "target_n": len(target)}


def mixture_surv(share_long, short_fit, d_long, sigma_long=0.35):
    """Finite-mean mixture: overnight long component plus the short/medium component."""
    mu_long = math.log(max(60.0, d_long)) - sigma_long * sigma_long / 2.0
    if short_fit is None:
        return lambda t: surv_lognormal(t, mu_long, sigma_long)
    mu, sigma = short_fit["params"]
    return lambda t: (share_long * surv_lognormal(t, mu_long, sigma_long) +
                      (1.0 - share_long) * surv_lognormal(t, mu, sigma))


def dwell_entry(share_long, short_fit, e_short, d_long_derived, mean_dwell_little):
    if share_long is None or share_long <= 0.0:
        sp0 = list(short_fit["params"]) if (short_fit and short_fit.get("params")) else [math.log(max(15.0, e_short)), 0.6]
        if sp0[0] is None:
            sp0 = [math.log(max(15.0, e_short)), 0.6]
        comp = {"name": "single_component_mean_matched", "weight": 1.0,
                "family": "lognormal_scenario", "params": sp0, "mean_min": e_short,
                "p50_min": math.exp(sp0[0]),
                "p90_min": math.exp(sp0[0] + 1.2815515655 * sp0[1]),
                "units": "minutes", "is_scenario": True,
                "note": "night-decay long-stay share is not identifiable for this lot (night floor "
                        "exceeds the arrival-derived long-stay rate); a single lognormal matched to "
                        "the Little-law mean is used instead"}
        return {"family": "single_component_mean_matched", "components": [comp],
                "params": {"components": [comp],
                           "note": "only the mean is data-derived; shape is a scenario"},
                "mean_min": mean_dwell_little, "p50_min": comp["p50_min"],
                "p90_min": comp["p90_min"], "long_stay_arrival_share": 0.0,
                "method": "Little law mean with a single mean-matched lognormal fallback"}
    sigma_long = 0.35
    mu_long = math.log(max(60.0, d_long_derived)) - sigma_long * sigma_long / 2.0
    sp = list(short_fit["params"]) if (short_fit and short_fit.get("params")) else [math.log(max(15.0, e_short)), 0.6]
    if sp[0] is None:
        sp = [math.log(max(15.0, e_short)), 0.6]
    def surv(t):
        return (share_long * surv_lognormal(t, mu_long, sigma_long) +
                (1.0 - share_long) * surv_lognormal(t, sp[0], sp[1]))
    def quant(p):
        lo, hi = 1e-6, 1e6
        for _ in range(120):
            mid = (lo + hi) / 2.0
            if surv(mid) > 1.0 - p:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0
    short_name = "short_medium_residual" if e_short <= 720.0 else "medium_long_residual"
    short = {"name": short_name, "weight": 1.0 - share_long,
             "family": short_fit["family"] if short_fit else "scenario_fallback",
             "params": sp, "mean_min": e_short,
             "p50_min": math.exp(sp[0]), 
             "p90_min": math.exp(sp[0] + 1.2815515655 * sp[1]),
             "is_scenario": True,
             "units": "minutes",
             "note": "residual plug: mean solved from Little's identity once the overnight-long share is fixed, not independently identified"}
    longc = {"name": "overnight_long", "weight": share_long, "family": "lognormal_scenario",
             "params": [mu_long, sigma_long], "mean_min": d_long_derived,
             "p50_min": math.exp(mu_long), "p90_min": math.exp(mu_long + 1.2815515655 * sigma_long),
             "is_scenario": True, "units": "minutes",
             "note": "long-stay mean is the residual plug that reproduces the observed mean occupancy; shape sigma is a scenario"}
    return {"family": "two_component_mixture", "components": [short, longc],
            "params": {"components": [short, longc], "sigma_long_scenario": sigma_long},
            "mean_min": mean_dwell_little, "p50_min": quant(0.5), "p90_min": quant(0.9),
            "long_stay_arrival_share": share_long,
            "method": "Little law mean + night-decay short component + residual long-stay plug"}


def main():
    caps = load_cohort()
    slots, occ = load_parking_panel(caps)
    keep, slot_valid = select_window(slots, occ)
    hour_start, minutes, obs_end, bins = build_bins(slots, keep)
    keep_set = set(keep)
    slot_index = {s: i for i, s in enumerate(slots)}
    pbins = primary_bins(bins)
    lh = local_hour_fn(hour_start, minutes)
    obs_hours = obs_end / 60.0
    cap_of = {p: float(caps[p].get("baseline_totalcar") or 0) for p in caps}
    valid_slots = {p: sum(1 for i in keep if occ[p][i] is not None) for p in caps}
    window = {"first_slot_utc": slots[keep[0]], "last_slot_utc": slots[keep[-1]],
              "local_start": local_label(parse_iso(slots[keep[0]])),
              "local_end": local_label(parse_iso(slots[keep[-1]])),
              "n_slots": len(keep), "slot_minutes": SLOT_MIN, "horizon_min": obs_end,
              "n_sites_in_cohort": len(caps)}
    print("WINDOW", json.dumps(window, ensure_ascii=False))
    eligible = [p for p in caps if cap_of[p] > 0 and valid_slots[p] >= 0.95 * len(keep)]
    caps_sorted = sorted(cap_of[p] for p in eligible)
    q1 = caps_sorted[len(caps_sorted) // 3]
    q2 = caps_sorted[2 * len(caps_sorted) // 3]
    def bucket(p):
        c = cap_of[p]
        return 0 if c <= q1 else (1 if c <= q2 else 2)
    groups = {0: [], 1: [], 2: []}
    for p in sorted(eligible):
        groups[bucket(p)].append(p)
    train, validation = [], []
    for b in (0, 1, 2):
        lst = groups[b]
        stride = max(1, len(lst) // 6)
        picks, seen, k = [], set(), 0
        while len(picks) < 6 and k < len(lst) * 4:
            cand = lst[(k * stride) % len(lst)]
            if cand not in seen:
                picks.append(cand)
                seen.add(cand)
            k += 1
        train.extend(picks[:4])
        validation.extend(picks[4:6])
    selected = train + validation
    train_set = set(train)
    series_lot = {p: lot_series(occ, p, keep) for p in selected}
    midnight = hour_start.replace(hour=0, minute=0)
    night_start = None
    for cand in (midnight, midnight + timedelta(days=1)):
        i0 = idx_of(cand, hour_start)
        if 0 <= i0 and (len(minutes) - i0) * SLOT_MIN >= 360:
            night_start = cand
            break
    anchors = [night_start + timedelta(minutes=30 * k) for k in range(5)]
    night_hours = set(range(1, 6))
    D_LONG_SCENARIO_MIN = 720.0
    conn_series, status_counts = load_connector_series(slot_index)
    sessions, censored = connector_sessions(conn_series, keep)
    starts_by_lot = {}
    complete_by_lot = {}
    for s in sessions:
        if s["start_slot"] >= keep[0] or s["left_censored"]:
            starts_by_lot.setdefault(s["lot"], []).append(s)
        if s["complete"]:
            complete_by_lot.setdefault(s["lot"], []).append(s)
    connectors_by_lot = {}
    idle_n_by_lot = {}
    charging_n_by_lot = {}
    charge_count_by_slot = {}
    for (pid, conn), items in conn_series.items():
        connectors_by_lot.setdefault(pid, set()).add(conn)
        for i, st in items.items():
            if i not in keep_set:
                continue
            if st == CHARGING:
                charging_n_by_lot[pid] = charging_n_by_lot.get(pid, 0) + 1
                charge_count_by_slot[(pid, i)] = charge_count_by_slot.get((pid, i), 0) + 1
            else:
                idle_n_by_lot[pid] = idle_n_by_lot.get(pid, 0) + 1
    lot_rows = []
    for pid in selected:
        vals = series_lot[pid]
        prof = lot_increments_profile(vals, keep, pbins, minutes)
        lam_bar = prof["total_inc"] / obs_hours
        present = [v for v in vals if v is not None]
        mean_occ = sum(present) / len(present)
        night_vals = [vals[k] for k in range(len(keep)) if lh(k) in night_hours and vals[k] is not None]
        night_floor = sum(night_vals) / len(night_vals) if night_vals else 0.0
        w_long = min(0.95, max(0.0, night_floor / mean_occ)) if mean_occ else 0.0
        notes = []
        taus_l, decay_l, anchor_l = night_decay(vals, hour_start, anchors, 300)
        lam_dep = prof["total_dec"] / obs_hours
        mean_dwell_little = mean_occ / lam_bar * 60.0 if lam_bar > 0 else None
        e_dwell_dep = mean_occ / lam_dep * 60.0 if lam_dep > 0 else None
        if mean_dwell_little is None or e_dwell_dep is None:
            rel_err = None
        else:
            rel_err = (e_dwell_dep - mean_dwell_little) / mean_dwell_little
        lam_long = night_floor * 60.0 / D_LONG_SCENARIO_MIN
        share_raw = (lam_long / lam_bar) if lam_bar > 0 else 0.0
        if 0.0 < share_raw < 0.90 and mean_dwell_little:
            share_long = share_raw
            e_short = (mean_dwell_little - share_long * D_LONG_SCENARIO_MIN) / (1.0 - share_long)
        else:
            share_long = 0.0
            e_short = mean_dwell_little or D_LONG_SCENARIO_MIN
        implausible = not (15.0 <= e_short <= 2880.0)
        saturated = (sum(1 for v in present if v >= 0.98 * cap_of[pid]) / len(present)) if present else 0.0
        if implausible:
            notes.append("mixture_decomposition_implausible_E_short=%.0f" % e_short)
        if share_long == 0.0:
            notes.append("single_component_mean_matched (unidentified long-stay share %.2f)" % share_raw)
        if saturated > 0.15:
            notes.append("saturation_censoring_share=%.2f" % saturated)
        sigma_s = 0.60
        mu_s = math.log(max(15.0, e_short)) - sigma_s * sigma_s / 2.0
        short_fit = {"family": "lognormal_scenario", "params": [mu_s, sigma_s], "sse": None}
        e_dwell_surv = (night_floor + max(0.0, lam_bar - lam_long) * e_short / 60.0) / lam_bar * 60.0 if lam_bar > 0 else None
        pred_occ = lam_bar * mean_dwell_little / 60.0 if mean_dwell_little else None
        d_long_derived = D_LONG_SCENARIO_MIN
        unusable = ((rel_err is not None and abs(rel_err) > 0.25) or implausible or saturated > 0.15)
        n_start = len(starts_by_lot.get(pid, []))
        lot_rows.append({"lot_id": pid, "n_spaces": cap_of[pid],
                         "split": "train" if pid in train_set else "validation",
                         "lambda_by_bin": prof["rate_by_bin"], "lam_bar": lam_bar,
                         "mean_occ": mean_occ, "night_floor": night_floor, "w_long": w_long,
                         "share_long": share_long, "mean_dwell_dep": e_dwell_dep,
                         "lam_dep": lam_dep, "saturated_share": saturated,
                         "e_short": e_short, "short_fit": short_fit,
                         "mean_dwell_little": mean_dwell_little, "e_dwell_surv": e_dwell_surv,
                         "pred_occ": pred_occ, "rel_err": rel_err, "unusable": unusable,
                         "d_long_derived": d_long_derived, "notes": notes,
                         "taus": taus_l, "decay": decay_l, "anchors": anchor_l,
                         "n_start_transitions": n_start,
                         "n_complete_sessions": len(complete_by_lot.get(pid, [])),
                         "n_connectors": len(connectors_by_lot.get(pid, set())),
                         "availability": (idle_n_by_lot.get(pid, 0) /
                                          max(1, idle_n_by_lot.get(pid, 0) + charging_n_by_lot.get(pid, 0)))})
    usable_train = [r for r in lot_rows if r["split"] == "train" and not r["unusable"]]
    usable_val = [r for r in lot_rows if r["split"] == "validation" and not r["unusable"]]
    print("CONSISTENCY_TABLE (mean occ vehicles, lambda veh/h, E[dwell] min)")
    for r in lot_rows:
        print("  %-8s sp=%-5.0f occ=%-7.2f lam=%-6.2f E_lit=%-7.1f E_surv=%-7.1f rel=%+6.1f%% w=%.2f E_sh=%-6.1f starts=%-4d %s %s" % (
            r["lot_id"], r["n_spaces"], r["mean_occ"], r["lam_bar"],
            r["mean_dwell_little"] or -1, r["e_dwell_surv"], 100.0 * (r["rel_err"] or 0),
            r["w_long"], r["e_short"], r["n_start_transitions"], r["split"],
            "UNUSABLE" if r["unusable"] else ""))
    print("USABLE_TRAIN", [r["lot_id"] for r in usable_train])
    print("USABLE_VALIDATION", [r["lot_id"] for r in usable_val])
    if not usable_train:
        raise SystemExit("no usable train lots")
    usable_train_ids = [r["lot_id"] for r in usable_train]
    ut_set = set(usable_train_ids)
    pooled_norm = pooled_per100(series_lot, usable_train_ids, cap_of)
    cap_train = sum(cap_of[p] for p in usable_train_ids)
    inc_sum = [0.0] * len(keep)
    dec_sum = [0.0] * len(keep)
    inc_ok = [False] * len(keep)
    for p in usable_train_ids:
        inc, dec = increments(series_lot[p])
        for k in range(len(keep)):
            if inc[k] is not None:
                inc_sum[k] += inc[k]
                dec_sum[k] += dec[k]
                inc_ok[k] = True
    counts = [0.0] * len(pbins)
    for k in range(len(keep)):
        j = bin_of_minute(pbins, minutes[k])
        if j is not None and inc_ok[k]:
            counts[j] += inc_sum[k]
    lot_profiles_per100 = []
    for r in usable_train:
        cap_l = cap_of[r["lot_id"]]
        lot_profiles_per100.append([v / (cap_l / 100.0) for v in r["lambda_by_bin"]])
    arrival_profile, arrival_se = [], []
    for j in range(len(pbins)):
        vals = [prof_l[j] for prof_l in lot_profiles_per100]
        mean_v = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean_v) ** 2 for v in vals) / max(1, len(vals) - 1))
        arrival_profile.append(mean_v)
        arrival_se.append(sd / math.sqrt(len(vals)))
    obs_occ_profile = []
    for j, b in enumerate(pbins):
        vals = [pooled_norm[k] for k in range(len(keep))
                if pooled_norm[k] is not None and b["start"] <= minutes[k] < b["end"]]
        obs_occ_profile.append(sum(vals) / len(vals) if vals else None)
    total_inc = sum(inc_sum[k] for k in range(len(keep)) if inc_ok[k])
    total_dec = sum(dec_sum[k] for k in range(len(keep)) if inc_ok[k])
    n_tr = len(usable_train)
    lam_bar_pooled = sum(r["lam_bar"] for r in usable_train) / n_tr
    mean_occ_veh_pooled = sum(r["mean_occ"] for r in usable_train) / n_tr
    mean_occ_pooled = 100.0 * sum(r["mean_occ"] / cap_of[r["lot_id"]] for r in usable_train) / n_tr
    mean_cap_train = sum(cap_of[r["lot_id"]] for r in usable_train) / n_tr
    mean_dwell_pooled = sum(r["mean_dwell_little"] for r in usable_train) / n_tr
    lam_dep_pooled = sum(r["lam_dep"] for r in usable_train) / n_tr
    e_dwell_dep_pooled = sum(r["mean_dwell_dep"] for r in usable_train) / n_tr
    rel_err_pooled = ((e_dwell_dep_pooled - mean_dwell_pooled) / mean_dwell_pooled) if e_dwell_dep_pooled else None
    night_floor_pooled = sum(r["night_floor"] for r in usable_train) / n_tr
    w_long_pooled = sum(r["w_long"] for r in usable_train) / n_tr
    taus_p, decay_p, anchor_p = night_decay(pooled_norm, hour_start, anchors, 300)
    share_long_pooled = min(0.90, max(0.0, sum(r["share_long"] for r in usable_train) / n_tr))
    e_short_pooled = ((mean_dwell_pooled - share_long_pooled * D_LONG_SCENARIO_MIN) /
                      (1.0 - share_long_pooled))
    sigma_sp = 0.60
    short_pooled = {"family": "lognormal_scenario",
                    "params": [math.log(max(15.0, e_short_pooled)) - sigma_sp * sigma_sp / 2.0, sigma_sp],
                    "sse": None}
    d_long_pooled = D_LONG_SCENARIO_MIN
    e_dwell_surv_pooled = mean_dwell_pooled
    surv_pooled = mixture_surv(share_long_pooled, short_pooled, D_LONG_SCENARIO_MIN)
    W = design_matrix(pbins, minutes, surv_pooled)
    warm = [k for k in range(len(keep)) if minutes[k] >= 180]
    pred_all = [sum(W[k][j] * arrival_profile[j] for j in range(len(pbins)))
                for k in range(len(keep))]
    obs_h, pred_h, hourly_cmp = [], [], []
    for j, b in enumerate(pbins):
        idx = [k for k in warm if b["start"] <= minutes[k] < b["end"]]
        o = []
        for k in idx:
            for r in usable_train:
                v = series_lot[r["lot_id"]][k]
                if v is not None:
                    o.append(100.0 * v / cap_of[r["lot_id"]])
        if not o or not idx:
            continue
        om, pm = sum(o) / len(o), sum(pred_all[k] for k in idx) / len(idx)
        obs_h.append(om)
        pred_h.append(pm)
        hourly_cmp.append({"local_hour": b["hour"], "minutes_observed": b["minutes_observed"],
                           "obs_mean_veh_per_100": om, "pred_mean_veh_per_100": pm})
    resid = [a - b for a, b in zip(obs_h, pred_h)]
    mean_obs = sum(obs_h) / len(obs_h)
    ss_tot = sum((v - mean_obs) ** 2 for v in obs_h)
    fit_stats = {"rmse_veh_per_100_spaces": math.sqrt(sum(r * r for r in resid) / len(resid)),
                 "r2": 1.0 - sum(r * r for r in resid) / ss_tot if ss_tot else None,
                 "pearson_r": pearson(obs_h, pred_h),
                 "peak_obs": max(obs_h), "peak_pred": max(pred_h),
                 "mean_obs": mean_obs, "mean_pred": sum(pred_h) / len(pred_h),
                 "n_hourly_points": len(obs_h), "warmup_min_excluded": 180,
                 "scope": "clock-hour aggregate over usable train lots, per 100 spaces"}
    cohort_sites = [p for p in eligible if p not in set(validation)]
    cohort_norm = {p: [None if v is None else 100.0 * v / cap_of[p] for v in lot_series(occ, p, keep)]
                   for p in cohort_sites}
    cohort_pool = pooled_per100(cohort_norm, cohort_sites, cap_of)
    cap_cohort = sum(cap_of[p] for p in cohort_sites)
    c_inc = [0.0] * len(keep)
    for p in cohort_sites:
        inc, _ = increments(cohort_norm[p])
        for k in range(len(keep)):
            if inc[k] is not None:
                c_inc[k] += inc[k]
    c_counts = [0.0] * len(pbins)
    for k in range(len(keep)):
        j = bin_of_minute(pbins, minutes[k])
        if j is not None:
            c_counts[j] += c_inc[k]
    cohort_profile = [c_counts[j] / cap_cohort * 100.0 / (pbins[j]["minutes_observed"] / 60.0)
                      for j in range(len(pbins))]
    c_total = sum(c_inc)
    c_occ = [v for v in cohort_pool if v is not None]
    cohort_fit = {"n_sites": len(cohort_sites),
                  "arrival_rate_per_100_spaces_hour": cohort_profile,
                  "mean_occupancy_veh_per_100": sum(c_occ) / len(c_occ),
                  "lambda_bar_per_100_hour": c_total / cap_cohort * 100.0 / obs_hours,
                  "mean_dwell_little_min": (sum(c_occ) / len(c_occ)) /
                                           (c_total / cap_cohort * 100.0 / obs_hours) * 60.0}

    # ---------------- charging pooled on every eligible site except the validation lots
    cohort_set = set(cohort_sites)
    train_connectors = set()
    tr_idle = tr_charge = 0
    for (pid, conn), items in conn_series.items():
        if pid not in cohort_set:
            continue
        train_connectors.add((pid, conn))
        for i, st in items.items():
            if i not in keep_set:
                continue
            if st == CHARGING:
                tr_charge += 1
            else:
                tr_idle += 1
    train_sessions = [s for s in sessions if s["lot"] in cohort_set]
    train_starts = [s for s in train_sessions if s["start_slot"] >= keep[0] or s["left_censored"]]
    train_complete = [s for s in train_sessions if s["complete"]]
    durs = sorted(s["duration_min"] for s in train_sessions)
    durs_complete = sorted(s["duration_min"] for s in train_complete)
    if not durs:
        raise SystemExit("no charging sessions among usable train lots")
    mean_dur = sum(durs) / len(durs)
    mean_dur_complete = (sum(durs_complete) / len(durs_complete)) if durs_complete else None
    start_counts = [0.0] * len(pbins)
    for s in train_starts:
        pos = keep.index(s["start_slot"])
        j = bin_of_minute(pbins, minutes[pos])
        if j is not None:
            start_counts[j] += 1
    lcharge = [start_counts[j] / (cap_cohort / 100.0) / (pbins[j]["minutes_observed"] / 60.0)
               for j in range(len(pbins))]
    product = [lcharge[j] / arrival_profile[j] if arrival_profile[j] else None
               for j in range(len(pbins))]
    product_mean = (sum(lcharge) / sum(arrival_profile)) if sum(arrival_profile) else None
    train_conn_count = len(train_connectors)
    conn_availability = tr_idle / max(1, tr_idle + tr_charge)
    charged_share = tr_charge / max(1, tr_idle + tr_charge)
    # occupied-but-not-charging balance (very loose post-charge lingering bound)
    diff_sum, diff_n, diff_neg = 0.0, 0, 0
    for pid in usable_train_ids:
        for k, i in enumerate(keep):
            v = series_lot[pid][k]
            if v is None:
                continue
            d = v - charge_count_by_slot.get((pid, i), 0)
            if d < 0:
                diff_neg += 1
            diff_sum += max(0.0, d)
            diff_n += 1
    mean_p = diff_sum / diff_n if diff_n else None
    ends_rate_h = len([s for s in sessions if s["lot"] in ut_set]) / (len(usable_train_ids) * obs_hours)
    lingering_bound = (mean_p / ends_rate_h * 60.0) if (ends_rate_h and mean_p) else None
    # ---------------- energy scenario
    energy_table = {("%.1fkW" % power): power * mean_dur / 60.0 for power in (3.5, 7.0, 11.0, 22.0, 60.0)}
    power_kw = 11.0
    efficiency = 0.9
    deficit_mean = power_kw * efficiency * mean_dur / 60.0
    battery_kwh = 60.0
    # ---------------- per-lot entries
    per_lot = []
    for r in lot_rows:
        pid = r["lot_id"]
        n_start = r["n_start_transitions"]
        if n_start >= 10:
            cc = [0.0] * len(pbins)
            for s in starts_by_lot.get(pid, []):
                pos = keep.index(s["start_slot"])
                j = bin_of_minute(pbins, minutes[pos])
                if j is not None:
                    cc[j] += 1
            crate = [cc[j] / (pbins[j]["minutes_observed"] / 60.0) for j in range(len(pbins))]
            crate_source = "observed"
        else:
            crate = [lcharge[j] * (r["n_spaces"] / 100.0) for j in range(len(pbins))]
            crate_source = "pooled_scaled"
        bin_min = sum(pbins[j]["minutes_observed"] for j in range(len(pbins)))
        crate_mean = sum(crate[j] * pbins[j]["minutes_observed"] for j in range(len(pbins))) / bin_min
        lot_sessions = starts_by_lot.get(pid, [])
        lotd = sorted(s["duration_min"] for s in lot_sessions)
        lotd_complete = sorted(s["duration_min"] for s in complete_by_lot.get(pid, []))
        if len(lotd) >= 5:
            cd = {"n": len(lotd), "family": "empirical_span_5min",
                  "mean_min": sum(lotd) / len(lotd), "p50_min": pct(lotd, 0.5),
                  "p90_min": pct(lotd, 0.9), "source": "observed",
                  "n_complete": len(lotd_complete),
                  "mean_complete_min": (sum(lotd_complete) / len(lotd_complete)) if lotd_complete else None,
                  "hist_5min": _hist5(lotd)}
        else:
            cd = {"n": len(lotd), "family": "pooled_empirical_span_5min",
                  "mean_min": mean_dur, "p50_min": pct(durs, 0.5),
                  "p90_min": pct(durs, 0.9), "source": "pooled",
                  "n_complete": len(lotd_complete),
                  "mean_complete_min": mean_dur_complete,
                  "hist_5min": _hist5(lotd) if len(lotd) >= 5 else _hist5(durs)}
        dwell = dwell_entry(r["share_long"], r["short_fit"], r["e_short"],
                            r["d_long_derived"], r["mean_dwell_little"])
        overstay_mean = max(0.0, (r["mean_dwell_little"] or 0.0) - cd["mean_min"])
        overstay = {"is_scenario": True, "identified": False,
                    "scenario_family": "lognormal", "scenario_mean_min": overstay_mean,
                    "plausible_range_min": [max(0.0, overstay_mean - 60.0), overstay_mean + 120.0],
                    "method": "scenario reconciling mean dwell and mean charge duration; not identifiable from a two-state connector feed (idle does not mean vacant)",
                    "not_identifiable_reason": "connector idle can be a vacant bay or a completed EV still parked"}
        entry = {
            "lot_id": pid, "n_spaces": r["n_spaces"], "n_connectors": r["n_connectors"],
            "date_range": "%s..%s" % (window["local_start"][:10], window["local_end"][:10]),
            "n_valid_slots": int(valid_slots[pid]), "n_slots_window": len(keep),
            "lambda_hour_by_bin": r["lambda_by_bin"],
            "lambda_units": "vehicles/hour for this lot (net-increase counting)",
            "lambda_bar_veh_per_hour": r["lam_bar"],
            "dwell_dist": dwell,
            "charge_session_rate_hour_by_bin": crate,
            "charge_session_rate_mean_hour": crate_mean,
            "charge_duration_hist_5min": cd.get("hist_5min"),
            "charge_session_rate_source": crate_source,
            "observed_p_ev_times_q_need": (crate_mean / r["lam_bar"]) if r["lam_bar"] > 0 else None,
            "n_charge_sessions_observed": n_start,
            "n_charge_transitions_observed": n_start,
            "charge_duration_dist": cd,
            "overstay_dist": overstay,
            "connector_availability": r["availability"],
            "connector_availability_note": "share of connector-slot observations reading idle; upper bound on truly free chargers",
            "mean_occupancy_vehicles": r["mean_occ"],
            "night_floor_occupancy_vehicles": r["night_floor"],
            "w_long_occupancy_share": r["w_long"],
            "fit_split": r["split"],
            "usable": not r["unusable"],
            "quality_notes": r["notes"],
        }
        per_lot.append(entry)
    consistency_rows = []
    for r in lot_rows:
        consistency_rows.append({
            "lot_id": r["lot_id"], "fit_split": r["split"], "n_spaces": r["n_spaces"],
            "mean_occupancy_vehicles": r["mean_occ"],
            "lambda_bar_veh_per_hour": r["lam_bar"],
            "mean_dwell_little_min": r["mean_dwell_little"],
            "mean_dwell_survival_min": r["e_dwell_surv"],
            "predicted_occupancy_vehicles": r["pred_occ"],
            "relative_error": r["rel_err"], "threshold": 0.25,
            "status": "unusable" if r["unusable"] else "ok",
            "w_long_occupancy_share": r["w_long"],
            "long_stay_arrival_share": r["share_long"],
            "night_floor_occupancy_vehicles": r["night_floor"],
            "mean_dwell_from_departures_min": r["mean_dwell_dep"],
            "relative_error_arrival_vs_departure": r["rel_err"],
            "saturation_share": r["saturated_share"],
            "n_charge_transitions_observed": r["n_start_transitions"],
        })
    consistency_rows.append({
        "lot_id": "POOLED_TRAIN", "fit_split": "train", "n_spaces": cap_train,
        "mean_occupancy_vehicles": mean_occ_veh_pooled,
        "lambda_bar_veh_per_hour": lam_bar_pooled,
        "mean_dwell_little_min": mean_dwell_pooled,
        "mean_dwell_survival_min": e_dwell_surv_pooled,
        "predicted_occupancy_vehicles": lam_bar_pooled * e_dwell_surv_pooled / 60.0,
        "relative_error": rel_err_pooled, "threshold": 0.25,
        "status": "unusable" if abs(rel_err_pooled) > 0.25 else "ok",
        "w_long_occupancy_share": w_long_pooled, "n_charge_transitions_observed": len(train_starts),
    })
    # ---------------- validation lots (never used in estimation)
    val_results = []
    for r in usable_val:
        pid = r["lot_id"]
        obs = [None if series_lot[pid][k] is None else 100.0 * series_lot[pid][k] / r["n_spaces"]
               for k in range(len(keep))]
        pred = [sum(W[k][j] * arrival_profile[j] for j in range(len(pbins)))
                for k in range(len(keep))]
        idxs = [k for k in range(len(keep)) if minutes[k] >= 180 and obs[k] is not None]
        yv = [obs[k] for k in idxs]
        pv = [pred[k] for k in idxs]
        mv = sum(yv) / len(yv)
        ss_t = sum((v - mv) ** 2 for v in yv)
        ss_r = sum((a - b) ** 2 for a, b in zip(yv, pv))
        val_results.append({
            "lot_id": pid, "n_spaces": r["n_spaces"],
            "rmse_vehicles": math.sqrt(ss_r / len(yv)),
            "relative_rmse": math.sqrt(ss_r / len(yv)) / mv,
            "pearson_r": pearson(yv, pv),
            "mean_obs_vehicles": mv, "mean_pred_vehicles": sum(pv) / len(pv),
            "own_lambda_bar_veh_per_hour": r["lam_bar"],
            "own_mean_dwell_little_min": r["mean_dwell_little"],
        })
    val_summary = {
        "n_lots": len(val_results), "lots": [v["lot_id"] for v in val_results],
        "mean_relative_rmse": (sum(v["relative_rmse"] for v in val_results) / len(val_results)) if val_results else None,
        "mean_pearson_r": (sum(v["pearson_r"] for v in val_results if v["pearson_r"] is not None) /
                           len([v for v in val_results if v["pearson_r"] is not None])) if val_results else None,
        "per_lot": val_results,
        "note": "prediction uses only train-lot parameters; validation lots never entered any estimation",
    }

    # ---------------- assemble output
    dwell_pooled = dwell_entry(share_long_pooled, short_pooled, e_short_pooled,
                               d_long_pooled, mean_dwell_pooled)
    arrival_se = [None if counts[j] <= 0 else (arrival_profile[j] / math.sqrt(counts[j]))
                  for j in range(len(pbins))]
    bins_meta = {"count": len(pbins),
                 "local_hour": [b["hour"] for b in pbins],
                 "minutes_observed": [b["minutes_observed"] for b in pbins],
                 "labels": [b["label"] for b in pbins],
                 "start_min": [b["start"] for b in pbins],
                 "end_min": [b["end"] for b in pbins],
                 "note": "clock-hour bins in window order: local 11 (partial 30 min) then 12..23 then 0..10"}
    params = {
        "schema_version": "traffic_gen_params/v1",
        "generator_version": GENERATOR_VERSION,
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {
            "parking_panel": "research/collection/taipei_372_polling_20261030/data/2026-10-30|31/parking_slots.jsonl",
            "connector_panel": "research/collection/taipei_372_polling_20261030/data/2026-10-30|31/connector_status_long.jsonl",
            "window_utc": [window["first_slot_utc"], window["last_slot_utc"]],
            "window_local": [window["local_start"], window["local_end"]],
            "local_timezone": "UTC+08:00 (Asia/Taipei, no DST)",
            "slots_used": len(keep), "slot_minutes": SLOT_MIN,
            "observed_sites": window["n_sites_in_cohort"],
            "occupancy_definition": "O = baseline_totalcar - availablecar (net occupancy, not arrivals)",
            "arrival_method": "net-increase counting: sum of max(0, delta O) per 5-min slot (lower bound on arrivals; censored when a lot is saturated)",
            "charging_state_field": "connector_status_long.status_raw values are only CHARGING and IDLE",
        },
        "split": {
            "rule": "site-level isolation: only the usable train lots estimate shared parameters; validation lots are never used in estimation",
            "train_lots_requested": train, "validation_lots_requested": validation,
            "usable_train_lots": usable_train_ids,
            "usable_validation_lots": [r["lot_id"] for r in usable_val],
            "unusable_lots": [r["lot_id"] for r in lot_rows if r["unusable"]],
            "capacity_buckets": {"small_leq": q1, "mid_leq": q2, "rule": "terciles over eligible sites"},
        },
        "bins": bins_meta,
        "traffic_fit": {
            "train": {
                "arrival_rate_per_100_spaces_hour": arrival_profile,
                "arrival_rate_se": arrival_se,
                "dwell": dwell_pooled,
                "mean_occupancy_veh_per_100": mean_occ_pooled,
                "lambda_bar_per_100_hour": lam_bar_pooled / (mean_cap_train / 100.0),
                "arrival_profile_basis": "mean over usable train lots of per-lot vehicles per 100 spaces per hour",
                "method": "lambda by net-increase counting; mean dwell by Little law E[O]=lambda*E[S]; short-stay shape from night occupancy decay; long-stay residual plug",
                "sample_split": "usable train lots only: " + ", ".join(usable_train_ids),
                "fit_quality": fit_stats,
                "hourly_comparison": hourly_cmp,
                "night_decay": {"anchors": anchor_p, "points": len(taus_p),
                                "ratio_at_240min": decay_p[-1] if decay_p else None,
                                "w_long_occupancy_share": w_long_pooled},
                "uncertainty": {"lambda": "Poisson counting error, correlated across hours",
                                "dwell_mean": "Little law, depends on the arrival counter",
                                "dwell_short_shape": "night decay family fit, identifiable only to 300 min",
                                "dwell_long_mean": "residual plug, not independently identified"},
            },
            "cohort_reference": {
                "note": "supplementary only: every eligible site except the 6 validation lots; NOT used by the train split",
                "arrival_rate_per_100_spaces_hour": cohort_fit["arrival_rate_per_100_spaces_hour"],
                "mean_occupancy_veh_per_100": cohort_fit["mean_occupancy_veh_per_100"],
                "lambda_bar_per_100_hour": cohort_fit["lambda_bar_per_100_hour"],
                "mean_dwell_little_min": cohort_fit["mean_dwell_little_min"],
                "n_sites": cohort_fit["n_sites"],
            },
        },
        "charging": {
            "lambda_charge_per_100_spaces_hour": lcharge,
            "lambda_charge_units": "charging sessions started per 100 spaces per hour",
            "n_start_transitions": len(train_starts),
            "n_complete_sessions": len(durs_complete),
            "mean_charge_duration_min": mean_dur,
            "mean_complete_charge_duration_min": mean_dur_complete,
            "recount_method": RECOUNT_METHOD,
            "charge_duration_dist": {"n": len(durs), "family": "empirical_span_5min",
                                     "mean_min": mean_dur, "p50_min": pct(durs, 0.5),
                                     "p90_min": pct(durs, 0.9), "max_min": max(durs),
                                     "n_complete": len(durs_complete),
                                     "mean_complete_min": mean_dur_complete,
                                     "hist_5min": _hist5(durs),
                                     "share_le_5min": sum(1 for d in durs if d <= 5) / len(durs),
                                     "resolution_note": "span duration = (last-first)+5 min with internal gaps counted as charging; slots are 5 min so the true span lies in +/-5 min"},
            "censoring": censored,
            "connector_availability_upper_bound": conn_availability,
            "connector_share_charging": charged_share,
            "n_connectors_train": train_conn_count,
            "post_charge_lingering": {"identified": False, "is_scenario": True,
                                      "note": "cannot be identified from a two-state connector feed: idle may be a vacant bay or a completed EV still parked. No numeric point estimate is reported; see per_lot overstay_dist for the scenario field",
                                      "occupied_minus_charging_negative_slots": diff_neg},
            "p_ev_times_q_need": {"per_hour": product, "mean": product_mean,
                                  "note": "lambda_charge/lambda_arrival identifies only the product p_EV*q_need; neither factor is separately identified in these data"},
            "status_counts": status_counts,
        },
        "ev": {
            "p_ev_status": "unidentified from lot-level occupancy",
            "q_need_status": "unidentified; only the product is identified",
            "product_required_mean": product_mean,
            "q_need_by_p_ev": {("%.2f" % p): (product_mean / p if product_mean is not None else None)
                               for p in (0.02, 0.03, 0.05, 0.08, 0.12, 0.20)},
        },
        "energy": {
            "is_scenario": True,
            "charger_power_kw": power_kw, "efficiency": efficiency,
            "deficit_mean_kwh": deficit_mean, "deficit_sd_kwh": 8.0,
            "deficit_clip_kwh": [4.0, 55.0], "battery_kwh": battery_kwh,
            "implied_energy_by_power_kwh": energy_table,
            "consistency": "energy = min(deficit, power*efficiency*dwell); charge time >= energy/power by construction; shortfall is reported in meta",
            "assumption_note": "charger power is not observable in the Taipei feed; the power is a scenario and the mean deficit is derived from the observed mean charge duration",
        },
        "generator": {
            "horizon_min": 1440, "minute_step_min": 1.0,
            "reference_spaces": 100, "default_n_spaces": cap_train / len(usable_train_ids),
            "max_dwell_min": 4320, "min_dwell_min": 1.0, "max_arrivals": 40000,
        "max_dwell_note": "6x the 720 min overnight component so long-stay tails are not clipped by the day boundary",
            "dwell_truncation_note": "the survival tail beyond the 300-min night decay is not identified; the long-stay component mean is a residual plug and its sigma is a scenario",
        },
        "consistency": {"threshold_relative_error": 0.25, "rows": consistency_rows,
                        "unusable_lots_excluded": [r["lot_id"] for r in lot_rows if r["unusable"]],
                        "definition": "mean_dwell_survival = w_long*720min + (1-w_long)*E_short(night decay); predicted occupancy = lambda_bar*mean_dwell_survival/60; relative_error vs observed mean occupancy"},
        "per_lot": per_lot,
        "validation": val_summary,
        "limitations": [
            "net occupancy only: arrivals and departures are individually unobserved; the arrival counter is a lower bound and is censored in saturated lots",
            "charging sessions are only connector state changes; idle does not mean vacant",
            "short-stay and long-stay shares cannot be uniquely separated with lambda; the long-stay mean is a residual plug",
            "dwell survival is identified only up to 300 min of night decay",
            "p_EV and q_need are not separately identified; only their product is",
            "charger power is not observable; energy is a scenario consistent with observed durations",
            "one continuous 23.3 h window from a single polling campaign; no seasonality or weekend variation",
        ],
    }
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    (HERE / "fitted_parameters.json").write_text(
        json.dumps(params, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    panel_out = {"window": window, "bins": bins_meta,
                 "slot_start_utc": [slots[i] for i in keep],
                 "lots": {p: {"n_spaces": cap_of[p],
                              "fit_split": "train" if p in train_set else "validation",
                              "usable": not next(r for r in lot_rows if r["lot_id"] == p)["unusable"],
                              "occupancy_vehicles": series_lot[p]} for p in selected}}
    (OUT_DATA / "panel_selected_lots.json").write_text(
        json.dumps(panel_out, ensure_ascii=False, indent=1), encoding="utf-8")
    charge_out = {"pooled_train": {"n_start_transitions": len(train_starts),
                                   "n_complete_sessions": len(durs),
                                   "duration_hist_5min": {str(k): sum(1 for d in durs if d == k)
                                                          for k in sorted(set(durs))},
                                   "lambda_charge_per_100_spaces_hour": lcharge},
                 "censoring": censored,
                 "per_lot": {r["lot_id"]: {"n_start_transitions": r["n_start_transitions"],
                                           "n_complete_sessions": r["n_complete_sessions"],
                                           "n_connectors": r["n_connectors"],
                                           "connector_availability": r["availability"],
                                           "fit_split": r["split"]} for r in lot_rows}}
    (OUT_DATA / "charge_sessions_summary.json").write_text(
        json.dumps(charge_out, ensure_ascii=False, indent=1), encoding="utf-8")
    diag = {"window": window, "bins": bins_meta, "anchors": anchor_p,
            "decay_pooled": {"taus_min": taus_p, "ratio": decay_p,
                             "short_fit": {k: v for k, v in (short_pooled or {}).items() if k != "surv"}},
            "inversion_fit": fit_stats, "hourly_comparison": hourly_cmp,
            "cohort_reference": cohort_fit, "validation": val_summary,
            "per_lot_diagnostics": {r["lot_id"]: {"taus": r["taus"], "decay": r["decay"],
                                                  "short_fit": r["short_fit"],
                                                  "lambda_by_bin": r["lambda_by_bin"],
                                                  "anchors": r["anchors"]} for r in lot_rows}}
    (OUT_DATA / "fit_diagnostics.json").write_text(
        json.dumps(diag, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("PARAMS_SHA256", hashlib.sha256(
        (HERE / "fitted_parameters.json").read_bytes()).hexdigest())
    print("POOLED", json.dumps({"arrival_profile": [round(v, 2) for v in arrival_profile],
                                "mean_occ_per100": round(mean_occ_pooled, 2),
                                "lambda_bar_per100_hour": round(lam_bar_pooled / (mean_cap_train / 100.0), 3),
                                "mean_dwell_little_min": round(mean_dwell_pooled, 1),
                                "w_long": round(w_long_pooled, 3),
                                "e_short": round(e_short_pooled, 1),
                                "d_long_derived": round(d_long_pooled, 1),
                                "rel_err_survival": round(rel_err_pooled, 3),
                                "fit": {k: (round(v, 3) if isinstance(v, float) else v)
                                        for k, v in fit_stats.items()}}, ensure_ascii=False))
    print("CHARGE", json.dumps({"source_lots": len(cohort_sites), "starts": len(train_starts), "complete": len(durs),
                                "mean_dur_min": round(mean_dur, 1),
                                "p50": pct(durs, 0.5), "p90": pct(durs, 0.9),
                                "availability_upper": round(conn_availability, 3),
                                "charged_share": round(charged_share, 3),

                                "product_mean": round(product_mean, 5),
                                "lcharge": [round(v, 3) for v in lcharge]}, ensure_ascii=False))
    print("ENERGY", json.dumps({"power_kw": power_kw, "mean_dur": round(mean_dur, 1),
                                "deficit_mean_kwh": round(deficit_mean, 2),
                                "implied": {k: round(v, 1) for k, v in energy_table.items()}}, ensure_ascii=False))
    print("VALIDATION", json.dumps({k: v for k, v in val_summary.items() if k != "per_lot"}, ensure_ascii=False))


if __name__ == "__main__":
    main()