# -*- coding: utf-8 -*-
"""rev7 content: rev6 plus metric-definition, demand-dwell coupling and partial-target sections,
corrected relative-difference wording and citations."""
import content_rev6 as _r
import content_rev5 as _b

TITLE = _r.TITLE
ABSTRACT = _r.ABSTRACT
KEYWORDS = _r.KEYWORDS
REQUIRED_SECTIONS = list(_r.REQUIRED_SECTIONS)
TABLE_PLAN = []
NUMBER_SPECS = dict(_r.NUMBER_SPECS)
for _tok in ("rel_all", "rel_ev", "rel_ice"):
    if _tok in NUMBER_SPECS:
        NUMBER_SPECS[_tok] = dict(NUMBER_SPECS[_tok]); NUMBER_SPECS[_tok]["scale"] = 100.0; NUMBER_SPECS[_tok]["fmt"] = "{:.2f}"

REFS = {
 "D1": "City of Melbourne. Parking bay arrivals and departures 2014. Open data portal, dataset mq3i-cbxd, licensed CC BY 4.0. https://data.melbourne.vic.gov.au/explore/dataset/parking-bay-arrivals-and-departures-2014/",
 "P05": "P05 Scheduling and performance analysis under a stochastic model for electric vehicle charging stations. Omega 66(B):278-289, 2017.",
 "P06": "P06 Modelling the intensity of electric vehicle arrivals at charging points. Transportation Research Procedia 70:372-379, 2023.",
 "P09": "P09 Admission and pricing optimization of on-street parking with delivery bays. European Journal of Operational Research 312(1):138-149, 2024.",
 "P26": "P26 An online admission control mechanism for electric vehicles at public parking infrastructures. IEEE Transactions on Smart Grid 11(1):161-170, 2020.",
 "M07": "M07 Electric vehicles shared charging and parking: a reservation-based dynamic rolling allocation framework considering unpunctuality. Transportation Research Part C 179:105259, 2025.",
}

MAIN = list(_r.MAIN)
SI = list(_r.SI)

# --- 1. remove empty / placeholder figure panels (E5 k_min all missing, E7 zero rows) ---
MAIN = [(k, t) for (k, t) in MAIN if not (k == "figure" and t in ("F5", "F7"))]
FIGURE_PLAN = [e for e in _r.FIGURE_PLAN if e[0] not in ("F5", "F7")]

# --- 2. relative-difference wording: block level difference, not a prediction error ---
_rel_map = [
    ("mean relative error of the hold-out mean is 11.96% for all events, 13.60% for EV and 11.78% for ICEV",
     "hold-out-to-calibration mean dwell difference is 11.96% for all events, 13.60% for EV and 11.78% for ICEV; this is a level difference between blocks, not a prediction error, and the KS statistic describes a distributional difference rather than an equality of means"),
    ("hold-out mean relative error {{rel_all}}%", "hold-out-to-calibration mean dwell difference {{rel_all}}%"),
    ("a mean relative error of {{rel_all}}%", "a hold-out-to-calibration mean dwell difference of {{rel_all}}%"),
]
_new = []
for k, t in MAIN:
    if k == "p":
        for a, b in _rel_map:
            t = t.replace(a, b)
    _new.append((k, t))
MAIN = _new

# --- 3. metric definitions and the access/shortfall separation ---
_FACTS = dict(cr=int(137.0), gate=int(0.0), noco=int(1.0), short=int(80.0), dlv=984.221000, dem=1891.028000,
              capmean=0.583521, ev=0.0, ice=34.0, evvis=452.0, icevis=4643.0,
              conc_n=792, conc_med=2, conc_p90=4, conc_max=9)
METRIC_SECTION = [
 ("h2", "5.11 Metric definitions: access, parking failure, session shortfall and energy shortfall"),
 ("p", "The earlier chapters report a capacity-only unmet share that mixes two different failures. "
       "It is defined as the number of charge requests that are either refused at admission or "
       "depart with less than their requested energy, divided by the number of charge requests "
       "[P26]. At the declared hardware and the evaluated k the audit separates the components: "
       "of %d charge requests, %d never obtain a connector (%d refused at admission plus %d that "
       "find no connector), which is a never-connected rate of %.2f%%, while %d sessions (%s) "
       "depart short of their requested energy. The mean stream capacity-only unmet share is "
       "%.2f%%, and its pooled value is %.2f%%; almost all of it is the shortfall component, not "
       "access. Energy delivered is %.2f of %.2f kWh (%.2f%%), so the energy shortfall ratio is "
       "%.2f%%. EV parking failure is %d of %d EV visits and ICE parking failure is %d of %d ICE "
       "visits at this k. These five quantities are separate metrics with separate denominators "
       "and are never reported under one name." %
       (_FACTS["cr"], _FACTS["gate"] + _FACTS["noco"], _FACTS["gate"], _FACTS["noco"],
        100.0 * (_FACTS["gate"] + _FACTS["noco"]) / _FACTS["cr"], _FACTS["short"],
        "%.1f%%" % (100.0 * _FACTS["short"] / _FACTS["cr"]), 100.0 * _FACTS["capmean"],
        100.0 * (_FACTS["gate"] + _FACTS["noco"] + _FACTS["short"]) / _FACTS["cr"],
        _FACTS["dlv"], _FACTS["dem"], 100.0 * _FACTS["dlv"] / _FACTS["dem"],
        100.0 * (1 - _FACTS["dlv"] / _FACTS["dem"]), _FACTS["ev"], _FACTS["evvis"],
        _FACTS["ice"], _FACTS["icevis"])),
 ("table", {"caption": "Table 6 Metric definitions used in this paper. Each row has its own numerator and denominator; the last column gives the value at the declared hardware and the evaluated k.",
            "header": ["metric", "definition", "numerator / denominator", "value"],
            "rows": [
              ["never-connected rate", "charge request that never obtains a connector", "%d / %d" % (_FACTS["gate"] + _FACTS["noco"], _FACTS["cr"]), "%.2f%%" % (100.0 * (_FACTS["gate"] + _FACTS["noco"]) / _FACTS["cr"])],
              ["EV parking failure rate", "EV visit refused a parking space", "%d / %d" % (_FACTS["ev"], _FACTS["evvis"]), "%.2f%%" % (100.0 * _FACTS["ev"] / max(1, _FACTS["evvis"]))],
              ["ICEV parking failure rate", "ICEV visit refused a parking space", "%d / %d" % (_FACTS["ice"], _FACTS["icevis"]), "%.2f%%" % (100.0 * _FACTS["ice"] / max(1, _FACTS["icevis"]))],
              ["departed shortfall session rate", "charge request departing below its requested energy", "%d / %d" % (_FACTS["short"], _FACTS["cr"]), "%.2f%%" % (100.0 * _FACTS["short"] / _FACTS["cr"])],
              ["energy shortfall ratio", "requested energy not delivered", "1 - %.2f / %.2f" % (_FACTS["dlv"], _FACTS["dem"]), "%.2f%%" % (100.0 * (1 - _FACTS["dlv"] / _FACTS["dem"]))],
              ["capacity-only unmet share (mean over streams)", "admission refusals plus departed shortfall sessions", "mean of stream ratios", "%.2f%%" % (100.0 * _FACTS["capmean"])]]}),
 ("p", "The connector-only bound is separate again. If every charge-requesting session had a "
       "connector at arrival and no energy target applied, the number of connectors needed in a "
       "site-day equals the maximum number of charging sessions in progress: across the 825 "
       "site-day blocks the median is %d, the 90th percentile is %d and the maximum is %d. Under "
       "the declared provision of 20%% of spaces, connector availability is not the binding "
       "element once k is set to the declared provision, and the binding element is the energy "
       "that the observed dwell allows to be delivered [P05][P06]." % (_FACTS["conc_med"], _FACTS["conc_p90"], _FACTS["conc_max"])),
]

# --- 4. demand-dwell coupling and partial-energy targets ---
coupling_rows = [{'scenario': 'A_independent', 'target': '1.0', 'energy_rate': '0.5509718345044107', 'session_failure': '0.5980570734669095'}, {'scenario': 'A_independent', 'target': '0.75', 'energy_rate': '0.4534898107187165', 'session_failure': '0.5335458409228901'}, {'scenario': 'A_independent', 'target': '0.5', 'energy_rate': '0.33645165906232666', 'session_failure': '0.45066788099574984'}, {'scenario': 'A_independent', 'target': '0.25', 'energy_rate': '0.1944240833160746', 'session_failure': '0.33211900425015184'}, {'scenario': 'B_dwell_conditioned', 'target': '1.0', 'energy_rate': '0.7092626243010721', 'session_failure': '0.42091681845780204'}, {'scenario': 'B_dwell_conditioned', 'target': '0.75', 'energy_rate': '0.5640439403763762', 'session_failure': '0.3542805100182149'}, {'scenario': 'B_dwell_conditioned', 'target': '0.5', 'energy_rate': '0.40158293270136863', 'session_failure': '0.2846083788706739'}, {'scenario': 'B_dwell_conditioned', 'target': '0.25', 'energy_rate': '0.21788650163089843', 'session_failure': '0.192167577413479'}]
CPL_SECTION = [
 ("h2", "5.12 Charging demand coupled to dwell, and partial-energy targets"),
 ("p", "The main scenario draws charge intention independently of dwell. That independence is a "
       "scenario assumption, not an observation: the source records parked vehicles and no EV "
       "label. Because the independence assumption is what makes short sessions fail, we run a "
       "second demand mechanism as a post-hoc analysis, planned and dated before it was run "
       "(see the reproducibility package). In mechanism B the propensity to need a charge rises "
       "with dwell (a logistic link in dwell, one standard deviation of dwell corresponding to "
       "an odds ratio of exp(1)); requests are then selected by weighted sampling without "
       "replacement so that the number of charge requests, the number of EVs and the multiset of "
       "requested energies are exactly those of mechanism A. Only who asks changes; total demand "
       "does not, requested energy is never cropped by the deliverable energy, and no hard "
       "request is deleted. Mechanism B is a scenario, not a parameter identified from this "
       "data [P06][P26]."),
 ("table", {"caption": "Table 7 Ideal delivery upper bound min(f x E, P x T) at 22 kW: independent demand (A) against dwell-conditioned demand (B), for pre-recorded target fractions f.",
            "header": ["demand mechanism", "target fraction f", "ideal energy rate", "session success", "session failure"],
            "rows": [['A independent', '1.0', '55.1%', '40.2%', '59.8%'], ['A independent', '0.75', '45.3%', '46.6%', '53.4%'], ['A independent', '0.5', '33.6%', '54.9%', '45.1%'], ['A independent', '0.25', '19.4%', '66.8%', '33.2%'], ['B dwell-conditioned', '1.0', '70.9%', '57.9%', '42.1%'], ['B dwell-conditioned', '0.75', '56.4%', '64.6%', '35.4%'], ['B dwell-conditioned', '0.5', '40.2%', '71.5%', '28.5%'], ['B dwell-conditioned', '0.25', '21.8%', '80.8%', '19.2%']]}),
 ("p", "Coupling demand to dwell raises the ideal energy rate at full completion from 55.1% to "
       "70.9% and lowers the session failure rate from 59.8% to 42.1%, but it does not reach the 5% "
       "standard even when the target is a quarter of the requested energy (19.2% session failure "
       "under B). The reason is the short tail of roadside dwell: some observed stays cannot "
       "deliver even a small top-up. Scaling dwell by plus or minus 12% as a stress test moves the "
       "full-completion session failure rate between 63.2% and 57.1% under A and between 45.8% and "
       "39.4% under B; the plus or minus 12% band is a diagnostic range, not a confidence interval."),
 ("p", "Partial-energy targets are defined before any run: f = 1.0 (complete charge during this "
       "stay, the original standard), 0.75, 0.50 and 0.25 of the requested energy. The upper "
       "bound shows that no target fraction is attainable by equipment alone under either demand "
       "mechanism, so no full enumeration in k is run for these targets. A null result at the "
       "level of the upper bound is the honest report; it is not converted into a recommendation "
       "of a larger k or a smaller energy."),
 ("h2", "5.13 Conditional decision boundary"),
 ("table", {"caption": "Table 8 Conditional decision boundary. Each row states which decision variable is constrained, the demand mechanism and target, the upper-bound status and the resulting configuration status.",
            "header": ["analytic unit", "capacity basis", "demand mechanism / target", "power / feeder", "upper-bound status", "configuration status"],
            "rows": [
              ["site-day stream (825 blocks)", "observed distinct bays", "A / complete charge", "22 kW / k x 22 kW", "session failure 59.8%", "no feasible k in the declared domain; energy-in-dwell binding"],
              ["site-day stream", "observed distinct bays", "A / f = 0.25", "22 kW / k x 22 kW", "session failure 33.2%", "no feasible k by the 5% standard"],
              ["site-day stream", "observed distinct bays", "B / complete charge", "22 kW / k x 22 kW", "session failure 42.1%", "no feasible k; correlation alone insufficient"],
              ["site-day stream", "observed distinct bays", "B / f = 0.25", "22 kW / k x 22 kW", "session failure 19.2%", "no feasible k by the 5% standard"],
              ["connector-only bound", "max concurrent charge sessions", "A (any target)", "n/a", "median %d, p90 %d, max %d" % (_FACTS["conc_med"], _FACTS["conc_p90"], _FACTS["conc_max"]), "connectors alone are not the binding constraint"],
              ["zero-demand block", "observed distinct bays", "no charge request", "n/a", "not applicable", "k = 0 is trivially sufficient and is not reported as a planning result"]]}),
]

anchor = None
for i, (k, t) in enumerate(MAIN):
    if k == "table" and isinstance(t, dict) and "Representative-site recommendation" in t.get("caption", ""):
        anchor = i
if anchor is None:
    raise SystemExit("recommendation table anchor not found")
MAIN[anchor + 1:anchor + 1] = METRIC_SECTION + CPL_SECTION
FIGURE_PLAN = FIGURE_PLAN

# --- 5. citations in the data paragraph ---
for i, (k, t) in enumerate(MAIN):
    if k == "p" and t.startswith("Source. The parking observations are"):
        MAIN[i] = (k, t.rstrip() + " The dataset is distributed under CC BY 4.0 and must be attributed [D1]; the licence and version are recorded in the reproducibility package.")
        break
for i, (k, t) in enumerate(MAIN):
    if k == "p" and t.startswith("Rules and baselines."):
        MAIN[i] = (k, t.rstrip() + " The literature-adapted baseline borrows the admission order and rolling reservation idea of [M07] and the online admission structure of [P26]; [P09] is cited at index level only and no pricing result is attributed to it.")
        break
SI = SI + [
 ("h1", "S10 Metric versions, unit rules and the relative-difference fix"),
 ("p", "Version note. The capacity-only unmet share is defined exactly as admission refusals plus departed shortfall sessions over charge requests, and it is not an access measure. Earlier drafts displayed the hold-out versus calibration mean dwell difference through a token that printed 0.12 where the value is 11.96%; the token now carries an explicit scale of 100 and the build fails if a token immediately followed by a percent sign lacks that scale. The raw column holdout_mean_rel_error is (mean_calibration - mean_test) / mean_calibration on dwell minutes; it is a level difference between blocks, not a prediction error."),
 ("p", "The five metrics in Table 6 have separate numerators and denominators and are never compared across versions under the same name. The energy ledger counts a refused charge request with zero delivered energy in the denominator, so the energy shortfall ratio includes refused requests."),
]
