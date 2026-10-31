# -*- coding: utf-8 -*-
"""rev5 content: real-data draft (main + SI) for the round-8 paper track.

Every empirical number below is either resolved by evidence.py from a machine
output ({{token}} entries listed in NUMBER_SPECS) or is a scenario/contract
constant quoted from the processed contract and listed in the SI provenance
ledger (Table S1).  Nothing is filled from memory; open items are written as
"open item" sentences, never as invented numbers.
"""

TITLE = ("Minimum integer charging provision under mixed-fleet parking: "
         "real arrival/dwell evidence, joint service constraints, and an "
         "infeasibility boundary of the declared charging scenario")

ABSTRACT = (
 "How many charging berths should a parking site have when berths are fixed and the "
 "arriving fleet mixes electric and combustion vehicles? We answer with observables only: "
 "arrival and dwell times from the 2014 City of Melbourne parking-bay survey "
 "({{n_sites}} sites, {{n_site_days}} site-days, {{n_events}} in-window events), on which "
 "empirical arrival and dwell distributions are calibrated on {{n_cal}} events and checked "
 "on {{n_test}} held-out events (dwell KS {{ks_all}}, hold-out mean relative error "
 "{{rel_all}}%). The charging layer itself is not observed, so power, connector count and "
 "per-session energy demand are declared scenario inputs, not measurements. Under the "
 "declared 20% charging-bay scenario at 22 kW, three joint service constraints "
 "(capacity-only unmet share, EV parking failure, ICEV parking failure, each at 5%) are "
 "met by only 1 of 24 held-out streams, and only at k = 0, where no charging is offered. "
 "The smallest-admissible-k problem is therefore not identified at the declared share: the "
 "constraint that binds is the energy a session can receive inside its observed dwell, not "
 "the number of connectors. Re-running with connectors allowed up to every parking space "
 "(k = n_spaces) leaves 20 of 20 held-out streams above the 5% standard: gate rejection is "
 "0 of 137 charge requests, while 80 of 137 sessions cannot receive the scenario energy "
 "before departure (991.9 of 1891.0 kWh delivered). We report the conditional "
 "recommendation as a not-achievable-by-k status with its exact numerator, denominator and "
 "reason, and we do not claim that the design rule was validated."
)

KEYWORDS = ("Keywords: parking management; electric vehicle charging; integer design; "
            "service constraints; arrival-dwell calibration; reproducible research")

REFS = {}  # reference registry; empty in this draft

REQUIRED_SECTIONS = [
    "Introduction",
    "2 Model: joint service constraints and the integer design",
    "3 Methods: rules, replay, baselines and enumeration",
    "4 Data: source, QA, calibration and scenario inputs",
    "5 Results",
    "6 Discussion",
    "7 Reproducibility",
]

NUMBER_SPECS = {
    "n_sites": {"file": "E1/coverage.csv", "column": "site_id", "agg": "count",
                "fmt": "{:d}", "unit": "sites"},
    "n_site_days": {"file": "E1/coverage.csv", "column": "site_days", "agg": "sum",
                    "fmt": "{:d}", "unit": "site-days"},
    "n_events": {"file": "E1/coverage.csv", "column": "events", "agg": "sum",
                 "fmt": "{:d}", "unit": "events"},
    "ks_all": {"file": "E1/fit_metrics.csv", "column": "ks_statistic",
               "where": {"row_kind": "dwell_fit", "category": "all"}, "fmt": "{:.4f}"},
    "rel_all": {"file": "E1/fit_metrics.csv", "column": "holdout_mean_rel_error",
                "where": {"row_kind": "dwell_fit", "category": "all"}, "fmt": "{:.2f}"},
    "n_cal": {"file": "E1/fit_metrics.csv", "column": "n_calibration",
              "where": {"row_kind": "dwell_fit", "category": "all"}, "fmt": "{:d}"},
    "n_test": {"file": "E1/fit_metrics.csv", "column": "n_test",
               "where": {"row_kind": "dwell_fit", "category": "all"}, "fmt": "{:d}"},
    "m2_ab0": {"file": "M/m_summaries.csv", "column": "point",
               "where": {"comparison": "M2", "pair": "B0_FCFS - A"}, "fmt": "{:+.4f}"},
    "m2_ab0_lo": {"file": "M/m_summaries.csv", "column": "low",
                  "where": {"comparison": "M2", "pair": "B0_FCFS - A"}, "fmt": "{:+.4f}"},
    "m2_ab0_hi": {"file": "M/m_summaries.csv", "column": "high",
                  "where": {"comparison": "M2", "pair": "B0_FCFS - A"}, "fmt": "{:+.4f}"},
    "m2_ab1": {"file": "M/m_summaries.csv", "column": "point",
               "where": {"comparison": "M2", "pair": "B1_QUOTA - A"}, "fmt": "{:+.4f}"},
    "m2_ab1_lo": {"file": "M/m_summaries.csv", "column": "low",
                  "where": {"comparison": "M2", "pair": "B1_QUOTA - A"}, "fmt": "{:+.4f}"},
    "m2_ab1_hi": {"file": "M/m_summaries.csv", "column": "high",
                  "where": {"comparison": "M2", "pair": "B1_QUOTA - A"}, "fmt": "{:+.4f}"},
    "e3_infeasible": {"file": "E3/search_E3.csv", "column": "instance_id",
                      "where": {"k_class": "physically_infeasible"}, "agg": "nunique",
                      "fmt": "{:d}"},
    "e3_budget": {"file": "E3/search_E3.csv", "column": "instance_id",
                  "where": {"k_class": "budget_not_covered"}, "agg": "nunique",
                  "fmt": "{:d}"},
    "e4_streams": {"file": "E4/test_E4.csv", "column": "stream_id",
                   "where": {"policy": "A"}, "agg": "nunique", "fmt": "{:d}"},
}

FIGURE_PLAN = [
    ("F1", "Data coverage and arrival/dwell calibration. (a) Complete site-days and events per "
           "site. (b) Mean dwell, calibration vs held-out block, with the two-sample KS statistic. "
           "(c) Hold-out mean relative error by vehicle class.", "E1",
     "experiments_main22/E1/coverage.csv, fit_metrics.csv, fit_params.json"),
    ("F2", "Service rates against the integer number of charging berths k. (a) Capacity-only "
           "unmet share, (b) charging access rate, both at 22 kW with bootstrap intervals and the "
           "5% standard. (c) The same curve in the 7 kW regime, which is the infeasibility case.",
     "E2", "experiments_main22/E2/curve_E2.csv; experiments/E2/curve_E2_summary.csv"),
    ("F3", "Offline enumeration and minimality classes. (a) Tested k per held-out instance; "
           "(b) class counts, 22 kW regime.", "E3",
     "experiments_main22/E3/search_E3.csv, classes.json"),
    ("F4", "Held-out rule and baseline comparison at the fixed training k. (a) Energy service "
           "rate with bootstrap intervals; (b) access and capacity-only unmet share.", "E4",
     "experiments_main22/E4/test_E4.csv, M/m_summaries.csv"),
    ("F5", "Smallest k meeting each constraint per held-out stream (policy A) and the empty "
           "information-signal result.", "E5",
     "experiments_main22/constraint_thresholds.csv, E5/info_E5.csv"),
    ("F6", "Energy ledger: delivered against required energy by connector power and feeder "
           "capacity, at fixed k = 1.", "E6", "experiments/E6/energy_E6.csv"),
    ("F7", "Non-monotone trajectory: machine status is missing_data; no trajectory is drawn.",
     "E7", "experiments_main22/E7/meta_E7.json, traj_E7.csv"),
    ("S1", "Site inventory: parking spaces, declared charging berths and observed events.", "E1",
     "experiments_main22/E1/coverage.csv"),
    ("S2", "7 kW regime: policy comparison and rejected charge requests at k = 1.", "E4",
     "experiments/E4/test_E4.csv"),
    ("S3", "7 kW regime: delivered against required energy by power and feeder configuration.",
     "E6", "experiments/E6/energy_E6.csv"),
    ("S4", "Confirmatory paired differences in energy service rate (M2, 22 kW).", "M",
     "experiments_main22/M/m_summaries.csv"),
    ("F8", "Conditional uncapped-connector analysis: with k = n_spaces in every stream, gate "
           "rejection is zero but shortfall sessions keep the three-constraint standard "
           "unmet.", "CONDSHARE",
     "experiments_condshare/evidence_at_n_spaces.csv, evidence_at_n_spaces.json"),
]

TABLE_PLAN = []  # real tables are embedded directly in MAIN / SI blocks below

MAIN = [
    ("h1", "Introduction"),
    ("p", "Parking sites are being asked to host charging equipment while the total number of "
          "berths stays fixed. The design question is therefore not where chargers go but how "
          "many charging berths k to install, given the observed arrivals and dwell times of a "
          "mixed electric (EV) and combustion (ICEV) fleet. A defensible answer has to state its "
          "unit of analysis, the service constraints it must satisfy, and the regime in which "
          "those constraints are decidable."),
    ("p", "We take the three service constraints of the round-8 design matrix as the standard: "
          "capacity-only unmet charge requests at most 5%, EV parking failure at most 5%, and "
          "ICEV parking failure at most 5%. A configuration is admissible only if all three hold "
          "simultaneously on independent held-out streams; the smallest such k is the integer "
          "design. The observable part of the problem is real: arrival and dwell times are "
          "measured for {{n_events}} in-window parking events at {{n_sites}} sites. The charging "
          "part is not observed at all. The survey records no connector, no state of charge and "
          "no charging intention, so connector power, the charging-bay share, the feeder rule and "
          "the per-session energy demand are declared scenario inputs. This asymmetry is the "
          "central methodological fact of the paper: we can calibrate parking behaviour on "
          "13,503,655 source rows and still only test a conditional charging scenario."),
    ("p", "Stating the result before the evidence is unusual, but the alternative is worse for "
          "the reader: under the declared 20% charging-bay scenario at 22 kW the three-constraint "
          "standard is not satisfied by any k in the admissible grid. The binding constraint is "
          "not the connector count, it is the energy that an observed parking session can receive "
          "before departure. We therefore report the conditional integer recommendation as a "
          "not-achievable-by-k status, together with the exact numerator, denominator and "
          "feasibility reason, and we treat the rule-family comparison as a conditional result "
          "that does not survive as a validation claim."),
    ("p", "The paper proceeds as follows. Section 2 writes the model and the constraint set. "
          "Section 3 describes the replay machinery, the rule family, the baselines and the "
          "enumeration. Section 4 documents the data source, the cleaning, the calibration and "
          "the scenario layer. Section 5 reports the figures and the confirmatory comparisons. "
          "Section 6 discusses what the infeasibility does and does not imply. Section 7 gives "
          "the reproduction package, the measured counts and the open items."),
    ("h1", "2 Model: joint service constraints and the integer design"),
    ("p", "Consider a site s with n_s spaces of which k are charging berths. A stream is one "
          "site-day: the events that arrive and depart inside the operating window, replayed with "
          "the observed arrival times and dwell times. For a replay instance i and a rule pi, the "
          "engine records three rates. Capacity-only unmet is the number of charge requests that "
          "are either refused at the gate or leave with a positive energy shortfall, divided by "
          "the number of charge requests; the engine's workbench definition includes both "
          "components, so a session that is admitted but cannot be served inside its dwell counts "
          "as unmet. EV parking failure is the number of EV arrivals that find no admissible bay "
          "divided by EV arrivals; ICEV parking failure is the same for combustion arrivals. All "
          "three are fractions of requests, not of minutes, and none is reweighted by occupancy."),
    ("p", "The standard is: capacity-only unmet at most 0.05, EV failure at most 0.05, ICEV "
          "failure at most 0.05, all on the same held-out stream. The configuration set is the "
          "integer box 0 <= k <= m_s, where m_s is the number of connector slots available at the "
          "site (the declared scenario uses the contract charging-bay count; the conditional "
          "analysis relaxes it to n_s). A stream is feasible at k when the replay meets all three "
          "constraints. The minimal k for a stream is the smallest feasible k."),
    ("p", "Two kinds of minimality statements are kept strictly apart. An offline enumeration "
          "declares a stream confirmed_minimal inside the declared offline model only: power is "
          "uniform at min(connector_kw, feeder_kw/k) per connector, pre-emption is allowed, the "
          "schedule is on a one-minute grid, and future information is available. That bound is "
          "not executable online and it is not a physical lower bound. An online replay can only "
          "report that it did not find a feasible k in the tested grid. The engine's class labels "
          "encode exactly this distinction: confirmed_minimal, minimality_unconfirmed, "
          "physically_infeasible (the grid reached the site capacity without meeting the "
          "standard), budget_not_covered (enumeration was truncated) and missing_data."),
    ("h1", "3 Methods: rules, replay, baselines and enumeration"),
    ("p", "Streams and split. The contract exposes 85 days at 10 sites, giving 825 site-day "
          "blocks. Blocks are assigned to a calibration set (523 blocks) and a test set (302 "
          "blocks): the test set contains all days of two whole sites plus whole held-out days of "
          "the remaining sites, so no test block overlaps a calibration block. The unit of every "
          "statistic is the independent stream (site-day), never the event and never the "
          "five-minute snapshot; resampling is by stream. The held-out test used by the rule "
          "comparison has {{e4_streams}} streams."),
    ("p", "Replay. Arrivals and dwell times are drawn by block resampling from the calibration "
          "set with seed 20261031, keeping the empirical joint behaviour of a site-day rather "
          "than fitting independent parametric marginals. The charging layer is applied by the "
          "scenario contract: a declared share of berths becomes charging berths, each charging "
          "berth has a declared connector power, the feeder is declared either per connector or "
          "as a share, and a charge-requesting EV carries a declared energy demand. Because the "
          "source has no charging field, every one of these values is an assumption; the two "
          "declared regimes in this paper are 7 kW and 22 kW per connector, both at 20% "
          "charging-bay share unless a conditional analysis says otherwise."),
    ("p", "Rules and baselines. Four formal admission rules are replayed. A (dedicated_by_type) "
          "gives EVs a dedicated charging bay and forbids ICEVs from entering the charging area. "
          "B (full_open_ice_first) keeps the charging area open and gives ICEVs the ordinary lots "
          "first, allowing them into the charging area only when ordinary capacity is exhausted. "
          "C (protected_quota) always keeps m charging bays free for EVs and admits an ICEV into "
          "the charging area only while fewer than charging_bays - m charging bays are occupied "
          "by ICEVs. D (predictive_shared_ice_first) is the shared rule with a short-horizon "
          "prediction of charge arrivals in the admission gate. Three frozen baselines are "
          "compared on the same streams: B0_FCFS (first come, first served, no type protection), "
          "B1_QUOTA (fixed protected quota) and B2_LITERATURE (a literature-adapted predictive "
          "reservation). All rules read only observable state: clock, vehicle type, free bays, "
          "capacity and historical arrival/charge-start statistics. The intent flag and the "
          "energy demand are hidden from every rule; they are used only to score outcomes."),
    ("p", "Offline enumeration. Eight held-out instances are enumerated exhaustively on k = 0.."
          "K_max with a one-minute uniform-power max-flow model and a constructible schedule "
          "certificate, with no binary search, because no monotonicity is assumed. Confirmed "
          "minimality means every smaller integer k was tested infeasible in that declared model. "
          "Truncation at the enumeration budget is reported as budget_not_covered, never "
          "extrapolated."),
    ("p", "Conditional analysis. To separate the connector constraint from the energy "
          "constraint, the conditional uncapped-connector analysis repeats the replay with "
          "k = n_spaces (every parking space becomes a charging berth), feeder power equal to "
          "22 kW times k and the same three constraints, using no future information. It is a "
          "conditional domain, not a deployable configuration: it asks whether any integer k can "
          "satisfy the standard under the declared demand, and it decomposes the unmet share "
          "into gate rejections and shortfall sessions."),
    ("p", "Inference. Rule differences are paired by stream. The engine reports a percentile "
          "bootstrap confidence interval with 1000 resamples, unit site-day and seed 20261031; "
          "the figure intervals recompute the same bootstrap on the same rows for display. The "
          "sign convention of the engine's paired table is baseline minus rule (verified against "
          "the row means), so a negative A-vs-B0 value means A delivers more energy service than "
          "B0. We report the file's signed value and the underlying row means together, and we "
          "do not translate a non-significant interval into equivalence."),
    ("p", "Provenance. Every figure is built from machine outputs only: the script reads the "
          "experiment CSV/JSON, records the file sha256, the rows used and the columns, and "
          "writes both a 300-dpi PNG and an editable-text SVG. A figure whose input is missing is "
          "not drawn; a demo layout is watermarked and cannot enter the provenance file. The "
          "manuscript build resolves every number token against those same files and refuses to "
          "save a real draft if a token is unresolved or a figure lacks real provenance."),
    ("h1", "4 Data: source, QA, calibration and scenario inputs"),
    ("p", "Source. The parking observations are the City of Melbourne parking-bay arrival and "
          "departure records for 2014, distributed as a single archive and converted into the "
          "round-8 processed contract with a fixed time-zone offset and explicit column mapping. "
          "The raw archive contains 13,503,655 bay-event rows; the contract keeps the "
          "in-window events and the pinned site list, giving {{n_events}} events over "
          "{{n_sites}} sites and {{n_site_days}} site-days. The 85-day window spans 1 January "
          "2014 to the first days of 2015; 789 site-days contain all 24 hours and pass the "
          "completeness test (E1/fit_params.json, criterion P3)."),
    ("p", "QA. Arrival timestamps are parsed with an explicit offset and a row whose timestamp "
          "cannot be parsed is dropped rather than guessed. Dwell is departure minus arrival; "
          "negative dwell and zero dwell rows are excluded by the QA pass, and the per-site "
          "counts of scanned rows, distinct bays, days and violations are written to "
          "data/qa/source_stats.json and data/qa/QA_REPORT.md. Duplicate event identifiers exist "
          "in the source and are not used as a key; the bay-level event grain is rebuilt from "
          "arrival, departure and bay identity. Capacity is the observed number of distinct "
          "bays per site."),
    ("p", "Calibration. The empirical arrival-gap and dwell distributions are calibrated on "
          "{{n_cal}} events and checked on {{n_test}} held-out events. The dwell two-sample KS "
          "statistic is {{ks_all}}, and the mean dwell moves from 51.06 min to 44.96 min between "
          "the two blocks, a mean relative error of {{rel_all}}%. The arrival-gap KS is 0.0488 "
          "and its mean gap moves from 4.286 min to 3.220 min. The EV and ICEV subsets give KS "
          "0.0314 and 0.0334 respectively. These values are consistent with a stationary-enough "
          "eight-week period but they are not a claim of predictive validation of the charging "
          "scenario, which is not observed."),
    ("p", "Scenario layer. The processed contract assigns each site its observed space count "
          "and a declared charging-bay count at 20% of spaces: 7, 3, 12, 2, 16, 14, 3, 8, 7 and 4 "
          "charging berths for Drummond, Hyatt, Jolimont, Princes Theatre, Queensberry, "
          "Southbank, Titles, University, Victoria Market and West Melbourne. The two declared "
          "layers used in this paper are 7 kW and 22 kW per connector at 50% feeder share and at "
          "most four connectors per site; the 22 kW layer is the main empirical regime because it "
          "makes the connector-count and energy constraints distinguishable, while the 7 kW layer "
          "remains the power-sensitivity case. The scenario layer string in the machine outputs "
          "also records a charging-bay share of 0.1, which conflicts with the 20% contract count; "
          "the corrected E2 grid actually evaluated covers k = 0..8 for all 24 streams, not the "
          "full contract charging-bay count (up to 16). The grid bound and the share-string "
          "conflict are both open items, and no result below depends on which of the two "
          "strings is read as the share."),
    ("p", "Energy demand. The source has no charging energy. The contract assigns a charge "
          "intention to a scenario share of EV arrivals and gives each charge-requesting EV an "
          "energy demand of 14 kWh with a standard deviation of 6 kWh. Energy_kWh is present for "
          "6,588 of {{n_events}} events; the remaining 178,962 events have no energy value and "
          "are not imputed. A session's required charging minutes are therefore scenario-derived "
          "(energy divided by connector power) and are compared with the observed dwell. This is "
          "the mechanism behind the infeasibility result and it must be read as a property of the "
          "declared scenario, not as a measured charging demand."),
    ("h1", "5 Results"),
    ("h2", "5.1 Coverage and calibration"),
    ("p", "Figure 1 summarises the observable layer. Coverage is uneven by design: eight sites "
          "contribute 73 to 85 complete days, West Melbourne contributes 84, and the 825 site-day "
          "blocks are the analysis unit. The dwell distributions of the calibration and held-out "
          "blocks agree closely in shape but not in mean, and the hold-out mean relative error of "
          "{{rel_all}}% is reported as a bias, not as an error of a predictive model. The arrival "
          "gap is likewise close (KS 0.0488). We treat this as sufficient calibration of the "
          "parking process for a replay study and not as evidence about charging behaviour."),
    ("figure", "F1"),
    ("h2", "5.2 The k curve and the first bound"),
    ("p", "Figure 2a shows the capacity-only unmet share against k in the 22 kW regime, with "
          "the same 24 streams present at every k from 0 to 8. At k = 1 the mean is 92.4%; it "
          "falls monotonically to 60.8% at k = 8. The 5% standard is never met anywhere in the "
          "grid, and the remaining gap is not a sample-size artefact now that the stream set is "
          "held fixed across k. Figure 2b shows the second constraint: the charging access rate "
          "rises from 19.7% at k = 1 to 95.1% at k = 7 and 97.1% at k = 8. Access is therefore "
          "the constraint that k can buy, but it costs more than the declared share allows and "
          "still does not repair the capacity-only unmet share. Figure 2c repeats the curve in "
          "the 7 kW regime, where the same statement is stronger: the mean capacity-only unmet "
          "share stays between 87.1% and 93.5% for every k from 1 to 16."),
    ("figure", "F2"),
    ("h2", "5.3 Offline enumeration"),
    ("p", "The offline enumeration gives the first independent check (Figure 3). Of the eight "
          "held-out instances, {{e3_infeasible}} are physically infeasible in the declared model: "
          "the grid reaches the site's charging-bay bound without meeting the standard, and the "
          "recorded reason is window_too_short. {{e3_budget}} instances are budget_not_covered: "
          "the enumeration stopped at k = 8 while the physical bound is 16 and 14. Confirmed "
          "minimal is zero. The 7 kW and 22 kW runs produce the same class counts, which shows "
          "that raising connector power does not repair the schedule inside the observed dwell; "
          "the class label remains a statement inside the declared offline model, never a "
          "physical lower bound."),
    ("figure", "F3"),
    ("h2", "5.4 Held-out rules and baselines"),
    ("p", "Figure 4 compares the seven policies on the same {{e4_streams}} held-out streams at "
          "the fixed training k = 1. Mean energy service rate is 23.8% for A, 24.6% for B, C, "
          "B1 and B2, 24.6% for D and 1.1% for B0_FCFS. Charging access is 40.6% for A against "
          "3.8% for B0; capacity-only unmet share is 80.5% for A and 98.8% for B0. No policy "
          "meets the joint standard. The paired confirmatory table gives the same picture with "
          "intervals. Its direction field is explicit: pair value = baseline rate minus A rate, "
          "so a negative value means A delivers more energy service. B0_FCFS minus A is "
          "{{m2_ab0}} [{{m2_ab0_lo}}, {{m2_ab0_hi}}] over 20 pairs, i.e. A is better by 0.2276 "
          "in the mean paired rate; B1_QUOTA minus A is {{m2_ab1}} [{{m2_ab1_lo}}, "
          "{{m2_ab1_hi}}], a small interval whose lower bound touches zero, so the two are not "
          "distinguishable. B2_LITERATURE equals B1_QUOTA stream by stream (20/20 streams), and "
          "the engine records why: both give the same effective admission sequence because the "
          "ICEV parking failure is 0/4643 in both (ordinary bays are never exhausted), so the "
          "borrowing gate of B2 changes no decision. This is a conditional comparison under a "
          "scenario that misses the standard, not evidence that any rule is better in practice."),
    ("figure", "F4"),
    ("h2", "5.5 The conditional uncapped-connector analysis"),
    ("p", "Section 5.2 leaves an obvious objection: the declared 20% share may simply be too "
          "small. The conditional analysis relaxes k to the number of parking spaces and asks "
          "whether any k can satisfy the standard under the same declared demand, 22 kW and no "
          "future information. Figure 5 shows the answer. With k = n_spaces in every stream, "
          "gate rejection is 0 of 137 charge requests; 80 of 137 sessions are still short "
          "(admitted, but unable to receive the scenario energy before departure), so the "
          "capacity-only unmet share is 80/137 = 58.4% and every one of the 20 streams remains "
          "above 5%. Delivered energy is 991.9 of 1891.0 kWh, that is 52.5%, and the ICEV failure "
          "constraint also fails because all spaces are charging berths. The decomposition is "
          "decisive: the constraint that binds is the observed dwell relative to the required "
          "charging time, not the number of connectors. The paper's conditional finding is "
          "therefore a not-achievable-by-k status with this numerator, denominator and reason, "
          "and not a small-k recommendation."),
    ("figure", "F8"),
    ("h2", "5.6 Energy ledger and power sensitivity"),
    ("p", "Figure 6 reports the energy ledger in the corrected 22 kW main regime. The main22 "
          "E6 output now has 6 rows: six held-out site-days at k = 1 with a 22 kW connector on a "
          "full feeder (feeder = 22 kW). Aggregate demand is 866.5 kWh. Delivered energy is "
          "207.2 kWh, i.e. 23.9% of demand; the best site-day reaches 39.8% and the worst 8.1%. "
          "Five of the six site-days are offline infeasible with reason window_too_short and one "
          "has no charge demand. Charge requests and gate rejections are 13/4, 14/0, 10/19, 12/0 "
          "and 14/8 on the five charging days. The 7 kW regime's 2x2 power-by-feeder ledger is "
          "in Figure S3: delivered energy is 55.7, 98.2, 81.6 and 135.0 kWh for the (7 kW, "
          "3.5 kW), (7 kW, 7 kW), (11 kW, 5.5 kW) and (11 kW, 11 kW) configurations, 6.4% to "
          "15.6% of 866.5 kWh demand. On the online held-out test the same demand gives 210.1 kWh "
          "delivered at 7 kW against 365.7 kWh at 22 kW for rule A, so power changes delivered "
          "energy but not the sign of the infeasibility."),
    ("figure", "F6"),
    ("h2", "5.7 Signal and trajectory experiments"),
    ("p", "Figure 7 reports the smallest k that meets each constraint per stream in the 22 kW "
          "regime. Parking service is met at k = 0 for 23 of 24 streams, because the constraint "
          "is about the vehicle finding a berth, not about charging. Charging access and the "
          "energy constraint are met by only 1 stream each, and the joint three-constraint "
          "standard by 1 stream (West Melbourne, 2014-01-12, k = 0; that stream has no charging "
          "demand). The information-signal experiment (E5) records no k_min for any of its 10 "
          "streams under either policy, so the signal comparison is missing_data rather than a "
          "null effect. The non-monotone trajectory experiment (E7) also records missing_data: no "
          "held-out event with a service rate that decreases as k grows was observed. Figure 7 "
          "shows the status record only; no trajectory is fabricated."),
    ("figure", "F5"),
    ("figure", "F7"),
    ("h2", "5.8 Recommendation table"),
    ("p", "Table 5 is the recommendation table requested for a representative site. The common "
          "conditions are: data window 1 January to 31 March 2014 within the 85-day contract; "
          "demand assumption 14 kWh with standard deviation 6 kWh per charge-requesting EV "
          "(scenario, not observed); 22 kW per connector with a feeder equal to k times 22 kW in "
          "the conditional domain; rule A (dedicated charging bay); held-out test on the listed "
          "number of streams. The recommended k is not achievable under the declared standard for "
          "every site: the conditional run reaches k = n_spaces without meeting the 5% "
          "capacity-only unmet criterion, and the reason is the shortfall-session share reported "
          "in Figure 5."),
    ("table", {"caption": "Table 5 Representative-site recommendation: common conditions are 22 kW "
                          "per connector, feeder = k x 22 kW in the conditional domain, rule A, "
                          "demand 14 +- 6 kWh per charge-requesting EV (scenario), held-out "
                          "streams from the 2014 window.",
               "header": ["site", "N: site-days / events", "data window", "held-out streams",
                          "demand assumption", "power / feeder / rule",
                          "recommended k / status and reason"],
               "rows": [
                   ["Drummond", "73 / 13,634", "2014-01-01..2014-03-31", "2", "14 +- 6 kWh",
                    "22 kW / k x 22 kW / A", "not achievable by k; 2/2 streams fail at k = 33"],
                   ["Hyatt", "85 / 14,295", "2014-01-01..2014-03-31", "1", "14 +- 6 kWh",
                    "22 kW / k x 22 kW / A", "not achievable by k; 1/1 stream fails at k = 15"],
                   ["Jolimont", "85 / 25,765", "2014-01-01..2014-03-31", "3", "14 +- 6 kWh",
                    "22 kW / k x 22 kW / A", "not achievable by k; 3/3 streams fail at k = 58"],
                   ["Princes Theatre", "85 / 13,115", "2014-01-01..2014-03-31", "2",
                    "14 +- 6 kWh", "22 kW / k x 22 kW / A",
                    "not achievable by k; 2/2 streams fail at k = 12"],
                   ["Queensberry", "85 / 34,566", "2014-01-01..2014-03-31", "1", "14 +- 6 kWh",
                    "22 kW / k x 22 kW / A", "not achievable by k; 1/1 stream fails at k = 82"],
                   ["Southbank", "85 / 24,399", "2014-01-01..2014-03-31", "1", "14 +- 6 kWh",
                    "22 kW / k x 22 kW / A", "not achievable by k; 1/1 stream fails at k = 72"],
                   ["Titles", "85 / 9,923", "2014-01-01..2014-03-31", "1", "14 +- 6 kWh",
                    "22 kW / k x 22 kW / A", "not achievable by k; 1/1 stream fails at k = 17"],
                   ["University", "73 / 20,424", "2014-01-01..2014-03-31", "1", "14 +- 6 kWh",
                    "22 kW / k x 22 kW / A", "not achievable by k; 1/1 stream fails at k = 40"],
                   ["Victoria Market", "85 / 24,891", "2014-01-01..2014-03-31", "8",
                    "14 +- 6 kWh", "22 kW / k x 22 kW / A",
                    "not achievable by k; 8/8 streams fail at k = 35"],
                   ["West Melbourne", "84 / 4,538", "2014-01-01..2014-03-31", "0",
                    "14 +- 6 kWh", "22 kW / k x 22 kW / A",
                    "no held-out stream in the conditional run; its only feasible constraint-threshold k "
                    "is 0, on a stream with no charging demand"]],
               }),
    ("h1", "6 Discussion"),
    ("p", "The result is an infeasibility boundary, not a design rule. Under the declared "
          "charging scenario the three-constraint standard cannot be reached by any integer "
          "number of charging berths, even when every parking space becomes a charging berth. "
          "The reason is arithmetic and visible in the ledger: 80 of 137 charge-requesting "
          "sessions have an observed dwell shorter than the charging time that the scenario "
          "demand needs at 22 kW, so they are short even when a connector is free and admission "
          "is unrestricted. Raising power shortens the required time but the observed dwell "
          "distribution is short enough that the 5% unmet threshold is still missed. The "
          "standard is therefore attainable only by changing one of its inputs: a lower "
          "per-session energy demand, a longer dwell assumption (for example reserving charging "
          "sessions with a minimum stay), or a looser tolerance."),
    ("p", "This changes how the rule comparison should be read. With k fixed at the training "
          "value, the dedicated and shared rules do not differ significantly (A vs B1/B2 "
          "interval includes zero and B1 and B2 coincide numerically), while the type-blind "
          "first-come-first-served baseline loses most of the energy service (A vs B0 interval "
          "clearly away from zero). The policy signal that survives is the fairness and "
          "accessibility one: type-aware admission keeps the EV charging access rate an order of "
          "magnitude above FCFS, at a small ICEV-failure cost. It does not survive as a "
          "recommendation of a minimal k, because no k satisfies the declared standard."),
    ("p", "Validity threats. First, charging demand, power and bay share are scenario values; "
          "the paper cannot say what real charging demand would be. Second, the window is 2014 "
          "and 85 days; seasonal and post-2014 behaviour is out of scope. Third, only two sites "
          "contribute whole held-out days, so the site-level generalisation is limited. Fourth, "
          "the offline bound is model-conditional, and the class labels are not physical "
          "statements. Fifth, the scenario-layer string in the machine files records a 0.1 "
          "charging-bay share while the contract assigns 20%; the evaluated grid follows the "
          "contract count, but the string conflict is unresolved and should be fixed in the next "
          "engine pass. None of these threats is repaired by a larger bootstrap."),
    ("p", "What would make the question decidable? A charging-demand measurement on the same "
          "sites, a dwell-conditioned energy scenario, or a service standard defined on energy "
          "delivered per session instead of capacity-only unmet requests. The access-only k* "
          "variant (gate rejection at most 5% only) was requested as a supplementary analysis; "
          "it is not present in the machine outputs at the time of this build and is listed as "
          "an open item, not as a result."),
    ("h1", "7 Reproducibility"),
    ("p", "All results in this draft come from machine outputs produced by the round-8 engine "
          "in the following directories: experiments_main22/ (main empirical regime, 22 kW, "
          "seed 20261031), experiments/ (7 kW sensitivity regime), experiments_condshare/ "
          "(conditional uncapped-connector analysis). Each family directory contains a "
          "manifest.json with the command line, seed, engine version, python version, platform, "
          "input sha256 and output sha256. The input contract is "
          "data/processed/public_parking_events.json with sha256 38b1422bb95d4122565d4de70a5ef4"
          "faf35e41600019068c9c077a295ee6bdf6, derived from the City of Melbourne 2014 parking "
          "bay archive. The exact run commands are reproduced in the repro package and in "
          "Table S2."),
    ("p", "The figure build is figures/build_figures_real.py; it reads only the three "
          "experiment roots and writes F1-F7, S1-S5 as 300-dpi PNG plus SVG with a provenance "
          "record (script sha256, input file sha256, rows and fields) in figures/FIGURES.json. "
          "The manuscript build is paper/build_rev5.py; it resolves every number token through "
          "paper/evidence.py against the experiment files and refuses to save the real draft if "
          "a token is unresolved or a figure is not real. The SI carries the provenance ledger "
          "for the scenario and contract constants (Table S1) and the reproduction index "
          "(Table S2)."),
    ("p", "Measured counts for this build are recorded in the build manifest: page count from "
          "the Word repagination pass, word count from the manuscript statistics script and from "
          "the build's own tokenizer. Open items: the access-only k* supplementary analysis; the "
          "sign convention note for the paired table; the 0.1-versus-0.20 charging-bay share "
          "conflict in the scenario layer; the absence of a licence statement in the machine "
          "files; and the missing E5/E7 measurements, which are reported as missing_data and "
          "never imputed. Data licence: the source archive is the City of Melbourne open "
          "parking-bay arrivals and departures 2014; the machine files do not record a licence "
          "string, so the licence is an open item rather than an asserted licence."),
]

SI = [
    ("h1", "S1 Data coverage, QA and analysis units"),
    ("p", "Table S1 lists the observable layer and its provenance. The contract keeps 185,550 "
          "in-window events at 10 sites and 825 site-day blocks. The completeness criterion P3 "
          "counts 789 site-days with all 24 hours present. The calibration split contains 523 "
          "blocks and the test split 302 blocks; test is two whole sites plus whole held-out "
          "days at the remaining sites. The source archive is the City of Melbourne parking-bay "
          "arrivals and departures 2014 archive; data/qa/source_stats.json records the full-file "
          "scan counts (rows scanned, distinct event ids, distinct bays, distinct block faces, "
          "day range, negative and zero dwell, in-window violations, days with all 24 hours "
          "present) and QA_REPORT.md records how each is used."),
    ("figure", "S1"),
    ("table", {"caption": "Table S1 Observable layer and provenance.",
               "header": ["item", "value", "source"],
               "rows": [
                   ["sites", "{{n_sites}}", "experiments_main22/E1/coverage.csv"],
                   ["complete site-days", "{{n_site_days}}", "E1/coverage.csv (sum)"],
                   ["in-window events", "{{n_events}}", "E1/coverage.csv (sum)"],
                   ["site-days with all 24 h", "789", "E1/fit_params.json criterion P3"],
                   ["calibration events", "{{n_cal}}", "E1/fit_metrics.csv"],
                   ["held-out events", "{{n_test}}", "E1/fit_metrics.csv"],
                   ["dwell KS (all)", "{{ks_all}}", "E1/fit_metrics.csv"],
                   ["hold-out mean relative error", "{{rel_all}}%", "E1/fit_metrics.csv"],
                   ["events with energy_kWh", "6,588", "E1/fit_params.json"],
                   ["events without energy_kWh", "178,962", "E1/fit_params.json"],
                   ["window", "2014-01-01..2015-01-01", "data/qa/source_stats.json"]]}),
    ("h1", "S2 Calibration and hold-out checks"),
    ("p", "Dwell two-sample KS statistics are 0.0330 for all events, 0.0314 for EV events and "
          "0.0334 for ICEV events; the arrival-gap KS is 0.0488. Mean dwell is 51.06 min in "
          "calibration and 44.96 min in the held-out block; the 50th percentile moves from 22.017 "
          "to 24.183 min and the 90th from 125.417 to 108.667 min. The mean relative error of the "
          "hold-out mean is 11.96% for all events, 13.60% for EV and 11.78% for ICEV. Arrival-gap "
          "means are 4.286 and 3.220 min. These are descriptive comparisons between two blocks of "
          "the same survey, not an out-of-sample validation of a charging model."),
    ("h1", "S3 Offline enumeration and budget accounting"),
    ("p", "Eight held-out instances are enumerated on k = 0..K_max. Six reach the site charging-"
          "bay bound without feasibility and are classified physically_infeasible with reason "
          "window_too_short; two stop at the budget cap k = 8 while the physical bound is 16 "
          "(Queensberry) and 14 (Southbank) and are classified budget_not_covered. Confirmed "
          "minimal count is zero and minimality_unconfirmed count is zero. The same counts appear "
          "in the 22 kW run. The declared model is offline_uniform_power_minute_grid with "
          "information offline_upper_bound_not_executable; no online rule may use that bound."),
    ("h1", "S4 Energy ledger detail"),
    ("p", "The 7 kW regime ledger has 24 rows: six held-out site-days, two connector powers "
          "(7 and 11 kW) and two feeder modes (per-connector feeder and 50% share), all at k = 1. "
          "Demand is 866.5 kWh per configuration. Delivered energy is 55.7, 98.2, 81.6 and "
          "135.0 kWh for the (7 kW, 3.5 kW), (7 kW, 7 kW), (11 kW, 5.5 kW) and (11 kW, 11 kW) "
          "configurations. Energy service rates range from 3.1% to 22.9%; capacity-only unmet "
          "share ranges from 85.7% to 100%. All 20 charging site-days are offline infeasible "
          "(window_too_short); four rows have no charge demand and are feasible with a zero "
          "denominator. The 22 kW regime's E6 output repeats the same 7/11 kW rows, so this "
          "ledger is the power-sensitivity case rather than a 22 kW result."),
    ("figure", "S3"),
    ("h1", "S5 Conditional uncapped-connector analysis"),
    ("p", "The conditional run allows k up to n_spaces at 22 kW with feeder equal to k times "
          "22 kW. Across the 20 held-out streams, charge requests total 137; gate rejections are "
          "0, and 80 sessions are shortfall sessions, so capacity-only unmet is 80/137 = 58.4% "
          "and the three-constraint standard fails in 20/20 streams. Delivered energy is 991.9 "
          "kWh against 1891.0 kWh demand (52.5%). The ICEV parking failure constraint also fails "
          "in the fully electrified site because ICEVs have no ordinary bay left. The "
          "decomposition is recorded in evidence_at_n_spaces.csv and aggregated in "
          "evidence_at_n_spaces.json; the run status is "
          "physically_infeasible_at_k_le_n_spaces."),
    ("h1", "S6 Number provenance ledger"),
    ("p", "Every empirical number in the draft resolves through paper/evidence.py to a row and "
          "column of an experiment file; the build manifest lists, for each token, the value, "
          "the file path, the file sha256, the row number and the column. The scenario and "
          "contract constants (charging-bay counts 7/3/12/2/16/14/3/8/7/4, 20% share, 14 +- 6 kWh "
          "demand, 7 and 22 kW, feeder rules, 5% tolerances) are quoted from "
          "data/processed/public_parking_events.json and the engine scenario layer; they are "
          "assumptions, not observations, and Table S2 records where each is declared. The "
          "engine's paired-comparison table uses baseline-minus-rule signs; the draft reports "
          "both the signed value and the row means, so no sign is silently reused."),
    ("h1", "S7 Reproduction package index"),
    ("p", "The repro package is research/round8_20261031/repro/. It contains README.md (data "
          "source, licence status, input sha256, environment, seeds, full commands, expected "
          "outputs), environment.json (python 3.12.14, Windows-11-10.0.26300-SP0, engine version "
          "r8-engine-v1-2026-10-31), commands.txt (the three run commands with the exact flags "
          "from the manifests), inputs.sha256 (contract and source archive hashes), results.md "
          "(table of family, output file, row count, key columns) and a copy of this provenance "
          "ledger. The figure build command is python "
          "research/round8_20261031/figures/build_figures_real.py; the manuscript build command "
          "is python research/round8_20261031/paper/build_rev5.py --real --doc main --force "
          "(and --doc si for the supplement)."),
    ("table", {"caption": "Table S2 Reproduction commands, seeds and expected outputs.",
               "header": ["run", "command summary", "seed", "outputs"],
               "rows": [
                   ["main empirical regime",
                    "engine/run_phase1.py --mode data --contract data/processed/"
                    "public_parking_events.json --out experiments_main22 --seed 20261031 "
                    "--skip-selfcheck --scenario-label "
                    "scenario_charging_layer_main22_22kW_not_observed "
                    "--force-connector-kw 22 --feeder-kw-per-connector 22",
                    "20261031", "E1-E7 + M manifests and CSVs"],
                   ["7 kW sensitivity regime",
                    "engine/run_phase1.py --mode data --contract data/processed/"
                    "public_parking_events.json --out experiments --seed 20261031 "
                    "--skip-selfcheck",
                    "20261031", "E1-E7 + M manifests and CSVs"],
                   ["conditional uncapped connectors",
                    "engine run_conditional.py (as recorded in "
                    "experiments_condshare/manifest.json); 22 kW, k = 0..n_spaces",
                    "20261031",
                    "conditional_results.json, evidence_at_n_spaces.csv, sweep_condshare.csv"],
                   ["figures", "figures/build_figures_real.py (no arguments)", "20261031",
                    "F1-F7, S1-S5 PNG+SVG, FIGURES.json"],
                   ["manuscript", "paper/build_rev5.py --real --doc main|si --force",
                    "20261031", "rev5 docx + build manifest + evidence manifest"]]}),
]
