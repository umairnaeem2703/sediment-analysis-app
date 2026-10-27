# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Product requirements, target architecture, data contracts and the development pipeline are defined in `docs/project_spec.md`; it is the source of truth for planned changes.

## Working principles

- **Surface confusion and trade-offs.** When a request is ambiguous or two approaches differ materially, say so and name the trade-off rather than silently picking one. Don't hide uncertainty behind a confident answer.
- **Write the minimum code.** Solve the stated problem only. No speculative features, configuration options, abstractions, or error handling for cases that cannot occur.
- **Touch only what you must, and clean up your own mess.** Change only the lines the task needs; don't reformat or "improve" adjacent code. Remove temporary files, debug prints, and dead code you introduced.
- **Define success criteria, then loop until verified.** Before editing, state how the change will be checked (for example, a specific `pytest` target or an observable behaviour). Iterate until those checks pass, and report any failures with their output rather than claiming success.

## Commands

A virtualenv lives in `.venv` (Windows: `.venv\Scripts\Activate.ps1`). There is no README. Lint and format with ruff (`ruff.toml`); CI runs both.

```
pip install -r requirements.txt
python app.py                                   # launch the Tkinter wizard
ruff check . && ruff format --check .          # lint and format check
pytest                                          # the whole suite (tests/unit, contract, pipeline, ui)
pytest tests/unit/test_smoke.py                 # one file
pytest tests/unit/test_smoke.py::test_name      # one test
pyinstaller ...                                 # packaging; no spec file is checked in
python -m tests.benchmarks.regenerate_suspended # rewrite the suspended goldens; merge them only after hydrologist sign-off
python -m tests.benchmarks.regenerate_bedload   # the same for the bedload goldens
python -m tests.benchmarks.regenerate_reservoir # the same for the reservoir curve goldens
python -m tests.benchmarks.regenerate_integration # the same for the integration and projection goldens
python -m tests.benchmarks.before_after_bedload # the before and after D35/D36 table for the hydrologist (review only)
```

The oracle for the formulas is the hand calculation in `tests/verification/` (`make_suspended_oracle.py`, `make_bedload_oracle.py`, `make_reservoir_oracle.py` and `make_integration_oracle.py` each write a reviewable workbook and the CSVs the unit tests read); `tests/benchmarks/` holds the reviewed golden outputs.

Tests that build widgets use the session-scoped `tk_root` fixture in `tests/conftest.py`. Build UI inside a `tk.Toplevel(tk_root)` rather than calling `tk.Tk()` per test, which intermittently fails on Windows ("Can't find a usable tk.tcl"). The tests need a display. Tk delivers generated events only to mapped windows (call `update()` first), and a background thread may call into Tk only while the main thread is inside `mainloop()` (the `run_task` test runs one).

## Architecture

A Windows desktop app (Tkinter) that walks a hydrologist through estimating the sediment that reaches one dam, as a wizard started by `app.py` (`src/ui/wizard.py`). Imports point downward only: `src/ui` → `src/services` → `src/core`.

- **`src/ui`** collects input and shows results; it holds no calculation and no file parsing. `Wizard` owns navigation: a step opens only when every earlier step is complete, and `invalidate_after(index, reason)` resets the later steps and names the results that were lost. Each step is a `Step` subclass in `src/ui/steps/` (`build`, `on_show`, `is_complete`, `reset`). Built so far: 1 Project, 2 Regional data (an editable basin grid that flags invalid cells), 3 Select dam, 4 Suspended sediment (Compute shows a grid per sub-basin and the dam total), 5 Bedload (the dam's flow file, the grain fractions and the sigma, lag-1 phi and seed of the monthly split; Compute shows an annual table and a trend chart in two tabs, and flags flow made from a DSİ monthly table as synthetic), 6 Reservoir curve (the curve inputs prefilled from the dam sheet, with Hmin or a shape class, and the table's level interval, 0.5 m by default; Generate shows the table and a chart in two tabs), 7 Integration and projection (the years to project, 100 by default; Compute shows the annual totals and elevations, the accumulation to date, the lifespan at the mean, minimum and maximum rates, the projection table and a chart, and needs the commissioning year), 8 Report (shows the years of the minimum and maximum annual volume and every warning; Export writes a new run folder). Long work goes through `Wizard.run_task`. Shared dialogs and helpers are in `src/ui/common.py`.
- **`src/services`** is Tk-free. `project.py` is the project folder (`project.json`, and `import_file` which copies every input into `inputs/` and never touches the original). `labels.py` holds the canonical column labels of every input and the one rule that matches a header to them (`match_columns`). `regional.py` loads and validates the basin table, zonal means and dam sheets; `TableError` carries the cells to flag. `regional_data.py` (`RegionalData`) imports them, applies grid edits and keeps the project's dams in step with the table. `dam_settings.py` validates the step 3 fields. `suspended.py` computes one dam's suspended sediment from its own sub-basin rows and the zonal means (`compute_suspended`) and writes `suspended.csv` into a folder it is given (`write_suspended_csv`); the M5 reporting service will create the run folder. `bedload.py` is the same for bedload: `load_flow` (a daily series, or a DSİ monthly table split into synthetic daily flow), `load_fractions`, `import_flow` and `import_fractions` (check, then copy into the project), `compute_bedload` and `compute_dam_bedload`, and `write_bedload_csv`. `reservoir.py` prefills the curve inputs from the dam sheet and the edits kept on the dam (`curve_inputs`, `CurveOverrides` in `project.py`), validates and stores them (`validate_curve_entries`, `apply_curve_settings`), fits the curve (`compute_curve`, `compute_dam_curve`) and writes `reservoir_curve.csv` (`write_reservoir_csv`). `integration.py` joins the dam's suspended total, bedload and curve with its trap efficiency and years (`compute_integration`, `compute_dam_integration`) and writes `integration.csv` and `projection.csv` (`write_integration_csv`, `write_projection_csv`). `reporting.py` draws the bedload trend, annual volume, curve and projection charts with `Figure` (never pyplot) and saves each as a PNG. `run_export.py` (`export_run`) writes the run folder `outputs/<dam-slug>_<YYYYMMDD_HHMM>/` (`_2`, `_3`, ... when it exists): `results.xlsx` (sheets Inputs, Suspended, Bedload, Annual, Curve, Projection, Extremes, Warnings), the four PNGs, one CSV per phase and `run.json` (app version from `src.__version__`, the SHA-256 of every input, the parameters, flags and every warning); inputs are hashed first, so a missing one leaves no folder.
- **`src/core`** is pure maths and must stay free of Tkinter, matplotlib and file I/O; `tests/unit/test_layering.py` checks it.
  - RUSLE (`rusle.py`): `YieldCalculator` and `ZonalMatcher` turn basin/sub-basin tables and zonal statistics into suspended-sediment yield.
  - Wilcock & Crowe bedload (`wilcock.py`): `FractionalModel` computes shear stress from daily flow (Manning, rectangular channel) and transport per grain-size fraction, vectorised in `compute_transport_series`. `tau_ri` and `bi` are always computed from the grain size; a supplied column is only cross-checked into `FractionalModel.warnings` (D36). `TimeSeriesAggregator` produces annual summaries. `monthly_flow_preprocessor.py` turns DSİ monthly tables into daily flow (a log-normal split, optionally with a lag-1 AR(1) component `phi`, default 0; each month is rescaled to its volume); reading and writing those files is `services/flow_files.py`, and the plots are in `services/reporting.py`.
  - Integration (`integration.py`, `projection.py`): `annual_totals` (T = TE · (Vs + Vb) in hm³) and `sediment_elevations` (limited to Hcrest and counted); `accumulate` (S0 for c <= y < a, the mean for years outside the record), `annual_rates`, `project` (the years entered, 100 by default; `check_horizon`), `lifespan` and `exceeded_year`; `extremes` picks the minimum and maximum annual total (a tie goes to the earliest year). Years are the record's labels, used as they are.
  - Reservoir curve (`reservoir.py`): `fit_curve` builds a `ReservoirCurve`, the power law `V = Vmax·x^m` of B3.3 with `volume`, `area` and `elevation`. `m` is fitted through (Hmin, Vdead) when Hmin is given, otherwise it is the shape class's (`SHAPE_CLASSES`). `check_inputs`, `check_shape`, `check_step`, `curve_warnings` and `curve_table` are the checks and the level table (0.5 m unless the user enters another interval).

## Things to know

- **Turkish data is first-class.** Names and values in cells may be Turkish. Column labels are English, one canonical label per column, all defined in `src/services/labels.py` and read by `match_columns` with one rule (`fold`, D67); the DSİ monthly flow keeps its own Turkish layout. Never add a header alias or match a header anywhere else. Use `turkish_lower` and `to_ascii_turkish` from `rusle.py` (and `name_key` from `services/regional.py` for names) for any name matching, since plain `.lower()` mishandles `I`/`İ`. `INPUT_FORMAT.md` is the user's version of the label table; keep it in step with `labels.py`. `read_table` in `src/utils/paths.py` tries several encodings (utf-8-sig, cp1254, iso-8859-9, ...) and falls back to `;`-delimited CSV; `dtype=str` keeps cells as written. Route file loading through it. `tests/contract/test_regional.py` covers encodings and refused commas in numbers, `tests/contract/test_labels.py` the labels and the one matching rule; the helper tests are in `tests/contract/test_turkish_helpers.py`.
- **Use `resource_path()`** (`src/utils/paths.py`) for bundled files such as `inputs/`, so the PyInstaller `_MEIPASS` case works.
- **User-selected inputs only.** No input file is loaded at startup. Every table comes from a file the user picks, and is copied into the project; the original is never modified.
- `inputs/` holds the sample files and is the reference for the expected column layouts: `master_yield.csv` (basin table), `raw_zonal_means.csv`, `bathymetry/*_bathymetry.csv` (one dam sheet per dam), `dam_flow_data/*_flow.csv` (DSİ monthly flow) and `fractional_parameters.csv`.
