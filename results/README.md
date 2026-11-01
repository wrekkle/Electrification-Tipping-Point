# Selected results

The figures and tables the paper cites and the domestic work reports. They cover two cases that
are not pooled: figures F1-F9 and the result tables are the Melbourne 2014 historical case;
figures D1, D2 and the domestic table are the Yantai 2025 case. The full experiment tree (raw
per-stream runs, all search states, bootstrap draws, replay intermediates) stays in the authors'
local archive and is summarized here.

## Melbourne 2014

| path | content | produced by |
|---|---|---|
| `figures/F1.png` ... `figures/F9.png`, same names as `.svg` | main-text figures, vector and 300 dpi raster | figure pipeline in the local research archive; palette inherited from the frozen submission |
| `data/ideal_bound_allsites.csv` | analytic delivery upper bound per connector power, ten sites pooled | `analysis/example.py` logic, full-site run |
| `data/ideal_bound_streams.csv` | per-stream upper bound at 22 kW | same |
| `data/metrics_v2_summary.json` | access / parking / session / energy decomposition | metrics module, declared hardware |
| `data/metrics_v2_decomposition.csv` | per-stream decomposition (20 held-out streams) | same |
| `data/demand_coupling_denominators.csv` | mechanisms A and B at 22 kW, delivered over original and over target energy | post-hoc demand-coupling analysis |
| `data/connector_concurrency_vs_declared.csv` | maximum simultaneous charge sessions against declared connectors, per site-day | connector analysis |
| `data/in_violation_sensitivity.json` | `InViolation` retention and exclusion sensitivity | source-flag analysis |
| `data/site_audit.csv` | site aggregation, capacity consistency and dwell audit | data QA |

F9 is a three-panel figure (ideal bound against connector power, demand-dwell matching, and a
per-stream failure lower bound). It is dense by design and reads better at full size than in a
README. F1 and F6 are the versions used in the internal manuscript build of 2026-10-31; the PNG
files here are byte-identical to the files in the research archive.

## Yantai 2025 (v2)

| path | content | produced by |
|---|---|---|
| `figures/domestic/D1_coverage_dwell.png` and `.svg` | observed coverage: sessions per lot-day and dwell distribution (35 lots, 1,619 lot-days) | data QA and figure script in the domestic archive |
| `figures/domestic/D2_scenario_replay_v2.png` and `.svg` | v2 access result: per-lot-day minimum connectors and required / ideal / delivered energy | v2 replay summary and figure script |
| `figures/domestic/D2_scenario_replay.png` and `.svg` | v1 figure, kept as history; superseded, numbers withdrawn | v1 replay |
| `data/domestic_scenario_replay_v2.csv` | one row per declared scenario: request counts, per-lot minimum-connector quantiles, held-out service and failure shares for the per-lot and the city-uniform policies, energy rates | v2 replay summary (22 kW, seed 20261101) |

The domestic table is a direct copy of the recorded v2 summary fields, rounded; the replay code
itself is not published, so the table and the figures are the checkable evidence. Columns:
`scenario`, `p_ev`, `q_need`, `realized_pq`, `candidate_sessions`,
`charge_requests`, `k_min_median`, `k_min_p90`, `k_min_max`, `k_vector_sum`,
`k_vector_max`, `uniform_k_train`, `holdout_dates`, `holdout_requests`,
`holdout_perlot_immediate_share`, `holdout_perlot_failure_share`,
`holdout_perlot_required_kwh`, `holdout_perlot_ideal_kwh`,
`holdout_perlot_delivered_kwh`, `holdout_perlot_ideal_energy_rate`,
`holdout_perlot_actual_energy_rate`, `holdout_uniform_immediate_share`,
`holdout_uniform_actual_energy_rate`, `access_standard`, `connector_kw`,
`energy_median_kwh`, `seed`. The `perlot` columns use each lot's
training-selected connector count (111 / 172 / 258 connectors in total, at most 9 / 15 / 23 per
lot) on the 16 held-out dates. The `uniform` columns use one city-wide count per scenario
(9 / 15 / 23), the conservative case drawn in panel (b) of D2 v2. v2 is the current version; v3
is in development.

## Figure conventions

Figures use the frozen submission's blue ramp (`#08306b`, `#109cf1`, `#5ba3d0`,
`#7fb9da`, `#b7d4ea`, `#d9e8f5`) with serif type, and pair colour with marker shape and
line style so they stay readable in greyscale. The domestic figures use the same palette with
neutral grey for auxiliary elements.
