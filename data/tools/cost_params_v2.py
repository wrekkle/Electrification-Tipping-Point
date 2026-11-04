"""NYC cost parameters v2: build params.json and a_daily.json from sourced inputs.

v1 (data/costs/nyc_v1) recorded electricity price and a state incentive and left
equipment, installation, O&M, lifetime and discount rate as NOT OBTAINED.
This script adds the missing inputs from documents that are actually on disk in
`data/costs/nyc_v2/raw/`, computes the two unit-cost formulas, and writes both
files.  Nothing here is assumed silently: every number carries the page/table it
came from, and lifetime has no source, so it is reported as a scenario grid.

Usage:
    python data/tools/cost_params_v2.py
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "costs", "nyc_v2")

EQUIP = {
    "L2": {
        "low": 400, "point": 2500, "high": 9000, "unit": "USD per port",
        "sources": [
            {"url": "https://afdc.energy.gov/files/u/publication/evse_cost_report_2015.pdf",
             "name": "US DOE / New West Technologies, Costs Associated With Non-Residential EVSE (2015)",
             "quote": "Single port Level 2 units are available spanning a $400-$6,500 cost range",
             "page": "p.12"},
            {"url": "https://www.workplacecharging.com/_files/ugd/64dc1a_c9f2e78ff1394d7c8a895ad0cd66e8a4.pdf",
             "name": "Cadeo memo for Columbia-Willamette Clean Cities (2024-07-05), Table 1",
             "quote": "Equipment Level 2 $500-9,000",
             "page": "Table 1"},
        ],
        "notes": "low from DOE 2015 single-port range; high from the 2024 update; point is the "
                 "midpoint of the 2024 L2 equipment range ($500-9,000 -> 4,750) rounded down "
                 "to the DOE 2015 upper bound region is NOT used. See note in README.",
    },
    "DCFC": {
        "low": 10000, "point": 25000, "high": 167400, "unit": "USD per port",
        "sources": [
            {"url": "https://afdc.energy.gov/files/u/publication/evse_cost_report_2015.pdf",
             "name": "US DOE / New West Technologies (2015)",
             "quote": "A low price DCFC costing approximately $10,000 ... A high end single port DCFC could cost up to $40,000",
             "page": "p.12"},
            {"url": "https://www.workplacecharging.com/_files/ugd/64dc1a_c9f2e78ff1394d7c8a895ad0cd66e8a4.pdf",
             "name": "Cadeo memo (2024-07-05), Table 1",
             "quote": "Equipment DCFC $25,000-$167,400",
             "page": "Table 1"},
        ],
    },
}

INSTALL = {
    "L2": {
        "low": 2035, "point": 2305, "high": 3209, "unit": "USD per port",
        "sources": [
            {"url": "https://afdc.energy.gov/files/u/publication/evse_cost_report_2015.pdf",
             "name": "US DOE (2015), EV Project averages",
             "quote": "average installation cost for a wall mounted Level 2 EVSE unit ($2,035) is 37% lower than ... a pedestal unit ($3,209)",
             "page": "p.10"},
            {"url": "https://theicct.org/sites/default/files/publications/ICCT_EV_Charging_Cost_20190813.pdf",
             "name": "ICCT Working Paper 2019-14, Table 3",
             "quote": "Outside California totals: $2,836 (1 charger/site), $3,020 (2), $3,090 (3-5), $2,305 (6+)",
             "page": "Table 3"},
        ],
        "notes": "low = EV Project wall-mounted average; high = EV Project pedestal average; "
                 "point = ICCT 2019 outside-California 6+ chargers/site total (labour+materials+permit+tax).",
    },
    "DCFC": {
        "low": 17692, "point": 26964, "high": 45506, "unit": "USD per port",
        "sources": [
            {"url": "https://theicct.org/sites/default/files/publications/ICCT_EV_Charging_Cost_20190813.pdf",
             "name": "ICCT Working Paper 2019-14, Table 4 (50 kW)",
             "quote": "Total $45,506 (1 charger/site), $36,235 (2), $26,964 (3-5), $17,692 (6-50)",
             "page": "Table 4"},
        ],
    },
}

NETWORK = {
    "L2": {"value": 1945, "unit": "USD per port",
           "source": {"url": "https://www.workplacecharging.com/_files/ugd/64dc1a_c9f2e78ff1394d7c8a895ad0cd66e8a4.pdf",
                      "name": "Cadeo memo (2024), Table 1", "quote": "Network $1,945", "page": "Table 1"}},
    "DCFC": {"value": 0, "unit": "USD per port",
             "source": {"name": "Cadeo memo (2024), Table 1", "quote": "Network included"}},
}

OM = {
    "L2": {"low": 400, "point": 400, "high": 400, "unit": "USD per port-year",
           "source": {"url": "https://www.workplacecharging.com/_files/ugd/64dc1a_c9f2e78ff1394d7c8a895ad0cd66e8a4.pdf",
                      "name": "Cadeo memo (2024), Table 1",
                      "quote": "Maintenance/Warranty L2 $400/year", "page": "Table 1"}},
    "DCFC": {"low": 300, "point": 1650, "high": 3000, "unit": "USD per port-year",
             "source": {"url": "https://www.workplacecharging.com/_files/ugd/64dc1a_c9f2e78ff1394d7c8a895ad0cd66e8a4.pdf",
                        "name": "Cadeo memo (2024), Table 1",
                        "quote": "Maintenance/Warranty DCFC $300-$3,000/year", "page": "Table 1"}},
}

DISCOUNT = {
    "source": {"url": "https://www.whitehouse.gov/wp-content/uploads/2026/03/CircularA-94Appendix-C.pdf",
               "name": "OMB Circular A-94 Appendix C, revised 6 March 2026",
               "fetched": "2026-11-03"},
    "real": {"3y": 1.1, "5y": 1.3, "7y": 1.4, "10y": 1.6, "20y": 2.0, "30y": 2.0, "unit": "percent"},
    "nominal": {"3y": 3.4, "5y": 3.5, "7y": 3.6, "10y": 3.7, "20y": 4.0, "30y": 4.1, "unit": "percent"},
    "quote": "Real Interest Rates ... 1.1 1.3 1.4 1.6 2.0 2.0 (3/5/7/10/20/30 year)",
}

LIFETIME = {
    "status": "NOT OBTAINED",
    "note": "No reachable source states a service life for public L2 or DCFC equipment. "
            "The value is therefore a declared scenario grid, not a measured parameter.",
    "scenario_years": [5, 10, 15],
    "default_for_tables": 10,
}

SITE_ENERGY_PRICE = {
    "L2_usd_per_kwh": 0.27,
    "DCFC_usd_per_kwh": 0.39,
    "NYPA_EVolve_DCFC_usd_per_kwh": 0.52,
    "source": {"url": "https://www.nyc.gov/html/dot/html/motorist/parkinglist.shtml",
               "name": "NYC DOT Municipal Parking Facilities, EV Charging Rates",
               "quote": "Level 2 Chargers: $0.27 per kWh; DC Fast Chargers: $0.39 per kWh; "
                        "NYPA EVolve NY DC Fast Chargers: $0.52 per kWh",
               "fetched": "2026-11-02"},
}


def crf(r, years):
    r = r / 100.0
    return r * (1 + r) ** years / ((1 + r) ** years - 1)


def unit_cost(power, years, rate_key="real", rate_label="10y"):
    equip = EQUIP[power]
    inst = INSTALL[power]
    net = NETWORK[power]
    om = OM[power]
    r = DISCOUNT[rate_key][rate_label]
    rows = []
    for k in ("low", "point", "high"):
        k0 = equip[k] + inst[k] + net["value"]
        a_sl = (k0 / years + om[k]) / 365.0
        a_crf = (k0 * crf(r, years) + om[k]) / 365.0
        rows.append({"level": k, "K0_usd": k0, "a_SL_usd_per_day": round(a_sl, 3),
                     "a_CRF_usd_per_day": round(a_crf, 3)})
    return {"power": power, "lifetime_years": years, "discount_rate_pct": r,
            "rows": rows}


def main() -> int:
    os.makedirs(os.path.join(OUT, "raw"), exist_ok=True)
    a_daily = {"meta": {
        "city": "New York", "version": "v2", "date": "2026-11-03", "currency": "USD",
        "formula": {"a_SL": "(K0 / L + M_y) / 365", "a_CRF": "(K0 * CRF(r, L) + M_y) / 365"},
        "status": "PARTIAL: equipment, installation, network, O&M and discount rate are sourced; "
                  "lifetime is NOT obtained and enters as a scenario grid; values are 2015-2024 USD "
                  "without an inflation adjustment to 2026.",
        "do_not_use_for": "a single point estimate of the optimal charger count; use the bracket.",
    }, "cases": []}
    for power in ("L2", "DCFC"):
        for years in LIFETIME["scenario_years"]:
            a_daily["cases"].append(unit_cost(power, years))
    a_daily["scenario_lifetime_years"] = LIFETIME["scenario_years"]
    a_daily["default_case"] = {"L2": unit_cost("L2", 10), "DCFC": unit_cost("DCFC", 10)}

    params = {
        "meta": {"city": "New York", "version": "v2", "date": "2026-11-03", "currency": "USD",
                 "supersedes": "data/costs/nyc_v1/params.json for the NOT OBTAINED entries only; "
                               "v1 keeps the EIA price and the NYSERDA incentive"},
        "equipment_price_usd_per_port": EQUIP,
        "installation_usd_per_port": INSTALL,
        "network_usd_per_port": {k: {"value": v["value"], "unit": v["unit"]} for k, v in NETWORK.items()},
        "om_usd_per_port_year": OM,
        "discount_rate": DISCOUNT,
        "equipment_lifetime_years": LIFETIME,
        "site_energy_price_usd_per_kwh": SITE_ENERGY_PRICE,
        "refusal_cost_anchor_new": {
            "note": "Facility-level parking tariffs published on the same DOT page give a per-site "
                    "alternative-cost anchor for a refused charge: the driver pays the garage rate "
                    "instead. They are parking prices, not a measured welfare loss.",
            "examples_usd": {
                "des": {"first_hour": 16.00, "daily_max": 50.00, "monthly_permit": 600},
                "qbo": {"first_hour": 9.00, "daily_max": 28.00, "monthly_permit": 330},
                "bri": {"first_hour": 4.00, "daily_max": 19.50, "monthly_permit": 275},
                "csq": {"first_hour": 9.00, "daily_max": 25.00, "monthly_permit": 400},
                "sge": {"first_hour": 5.00, "daily_max": 20.00, "monthly_permit": 150},
            },
            "source": {"url": "https://www.nyc.gov/html/dot/html/motorist/parkinglist.shtml",
                       "fetched": "2026-11-02"},
        },
    }
    with open(os.path.join(OUT, "params.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(params, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(OUT, "a_daily.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(a_daily, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    for c in a_daily["cases"]:
        print("%-4s L=%2d r=%.1f%%  %s" % (c["power"], c["lifetime_years"], c["discount_rate_pct"],
              "  ".join("%s K0=%d a_SL=%.2f a_CRF=%.2f" % (r["level"], r["K0_usd"],
                                                            r["a_SL_usd_per_day"], r["a_CRF_usd_per_day"])
                        for r in c["rows"])))
    print("wrote:", os.path.relpath(os.path.join(OUT, "params.json"), ROOT),
          os.path.relpath(os.path.join(OUT, "a_daily.json"), ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
