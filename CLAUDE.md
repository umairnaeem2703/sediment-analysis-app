# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Product requirements, target architecture, data contracts and the development pipeline are defined in `docs/project_spec.md`; it is the source of truth for planned changes.

## Working principles

- **Surface confusion and trade-offs.** When a request is ambiguous or two approaches differ materially, say so and name the trade-off rather than silently picking one. Don't hide uncertainty behind a confident answer.
- **Write the minimum code.** Solve the stated problem only. No speculative features, configuration options, abstractions, or error handling for cases that cannot occur.
- **Touch only what you must, and clean up your own mess.** Change only the lines the task needs; don't reformat or "improve" adjacent code. Remove temporary files, debug prints, and dead code you introduced.
- **Define success criteria, then loop until verified.** Before editing, state how the change will be checked (for example, a specific `pytest` target or an observable behaviour). Iterate until those checks pass, and report any failures with their output rather than claiming success.

## Commands

A virtualenv lives in `.venv` (Windows: `.venv\Scripts\Activate.ps1`). `README.md` is the user guide and `INPUT_FORMAT.md` the input format. Lint and format with ruff (`ruff.toml`); CI runs both.

```
pip install -r requirements.txt
python app.py                                   # launch the Tkinter wizard
python -m ruff check . && python -m ruff format --check .   # lint and format check
python -m pytest                                # the whole suite (tests/unit, contract, pipeline, ui)
python -m pytest tests/unit/test_smoke.py       # one file
python -m pytest tests/unit/test_smoke.py::test_name   # one test
python -m tests.benchmarks.regenerate_suspended # rewrite the suspended goldens; merge them only after hydrologist sign-off
python -m tests.benchmarks.regenerate_bedload   # the same for the bedload goldens
python -m tests.benchmarks.regenerate_reservoir # the same for the reservoir curve goldens
python -m tests.benchmarks.regenerate_integration # the same for the integration and projection goldens
python -m tests.benchmarks.before_after_bedload # the before and after D35/D36 table for the hydrologist (review only)
```

The oracle for the formulas is the hand calculation in `tests/verification/` (`make_suspended_oracle.py`, `make_bedload_oracle.py`, `make_reservoir_oracle.py` and `make_integration_oracle.py` each write a reviewable workbook and the CSVs the unit tests read); `tests/benchmarks/` holds the reviewed golden outputs.

Tests that build widgets use the session-scoped `tk_root` fixture in `tests/conftest.py`. Build UI inside a `tk.Toplevel(tk_root)` rather than calling `tk.Tk()` per test, which intermittently fails on Windows ("Can't find a usable tk.tcl"). The tests need a display. Tk delivers generated events only to mapped windows (call `update()` first), and a background thread may call into Tk only while the main thread is inside `mainloop()` (the `run_task` test runs one).

## Architecture

A Windows desktop app (Tkinter) that walks a hydrologist through estimating the sediment that reaches one dam, as an eight-step wizard started by `app.py` (`src/ui/wizard.py`; `README.md` section 4 describes the steps). A layer imports only from the layers below it: `src/ui` → `src/services` → `src/core`, never upward. `src/utils` (file reading, paths, logging) is shared by all three. `tests/unit/test_layering.py` checks these rules. Each module's docstring says what it holds, and `docs/project_spec.md` Part B has the design and the decision log (D-numbers).

- **`src/core`** is pure maths: no Tkinter, no matplotlib, no file I/O, and it imports only the standard library, numpy, pandas and itself. The models are RUSLE yield (`rusle.py`), Wilcock & Crowe bedload (`wilcock.py`) with the DSİ monthly-to-daily split (`monthly_flow_preprocessor.py`), the reservoir curve (`reservoir.py`) and the integration and projection (`integration.py`, `projection.py`). `text.py` holds the Turkish text helpers and the name key.
- **`src/services`** is Tk-free and holds one module per computation (`suspended.py`, `bedload.py`, `reservoir.py`, `integration.py`), the input contracts (`labels.py`, `regional.py`, `regional_data.py`, `dam_settings.py`) and the project folder (`project.py`: `project.json`, and `import_file` copies every input into `inputs/` and never touches the original). `dam_run.py` (`DamRun`) holds the four results of the dam being analysed: step 3 makes it when it uses a dam and drops it when the dam or an earlier step changes, steps 4 to 7 keep their result in it (`Step.result`), and steps 7 and 8 read it from `wizard.run`. `reporting.py` draws the charts with `Figure`, never pyplot. `run_export.py` (`export_run`) writes the run folder `outputs/<dam-slug>_<YYYYMMDD_HHMM>/`, hashing every input first so a missing one leaves no folder.
- **`src/ui`** collects input and shows results; it holds no calculation and no file parsing, and takes only constants and types from `src/core`. `Wizard` owns navigation: a step opens only when every earlier step is complete, and `invalidate_after(index, reason)` resets the later steps and names the results that were lost. Each step is a `Step` subclass in `src/ui/steps/` (`build`, `on_show`, `is_complete`, `reset`). Long work goes through `Wizard.run_task`; shared dialogs and helpers are in `src/ui/common.py`.
- **Logging** is `src/utils/log.py`: the app logs through `get_logger()` and never prints (only the command-line tool `services/flow_files.py` prints its result). Every error and warning dialog, imported file and background task is logged, and a failed task keeps its traceback in `logs/app.log` of the project (D72).

## Things to know

- **Turkish data is first-class.** Names and values in cells may be Turkish. Column labels are English, one canonical label per column, defined in `src/services/labels.py` and read by `match_columns` with one rule (`fold`, D67). The exception is the DSİ monthly flow, which keeps its own Turkish layout (month names, defined in `src/core/monthly_flow_preprocessor.py`). Never add a header alias or match a header anywhere else. Use `turkish_lower` and `to_ascii_turkish` from `text.py` for any text matching, and `name_key` (also `text.py`) for dam and sub-basin names (D70), since plain `.lower()` mishandles `I`/`İ`. `INPUT_FORMAT.md` is the user's version of the label table; keep it in step with `labels.py`. `read_table` in `src/utils/paths.py` tries several encodings (utf-8-sig, cp1254, iso-8859-9, ...) and falls back to `;`-delimited CSV; `dtype=str` keeps cells as written. Route file loading through it. `tests/contract/test_regional.py` covers encodings and refused commas in numbers, `tests/contract/test_labels.py` the labels and the one matching rule; the helper tests are in `tests/contract/test_turkish_helpers.py`.
- **Use `resource_path()`** (`src/utils/paths.py`) in tests and benchmarks to find the sample files in `inputs/`. The app itself reads no bundled file (see the next point), and packaging is out of scope (D30).
- **User-selected inputs only.** No input file is loaded at startup. Every table comes from a file the user picks, and is copied into the project; the original is never modified.
- `inputs/` holds the sample files and is the reference for the expected column layouts: `master_yield.csv` (basin table), `raw_zonal_means.csv`, `bathymetry/*_bathymetry.csv` (one dam sheet per dam), `dam_flow_data/*_flow.csv` (DSİ monthly flow) and `fractional_parameters.csv`.
