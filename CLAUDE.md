# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Product requirements, target architecture, data contracts and the development pipeline are defined in `project_spec.md`; it is the source of truth for planned changes.

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
pytest                                          # the new layout (tests/unit, contract, pipeline, ui); tests/legacy is skipped
pytest tests/unit/test_smoke.py                 # one file
pytest tests/unit/test_smoke.py::test_name      # one test
pytest -o addopts="" tests/legacy               # old core tests, run locally only (4 known failures from removed fixtures)
pyinstaller ...                                 # packaging; no spec file is checked in
```

Tests that build widgets use the session-scoped `tk_root` fixture in `tests/conftest.py`. Build UI inside a `tk.Toplevel(tk_root)` rather than calling `tk.Tk()` per test, which intermittently fails on Windows ("Can't find a usable tk.tcl"). The tests need a display. Tk delivers generated events only to mapped windows (call `update()` first), and a background thread may call into Tk only while the main thread is inside `mainloop()` (the `run_task` test runs one).

## Architecture

A Windows desktop app (Tkinter) that walks a hydrologist through estimating the sediment that reaches one dam, as a wizard started by `app.py` (`src/ui/wizard.py`). Imports point downward only: `src/ui` → `src/services` → `src/core`.

- **`src/ui`** collects input and shows results; it holds no calculation and no file parsing. `Wizard` owns navigation: a step opens only when every earlier step is complete, and `invalidate_after(index, reason)` resets the later steps and names the results that were lost. Each step is a `Step` subclass in `src/ui/steps/` (`build`, `on_show`, `is_complete`, `reset`). Built so far: 1 Project, 2 Regional data (an editable basin grid that flags invalid cells), 3 Select dam. Long work goes through `Wizard.run_task`. Shared dialogs and helpers are in `src/ui/common.py`.
- **`src/services`** is Tk-free. `project.py` is the project folder (`project.json`, and `import_file` which copies every input into `inputs/` and never touches the original). `regional.py` loads and validates the basin table, zonal means and dam sheets; `TableError` carries the cells to flag. `regional_data.py` (`RegionalData`) imports them, applies grid edits and keeps the project's dams in step with the table. `dam_settings.py` validates the step 3 fields.
- **`src/core`** is pure maths and must stay free of Tkinter. The spec's target is also no matplotlib and no file I/O, which `wilcock.py` and `monthly_flow_preprocessor.py` still break until M3.
  - RUSLE (`rusle.py`): `YieldCalculator` and `ZonalMatcher` turn basin/sub-basin tables and zonal statistics into suspended-sediment yield.
  - Wilcock & Crowe bedload (`wilcock.py`): `FractionalModel` computes shear stress from daily flow (Manning, rectangular channel) and transport per grain-size fraction, vectorised in `compute_transport_series`. `TimeSeriesAggregator` produces annual summaries and `BedloadVisualizer` the plots. `monthly_flow_preprocessor.py` turns DSİ monthly tables into daily flow. The spec moves the plotting and file I/O out of core in M3.
- **`src/data/reporter.py`** `IntegrationModule` is the old integration code. Nothing in the wizard uses it; M4 replaces it with `src/core/integration.py`. Wilcock exports are in metric tons/yr and are converted to m³ with `SEDIMENT_DENSITY_KG_M3 = 2650`, which must stay in sync with `FractionalModel.rho_s`.

The suspended, bedload, reservoir curve, integration and reporting steps are not built yet (milestones M2 to M5 in `project_spec.md`, which also lists the two planned formula fixes in `wilcock.py`).

## Things to know

- **Turkish data is first-class.** Input tables may use Turkish headers (`Havza`, `Baraj`, `Eğim`, ...). Use `find_basin_table_columns`, `turkish_lower` and `to_ascii_turkish` from `rusle.py` (and `name_key` from `services/regional.py` for names) for any column or name matching, since plain `.lower()` mishandles `I`/`İ`. `read_table` in `src/utils/paths.py` tries several encodings (utf-8-sig, cp1254, iso-8859-9, ...) and falls back to `;`-delimited CSV; `dtype=str` keeps cells as written. Route file loading through it. `tests/contract/test_regional.py` covers encodings, decimal commas and header aliases; the helper tests are in `tests/legacy/test_turkish_characters.py` (local only until they are ported).
- **Use `resource_path()`** (`src/utils/paths.py`) for bundled files such as `inputs/`, so the PyInstaller `_MEIPASS` case works.
- **User-selected inputs only.** No input file is loaded at startup. Every table comes from a file the user picks, and is copied into the project; the original is never modified.
- `inputs/` holds the sample files and is the reference for the expected column layouts: `master_yield.csv` (basin table), `raw_zonal_means.csv`, `bathymetry/*_bathymetry.csv` (one dam sheet per dam), `dam_flow_data/*_flow.csv` (DSİ monthly flow) and `fractional_parameters.csv`.
