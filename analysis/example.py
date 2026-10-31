#!/usr/bin/env python
"""Small end-to-end example: dwell sample -> ideal delivery upper bound -> figure.

Reads data/sample/parking_events_sample.csv (real observed rows, CC BY 4.0) and computes the
analytic upper bound of deliverable energy at four connector powers. This is the same bound as
equations (1)-(3) in docs/method.md, applied to a 300-row sample so it runs without the raw
archive. It is a smoke example, not a study result.
"""
import csv, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLE = os.path.join(ROOT, "data", "sample", "parking_events_sample.csv")
OUT_JSON = os.path.join(ROOT, "results", "sample_bounds.json")
OUT_PNG = os.path.join(ROOT, "results", "sample_bounds.png")

# The requested energy is a scenario field and is not present in the observed sample, so the
# example draws it from the declared scenario: truncated normal(14, 6) kWh on [2, 40], seed 20261031.
def main():
    import random
    rng = random.Random(20261031)
    dwell = []
    with open(SAMPLE, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                d = float(row["dwell_min"])
            except (TypeError, ValueError):
                continue
            if d > 0:
                dwell.append(d / 60.0)
    energy = []
    for _ in dwell:
        while True:
            e = rng.gauss(14.0, 6.0)
            if 2.0 <= e <= 40.0:
                energy.append(e)
                break
    total = sum(energy)
    rows = []
    for P in (7.0, 11.0, 22.0, 50.0):
        delivered = sum(min(e, P * t) for e, t in zip(energy, dwell))
        ok = sum(1 for e, t in zip(energy, dwell) if e <= P * t + 1e-9)
        rows.append({"power_kw": P, "sessions": len(dwell),
                     "requested_kwh": round(total, 2), "delivered_kwh": round(delivered, 2),
                     "energy_service_rate": round(delivered / total, 4),
                     "session_failure_rate": round(1 - ok / len(dwell), 4)})
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump({"source": "data/sample/parking_events_sample.csv",
                   "scenario_energy": "truncated normal(14,6) kWh on [2,40], seed 20261031",
                   "bounds": rows}, fh, indent=1)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("matplotlib not installed; JSON written, figure skipped")
        return rows
    plt.rcParams.update({"font.family": "serif", "font.serif": ["DejaVu Serif"]})
    fig, ax = plt.subplots(figsize=(6.2, 3.0), dpi=300)
    xs = [str(int(r["power_kw"])) for r in rows]
    ys = [100 * r["energy_service_rate"] for r in rows]
    fs = [100 * r["session_failure_rate"] for r in rows]
    ax.bar([i - 0.2 for i in range(len(xs))], ys, width=0.38, color="#08306b",
           label="energy service rate")
    ax.bar([i + 0.2 for i in range(len(xs))], fs, width=0.38, color="#5ba3d0",
           label="session failure rate")
    ax.axhline(5.0, color="#333333", linestyle=(0, (4, 2)), linewidth=0.8)
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs)
    ax.set_xlabel("connector power P (kW)")
    ax.set_ylabel("percent of requests / energy")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", color="#dddddd", linewidth=0.5)
    ax.legend(frameon=False, fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300)
    print("wrote", OUT_JSON, "and", OUT_PNG)
    return rows


if __name__ == "__main__":
    for r in main():
        print(r)
