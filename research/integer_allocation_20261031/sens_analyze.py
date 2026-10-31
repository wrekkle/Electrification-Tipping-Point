"""p_EV 情景灵敏度：整数 k_alpha 如何随未识别的 EV 份额变化（Lead）。"""
from __future__ import annotations
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "outputs")


def aggregate(document):
    per = {}
    for row in document["rows"]:
        bucket = per.setdefault(row["lot_id"], {}).setdefault(int(row["k"]), [])
        bucket.append(row)
    result = {}
    for lot, by_k in per.items():
        means = {}
        for k, rows in by_k.items():
            def mean(key):
                values = [r[key] for r in rows if r.get(key) is not None]
                return sum(values) / len(values) if values else None
            means[k] = {"unmet": mean("unmet_no_connector_events"),
                        "facility": mean("facility_cost"),
                        "delivered": mean("delivered_energy_kwh"),
                        "ev_arrivals": mean("ev_arrivals"),
                        "charge_requests": mean("charge_requests"),
                        "power_short": mean("power_dwell_shortfall_events")}
        result[lot] = means
    return result


def service_k(means, alpha):
    base = means.get(0, {}).get("unmet")
    if base is None or base <= 0:
        return 0 if base == 0 else None
    for k in sorted(means):
        value = means[k].get("unmet")
        if value is not None and value <= alpha * base:
            return k
    return max(means)


def main():
    files = sorted(f for f in os.listdir(OUT) if f.startswith("sens_pev_") and f.endswith(".json"))
    report = {"schema": "pev_sensitivity/v1", "files": files, "by_pev": {}}
    rows = []
    for name in files:
        with open(os.path.join(OUT, name), encoding="utf-8") as handle:
            doc = json.load(handle)
        pev = float(name[len("sens_pev_"):-len(".json")]) / 100.0
        agg = aggregate(doc)
        per_lot = {}
        for lot, means in agg.items():
            per_lot[lot] = {"k_5": service_k(means, 0.05), "k_10": service_k(means, 0.10),
                            "k_20": service_k(means, 0.20),
                            "ev_arrivals": means.get(1, {}).get("ev_arrivals"),
                            "charge_requests": means.get(1, {}).get("charge_requests"),
                            "unmet_at_k40": means.get(40, {}).get("unmet")}
            rows.append((pev, lot, per_lot[lot]["ev_arrivals"], per_lot[lot]["charge_requests"],
                         per_lot[lot]["k_5"], per_lot[lot]["k_10"]))
        report["by_pev"]["%.4f" % pev] = per_lot
    with open(os.path.join(OUT, "pev_sensitivity.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
    print("p_ev lot ev_arr charge_req k5 k10")
    for pev, lot, evs, reqs, k5, k10 in rows:
        print("%.2f %s %s %s %s %s" % (pev, lot, evs, reqs, k5, k10))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
