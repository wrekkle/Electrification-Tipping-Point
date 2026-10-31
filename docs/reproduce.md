# Reproducing the public checks

Everything below uses only files tracked in this repository.

## Environment

- Python 3.12 (3.10+ should work), `pip install -r requirements.txt`.
- No GPU, no MATLAB, no network needed for the quick start. MATLAB is optional: the
  `matlab/prei` folder is a separate reference implementation, documented there; it is not
  required for the Python quick start.

## Quick start (about 5 seconds)

```
python analysis/example.py
python scripts/check_public.py
```

Expected: `results/sample_bounds.json` and `results/sample_bounds.png` written; the check
prints one PASS line per contract and exits 0.

## Tests

```
python -m unittest discover -s apps/parking_lab/workbench/tests -p "test_*.py"
```

The workbench tests cover rules, allocation, demand generation, metrics and the energy ledger;
they run on synthetic fixtures included in `apps/`.

## Full-data reproduction

The full study needs the 236 MB raw archive and the processed contract (185,550 events):

1. Download and verify the archive as in `data.md`.
2. Rebuild the processed window extract and the declared scene with the code in
   `apps/parking_lab/workbench/publicdata.py` (documented scenario parameters, seed 20261031).
3. Re-run the analysis and figure entry points from the local research archive; the selected
   outputs shipped here are listed in `../results/README.md`.

The raw-to-window selection list (which block faces belong to each of the ten sites) is part of
the local archive and is **not** published; this is a known reproduction gap, recorded in the
results README. The window-to-contract and contract-to-bounds steps are deterministic from the
documented rules.
