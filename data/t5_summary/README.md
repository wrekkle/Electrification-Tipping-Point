# Three-scheme summary table (public derived data)

`paired_worlds_2026-11-04.csv` holds the 120 evaluation worlds of the three-scheme
comparison, one row per world, derived from the frozen evaluation table of the study.
It contains no observed vehicle records and no personally identifying fields.

## Columns

| column | meaning |
|---|---|
| world_id | evaluation world identifier (site, time block, mechanism, declared scenario, repetition) |
| site_id | one of five New York parking sites (nyc-bri, nyc-jgu, nyc-jon, nyc-qfa, nyc-sge) |
| block_id | time block (week0, week3, week6) |
| mechanism | background-occupancy generator (M1, M2) |
| scenario_id | declared cost scenario (R2 base, R2 bg095) |
| n_S1 / n_S2 | number of charging bays chosen by the selection stage for the dedicated scheme (S1) and for the shared-opening scheme (S2) |
| m_S3 | number of mobile devices chosen for S3 (0 in every evaluation world) |
| J_S1 / J_S2 / J_S3 | seven-day social cost of each scheme under the declared cost vector, USD |
| delta_S2_S1 | paired difference J_S2 - J_S1 (negative = shared opening is cheaper) |
| delta_S3_S2 | paired difference J_S3 - J_S2 (zero where m = 0) |
| fixed_config_delta_S2_S1 | paired difference when the bay count is held at the S1 choice (operating effect only) |

## How it was derived

Each evaluation world is replayed three times, once per scheme, on the same frozen
vehicle cohort. The published table keeps one row per world and drops the per-vehicle
ledger. The derivation command and the source file are recorded in the study log
(`research/t64_followup_20261103/cross_site/tables/evaluation.csv`, internal).

## What it does not support

The stream is semi-synthetic: arrivals and dwell come from New York parking records,
while electric/fuel and charging-need labels are a declared scenario. The cost vector is
declared, not calibrated. The 120 worlds come from the same five sites as the 80
selection worlds, so the differences describe transfer across time blocks and declared
scenarios, not across cities. No field saving is claimed.

## Figure

`python apps/parking_lab/workbench/make_summary_figure.py` regenerates
`results/figures/T5_scheme_summary.png` from this table.
