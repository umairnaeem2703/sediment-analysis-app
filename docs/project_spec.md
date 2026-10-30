# Project Specification: Sediment Analysis App

| | |
|---|---|
| **Version** | 1.0 (as built; decisions D1 to D69) |
| **Date** | 2026-10-23 |
| **Source brief** | `brief/goals_milestones.md` |
| **Status of code** | The eight-step Tkinter wizard is built (M1 to M5). This spec records the requirements, the decisions and the pipeline. |
| **Roles** | *Developer* builds. *Hydrologist* is the domain reviewer who signs off every numerical change. *GIS analyst* supplies zonal RUSLE means and produces the 5-class RGB maps outside the app. |

**How to change this spec.** Edit it on a branch with the same pull request flow as code (B7). A change to a calculation, a data contract or a decision gets a new entry in the decision log (Appendix) and a hydrologist sign-off.

---

# Part A: Product requirements (what to build and why)

## A1. Purpose

Reservoirs fill with sediment. The goal of this project, in the brief's words, is *to calculate total suspended and bedload sediment volumes to analyze existing sediment accumulation, its impact on reservoir fill rates, and the resulting effects on the dam's operational lifespan.*

For each dam in a region, the app must answer four questions:

1. How much suspended sediment reaches the reservoir each year?
2. How much bedload reaches it in each year of the flow record?
3. How much sediment has accumulated since commissioning, and at what elevation does it sit?
4. At the mean, best-year and worst-year rates, in which year does sediment reach the dead-storage level?

**Success measures**

- Each sample dam in `inputs/` runs M1 to M5 end to end with no manual spreadsheet work.
- Every number the hydrologist reviews can be traced to an input, a parameter and an equation in B3.
- Every figure in the report has a stored `run.json` that reproduces it.
- Results are deterministic for the same inputs and seed.

## A2. Users and context

Hydrologists and engineers (DSİ-style studies) using one Windows machine, offline. Input data is Turkish-origin: headers, basin names and encodings vary (D1, D15). The UI and reports are in English.

## A3. Scope

**In scope**

| Milestone | Capability |
|---|---|
| M1 | Regional data ingestion into a project |
| M2 | Suspended sediment yield (RUSLE gross erosion x sediment delivery ratio) per dam |
| M3 | Bedload (Wilcock & Crowe fractional model) per dam |
| M4 | Reservoir elevation-volume curve, integration of suspended and bedload, accumulation and lifespan |
| M5 | Final analysis and reporting: min and max years, workbook, charts, CSV, `run.json` |

**Out of scope** (each is a decision, so revisit it by changing the decision, not by drifting)

| Item | Decision |
|---|---|
| Raster handling and the 5-class RGB maps (the GIS analyst's deliverable) | brief |
| A database | D4 |
| Web or multi-user delivery | D1 |
| PDF reports | D14 |
| Installer or release builds (code stays PyInstaller-compatible) | D30 |
| Cascade routing between dams | D21 |
| Computed trap efficiency (Brune curve) | D7 |
| Flow-dependent depth in the Wilcock hydraulics | D9 |
| Translation of the UI | D15 |

**Could-have later:** a batch run over all dams in a project (D3); release builds (D30).

## A4. Glossary and symbols

| Term | Meaning |
|---|---|
| SIO | *Sediment İletim Oranı*, the sediment delivery ratio (SDR) |
| USDA-SCS SIO, ÇEM SIO | The two empirical SIO formulas; the app averages them |
| Water year | Oct (Y-1) to Sep (Y), labelled Y. DSİ monthly tables use it. |
| Hbed, Hmin, Hmax, Hcrest | Riverbed elevation at the dam axis, minimum operating level, maximum reservoir level, crest level (m) |
| Vmax, Vactive, Vdead | Volume at Hmax, active volume, dead volume = Vmax - Vactive (hm³) |
| TE | Trap efficiency, the share of delivered sediment that stays in the reservoir (%) |
| Commissioning year, analysis year | First year of operation; the year the projection starts from |
| Level-pool fill | Sediment is assumed to fill the reservoir from the bed up, as a horizontal surface |
| D50, Fs | Median grain size (m) and sand fraction of the bed in the Wilcock model |

## A5. Workflow

The main window is a wizard (D17, D18) with a step list on the left and Back/Next at the bottom. Next is enabled only when the step is valid and computed. The step list allows jumping back to completed steps. Editing an earlier step invalidates every later result and says so. To analyse another dam, jump back to step 3.

| # | Step | The user... | The app shows |
|---|---|---|---|
| 1 | Project | Creates or opens a project folder | Project name and folder |
| 2 | Regional data (M1) | Imports the basin table, zonal means and dam sheets (each is copied into the project) | Editable basin grid, validation messages |
| 3 | Select dam | Picks a dam; enters commissioning year, analysis year, TE and optionally Hmin | The dam's sub-basins and sheet values |
| 4 | Suspended (M2) | Presses Compute | Per sub-basin SIO, mass, volume; the dam total |
| 5 | Bedload (M3) | Picks the flow file (daily or DSİ monthly) and the fractions file | Annual flow and bedload table, trend chart, "synthetic daily flow" flag |
| 6 | Reservoir curve (M4a) | Confirms or edits the prefilled curve inputs and sets the table's level interval (0.5 m by default) | Curve table and chart, plausibility warnings |
| 7 | Integration & projection (M4b) | Sets the years to project (100 by default) and presses Compute | Annual totals and elevations, accumulation to date, projection and lifespan chart |
| 8 | Report (M5) | Presses Export | Min and max years; paths of the written files |

## A6. Functional requirements

Test IDs follow `<layer>-<milestone>-<nn>`; the layers are `U` unit, `C` input contract, `P` per-dam pipeline, `W` wizard (B6). Tests for every requirement exist.

### M1: Regional data ingestion

| ID | Requirement | Acceptance criteria | Tests |
|---|---|---|---|
| FR-M1-01 | New, open and save a project folder holding `project.json` | A saved project reopens with identical dams, parameters and file paths. A missing or newer `schema_version` gives a clear error. | C-M1-01, W-M1-01 |
| FR-M1-02 | Importing a file copies it into `<project>/inputs/`; originals are never modified (D33) | Source file bytes are unchanged after an import. Edits in the grid are saved to the copy. | C-M1-02 |
| FR-M1-03 | Load the basin table and validate it | Required columns matched by their canonical labels (D67), including `Drainage Area (km2)`. Area > 0. Slope present and numeric. Blank rows skipped. Duplicate sub-basin names within a dam are an error. | C-M1-03, C-M1-04 |
| FR-M1-04 | Edit the basin table in a grid | Edited cells persist to the project copy (D41). Invalid cells are flagged before M2 runs, and a table with invalid cells is still imported (D38). | C-M1-08, W-M1-02 |
| FR-M1-05 | Load a dam sheet and cross-check it | Dam name matches a basin-table dam (Turkish-aware). Sheet drainage area and slope differ from the table by more than 1%: warning. Missing required fields: error naming them. | C-M1-05, C-M1-06 |
| FR-M1-06 | Load zonal means | `MEAN` and `Sub-basin Name` columns matched by their canonical labels (D67); empty or non-numeric means are skipped with a count in the warnings. | C-M1-07 |
| FR-M1-07 | Select the dam to analyse and enter its settings (D40, D42) | The dam needs a sheet. Commissioning year is optional; the analysis year is blank for the current year and not before the commissioning year; trap efficiency is above 0 and at most 100 (default 100); Hmin is optional. Choosing another dam or changing a setting resets the later steps. | C-M1-09, W-M1-03 |

### M2: Suspended sediment

| ID | Requirement | Acceptance criteria | Tests |
|---|---|---|---|
| FR-M2-01 | Match each of the dam's sub-basins to a zonal mean | Exact or alias matches are accepted. A loose match (one name inside the other, with the same number in both) is accepted only when all candidates carry one value, and is listed in the warnings. A number shared by two otherwise different names is no match (D68). An ambiguous or missing match is an error naming the sub-basin. | U-M2-01, C-M2-01 |
| FR-M2-02 | Compute per sub-basin metrics (B3.1) | Gross mass, both SIOs, average SIO, yield mass, volume and specific yield agree with the hand calculations in `tests/verification/` to 1e-9 relative. | U-M2-02, U-M2-03 |
| FR-M2-03 | The dam's suspended volume is the sum of **its own** sub-basins only | A project with three dams gives three different totals. No total ever mixes dams. | P-M2-01 |
| FR-M2-04 | Show and export the results | Grid in the UI; `suspended.csv` in the run folder | W-M2-01, P-M2-02 |

### M3: Bedload

| ID | Requirement | Acceptance criteria | Tests |
|---|---|---|---|
| FR-M3-01 | Ingest flow as a daily series or as a DSİ monthly table (D10) | Daily: `Date` and `Flow Q (m3/s)` (the Turkish headers `Tarih` and `Debi` are no longer read, D67). Monthly: detected automatically and converted by the log-normal split with sigma, lag-1 phi and seed from the wizard (D62). Monthly volumes are conserved exactly, and the result is flagged synthetic. | U-M3-01, C-M3-01, C-M3-02, W-M3-03 |
| FR-M3-02 | Load grain fractions (D36) | `di` (m) and `Fi` required; `Fi` sums to 1 within 0.02. tau_ri is always computed from the formula (D50). A supplied `tau_ri` or `bi` is cross-checked; a difference above 1% adds a warning. The sample file agrees with the formula, so it gives no warning. | U-M3-02, C-M3-03 |
| FR-M3-03 | Compute daily transport with the published Wilcock & Crowe function (D35) | W* is continuous at phi = 1.35 (relative jump below 1e-3; the published coefficients are rounded, so the branches differ by 4.2e-4, D47). Values match hand calculations at phi = 0.5, 1.0, 1.35, 2, 4 and 10. | U-M3-03, U-M3-04 |
| FR-M3-04 | Summarise by water year when the series carries `Water_Year`, otherwise by calendar year | Group keys, annual mean flow, mean transport, annual volume (m³/yr) and mass (t/yr). Rows with bad dates or flows are dropped with a count in the warnings. Negative flow and a date listed twice are errors; days missing between the first and last date are counted in a warning (D69). | U-M3-05, C-M3-04 |
| FR-M3-05 | Show and export the results | Table, trend chart (PNG), `bedload.csv` | W-M3-01, P-M3-01 |

### M4: Reservoir curve, integration, lifespan

| ID | Requirement | Acceptance criteria | Tests |
|---|---|---|---|
| FR-M4-01 | Curve inputs are prefilled from the dam sheet and validated | Hbed < Hmin < Hmax <= Hcrest and 0 < Vactive < Vmax. Hmin may be empty (shape class used). Warnings: fitted m outside [1, 4.5]; Hmax - Hbed below 10 m; computed surface area at Hmax above the sheet's drainage area. | U-M4-01, C-M4-01, W-M4-01 |
| FR-M4-02 | Generate the curve (D19, B3.3) | The curve passes through (Hbed, 0) and (Hmax, Vmax), and through (Hmin, Vdead) when Hmin is given. The table steps by the level interval the user enters in step 6 (0.5 m by default, above 0) from Hbed to Hcrest, with elevation, volume (hm³) and area (km²). Chart included. | U-M4-02, U-M4-03, C-M4-01, P-M4-01, W-M4-01 |
| FR-M4-03 | Compute annual totals and sediment elevations (B3.4) | Total = TE x (suspended + bedload). Elevation is read from the curve; volumes above the volume at the crest are limited to Hcrest and warned (D54). | U-M4-04, C-M4-02, P-M4-02, W-M4-02 |
| FR-M4-04 | Accumulation to date (D12) | Sum of annual totals from the commissioning year up to (not including) the analysis year, using each record year's own total and the mean for years outside the record. Years in the record before commissioning are ignored. Requires a commissioning year. | U-M4-05, C-M4-02 |
| FR-M4-05 | Projection and lifespan (D20) | Cumulative volume to the number of years the user enters in step 7 (100 by default) at the mean, min-year and max-year rates; lifespan = year the cumulative volume reaches Vdead. "Already exceeded in year X" when accumulation to date is above Vdead. | U-M4-06, U-M4-07, C-M4-02, P-M4-03, W-M4-02 |

### M5: Final analysis and reporting

| ID | Requirement | Acceptance criteria | Tests |
|---|---|---|---|
| FR-M5-01 | Isolate the minimum and maximum total-volume years | Year, total volume and elevation for each; ties resolve to the earliest year | U-M5-01 |
| FR-M5-02 | Write the run folder `outputs/<dam-slug>_<YYYYMMDD_HHMM>/` | `results.xlsx` (sheets Inputs, Suspended, Bedload, Annual, Curve, Projection, Extremes, Warnings), PNG charts (bedload trend, annual volume, curve, projection with the Hmin line), one CSV per phase | P-M5-01, P-M5-02, W-M5-01 |
| FR-M5-03 | Write `run.json` | App version, timestamp, dam, every input with its SHA-256, all parameters, sigma, phi and seed, flags, warnings | P-M5-03 |

### Cross-cutting

| ID | Requirement | Acceptance criteria | Tests |
|---|---|---|---|
| FR-X-01 | No input is loaded unless the user chose it, and there are no silent fallbacks | No bundled sample is read at startup or when an input is missing; a missing input is an error naming it | C-X-01, W-X-01 |
| FR-X-02 | Turkish-first parsing: `read_table`, `turkish_lower`, `to_ascii_turkish`, several encodings, dot decimals only (D66) | A UTF-8-BOM file, a CP1254 file and a semicolon-delimited file all load identically; a number with a comma is refused | C-X-02, C-X-03 |
| FR-X-03 | Validation errors name the file, row or cell and the expected form | Error text contains the offending location | C-X-04 |
| FR-X-04 | Editing a step invalidates later steps | Later steps become locked and their results are cleared | W-X-02 |
| FR-X-05 | Long computations run off the Tk thread | The UI stays responsive; the result is delivered via `run_in_background` | W-X-03 |
| FR-X-06 | Each input has one canonical label per column, matched by one rule (D67) | Every shipped sample loads without a warning; a retired alias or a Turkish header is refused naming the canonical label; columns outside the format give one warning per file | C-X-05 |

## A7. Data contracts

All inputs are copied into the project (FR-M1-02). Every column has **one canonical label** (`src/services/labels.py`, D67); `INPUT_FORMAT.md` is the same table written for the user. A header matches its label when the two are equal after folding case, Turkish letters, spaces, `.` `:` `%` and the superscripts `²` `³` (`labels.fold`), so `drainage area (km²)` matches `Drainage Area (km2)`. No other spelling and no other language is accepted. A missing required label is refused with the canonical labels and the columns the file has; two headers that fold to one label are refused; columns outside the format are ignored, with one warning per file naming them. Numbers use a point (D66). The sample files in `inputs/` are the reference layouts and load without a warning.

**Basin table** (sample: `inputs/master_yield.csv`; all five columns required)

| Column | Unit | Rule |
|---|---|---|
| Dam Name | | Required |
| Basin Name | | Required |
| Sub-basin Name | | Required, unique within a dam |
| Drainage Area (km2) | km² | Required, > 0. Downstream dams hold the *incremental* catchment (D21). |
| Main Waterway Slope | m/m | Required, numeric. Read as a decimal fraction (D23). |

**Zonal means** (sample: `inputs/raw_zonal_means.csv`; both columns required): `Sub-basin Name` (the same label as the basin table, the join key) and `MEAN` (t/ha/yr).

**Dam sheet** (samples: `inputs/bathymetry/*_bathymetry.csv`; one row per dam). Required: Dam Name, Bottom Elevation of River, Crest Elevation, Maximum Reservoir Elevation, Active Volume, Maximum Volume The other columns are optional.

| Column | Symbol | Unit | Use |
|---|---|---|---|
| Dam Name | | | Match with the basin table |
| Drainage Area (km2) | | km² | Optional. Cross-check only |
| Longest River Length (km) | | km | Optional. Informational |
| Top Elevation of River, Bottom Elevation of River | | m | **Bottom Elevation of River = Hbed**, must be the bed at the dam axis (OI-01). Top is optional and informational. |
| Average Slope | | m/m | Optional. Cross-check only. **Values are decimal m/m, not percent (D23).** |
| Crest Elevation | Hcrest | m | Curve upper end |
| Maximum Reservoir Elevation | Hmax | m | Curve |
| Active Volume | Vactive | hm³ | Curve; Vdead = Vmax - Vactive |
| Maximum Volume | Vmax | hm³ | Curve |
| Average Flow | | hm³/yr | Optional. Shown in step 3 |

**Daily flow**: `Date` (dd/mm/yyyy; ISO also accepted) and `Flow Q (m3/s)` (m³/s) required; `Water_Year` optional.

**DSİ monthly flow** (samples: `inputs/dam_flow_data/*_flow.csv`): `Yıllar` and `Ekim` ... `Eylül` required, in hm³; the `TOP.` column is optional and the `TOP.`/`ORT.` rows are ignored. This keeps the DSİ's own Turkish layout; the one folding rule also accepts `Yillar`, `Kasim` and so on.

**Fractions** (sample: `inputs/fractional_parameters.csv`)

| Column | Unit | Rule |
|---|---|---|
| di | m | Required, > 0 |
| Fi | | Required, sums to 1 within 0.02 |
| tau_ri, bi | | Optional, cross-checked only (D36) |

**`project.json`** (schema version 1; paths are relative to the project folder)

```json
{
  "schema_version": 1,
  "name": "Sakarya_Region",
  "inputs": {
    "basins": "inputs/basins.csv",
    "zonal_means": "inputs/zonal_means.csv",
    "fractions": "inputs/fractions.csv"
  },
  "dams": [
    {
      "name": "Çubuk 1",
      "slug": "cubuk_1",
      "sheet": "inputs/dams/cubuk_1.csv",
      "flow": {"path": "inputs/flow/cubuk_1_flow.csv", "sigma": 0.6, "seed": 0, "phi": 0},
      "curve": {"bed_elev_m": null, "crest_elev_m": null, "max_elev_m": null, "active_vol_hm3": null, "max_vol_hm3": null},
      "commissioning_year": null,
      "analysis_year": null,
      "h_min_m": null,
      "shape_class": "hill",
      "trap_efficiency_pct": 100
    }
  ]
}
```

`null` means "not yet entered"; `analysis_year: null` means the current year. `curve` holds the curve inputs the user changed from the dam sheet in step 6, and `null` keeps the sheet's value (D52). Output columns are named for their units (`Volume_m3`, `Volume_hm3`, `Elevation_m`, `Area_km2`).

## A8. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | Runs on Windows 10 or 11, offline. Until packaging is revisited (D30) it runs from the project's Python 3.14 virtualenv. |
| NFR-02 | A per-dam run over about 40 water years completes in 10 s or less, and the UI never blocks. |
| NFR-03 | Results are deterministic for the same inputs, parameters and seed. |
| NFR-04 | Every warning is shown to the user, written to `run.json` and written to the Warnings sheet. |
| NFR-05 | Layering rules (B2) hold: `src/core` imports no Tk, matplotlib, file dialogs or file I/O. |
| NFR-06 | Units appear on every field, column and chart axis. |
| NFR-07 | Code stays PyInstaller-compatible: bundled files are found through `resource_path()`. |

## A9. Assumptions, limitations and open issues

**Accepted limitations** (decided; the report states them)

| ID | Limitation | Decision |
|---|---|---|
| AL-01 | Suspended sediment uses a deposited bulk density of 1.3 t/m³ and bedload the solid density 2.65 t/m³, and the two volumes are added. Bedload's share of reservoir volume is therefore understated. | D8 |
| AL-02 | Wilcock hydraulics use a fixed rectangular channel: depth 0.5 m, width 50 m, n 0.05, D50 0.02 m, Fs 0.10, for every dam and every flow. Channel slope is unused. The consultant's constants (g 9.81, ρw 1000, ρs 2650, Fs 10%) are used as given; the d84 of 0.03 m in the same table is used by no formula. | D9 |
| AL-03 | Monthly DSİ flow is split into days at random (log-normal, sigma 0.6; optionally with a lag-1 phi, default 0). Bedload depends strongly on sigma and on phi. | D10, D62 |
| AL-04 | The USDA-SCS SIO coefficient 0.51 is used with area in km². It is conventionally quoted for mi²; the km² equivalent is about 0.566, which would raise SIO by about 11% and suspended yield by about 4%. | D37 |
| AL-05 | The ÇEM SIO changes by less than 0.1% across the sample slopes, so slope hardly affects it. The slope column is read as m/m. | D11, D23 |
| AL-06 | Dams are independent. Sediment trapped by an upstream dam is not removed from a downstream dam. | D21 |
| AL-07 | The elevation-volume curve is a one-parameter power law, not a survey, and sediment fills it as a level pool from the bed up. | D19, D20 |
| AL-08 | Years outside the flow record use the record mean for accumulation. | D12 |
| AL-09 | D50 stands in for the surface-mean grain size in the Wilcock reference stress. | D9 |
| AL-10 | The record's last year may be partial; the annual volume is the mean daily rate times a full year. | |

**Open issues** (need an owner before the milestone that depends on them)

| ID | Issue | Needed by | Status |
|---|---|---|---|
| OI-01 | Çubuk 2: Hmax - Hbed = 5.3 m for 22.4 hm³ implies a surface of about 8 to 17 km². Confirm that `Bottom Elevation of River` is the bed at the dam axis. | M4 | Closed 2026-10-26: the hydrologist said to take it as the bed at the dam axis |
| OI-02 | Commissioning years and (optionally) Hmin for the three sample dams are missing. The integration goldens use placeholder years (commissioned 1990, analysed 2020) until they are supplied. | M4 | Closed 2026-10-26: the user enters the commissioning year (and Hmin) in the application, step 3 and step 6; the placeholder years stay in the goldens only |
| OI-03 | Convention check: "analysis year" is treated as the first year *not yet* accumulated (so the default, the current year, excludes the incomplete current year). | M4 | Closed 2026-10-26: the hydrologist approved the convention (D56) |
| OI-04 | Hydrologist review of the bedload before and after D35 and D36, and confirmation of the tau_ri form (D50). | M3 | Closed 2026-10-26: the hydrologist approved the formulas (D35, D36, D50), the oracle and the goldens |
| OI-05 | Hydrologist confirmation of the shape classes (gorge 1.25, hill 2, foothill 3, lake 4) and of the plausibility thresholds in FR-M4-01. | M4 | Closed 2026-10-26: the shape classes stay as the default; an Hmin the user enters takes precedence |
| OI-06 | Independent hand calculations for `tests/verification/` (the spreadsheet is written by the developer, reviewed by the hydrologist). Closed for M2: the hydrologist signed off `suspended_verification.xlsx`. | M2 |
| OI-07 | The dam sheet is cross-checked against the sum of the dam's sub-basin areas and their area-weighted mean slope (D43). A downstream dam holds the *incremental* catchment in the table (D21) but the total drainage area in its sheet, so its area check will warn. Decide whether to compare against the cumulative upstream area. | M4 |
| OI-08 | The golden manifests record a `code_version` that is a branch commit not on `main` (suspended 582e3d6, reservoir 6e41806, bedload 4d7a0a3, integration 3cbc7d3), and the bedload and integration manifests do not record the lag-1 phi (0 for every golden). Fix both at the next regeneration, which needs hydrologist sign-off anyway; the goldens themselves are unaffected. | Next regeneration | Open |

---

# Part B: Technical design (how to build it)

## B1. Stack

| Concern | Choice |
|---|---|
| Language | Python 3.14 |
| UI | Tkinter / ttk (D13) |
| Data | pandas, numpy |
| Charts | matplotlib: `TkAgg` inside the UI, `Agg` for exported PNGs |
| Excel | openpyxl |
| Tests and lint | pytest; ruff (`check` and `format`). Added to `requirements.txt`. |
| Dependencies | One `requirements.txt` with loose `>=` ranges (D31) |
| Packaging | Deferred (D30); `resource_path()` keeps PyInstaller possible |

## B2. Architecture

Three layers; imports point downward only (D16).

```
        +---------------------------+
        |  src/ui   (Tk wizard)     |  collect input, call services on a
        +-------------+-------------+  background thread, render results
                      |
        +-------------v-------------+
        |  src/services             |  per-dam pipeline M1..M5, project I/O,
        +-------------+-------------+  run folder, xlsx / png / csv / run.json
                      |
        +-------------v-------------+
        |  src/core   (pure math)   |  no Tk, no matplotlib, no file I/O
        +---------------------------+
        src/utils: paths.py (read_table, resource_path) used by services and ui
```

**Rules.** `core` imports only the standard library, numpy and pandas. `services` never imports `tkinter`. `ui` holds no calculation and no file parsing. Dialogs live in `ui/common.py` only.

**Target module map**

| Module | Status | Notes |
|---|---|---|
| `src/core/rusle.py` | kept | Formulas unchanged (D37). Dead helpers removed (`raster_mean_t_ha_yr`, `to_phase2_handoff`). Reads the canonical `Drainage Area (km2)` label (D67). |
| `src/core/wilcock.py` | kept, changed | D35 and D36 fixes. `BedloadVisualizer` and the matplotlib import move to `services/reporting.py` (done in M3.1). |
| `src/core/monthly_flow_preprocessor.py` | kept, trimmed | `load`, `export_csv` and `main` moved to `services/flow_files.py` in M3.1 (`run`, which only called `load`, is gone). |
| `src/core/reservoir.py` | new | Curve fit, table, inverse, area, plausibility checks |
| `src/core/projection.py` | new | Accumulation, projection, lifespan |
| `src/core/integration.py` | new | Annual totals with TE and the elevations they reach, limited to the crest. Replaces `src/data/reporter.py` |
| `src/services/project.py` | new | Project model, `project.json`, import-copy |
| `src/services/regional.py`, `suspended.py`, `bedload.py`, `reservoir.py`, `integration.py` | new | One service per wizard computation |
| `src/services/reporting.py`, `run_export.py` | new | `reporting.py` draws the charts (png); `run_export.py` writes the run folder: xlsx, csv, `run.json` (D63) |
| `src/ui/wizard.py`, `src/ui/steps/` | new | Controller and one view per step |
| `src/ui/common.py`, `src/utils/paths.py` | kept | |
| `src/data/database.py` (`BasinDatabase`), `src/ui/{app,rusle_view,wilcock_view,integration_view}.py`, back-compat shims, `load_raster_matrix` | removed in M1 | |
| `src/data/reporter.py` | removed in M4.2 | Replaced by `src/core/integration.py`; `src/data/` is gone |

## B3. Calculation reference

Symbols are as in A4. "(D35)" and "(D36)" mark the two changes from today's code; everything else matches `src/core` as of this spec.

### B3.1 Suspended sediment (M2)

For each sub-basin with zonal mean *E* (t/ha/yr), area *A* (km²) and slope *S* (m/m):

- area in hectares: `A_ha = 100 A`
- gross erosion: `G = E · A_ha` (t/yr)
- USDA-SCS: `SIO_u = 0.51 · A^(-0.11)` (0 if A <= 0)
- ÇEM: `SIO_c = 1 / (2.05823 + 0.02816 · S²)`
- average: `SIO = (SIO_u + SIO_c) / 2`
- yield mass: `Y = G · SIO` (t/yr)
- volume: `V_s = Y / 1.3` (m³/yr, bulk density 1.3 t/m³)
- specific yield: `V_s / A` (m³/yr/km²)

The dam's suspended volume is `ΣV_s` over that dam's sub-basins.

### B3.2 Bedload (M3)

Constants: g = 9.81, ρw = 1000, ρs = 2650 kg/m³, s = ρs/ρw, h = 0.5 m, B = 50 m, n = 0.05, D50 = 0.02 m, Fs = 0.10.

For each daily flow *Q* (m³/s), with *Q* = 0 giving zero transport:

- `v = Q / (B · h)`
- `τ = ρw · g · n² · v² / h^(1/3)` (Pa)
- `u* = sqrt(τ / ρw)`

Reference stress per fraction *di* (D36: always computed; D50: the hydrologist's form):

- `τrm* = 0.021 + 0.015 · exp(-20 · Fs)` (0.02303 for Fs = 0.10)
- `b_i = 0.67 / (1 + exp(1.5 - di / D50))`
- `τri* = τrm* · (di / D50)^b_i`
- `τri = τri* · (s - 1) · ρw · g · di` (Pa)

For the sample fractions (di = 4, 10, 20, 32, 50 mm) τri* is 0.01828, 0.02033, 0.02303, 0.02717, 0.03608 and τri is 1.184, 3.290, 7.456, 14.073, 29.197 Pa. The sample file's `tau_ri_star` and `tau_ri` columns (1.18, 3.29, 7.46, 14.07, 29.2 Pa) are the same to the file's rounding (at most 0.31%), so it gives no warning.

D50 departs from the printed Wilcock & Crowe (2003) Eqs. 3 and 5. The paper applies the hiding function to the stress in Pa, `τri = τrm · (di / Dsm)^b` with `τrm = τrm* · (s - 1) · ρw · g · Dsm`, which gives 5.918, 6.580, 7.456, 8.796 and 11.679 Pa for the sample. The hydrologist's values are the reference, so the program reproduces them. The hydrologist is asked to confirm the form under OI-04.

Transport:

- `φ_i = τ / τri`
- `W*_i = 0.002 · φ^7.5` for `0 < φ < 1.35`
- `W*_i = 14 · (1 - 0.894 / φ^0.5)^4.5` for `φ >= 1.35` **(D35; today's code omits the square root)**
- `q_bi = W*_i · Fi · u*³ / ((s - 1) · g)` (m²/s)
- `q_b = Σ q_bi`

D35 is a transcription fix. With it, W* at φ = 1.35 is 0.0190 from both branches. Today's code gives 0.0190 below and 0.1059 above, and overstates W* by 6.3x, 4.6x and 2.9x at φ = 2, 4 and 10.

Annual summary (group key `Water_Year` if present, else calendar year):

- `Q_mean`, `q̄_b` = mean of the daily values in the group
- `V_b = q̄_b · B · 31,557,600` (m³/yr; 365.25 days)
- `M_b = V_b · 2.65` (t/yr)

Monthly-to-daily (D10): for each month with volume *V* (hm³) and *d* days, draw weights `w_k ~ LogNormal(-σ²/2, σ)` (mean one) with a generator seeded by `(seed, year, month)`; the daily volume is `V · 10⁶ · w_k / Σw`, and `Q_k = daily_volume / 86,400`. Volume is conserved exactly. `σ = 0` gives an even split.

Lag-1 form (D62): the log-flow follows an AR(1) chain, so a day depends partly on the day before. With `ε` standard normal draws from the same generator, `z_1 = ε_1` at the start of the record and `z_t = φ·z_{t-1} + √(1-φ²)·ε_t` after it, so `z` has variance one for any φ. The weights are `w_t = exp(σ·z_t - σ²/2)`, and the daily volume is `V · 10⁶ · w_t / Σw` as above, which corrects each month to its observed volume. The chain carries over from the last day of one month into the first of the next, and restarts when a month is missing from the table. `0 ≤ φ < 1`; `φ = 0` gives the independent split above.

### B3.3 Reservoir curve (M4a)

Let `x = (H - Hbed) / (Hmax - Hbed)`.

- volume: `V(H) = Vmax · x^m` (hm³), defined from Hbed up to Hcrest
- surface area: `A(H) = dV/dH = m · V(H) / (H - Hbed)` (km², because hm³ per m = 10⁶ m²)
- inverse: `H(V) = Hbed + (Hmax - Hbed) · (V / Vmax)^(1/m)`
- dead volume: `Vdead = Vmax - Vactive`

Choosing *m* (D19):

- if Hmin is given: `m = ln(Vdead / Vmax) / ln((Hmin - Hbed) / (Hmax - Hbed))`, so the curve passes through (Hmin, Vdead)
- otherwise *m* is the shape-class value (gorge 1.25, hill 2, foothill 3, lake 4) and `Hmin = H(Vdead)`

Worked examples (shape class): Kavşakkaya, foothill: Hmin = 1088.86 m, A(Hmax) = 4.09 km². Çubuk 1, hill: Hmin = 892.69 m, A(Hmax) = 0.57 km². Çubuk 2, hill: A(Hmax) = 8.45 km² (OI-01).

### B3.4 Integration, accumulation, lifespan (M4b)

All volumes in hm³ from here (m³ / 10⁶).

- annual total for record year *y*: `T(y) = TE · (V_s + V_b(y))`, with `TE` as a fraction
- sediment elevation for a cumulative volume *S*: `H(S)`, clamped to Hcrest with a warning
- rates: mean `T̄`, `T_min = min T(y)`, `T_max = max T(y)`
- accumulation to date, with commissioning year *c* and analysis year *a*: `S0 = Σ T'(y)` for `c <= y < a`, where `T'(y) = T(y)` for years in the record and `T̄` otherwise
- projection at rate *r*: `S(a + k) = S0 + k · r`, for k = 0 to the years entered (100 by default, at most 1000; D61, D69)
- lifespan at rate *r*: `a + (Vdead - S0) / r`; if `S0 >= Vdead`, "already exceeded"; if `r = 0`, "not reached"

In the DSİ case the record years are water-year labels, and they are used as-is.

## B4. Persistence

```
<project>/
  project.json
  inputs/                     copies of every imported file
  outputs/<dam-slug>_<YYYYMMDD_HHMM>/
      results.xlsx, *.png, suspended.csv, bedload.csv, reservoir_curve.csv, integration.csv, projection.csv, run.json
```

Run-folder slugs use `to_ascii_turkish`, lowercased, with spaces replaced by underscores. A run never overwrites another run. `project.json` is rewritten whenever the user changes a parameter or imports a file, and carries `schema_version` for future migration.

## B5. Errors and warnings

- A validation error stops the step and names the file, row or cell and the expected form (FR-X-03).
- A warning does not stop the step. It appears in the UI, in `run.json` and in the Warnings sheet (NFR-04).
- Services raise `ValueError` or `KeyError` with those messages. Only the UI turns them into dialogs.
- Python `logging` records progress and every error dialog on the console and, while a project is open, in `logs/app.log` inside the project folder; an error the program did not foresee is logged with its traceback and the dialog names the file (D72).

## B6. Test strategy

The suite was rebuilt in four layers (D28, after D24), planned together with the requirements in A6.

| Layer | ID prefix | Folder | Oracle |
|---|---|---|---|
| Unit: formula verification | `U` | `tests/unit/` | Independent hand calculations in a spreadsheet in `tests/verification/`, reviewed by the hydrologist. Never the code's own output. |
| Input contract | `C` | `tests/contract/` | The data contracts in A7: canonical labels, encodings, refused commas in numbers, mislabelled headers, malformed files |
| Pipeline | `P` | `tests/pipeline/` | Reviewed golden outputs in `tests/benchmarks/`, one set per sample dam |
| Wizard | `W` | `tests/ui/` | Behaviour: navigation, gating, invalidation. Dialogs patched. |

**Conventions**

- Test IDs follow `<layer>-<milestone>-<nn>` and appear in the test name, so `pytest -k M3` selects a milestone.
- Wizard tests share the session-scoped `tk_root` fixture and build their UI in a `tk.Toplevel` (the current `tests/conftest.py` pattern). They need a display, which the Windows runner provides.
- Golden files are regenerated only through a script that records the code version, and are committed only after hydrologist sign-off.
- Old tests move to `tests/legacy/` (D29). `pytest.ini` gains `addopts = --ignore=tests/legacy`; run them locally with `pytest -o addopts="" tests/legacy`. A legacy test is ported only if it maps to a requirement and passes review. The folder was deleted at M5 and `addopts` removed (D65).
- `.gitignore` ignores `*.csv` and `*.xlsx` outside `inputs/`; M0 adds exceptions for `tests/**` so benchmark files are tracked.

The traceability matrix is the Tests column in A6.

## B7. Infrastructure and development pipeline

**Hosting.** Public GitHub repository `umairnaeem2703/sediment-analysis-app`. Actions are free for public repositories. Real sample data stays in `inputs/` (D22).

**Branching and Definition of Done** (D26). Every task is a short-lived branch off `main`:

1. Write failing tests that reference the requirement ID.
2. Implement the smallest change that passes.
3. `pytest` and `/validate-calc-engine` pass.
4. `/code-review` has no open findings.
5. Commit with `/commit-msg` (conventional format).
6. Open a pull request; CI is green; squash-merge.
7. A change to any calculated number also needs hydrologist sign-off and regenerated goldens.

**CI** (`.github/workflows/ci.yml`, D25): on push and pull request, on `windows-latest`: checkout, `setup-python` 3.14, `pip install -r requirements.txt`, `ruff check .`, `ruff format --check .`, `pytest`. A failing run blocks the merge to `main` through branch protection. There is no mypy or coverage gate.

**Local tooling.** Shared Claude config (`.claude/`, except `.claude/settings.local.json`) is tracked (D27), so the team works with the same skills, hooks and agents. CI never depends on them. `/validate-calc-engine` is updated locally in M0.

**Packaging and release** are out of scope (D30).

## B8. Roadmap

Each milestone is a vertical slice: services, wizard step, tests and sign-off. Exit criteria are listed; there are no dates.

| Milestone | Tasks | Exit criteria | Status |
|---|---|---|---|
| **M0 Pipeline setup** | Fast-forward local `main` to `origin/main` (it already contains `branch1`), then retire `branch1` and `branch2` (confirm before deleting remote branches). Add ruff and one formatting-only commit with no logic changes. Add the `.gitignore` exceptions. Add the CI workflow and branch protection. Move current tests to `tests/legacy/` and create the new layout with one import smoke test. Create `src/services/`. | CI is green on a pull request; `pytest` runs the new layout only | Done |
| **M1 Regional data** | Project model, `project.json`, import-copy. Basin and dam-sheet validators, including the `Drainage Area (km2)` label and cross-checks. Wizard shell with steps 1 to 3. Remove the old tabs, back-compat shims, `src/data/database.py` and dead code. Update the architecture section of `CLAUDE.md`. | FR-M1-* tests pass; the three sample dams load; the app opens to the wizard | Done (steps 1 to 3 and the cut-over; the old UI is tagged `legacy-ui`) |
| **M2 Suspended** | Suspended service and step 4. Verification workbook for B3.1. Golden outputs for the three dams. | FR-M2-* tests pass; hydrologist signs off the goldens | Done (the hydrologist signed off the workbook; the goldens in `tests/benchmarks/` equal its three sample cases) |
| **M3 Bedload** | D35 and D36 fixes. Move plotting and file I/O out of core. Bedload service and step 5. Before and after table for the hydrologist. | FR-M3-* tests pass; OI-04 closed | Built and signed off by the hydrologist (OI-04, 2026-10-26): M3.1 (formulas, oracle, core clean-up, before and after table) and M3.2 (bedload service, step 5, goldens) |
| **M4 Reservoir and projection** | `reservoir.py`, `projection.py`, `integration.py`. Steps 6 and 7. Commissioning years and Hmin collected (OI-02). | FR-M4-* tests pass; OI-01, OI-03, OI-05 closed | Done: M4.1 (curve, service and step 6) and M4.2 (integration, projection, step 7, `src/data/` removed); OI-01, OI-02, OI-03 and OI-05 closed 2026-10-26; goldens signed off by the hydrologist 2026-10-26 (the integration and projection goldens use placeholder years, so their dam values are provisional until the real years are entered) |
| **M5 Reporting** | Reporting service and step 8. `run.json` with the app version. Delete `tests/legacy/`. | FR-M5-* tests pass; end-to-end sign-off for the three dams; version 1.0.0 (no build) | Done (the hydrologist signed off the end-to-end run of the three dams on 2026-10-27) |

## B9. Gap analysis: current code vs target

| Area | Current (evidence) | Target | Milestone | Status |
|---|---|---|---|---|
| Dams mixed | The RUSLE tab sums every row, so three dams give 118,933 m³/yr (`src/ui/rusle_view.py:321`) | Per-dam total (FR-M2-03) | M2 | Done (M2): `compute_suspended` takes one dam's rows |
| Silent sample fallbacks | Integration loads bundled samples when nothing is chosen (`src/ui/integration_view.py:154-185`) | Error naming the missing input (FR-X-01) | M1 | Done (M1): the wizard loads only files the user chose |
| Logic in views | `_ensure_phase2_volume`, `_load_default_phase3`, report text (`integration_view.py:86-135, 225-251`) | Services (B2) | M1 to M4 | Done (M4.2): the old views are gone and each step has its service |
| Not a curve | `inputs/bathymetry.csv` had one row per dam; the user has since removed it. `prepare_bathymetry` treats rows as one curve. | Generated per-dam curve (FR-M4-02) | M4 | Done (M4.1): `core/reservoir.py`, `services/reservoir.py` and step 6; goldens signed off 2026-10-26 |
| No accumulation or lifespan | One year's volume is mapped to an elevation (`integration_view.py:194-205`) | FR-M4-03 to FR-M4-05 | M4 | Done (M4.2): `core/integration.py`, `core/projection.py` and step 7; goldens signed off 2026-10-26 (placeholder years, see B8) |
| Duplicate elevation columns | `Interpolated_Elevation_m`, `Elevation_m`, `Elevation` (`integration_view.py:199-205`) | One `Elevation_m` | M4 | Done (M4.2): every table has one `Elevation_m` column |
| W* high branch | Missing square root (`src/core/wilcock.py:63, 85`) | D35 | M3 | Done (M3.1): both code paths, pinned by `tests/unit/test_wilcock_formulas.py` |
| tau_ri precedence | File column wins (`wilcock.py:106-115`) | D36 | M3 | Done (M3.1): `bi` and `tau_ri` are computed, in the hydrologist's form (D50); supplied columns are cross-checked into `FractionalModel.warnings` |
| Plotting in core | matplotlib in `src/core/wilcock.py:5` and `BedloadVisualizer` | `services/reporting.py` | M3 | Done (M3.1); `tests/unit/test_layering.py` keeps it that way |
| File I/O in core | `MonthlyFlowPreprocessor.load/export_csv/main` | Services | M3 | Done (M3.1): `services/flow_files.py` |
| Area header | `find_basin_table_columns` does not match `Drainage Area (km2)`; 9 tests fail since the `inputs/` edits | Alias added (FR-M1-03) | M1 | Done (M1.1) |
| Dead code | `BasinDatabase` (`src/data/database.py`), `load_raster_matrix` (`src/utils/paths.py:67`), `raster_mean_t_ha_yr` and `to_phase2_handoff` (`rusle.py`), the "Antigravity" docstring (`src/__init__.py`) | Removed | M1 | Done (M1.5) |
| Back-compat shims | Aliases and properties on `SedimentApp` (`src/ui/app.py:58-178`) | Removed with the old UI | M1 | Done (M1.5) |
| Suspended averaging | `merge_sediment_data` averages across years before adding (`src/data/reporter.py:26-29`) | One static value per dam | M4 | Done (M4.2): `compute_integration` takes the dam's one suspended total; `reporter.py` is removed |
| No CI or lint | No `.github/`, no ruff config, no README | D25 | M0 | Done (M0) |
| Tests | 150 tests written without a plan; 9 fail on the edited inputs | Rebuilt (D24, D28) | M0 to M5 | Done (M5): the new layout holds every test; `tests/legacy/` is deleted (D65) |
| `.gitignore` | `*.csv` and `*.xlsx` ignored outside `inputs/` | Exceptions for `tests/**` | M0 | Done (M0) |
| Branches | Local `main` is behind `origin/main`; `branch1` and `branch2` are stale | Single `main` flow | M0 | Done (M0) |

The evidence column describes the code before M1. Files removed in M1.5 can be read at commit `cf06dfa`, for example `git show cf06dfa:src/ui/rusle_view.py`.

---

# Appendix: Decision log

| ID | Decision | Rationale |
|---|---|---|
| D1 | Single-user, offline Windows desktop app | The users are individual analysts; no server to run |
| D2 | Keep `src/core` formulas, rebuild the UI and controller | The formulas hold the domain value; the UI shape was wrong |
| D3 | Per-dam analysis inside a regional project; batch is later | Mixed dams gave a wrong total |
| D4 | No database | Plain files suffice and are easy to audit |
| D5 | Project folder with `project.json`, `inputs/` and `outputs/` | Remembers a session without a database |
| D6 | Phase 4 and 5 give annual totals, min and max years, and a cumulative projection | The brief's goal is fill rate and lifespan |
| D7 | Trap efficiency is a per-dam percentage, default 100 | Conservative and transparent |
| D8 | Keep 1.3 and 2.65 t/m³ | Accepted assumption (AL-01) |
| D9 | Keep the fixed Wilcock channel | Accepted limitation (AL-02) |
| D10 | Accept daily and DSİ monthly flow; flag synthetic | Some dams only have monthly data |
| D11 | ÇEM SIO as coded | Accepted (AL-05) |
| D12 | Projection starts at the commissioning year | The brief asks for *existing* accumulation |
| D13 | Tkinter / ttk | No new dependency |
| D14 | Excel, PNG and CSV outputs; no PDF | Enough for the reviewers |
| D15 | English UI, Turkish data | Existing behaviour; no translation catalogue |
| D16 | Layers `ui -> services -> core` | Moves logic out of views; core is testable without a display |
| D17 | Wizard UI | Guides the user through the phases in order |
| D18 | Eight wizard steps with gating | See A5 |
| D19 | Generated power-law curve, fitted through the dead-storage point when Hmin is known | No measured curve is available |
| D20 | Lifespan inputs and level-pool fill | Needed to reach dead storage |
| D21 | Dams independent; incremental catchment entered by the user | Cascade routing is out of scope |
| D22 | Real samples stay in the public repo | Owner's choice |
| D23 | Slope is decimal m/m; the `%` header is a mislabel | Owner's statement |
| D24 | Rebuild the test suite | The current tests were not planned |
| D25 | CI on `windows-latest` with ruff and pytest; blocking | Free for a public repo; Tk tests need Windows |
| D26 | Branch, test-first, review, squash; hydrologist sign-off for numeric changes | Small reviewable steps |
| D27 | Shared `.claude/` config is tracked; `.claude/settings.local.json` stays untracked | Team uses the same skills and hooks; the local file holds per-machine permissions |
| D28 | Four test layers with traceability | See B6 |
| D29 | Old tests go to `tests/legacy/`, local only | Safety net without blocking merges |
| D30 | Packaging and release out of scope | Deferred by the owner |
| D31 | Loose `>=` dependency ranges; add ruff | Owner's choice |
| D32 | Roadmap M0, then vertical slices M1 to M5; old UI removed in M1 | Avoids maintaining two UIs |
| D33 | Imports are copied into the project; originals untouched | Portable, auditable project folder |
| D34 | Spec in `docs/project_spec.md`, pointer in `CLAUDE.md` | Found by future sessions |
| D35 | Fix the missing square root in the W&C high-transport branch | Transcription error: discontinuity at phi = 1.35 and a 3x to 6x overstatement |
| D36 | tau_ri is always computed; a supplied value is cross-checked | A computed value does not depend on a rounded or hand-edited column, which stays as a check. (Recorded when the sample column looked off by di / D50; D50 shows that was the formula, and the column now agrees) |
| D37 | Keep `0.51 · A^(-0.11)` with area in km² | Accepted (AL-04) |
| D38 | A basin table with invalid cells is still imported and shown in the grid with the cells flagged. An unreadable file, missing columns or no data rows is refused and nothing is copied | The grid is where the data is fixed (FR-M1-04); a structural problem cannot be fixed there |
| D39 | The project's dams follow the basin table: one per dam name, matched by identifier (slug). Settings of dams that stay are kept; dams that leave the table are dropped and named in a notice | One source of truth for which dams exist |
| D40 | Step 2 is complete when the basin table is valid and the zonal means are loaded. A dam sheet is needed only for the dam chosen in step 3 | One dam can be analysed without every sheet |
| D41 | Grid edits rewrite the project's copy as comma-separated UTF-8 with BOM and canonical English headers; the file the user picked is never touched | Edits persist without altering originals (D33) |
| D42 | Step 3: commissioning year optional; analysis year blank means the current year and is not before the commissioning year; trap efficiency above 0 and at most 100, default 100; Hmin optional | Missing commissioning years (OI-02) must not block steps 4 to 6 |
| D43 | A dam sheet is cross-checked against the sum of the dam's sub-basin areas and their area-weighted mean slope; more than 1% apart gives a warning | The spec was silent for dams with several sub-basins (OI-07) |
| D44 | Work-package pull requests are squash-merged once CI is green and every review finding is fixed or declined in the PR description | Branch protection already requires the PR and the `ci` check |
| D45 | The suspended service writes `suspended.csv` into a folder it is given; step 4 creates no run folder. The file holds a row per sub-basin and a final `Total` row (area, gross mass, yield mass, volume) | The run folder and its naming belong to M5; the total is the number the reviewer reads |
| D46 | The M2 oracle is a workbook of live formulas for review plus a CSV of the same cases worked out with `math` in `tests/verification/make_suspended_oracle.py`; the unit tests read the CSV. A pull request with new goldens is held until the hydrologist signs them off | No spreadsheet engine was available to store the workbook's results. Evaluating the workbook's formulas separately gave the CSV values exactly. B6 allows goldens only after sign-off |
| D47 | W* continuity at phi = 1.35 is tested to a relative jump below 1e-3, not 1e-6 | The published Wilcock & Crowe coefficients are rounded: with D35 the branches give 0.018990 and 0.018998 (4.2e-4 apart). 1e-6 cannot be met without changing the published function |
| D48 | Step 5 takes the dam's flow file (a daily series or a DSİ monthly table, CSV or Excel), the grain fractions, and the sigma and seed of the monthly split. Each file is checked and copied into the project when it is chosen (`inputs/flow/<slug>_flow.*`, `inputs/fractions.*`); sigma and seed are stored on the dam. Changing a file, sigma or seed clears the result and the later steps. The result is shown as an annual table and a trend chart in two tabs | A missing input is an error naming it (FR-X-01); the settings belong with the flow they split; A5 asks for the table, the chart and the synthetic flag |
| D49 | The bedload service writes `bedload.csv` (one row per year, no total row) into a folder it is given, and `reporting.py` saves the trend chart as `bedload_trend.png` the same way; step 5 creates no run folder. Charts are built with matplotlib's `Figure`, not pyplot | Same boundary as D45 (the run folder is M5). A `Figure` holds no global state, so it can be embedded in the wizard and saved from a worker thread |
| D50 | tau_ri is `τrm* · (di / D50)^b_i · (s - 1) · ρw · g · di`: the hiding function scales the Shields number and each fraction is converted to a stress with its own di. This departs from the printed Wilcock & Crowe Eqs. 3 and 5 | The user decided on 2026-10-26 that the program reproduces the hydrologist's sample `tau_ri`, and this form matches it to the file's rounding (at most 0.31%). The printed form gives 5.9 to 11.7 Pa against the file's 1.18 to 29.2 Pa. With it D36 changes the mean bedload by under 0.01% (a single year by at most 2.3%) and D35 explains the drop in the mean (B9). Awaiting the hydrologist's confirmation (OI-04) |
| D51 | The curve table steps 0.5 m from Hbed; a crest that is not on that grid is added as the last row, so the table always ends at Hcrest. The surface area is written `m·Vmax/(Hmax - Hbed)·x^(m-1)`, equal to `m·V/(H - Hbed)` above the bed and defined at the bed itself (zero for m above 1) | FR-M4-02 asks for 0.5 m steps from Hbed to Hcrest, and Çubuk 1's crest (908.6 m) is not a multiple of 0.5 m; B3.3's form divides 0 by 0 at the bed |
| D52 | Step 6 prefills Hbed, Hmax, Hcrest, Vactive and Vmax from the dam sheet. An input the user changes is kept on the dam in an optional `curve` block of `project.json` (`null` keeps the sheet's value), and the step lists the differences from the sheet. `schema_version` stays 1: a project written before step 6 opens with no edits. Hmin stays the one field of step 3: editing it in step 6 writes `h_min_m`, updates step 3's field, and clears only the steps after step 6. The shape class is stored on the dam and has no default; Hmin or a shape class must be given | The sheet stays the source of the numbers, so a re-imported sheet is not hidden by copied values; two copies of Hmin would disagree; a silent default class would move every Hmin and result |
| D53 | The reservoir service writes `reservoir_curve.csv` (elevation, volume, area) into a folder it is given, and `reporting.py` saves `reservoir_curve.png` the same way; step 6 creates no run folder. The goldens use the shape classes of the worked examples in B3.3 (Kavşakkaya foothill, Çubuk 1 and 2 hill) and no Hmin | Same boundary as D45 and D49; the hydrologist confirms the classes under OI-05 |
| D54 | A sediment volume above the volume at the crest, V(Hcrest), is limited to the crest elevation and counted into one warning per table, instead of being limited at Vmax as the wording of FR-M4-03 says | B3.3 defines the curve up to Hcrest and B3.4 limits to Hcrest; Vmax is only the volume at Hmax, and a reservoir can fill above it |
| D55 | The elevation of a year of the record is H of that year's own total, the elevation of the accumulation to date is H(S0), and each projected year has H(S(a+k)) | B3.4 defines H for a cumulative volume; a year's own total read alone is what FR-M4-03 and the old code did, and the other two follow from the same function |
| D56 | Lifespan is `a + (Vdead - S0) / r` as a fractional year, not rounded and not cut at the 100-year projection. S0 >= Vdead is "already exceeded" and wins over r = 0; the year X is the first year from the commissioning year whose cumulative total reaches Vdead. r = 0 with S0 < Vdead is "not reached". The mean for years outside the record is the mean of the whole record, including record years before commissioning | B3.4 gives the formula; a rounded year would hide the small differences between the three rates; the mean of the record is the best estimate of an unrecorded year |
| D57 | Step 7 has nothing to enter: it uses steps 3 to 6 and needs the commissioning year, and without it says so and names step 3. The service writes `integration.csv` (per year: suspended and bedload as they stay after TE, total, elevation) and `projection.csv` (cumulative volume and elevation at each rate) into a folder it is given; the year-by-year accumulation stays in the result. The chart is drawn by `reporting.py`; saving it is M5 | Same boundary as D45, D49 and D53; D42 lets steps 4 to 6 run without a commissioning year, so this is the first step that cannot |
| D58 | `src/data/` and `tests/legacy/test_reporter.py` are removed | Nothing used them after M4.2 and the new modules replace them |
| D59 | The M4.2 oracle is a workbook with one sheet of live formulas for each of seven cases, plus four CSVs worked out with `math` in `tests/verification/make_integration_oracle.py`. The goldens use placeholder commissioning and analysis years (1990 and 2020, OI-02) | Same method as D46. The real years of the three dams are not known |
| D60 | The level interval of the table is an input of step 6: a number above 0 m, 0.5 m by default, read with a point as the decimal separator (D66). It sets only the table, its chart and its CSV, and it supersedes the 0.5 m step of D51 (the grid still starts at Hbed and a crest off it closes the table). It is not kept on the dam, and changing it un-completes step 6 without resetting later steps | The user asked to choose the interval. The curve, the integration and the projection do not depend on it, so it is not a model input and does not belong in `project.json` (D52). Step 7 reads the curve, not the table |
| D61 | The length of the projection is an input of step 7: a whole number of years of at least 1, 100 by default, read with a point as the decimal separator (D66). It sets only the projection table and chart; the accumulation, rates and lifespans do not depend on it and the lifespan is not cut at it (D56). It is not kept on the dam, and changing it un-completes step 7 until Compute | The user asked to choose the horizon instead of the fixed 100 years. It changes no calculated number, so like D60 it is not a model input. The length is limited to 1000 years (D69) |
| D62 | The monthly-to-daily split can carry a lag-1 autocorrelation φ in the log-flow (AR(1)): `0 ≤ φ < 1`, default 0, a setting of step 5 next to sigma and seed and kept on the dam (`flow.phi` in `project.json`; a project saved without it opens with 0). The chain runs on across month boundaries; each month's innovations still come from a generator seeded by `(seed, year, month)`, and every month is rescaled to its observed volume | The user asked for flood waves and dry-spell decay instead of independent daily noise. At φ = 0 the output is identical to the split of D10, so the bedload goldens are unchanged and need no new sign-off; a non-zero default would need them regenerated and signed off |
| D63 | The run folder is written by `src/services/run_export.py` (`export_run`), not by `reporting.py`, which keeps the charts (and gains `annual_volume.png` and `projection.png`). The folder is `outputs/<dam-slug>_<YYYYMMDD_HHMM>/`, and a run that finds it taken gets `_2`, `_3`, ... so none is overwritten. Every input is hashed before the folder is created, so a missing input is an error naming it and leaves no folder; `run.json` is written last, and a folder whose writing fails is removed. `run.json` also holds the project name and the parameters as name, value and unit; the level interval is the one entered in step 6 (`CurveResult.step_m`), `Hmin` is the one entered (blank when a shape class fixed the curve) and `Hmin of the curve` the level the curve gives | B2 listed workbook, charts, CSV and `run.json` in one file, which already held the charts and would have mixed drawing with file layout. Minute-resolution names can collide when a run is exported twice, and B4 says a run never overwrites another. Nothing here changes a calculated number |
| D64 | `results.xlsx` has the eight sheets of FR-M5-02. Suspended, Bedload, Annual, Curve and Projection are the tables of the CSV goldens (Suspended with its `Total` row). Inputs has the columns Group, Item, Value, Unit and SHA-256 (groups Run, Parameter and File). Extremes holds the Minimum and Maximum rows (Year, Total_hm3, Elevation_m), then a blank row and a table of the accumulation to date, the dead volume, the annual rates and the lifespan at each rate (a year, or the text "Already exceeded in X" or "Not reached"). Warnings has Phase and Warning, one row for each warning of the zonal means and dam sheet (Inputs), suspended, bedload, curve and integration, headed even when empty (NFR-04). The CSVs are the five of the phases; the extremes are in the workbook only | FR-M5-02 names the sheets but not their columns. The accumulation and lifespans appear in no other sheet, and Extremes is where the reader looks for the years that bound the record. `tests/pipeline/test_run_export.py` compares the tables with the existing goldens, so no new golden or sign-off is needed |
| D65 | `src.__version__ = "1.0.0"` is the app version that `run.json` and the Inputs sheet record. `tests/legacy/` is deleted, `addopts` is removed from `pytest.ini` and the validate-calc-engine skill no longer runs it; every legacy case was already in the new layout except the Turkish helper tests, which are ported to `tests/contract/test_turkish_helpers.py` (C-X-02). Computing step 7 again resets step 8 when its annual or projection table changed, and keeps it when they did not (FR-X-04). `to_phase3_handoff`, `compute_daily_fractional_transport` and `year_column` in `core/wilcock.py` are removed: nothing called them and the deleted legacy tests were the only ones that did; no calculated number changes | The roadmap fixes version 1.0.0 and the deletion for M5. A report written from a superseded integration must not stay marked as complete |
| D66 | Numbers are read with a point as the decimal separator. A comma in a number cell (`834,7`, `1,234`) is refused as not a number, in tables, monthly flow and the step fields | A comma cannot be told apart from a thousands separator (`1,234` was read as 1.234), so it is refused rather than guessed. Supersedes the decimal-comma reading in FR-X-02 |
| D67 | One canonical English label per column and one matching rule for every input. A header matches its label after folding case, Turkish letters, spaces, `.` `:` `%` and `²` `³`; alias lists, the Turkish header aliases (Havza, Eğim, Alan, Debi, Tarih, ORTALAMA ...) and the column-guessing in the zonal matcher are removed. All labels live in `src/services/labels.py`; `src/core` receives canonical columns only. Columns outside the format are ignored with one warning per file. The DSİ monthly layout keeps its own Turkish labels. All five basin-table columns are required; the daily flow label is `Flow Q (m3/s)` and the zonal join key is `Sub-basin Name` | Three matching rules and long alias lists accepted too many spellings, matched the same concept differently per file and dropped columns without a word. A user now has one format to follow (`INPUT_FORMAT.md`). Files with retired labels are refused with the standard missing-column message; no numeric result changes |
| D68 | A sub-basin matches a zonal entry exactly only through its normalised name or an alias of it; a number alone is not an alias. Every loose match (containment, or the same name with its number in another place) needs the same number in both names. "Çubuk 2" no longer takes the mean of "Kirmir 2", and "Çubuk 1" no longer matches "Çubuk 12" or "Dere-1" "Dere-11"; all are now a missing match, which is an error naming the sub-basin | The digits-only alias made two different sub-basins that end in the same number an exact match with no warning (found in the code audit). No sample name contains a number, so no golden changes |
| D69 | Inputs that would only produce an unusable result are refused: a projection of more than 1000 years (supersedes "no upper limit" in D61), a level interval that gives more than 100,000 table rows, a sigma above 30, where a month's daily weights can underflow to zero (they gave NaN flow), and a daily flow with a date listed twice (it counted twice in the annual mean). Days missing from a daily flow are counted in a warning, and the annual means use the days present | Found in the code audit. The limits are checked where the value is entered (the step 5 settings and the step 6 interval), before anything is kept on the dam. The steps fill their grids on the Tk thread, so a huge table froze the window, and the other two cases gave wrong numbers without a word. No sample input is affected and no golden changes |
| D71 | The results of steps 4 to 7 live in a `DamRun` (`src/services/dam_run.py`), one for the dam that step 3 uses, held by the wizard as `wizard.run`. A step keeps its result there through `Step.result`, and the integration and report steps read the other results from it and no longer hold the steps before them. A different dam, a project change or an edit of an earlier step drops the run, so a result can never be read for another dam; a missing result is an error naming it and the dam. The fields typed in a step (sigma, years, curve inputs) that decide whether its result is current stay in that step | The results lived in the step views and the later steps read their siblings' `.result`, so nothing but the order of the wizard tied a result to its dam, and the export had to be given four loose results. No calculated number changes |
| D72 | Logging uses the standard `logging` module through `src/utils/log.py`: one logger, a console handler (INFO and above) and, while a project is open, a file `logs/app.log` in the project folder, replaced when another project is opened. Every error dialog is logged (`show_error`), each background task and each project opening is logged, and an error that is not a `ValueError`, `OSError` or `KeyError` (a fault in the program, not in an input) is logged with its traceback by `run_in_background`; the dialog then reads "Unexpected <type>: <message>" and names the log. An error in a Tk callback is handled the same way (`install_error_handler`). A project folder that can not hold the log gets no file and no error. The retry that reads a `;`-separated file now catches only `ValueError` | The spec promised logging (B5) and the code had none: a background error showed a one-line dialog and the traceback went to a console a Windows user never sees, so a failure could not be diagnosed from a report. The log lives in the project folder so it travels with the project. No calculated number changes |
