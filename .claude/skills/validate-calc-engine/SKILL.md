---
name: validate-calc-engine
description: Verify calculation accuracy of the RUSLE and Wilcock-Crowe models by running the core pytest suites and, on failure, diffing against benchmark CSVs. Use when the user says "validate calculation engine", "run calculation tests", or runs /validate-calc-engine.
---

Verify the RUSLE (suspended yield), Wilcock & Crowe (bedload) and monthly-to-daily flow preprocessor calculation engines. Follow these steps in order. This skill is read-only: do not edit source, tests, or benchmark files.

## 1. Run the tests

Activate the virtualenv if it is not active (`.venv\Scripts\Activate.ps1`), then run from the repo root:

```
pytest tests/unit tests/contract tests/pipeline -v
```

This is the rebuilt suite (`project_spec.md` B6); the old `tests/legacy/` suites were deleted in M5. The monthly flow preprocessor tests are in `tests/unit/test_monthly_flow.py` (U-M3-01: the DSI monthly parser, the log-normal daily disaggregation, volume conservation, seeding, leap years, the hand-off into `TimeSeriesAggregator`) and `tests/contract/test_flow_files.py` (C-M3-02: the files on disk and the three sample DSI tables). The Wilcock formulas are checked against `tests/verification/make_bedload_oracle.py` by `tests/unit/test_wilcock_formulas.py`. These are Tk-free and need no display.

Tests under `tests/ui` need a display. If collection fails with an `ImportError`/`ModuleNotFoundError`, or Tk errors such as "Can't find a usable tk.tcl" or "no display", record it as a **missing dependency / environment problem**, name the module or error, and suggest `pip install -r requirements.txt`. Do not treat it as a numerical failure.

If everything passes, report the pass counts and stop. Do not do step 2.

## 2. On failure, compare against benchmarks

Benchmarks (reviewed reference outputs, one set per sample dam):

- `tests/benchmarks/` — added in M2 (suspended yield) and M3 (bedload) after hydrologist sign-off. Until a set exists there is no benchmark: the old `inputs/test_bedload_results.csv` and `inputs/test_yield_results.csv` were removed, so say so rather than guess.
- Hand calculations in `tests/verification/` (added in M2) are the oracle for the formulas; never use the code's own output as the reference.
- After the D35 fix (M3.1) a benchmark made before it is stale on purpose (the Wilcock & Crowe high-transport branch changed).
- No benchmark CSV exists for the flow preprocessor (`src/core/monthly_flow_preprocessor.py`). Its reference is the `TOP.` column of each source table in `inputs/dam_flow_data/*.csv`: the 12 monthly volumes for each water year must sum to it within 0.05 hm³, and daily flow must conserve each month's volume exactly. Check these directly rather than against a benchmark file.

Load them with `read_table` from `src/utils/paths.py` (files have a BOM and Turkish characters). Recompute using the same inputs the benchmarks derive from (`inputs/dam_flow_data/*.csv` converted to daily flow, and `inputs/fractional_parameters.csv`, for bedload; `inputs/master_yield.csv` and `inputs/raw_zonal_means.csv` for yield) via the core classes (`FractionalModel`, `TimeSeriesAggregator`, `YieldCalculator`, `ZonalMatcher`). Write any throwaway script to the scratchpad directory, not the repo. Match rows by key (Year; Dam/Sub-Basin/Year), not position. Match names with `turkish_lower` / `to_ascii_turkish`.

Use `np.isclose` with `rtol=1e-6` and a small `atol` (bedload values can be ~1e-10) unless the failing test states its own tolerance. Check that the metric-ton to m³ conversion uses density 2650 kg/m³.

If a benchmark or one of its input files is missing, say so; do not guess.

## 3. Report

Give a concise report:

1. **Result**: passed / failed / could not run, with counts.
2. **Failed assertions**: test id, assertion text, expected vs actual.
3. **Numerical discrepancies**: table of key, column, benchmark value, computed value, relative difference. Say if the benchmark itself looks stale versus a deliberate formula change (check `git log` on the relevant core file) rather than asserting which side is wrong.
4. **Missing dependencies / environment issues**: exact module or error.
5. **Likely cause** (only if evidenced) and a suggested next step.
