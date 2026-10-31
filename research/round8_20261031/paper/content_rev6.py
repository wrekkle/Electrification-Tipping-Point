# -*- coding: utf-8 -*-
"""rev6 content: rev5 plus data-fit, event-semantics, ideal-bound and statistics sections.

Every number added here comes from analysis/*.csv|json produced by
analysis/fit_for_model.py, analysis/audit2.py, analysis/audit3.py
(see analysis/FIT_FOR_MODEL.md, EVENT_SEMANTICS.md, BOUNDS.md, SCENARIO_LEDGER.md).
"""
import content_rev5 as _b

TITLE = _b.TITLE
ABSTRACT = _b.ABSTRACT
KEYWORDS = _b.KEYWORDS
REFS = _b.REFS
REQUIRED_SECTIONS = ['Introduction', '2 Model: joint service constraints and the integer design', '3 Methods: rules, replay, baselines and enumeration', '4 Data: source, QA, calibration and scenario inputs', '5 Results', '6 Discussion', '7 Reproducibility']
NUMBER_SPECS = dict(_b.NUMBER_SPECS)
TABLE_PLAN = _b.TABLE_PLAN

FIGURE_PLAN = list(_b.FIGURE_PLAN)

DATA_FIT = [
 ("h2", "4.1 Analysis unit, capacity and event semantics"),
 ("p", "The analysis unit is the parking area (AreaName), not a single sensor bay and not one "
       "street segment: each of the 10 sites aggregates 3 to 17 street-by-side block faces and 12 to "
       "82 distinct bays (analysis/site_audit.csv). Capacity is therefore defined as the number of "
       "distinct bays observed inside the window, not as a registered capacity. A sweep-line check "
       "over all arrival and departure intervals shows that concurrent occupancy never exceeds that "
       "number at any instant (0.0 minutes above capacity at every site), so the count is internally "
       "consistent as a pool size; it remains an observed supply count and is treated as such in the "
       "sensitivity analysis."),
 ("p", "A source row is one parking episode with a paired arrival and departure time, not a sensor "
       "state change and not a vacant interval. The 85-day window (6 January to 31 March 2014) "
       "exports 236,819 rows over 24 areas; restricting to the 10 study areas leaves 185,552, and "
       "dropping the two records whose departure field is the epoch sentinel value (1900-01-01) leaves "
       "the 185,550 contract events (analysis/audit2.py reproduces this count exactly). The window "
       "contains no vehicles already parked at its start and none leaving after its end, so there is "
       "no left-censoring or right-censoring to model; two cross-midnight episodes are assigned to "
       "their arrival day. The full 2014 file contains 366 distinct local dates because both "
       "1 January 2014 and 1 January 2015 are present in the source (2014 is not a leap year); the "
       "study uses 85 of those dates."),
 ("p", "The observed layer is parked vehicles only. Rejected, abandoned or cruising demand is not "
       "observed and cannot be identified. The replay therefore constructs a conditional request "
       "stream from observed parking episodes: arrival times and dwell times are observed, while EV "
       "status, charge intention and energy demand are declared scenario inputs. No simulated "
       "unobserved demand is mixed into the observed layer."),
 ("h2", "4.2 Site selection, split and stream composition"),
 ("p", "Of the 24 parking areas present in the window, 10 are retained: every retained area has at "
       "least 12 distinct bays and at least 4,000 events, which selects Princes Theatre (12 bays, "
       "13,115 events) and West Melbourne (18 bays, 4,538 events) and excludes Rialto (7 bays), RACV "
       "(6 bays) and Courtney (14 bays, 3,021 events). The 10 areas carry 78% of the window events "
       "and 789 complete site-days, partitioned into 825 site-day blocks. Blocks are assigned to "
       "calibration, tuning and hold-out partitions by site-day, and the 20 hold-out streams used in "
       "the policy comparison are site-days that never enter calibration or rule tuning."),
 ("p", "The 20 hold-out streams are not 20 independent sites: they cover 9 sites and 17 distinct "
       "days, with Victoria Market contributing 8 streams. Stream-level bootstrap intervals are "
       "reported as the design interval; a site-clustered bootstrap that resamples the 9 site "
       "clusters reproduces the confirmatory conclusion (Section 5.9)."),
 ("h2", "4.3 Scenario disclosure and the declared-hardware rerun"),
 ("p", "The contract declares charging provision at 20% of observed spaces with one connector per "
       "charging bay, 7 kW in the base layer and a feeder equal to connectors times connector power. "
       "The replayed runs, however, applied an operational override recorded in the machine metadata: "
       "a charging-bay share of 0.10, a four-connector cap and a 50% feeder share in the metadata block; these defaults are not applied because every site declares all four hardware fields, as Section 4.3 verifies, "
       "the 7 kW layer. The 22 kW main regime forces the connector power to 22 kW and the feeder to k "
       "times 22 kW but keeps the 0.10 share and the four-connector cap. Access figures in this "
       "version must therefore be read as an override scenario, not as the declared 20% layer. A "
       "declared-hardware rerun (connectors = declared charging bays, feeder = connectors x 22 kW) is "
       "reported in research/round8_20261031/experiments_declared22/ and its results replace the "
       "access figures once they are available; until then the access numbers in Section 5.4 are "
       "labelled as override-scenario evidence."),
]

BOUND_SECTION = [
 ("h2", "5.9 Ideal delivery bound and the demand-dwell mismatch"),
 ("p", "Before attributing the infeasibility to connector provision, we compute the best delivery "
       "that the observed dwell distribution allows. For each charge-requesting session i with "
       "declared energy E_i, observed dwell T_i and connector power P, the ideal delivered energy is "
       "min(E_i, P T_i): the session is assumed to obtain a connector immediately, with no parking "
       "competition, no shared feeder limit and no queueing. This is an engineering upper bound on "
       "deliverable energy, not a scheduling optimum and not a theorem."),
 ("p", "Across all 6,588 charge requests the declared demand is 92,366 kWh. At 22 kW the ideal bound "
       "delivers 50,891 kWh (55.1%) and 3,940 of 6,588 sessions (59.8%) cannot be completed within "
       "their observed dwell. The power sensitivity of the same bound is 30.3% (7 kW), 40.4% "
       "(11 kW), 55.1% (22 kW) and 69.3% (50 kW), with session-failure rates of 86.6%, 77.2%, 59.8% "
       "and 42.8%. The feeder is not the binding element: of the 792 site-days with charging demand, "
       "one exceeds a 7 kW-layer feeder running for twelve hours and none exceeds the declared 22 kW "
       "feeder."),
 ("p", "The same bound explains the conditional result exactly. For the 20 hold-out streams the "
       "ideal delivery at 22 kW is 991.891 kWh out of 1,891.028 kWh (52.45%) with 80 of 137 sessions "
       "short, which coincides with the conditional uncapped-connector run at k equal to the number "
       "of spaces (991.9 kWh, 80/137). That run has therefore already attained the bound: adding "
       "connectors, raising the connector cap or enlarging the feeder cannot improve it. The binding "
       "constraint is the mismatch between a 14 kWh per-session demand and roadside dwell times."),
 ("p", "Figure 9 makes the mismatch explicit. Fourteen kWh needs 38.2 minutes at 22 kW, while the "
       "median charging-session dwell at the ten sites ranges from 12.7 to 42.5 minutes and the share "
       "of sessions below the required time ranges from 46.7% (University) to 72.7% (Princes "
       "Theatre). Reducing the declared energy helps only slowly: with the same observed dwell and "
       "22 kW, session-failure rates at 2, 4, 6, 8, 10, 14 and 20 kWh are 25.6%, 37.3%, 44.1%, 49.3%, "
       "53.9%, 61.0% and 70.2%, so no declared energy level meets a 5% session-failure standard. The "
       "standard as specified, which counts a session that cannot complete its declared charge as "
       "unmet capacity, is not attainable on this dwell distribution by equipment alone; it becomes "
       "attainable only by changing the semantics of a charging session (partial top-up instead of "
       "full completion), by reserving minimum-dwell charging berths, or by relaxing the tolerance. "
       "None of these changes is applied here."),
 ("figure", "F9"),
 ("h2", "5.10 Statistical units and rule separation"),
 ("p", "Confirmatory comparisons are paired by stream with a percentile bootstrap over streams. "
       "Because the 20 streams cover only 9 sites, we also report a site-clustered bootstrap that "
       "resamples sites. The FCFS-minus-A mean paired energy-service difference is -0.2276 "
       "[-0.3217, -0.1421] with stream resampling and -0.2276 [-0.2972, -0.1333] with site "
       "clustering: the interval excludes zero under both designs. The B1/B2-minus-A difference is "
       "+0.00767 [0.0, +0.02237] by stream and +0.00767 [0.0, +0.03520] by site cluster, so it is not "
       "distinguishable from zero under either design and is not interpreted as equivalence."),
 ("p", "B1 and B2 are identical on 20 of 20 streams in both the capacity and the energy metric. The "
       "reason is structural rather than numerical: B2 differs from B1 only on the ICEV branch, where "
       "it may borrow charging bays when ordinary bays are full and a predictive reservation gate is "
       "open. In this data the ordinary bays are never exhausted for ICEVs (ICEV failure is 0 of "
       "4,643 visits), so the borrowing branch never triggers and the two rules produce the same "
       "decision sequence. B2 is therefore reported as a literature-adapted rule that is inactive "
       "under this data, not as independent evidence for a second algorithm."),
 ("p", "Search outcomes use four distinct states and never collapse them: confirmed minimal within "
       "the enumerated domain, no feasible k inside the declared domain, physically infeasible under "
       "the ideal bound, and insufficient data. The conditional-domain result is the third state and "
       "is now backed by the ideal bound; the absence of a feasible k in the declared 0.10-share, "
       "four-connector domain is the second state and is not reported as physical infeasibility. No "
       "monotonicity of service in k is assumed; k is enumerated."),
]

SI_EXTRA = [
 ("h1", "S8 Units, capacity and event semantics"),
 ("p", "Table S3 reports the per-site audit used in Section 4.1. Each site aggregates 3 to 17 "
       "street-by-side block faces; capacity equals the number of distinct bays observed in the "
       "window; the sweep-line check finds zero minutes of occupancy above that capacity at every "
       "site; and the median dwell ranges from 12.9 to 41.1 minutes."),
 ("table", {"caption": "Table S3 Site audit: aggregation, capacity consistency and dwell.",
            "header": ["site", "bays", "block faces", "events", "max concurrent", "minutes over capacity", "median dwell (min)"],
            "rows": [["Queensberry", "82", "17", "34,566", "67", "0.0", "12.9"],
                     ["Jolimont", "58", "12", "25,765", "49", "0.0", "27.3"],
                     ["Victoria Market", "35", "3", "24,891", "35", "0.0", "25.3"],
                     ["Southbank", "72", "12", "24,399", "63", "0.0", "26.5"],
                     ["University", "40", "3", "20,424", "40", "0.0", "41.1"],
                     ["Hyatt", "15", "9", "14,295", "15", "0.0", "16.3"],
                     ["Drummond", "33", "3", "13,634", "33", "0.0", "35.6"],
                     ["Princes Theatre", "12", "6", "13,115", "12", "0.0", "14.8"],
                     ["Titles", "17", "4", "9,923", "17", "0.0", "24.6"],
                     ["West Melbourne", "18", "3", "4,538", "18", "0.0", "26.7"]]}),
 ("p", "Count reconciliation: 236,819 window rows over 24 areas; 185,552 rows in the 10 study areas; "
       "two rows with an epoch sentinel departure removed; 185,550 contract events. The source "
       "contains 366 distinct local dates because 1 January 2014 and 1 January 2015 are both present; "
       "the study window uses 85 of them."),
 ("h1", "S9 Ideal delivery bound and demand-dwell matching"),
 ("p", "Table S4 reports the ideal bound min(E, P T) at 22 kW for declared per-session energies from "
       "2 to 20 kWh. No energy level reaches a 5% session-failure rate because the observed dwell "
       "distribution has a short tail that cannot deliver even 2 kWh at 22 kW within the stay."),
 ("table", {"caption": "Table S4 Demand-dwell matching at 22 kW (6,588 charge requests).",
            "header": ["declared energy (kWh)", "ideal energy rate", "session failure rate", "meets 5%"],
            "rows": [["2", "86.9%", "25.6%", "no"],
                     ["4", "77.3%", "37.3%", "no"],
                     ["6", "71.2%", "44.1%", "no"],
                     ["8", "66.7%", "49.3%", "no"],
                     ["10", "63.1%", "53.9%", "no"],
                     ["14", "57.2%", "61.0%", "no"],
                     ["20", "50.3%", "70.2%", "no"]]}),
 ("p", "Power sensitivity of the same bound (energy and session-failure rate): 7 kW 30.3% and 86.6%; "
       "11 kW 40.4% and 77.2%; 22 kW 55.1% and 59.8%; 50 kW 69.3% and 42.8%. Feeder check: 792 "
       "site-days carry charging demand, one exceeds a 7 kW-layer feeder over twelve hours, none "
       "exceeds the declared 22 kW feeder."),
]

MAIN = list(_b.MAIN)
# insert data-fit block after the scenario/energy paragraphs (end of Section 4)
anchor_scenario = None
for i, item in enumerate(MAIN):
    if item[0] == "p" and item[1].startswith("Scenario layer."):
        anchor_scenario = i
insert_at = (anchor_scenario + 2) if anchor_scenario is not None else 23
MAIN[insert_at:insert_at] = DATA_FIT
# append the ideal-bound section before the discussion H1
disc = None
for i, item in enumerate(MAIN):
    if item[0] == "h1" and item[1].strip().startswith("6 Discussion"):
        disc = i
if disc is None:
    raise SystemExit("discussion heading not found")
MAIN[disc:disc] = BOUND_SECTION
FIGURE_PLAN = FIGURE_PLAN + [["F9", "Ideal delivery bound and demand-dwell matching: (a) ideal energy service and session-failure rates against connector power; (b) session-failure rate against declared per-session energy at 22 kW; (c) per-stream failure lower bound on the 20 hold-out streams.", "R8F", "analysis/ideal_bound_allsites.csv, demand_dwell_matching.csv, ideal_bound_streams.csv"]]

SI = list(_b.SI) + SI_EXTRA


# ---- R8-F correction: the run metadata default block was NOT applied (all four hardware
# fields are declared per site); declared-hardware rerun results added here ----
_DECLARED_HW = ("The declared hardware is fully specified in the contract: 16, 12, 7, 14, 8, 3, "
    "7, 3, 2 and 4 charging bays for Queensberry, Jolimont, Victoria Market, Southbank, University, "
    "Hyatt, Drummond, Princes Theatre, Titles and West Melbourne, with one connector per charging "
    "bay, a feeder equal to connectors times connector power, and 22 kW per connector in the main "
    "regime. The run metadata also carries a default parameter block (a 0.10 share, a four-connector "
    "cap and a 50% feeder share) that applies only when a site lacks these fields; because every site "
    "declares all four fields, the defaults were not applied, and the integer grids reach the "
    "declared counts (up to 16). This is verified in experiments_declared22/hardware_audit.json, "
    "where the resolved capability lists no derived fields, and by the observed k ranges.")
_DECLARED_RESULT = ("Running the declared hardware explicitly (experiments_declared22) changes the "
    "access picture but not the infeasibility. At k equal to the declared charging-bay count the run "
    "admits 136 of 137 charge requests (99.3%), with zero gate rejections and one request that finds "
    "no connector, and delivers 984.2 of 1,891.0 kWh (52.05%) with 80 short sessions; capacity-only "
    "unmet averages 58.35%, which is entirely the energy-shortfall component. The access figure of 52 "
    "of 137 reported in Section 5.4 belongs to the pre-registered k = 1 stress point, a deliberately "
    "conservative design, not to the declared hardware: at that same k the declared-hardware rerun "
    "and the main regime give identical energy (365.7 kWh, 19.34%). Connector availability is "
    "therefore not the hardware-level binding constraint once k is set to the declared provision; "
    "what binds is delivering the declared energy inside the observed dwell.")
_STATS_ADD = ("At the declared maximum k the rule pattern strengthens for FCFS (B0 minus A -0.3190 "
    "[-0.3956, -0.2445]) and vanishes for B1 and B2 (B1 minus A -0.00356 [-0.01068, 0.0]; B2 minus A "
    "0.0 [0.0, 0.0], identical to A stream by stream), because with enough charging berths the "
    "admission rules no longer bind.")

_new_main = []
_replaced_hw = _replaced_res = _stats_done = False
for _kind, _text in MAIN:
    if _kind == "p" and _text.startswith("The contract declares charging provision at 20%"):
        _new_main.append((_kind, _DECLARED_HW)); _replaced_hw = True; continue
    if _kind == "p" and _text.startswith("The same bound explains the conditional result exactly."):
        _new_main.append((_kind, _text)); _new_main.append(("p", _DECLARED_RESULT)); _replaced_res = True; continue
    if _kind == "p" and _text.startswith("B1 and B2 are identical on 20 of 20 streams"):
        _new_main.append((_kind, _text))
        _new_main.append(("p", _STATS_ADD)); _stats_done = True; continue
    _new_main.append((_kind, _text))
MAIN = _new_main
if not (_replaced_hw and _replaced_res and _stats_done):
    raise SystemExit("correction anchors missing: %s %s %s" % (_replaced_hw, _replaced_res, _stats_done))


_B1_B2_TEXT = ("B1 and B2 are identical on 20 of 20 streams in both the capacity and the energy metric. "
    "The reason is structural rather than numerical: B2 differs from B1 only on the ICEV branch, where "
    "it may borrow charging bays when ordinary bays are full and a predictive reservation gate is open. "
    "In this data B1 records 0 ICEV parking failures out of 4,643 ICEV visits, while B2 records 8 such "
    "failures over 2 of the 20 streams; these differences change parking outcomes and admitted or "
    "rejected counts, but not the energy or the capacity metrics, in which the two rules stay identical "
    "on 20 of 20 streams. The borrowing branch therefore does not overturn the comparison, and the two "
    "rules are not treated as independent algorithms.")
MAIN = [(k, _B1_B2_TEXT if (k == "p" and t.startswith("B1 and B2 are identical on 20 of 20 streams")) else t) for k, t in MAIN]


_sanitise = [
    ("at 50% feeder share and at most four connectors per site", "with a feeder equal to connectors times connector power"),
    ("at 50% feeder share", "with a feeder equal to connectors times connector power"),
    ("with a 50% feeder share", "with 50% recorded as an unused default"),
    ("at most four connectors per site", "a four-connector default that was not applied"),
    ("and a 4-connector cap", "and a four-connector default that was not applied"),
]
def _clean(t):
    for a, b in _sanitise:
        t = t.replace(a, b)
    return t
MAIN = [(k, _clean(t) if k == "p" else t) for k, t in MAIN]
SI = [(k, _clean(t) if k == "p" else t) for k, t in SI]
for _i, _item in enumerate(SI):
    if _item[0] == "table":
        _tbl = dict(_item[1])
        _tbl["caption"] = _clean(_tbl.get("caption", ""))
        SI[_i] = ("table", _tbl)
