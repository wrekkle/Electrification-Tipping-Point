# Reproducing the public checks

状态: 生效
更新: 2026-11-01

Everything below uses only files tracked in this repository. Nothing here reads the private
research workspace.

## Environment

- Python 3.12 (3.10+ should work), `pip install -r requirements.txt`.
- No GPU, no MATLAB, no network needed for the quick start. MATLAB is optional: the
  `matlab/prei` folder is a separate reference implementation, documented there; it is not
  required for the Python quick start.

## Quick start (about five seconds)

```
python analysis/example.py
python scripts/check_public.py
```

Expected: `results/sample_bounds.json` and `results/sample_bounds.png` are written and the
example prints four rows (7, 11, 22 and 50 kW); the check prints one PASS line per contract and
exits 0.

Scope: the example applies the delivery bound from `method.md` equations (1)-(3) to 300 adopted
Melbourne rows. It is a smoke test for the code path and the repository layout. It does not
reproduce any figure under `results/figures`, does not regenerate the published result tables,
and does not touch the domestic replay.

## Tests

```
python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py"
```

The workbench tests cover rules, allocation, demand generation, metrics and the energy ledger;
they run on synthetic fixtures included in `apps/`. The same three steps run in
`.github/workflows/check.yml` on every push and pull request.

## What this repository can rebuild

- The ideal delivery bound, session failure rate and the minimal-connector rule on any dwell and
  energy input, through `analysis/example.py` and the workbench modules. The equations are fixed in
  `method.md`.
- The repository checks: link targets, tracked-path hygiene, sample size, figure presence and
  Python syntax, through `scripts/check_public.py`.
- The published aggregate table `../results/data/domestic_scenario_replay_v2.csv` is a recorded
  output, not recomputed here.

## Full-data reproduction (Melbourne 2014)

The full study needs the 236 MB raw archive and the processed contract (185,550 events):

1. Download and verify the archive as in `data.md`.
2. Rebuild the processed window extract and the declared scenario with the code in
   `apps/parking_lab/workbench/publicdata.py` (documented scenario parameters, seed 20261031).
3. Re-run the analysis and figure entry points from the local research archive; the selected
   outputs shipped here are listed in `../results/README.md`.

Two gaps are known and are not hidden. The raw-to-window selection list (which block faces
belong to each of the ten sites) is local only, so the processed contract cannot be rebuilt
exactly from the public archive. The figure pipeline that draws F1-F9 is local only; the
figures are published as files, with the palette and units documented in
`../results/README.md`. The window-to-contract and contract-to-bounds steps are deterministic from
the documented rules.

## Domestic reproduction gap

The Yantai raw rows, page snapshots, selection ledger and replay script stay in the authors'
local archive under the platform terms. The published evidence is the aggregate table
`../results/data/domestic_scenario_replay_v2.csv` and the figures under
`../results/figures/domestic/`. Those files can be checked against the numbers in
`../README.md`, but the replay cannot be re-run from this repository. v1 is withdrawn; v3 is in
development and not published.
