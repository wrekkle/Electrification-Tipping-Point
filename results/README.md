# Selected results

Machine outputs and figures from the current round-8 analysis. These are the files the paper
cites; the full experiment tree (raw per-stream runs, all search states, bootstrap draws) stays
in the local research archive and is summarized here.

| path | content | produced by |
|---|---|---|
| `figures/F1.png` … `figures/F9.png`, same names as `.svg` | main-text figures, vector and 300 dpi raster | figure pipeline in the local research archive; palette inherited from the frozen submission |
| `data/ideal_bound_allsites.csv` | analytic delivery upper bound per site and power | `analysis/example.py` logic, full-site run |
| `data/ideal_bound_streams.csv` | per-stream upper bound at 22 kW | same |
| `data/metrics_v2_summary.json` | access / parking / session / energy decomposition | metrics module, declared hardware |
| `data/metrics_v2_decomposition.csv` | per-stream decomposition (20 held-out streams) | same |
| `data/demand_coupling_denominators.csv` | mechanism A and B at 22 kW, delivered over original and over target energy | demand-coupling analysis |
| `data/connector_concurrency_vs_declared.csv` | maximum simultaneous charge sessions against declared connectors, per site-day | connector analysis |
| `data/in_violation_sensitivity.json` | InViolation retention/exclusion sensitivity | source-flag analysis |
| `data/site_audit.csv` | site aggregation, capacity consistency and dwell audit | data QA |

The figures in `figures/` are the same files embedded in the manuscript. Figures use the
frozen submission's blue ramp (`#08306b`, `#109cf1`, `#5ba3d0`, `#7fb9da`, `#b7d4ea`,
`#d9e8f5`) with serif type, and pair colour with marker shape and line style so they stay
readable in greyscale.
