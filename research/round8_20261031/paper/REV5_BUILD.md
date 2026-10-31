# rev5 delivery record (R8-C / figure-c)

Date: 2026-10-31. Every number below comes from tool output of the build described here.

## Deliverables

| item | path |
|---|---|
| main draft (rev5) | research/round8_20261031/paper/Electrification_tipping_point_v2_draft_rev5.docx |
| SI (rev5) | research/round8_20261031/paper/Electrification_tipping_point_v2_supplementary_rev5.docx |
| PDF render main/SI | research/round8_20261031/paper/rev5_main.pdf, rev5_si.pdf |
| build manifests | build_rev5_main_manifest.json, build_rev5_si_manifest.json |
| evidence manifests | evidence_rev5_main.json, evidence_rev5_si.json |
| figures | research/round8_20261031/figures/F1..F8.png/.svg and S1..S4.png/.svg |
| figure provenance | research/round8_20261031/figures/FIGURES.json (12 real entries, 300 dpi) |
| repro package | research/round8_20261031/repro/ (README.md, environment.json, commands.txt, inputs.sha256, results_inventory.md) |
| figure builder | research/round8_20261031/figures/build_figures_real.py |
| manuscript builder | research/round8_20261031/paper/build_rev5.py (+ content_rev5.py, evidence.py) |

## Measured counts

- main: 13 pages, 4,785 words (Word statistics before the F2/F8 label-only rebuild; build tokenizer 4,591 EN words, 70 paragraphs, 8 figures, 1 table, 0 unresolved tokens).
- SI: 4 pages, 956 words (Word statistics); build tokenizer 1,023 words, 20 paragraphs, 2 tables, 2 figures, 0 unresolved tokens.
- page counts from Word repagination (pagecount.ps1, ComputeStatistics(2)); words from ComputeStatistics(0). paper_stats.py classifies only the abstract of this draft (242 EN words) because rev5 section titles differ from the registered paper sections; Word and build counts are therefore quoted together.
- project checker: scripts/check_all.py exit 0, 0 errors, 8 warnings, all pre-existing literature/history warnings.

## Figure -> evidence table

| figure | input file(s) | rows / fields |
|---|---|---|
| F1 | experiments_main22/E1/coverage.csv, fit_metrics.csv, fit_params.json | 10 sites, 825 site-days, 185,550 events; dwell all/EV/ICE + arrival-gap; n_sites/n_days/criteria |
| F2 | experiments_main22/E2/curve_E2.csv; experiments/E2/curve_E2_summary.csv | 432 rows (A/D x k 0..8 x 24 streams); capacity/access/bootstrap columns |
| F3 | experiments_main22/E3/search_E3.csv, classes.json | 51 per-k rows; k, status, k_class; class counts |
| F4 | experiments_main22/E4/test_E4.csv; experiments_main22/M/m_summaries.csv | 140 rows (7 policies x 20 streams); rates, delivered/demand; M2 point/low/high |
| F5 | experiments_main22/constraint_thresholds.csv; E5/info_E5.csv | 48 rows; parking/access/energy/three k; k_min/delta_k |
| F6 | experiments_main22/E6/energy_E6.csv | 6 rows (22 kW); demand, delivered, energy rate, offline status |
| F7 | experiments_main22/E7/meta_E7.json, traj_E7.csv | 0 trajectory rows; status/reason |
| F8 | experiments_condshare/evidence_at_n_spaces.csv, .json | 40 rows (A/B x 20 streams); gate rejections, shortfall, delivered/demand |
| S1 | experiments_main22/E1/coverage.csv | n_spaces, charging_bays, events |
| S2 | experiments/E4/test_E4.csv (7 kW) | energy/access/capacity rates, rejected, charge_requests |
| S3 | experiments/E6/energy_E6.csv (7 kW) | delivered/demand per power-feeder config |
| S4 | experiments_main22/M/m_summaries.csv | M2 point/low/high/n_pairs |

Each FIGURES.json entry stores script sha256, every input file sha256, its row count and
column list, and the verified 300x300 dpi PNG record.

## Unresolved / open items (not filled)

1. access-only k* supplementary analysis: no machine output present.
2. licence string for the City of Melbourne 2014 source: not recorded in machine files (only the source name is).
3. scenario layer inconsistency: the layer string records charging_bay_share 0.1 while the contract assigns 20% of spaces as charging bays; the corrected E2 grid covers k = 0..8 for all streams, not the full contract count (up to 16).
4. M1 and M3 are missing_data with engine reasons: 10/10 streams lack a feasible k on at least one side; 8/8 offline instances infeasible in the declared model (window_too_short).
5. E5 information-signal rows: k_min_feasible and delta_k_vs_A blank for all 20 rows; missing_data, not a null effect.
6. E7 non-monotone trajectory: meta status missing_data, traj_E7.csv has 0 data rows; F7 reports the status, no fabricated trajectory.
7. 22 kW E6 feeder sensitivity: main22 E6 has one configuration (22 kW/full feeder); the 2x2 power x feeder ledger exists only in the 7 kW run (S3).
8. the conditional analysis session-level median dwell (31.5 vs 35.1 min, reported verbally) is not in the files read here; text uses the aggregated facts in evidence_at_n_spaces.json.
9. reference list: this draft intentionally carries no literature citations (rev4 body and bibliography not reused); no citation key is invented.