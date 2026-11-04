# Electrification Tipping Point

[![public-check](https://github.com/wrekkle/Electrification-Tipping-Point/actions/workflows/check.yml/badge.svg)](https://github.com/wrekkle/Electrification-Tipping-Point/actions/workflows/check.yml)

**Question.** In a parking facility with a fixed total number of spaces, how many bays should be wired for charging, when should an idle charging bay be opened to a vehicle that does not need a charge, and when is a mobile charger worth buying?

This repository holds the public code, the derived summary tables and the figures needed to check the answer. It is research code, not a deployed service, and not a published paper.

中文入口：[docs/README.zh.md](docs/README.zh.md)

![Three-scheme comparison: 107 of 120 evaluation worlds lower the seven-day social cost when the bay count is re-optimised under shared opening](results/figures/T5_scheme_summary.png)

*Figure: paired difference in seven-day social cost between shared opening (S2) and dedicated charging bays (S1), one point per evaluation world (left), and the split between the operating effect at fixed bay count and the re-sizing effect (right). Data: five New York parking sites, three time blocks, two declared cost scenarios, 120 evaluation worlds drawn from a semi-synthetic three-class vehicle stream. Costs are the declared scenario, not a calibrated social cost; the figure is descriptive and is not a field estimate.*

## Three results

1. **Re-sizing and opening interact.** Re-optimising the number of charging bays under the shared-opening rule lowers the seven-day social cost in 107 of 120 evaluation worlds, mean paired reduction 345.56 USD (naive world-level standard error 40.43). Holding the bay count at its dedicated-scheme choice lowers it by 77.66 USD. The gap between the two numbers is the re-sizing effect; both are computed on worlds that never enter the selection stage.
2. **Mobile service is dominated under the declared costs.** With k_mob = 0.289 USD/kWh at the centre cost vector, the lower bound on the cost of mobile service is positive whenever the premises hold, so any m > 0 configuration is strictly dominated by m = 0. Only 4 boundary cells (lower electricity price) let mobile service pay, by 1.65-40.47 USD per three-day window. The bound is a necessary condition, not a decision rule.
3. **Evidence is paired, not a field estimate.** Selection uses 80 worlds and evaluation uses 120 different worlds from the same five sites, so the reported differences describe transfer across time blocks and declared scenarios. The stream is semi-synthetic: arrivals and dwell are observed, while electric/fuel and charging-need labels are declared.

## Minimal run

```bash
python -m pip install -r requirements.txt
python analysis/example.py                        # small public example
python scripts/check_public.py                    # public checks
python apps/parking_lab/workbench/make_summary_figure.py   # rebuild the figure above
```

The figure is rebuilt from [data/t5_summary/paired_worlds_2026-11-04.csv](data/t5_summary/paired_worlds_2026-11-04.csv), a 120-row derived table documented in [data/t5_summary/README.md](data/t5_summary/README.md). The replay engine and its tests live in [apps/parking_lab/workbench](apps/parking_lab/workbench).

## Where to look

| path | what is there |
|---|---|
| [docs/method.md](docs/method.md) | symbols, units and equations |
| [docs/data.md](docs/data.md) | sources, processing rules, what is observed and what is declared |
| [experiments/prei/CASES.md](experiments/prei/CASES.md) | the two case studies (Melbourne 2014, Yantai 2025) in detail |
| [docs/reproduce.md](docs/reproduce.md) | what can be rebuilt here and what cannot |
| [results/README.md](results/README.md) | what each published figure and table is |
| [apps/parking_lab](apps/parking_lab) | replay engine, rules, metrics and tests |
| [data/](data/) | source, licence and the 300-row sample |
| [docs/README.zh.md](docs/README.zh.md) | Chinese entry with the same facts |

## Scope and licence

Two cases are kept separate and never added into one estimate; see [experiments/prei/CASES.md](experiments/prei/CASES.md). Third-party data stay under their publisher's licence: the Melbourne extract is CC BY 4.0 with attribution to the City of Melbourne. No licence has been chosen for the code yet, so it is provided for reading and review without a grant of reuse rights; see [LICENSE.md](LICENSE.md). Third-party papers are not redistributed.

The manuscript is in the authors' workspace and has not been submitted or published; there is no preprint and no DOI. Do not cite this repository as a published paper.
