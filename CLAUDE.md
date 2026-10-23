# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working principles

- **Surface confusion and trade-offs.** When a request is ambiguous or two approaches differ materially, say so and name the trade-off rather than silently picking one. Don't hide uncertainty behind a confident answer.
- **Write the minimum code.** Solve the stated problem only. No speculative features, configuration options, abstractions, or error handling for cases that cannot occur.
- **Touch only what you must, and clean up your own mess.** Change only the lines the task needs; don't reformat or "improve" adjacent code. Remove temporary files, debug prints, and dead code you introduced.
- **Define success criteria, then loop until verified.** Before editing, state how the change will be checked (for example, a specific `pytest` target or an observable behaviour). Iterate until those checks pass, and report any failures with their output rather than claiming success.

## Commands

A virtualenv lives in `.venv` (Windows: `.venv\Scripts\Activate.ps1`). There is no README, linter, or formatter config.

```
pip install -r requirements.txt
python app.py                                   # launch the Tkinter GUI
pytest                                          # all tests (pytest.ini sets pythonpath = .)
pytest tests/test_reporter.py                   # one file
pytest tests/test_wilcock.py::test_name         # one test
pyinstaller ...                                 # packaging; no spec file is checked in
```

Tests that build widgets use the session-scoped `tk_root` fixture in `tests/conftest.py`. Build UI inside a `tk.Toplevel(tk_root)` rather than calling `tk.Tk()` per test, which intermittently fails on Windows ("Can't find a usable tk.tcl"). The tests need a display.

## Architecture

A desktop app that estimates sediment delivered to a reservoir in three stages, each a tab in a `ttk.Notebook`. The stages hand data to each other as DataFrames/CSVs.

- **Phase 2 – RUSLE** (`src/core/rusle.py`, `src/ui/rusle_view.py`): `YieldCalculator` and `ZonalMatcher` turn basin/sub-basin tables and zonal raster statistics into suspended-sediment yield (`Suspended_Volume_m3` / `Volume_m3_yr`).
- **Phase 3 – Wilcock & Crowe bedload** (`src/core/wilcock.py`, `src/ui/wilcock_view.py`): `FractionalModel` computes shear stress from daily flow (Manning, rectangular channel) and transport per grain-size fraction. It is vectorised over the whole flow series in `compute_transport_series`. `TimeSeriesAggregator` produces annual summaries and `BedloadVisualizer` the plots.
- **Integration** (`src/data/reporter.py` `IntegrationModule`, `src/ui/integration_view.py`): `merge_sediment_data` sums sub-basin suspended volume per year, averages across years, and adds it as a constant to the bedload table, giving `Total_Volume_m3`. Wilcock exports are in metric tons/yr and are converted to m³ with `SEDIMENT_DENSITY_KG_M3 = 2650`, which must stay in sync with `FractionalModel.rho_s`. Optional bathymetry (volume → elevation) is interpolated with `np.interp` and clamped, with warnings, outside the table range.

`src/ui/app.py` `SedimentApp` is the controller. It owns the shared results (`phase2_df`, `phase3_df`, `annual_summary`, `final_merged_df`), which views set through `set_rusle_results` / `set_wilcock_results` / `set_integration_results`. The many delegating `@property` and method aliases at the bottom of `SedimentApp` are backwards-compatible shims for the tests. Keep them when refactoring views, or update the tests with them.

Core modules (`src/core`) must stay free of Tkinter. UI code is in `src/ui` and shared dialogs/helpers are in `src/ui/common.py`.

## Things to know

- **Turkish data is first-class.** Input tables may use Turkish headers (`Havza`, `Baraj`, `Eğim`, ...). Use `find_basin_table_columns`, `turkish_lower` and `to_ascii_turkish` from `rusle.py` for any column or name matching, since plain `.lower()` mishandles `I`/`İ`. `read_table` in `src/utils/paths.py` tries several encodings (utf-8-sig, cp1254, iso-8859-9, ...) and falls back to `;`-delimited CSV. Route file loading through it. `tests/test_turkish_characters.py` covers this.
- **Use `resource_path()`** (`src/utils/paths.py`) for bundled files such as `inputs/`, so the PyInstaller `_MEIPASS` case works.
- **User-selected inputs only.** No input file is loaded at startup. Every table is loaded from a file the user picks in the GUI.
- `inputs/` holds sample CSVs (`daily_flow_data`, `fractional_parameters`, `bathymetry`, `raw_zonal_means`, plus example outputs) and is the reference for the expected column layouts.
