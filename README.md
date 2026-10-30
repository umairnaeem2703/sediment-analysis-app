# Sediment Analysis

A Windows desktop program that walks a hydrologist through estimating the **sediment that reaches one dam**, how fast it **fills the reservoir's dead storage**, and when the dead storage is likely to be full. It works offline on one machine, from files you pick, and writes a self-contained run folder (tables, charts, workbook and an audit record) for each analysis.

Version 1.0.0. The interface and reports are in English; the input data may be Turkish (DSİ monthly flow tables, Turkish sub-basin names).

## Contents

1. [What the software does](#1-what-the-software-does)
2. [Getting started](#2-getting-started)
3. [Input files](#3-input-files)
4. [The eight steps](#4-the-eight-steps)
5. [Worked example: Kavşakkaya](#5-worked-example-kavşakkaya)
6. [Reading the run folder](#6-reading-the-run-folder)
7. [Assumptions and limitations](#7-assumptions-and-limitations)
8. [How the results are verified](#8-how-the-results-are-verified)
9. [Warnings reference](#9-warnings-reference)
10. [Glossary](#10-glossary)
11. [References](#11-references)
12. [For developers](#12-for-developers)

---

## 1. What the software does

For one dam at a time, the program combines three estimates and carries them forward in time:

| Phase | Question it answers | Main inputs |
|---|---|---|
| **Suspended sediment** (step 4) | How much suspended sediment does the catchment deliver each year? | Basin table, zonal means (RUSLE soil loss), dam sheet |
| **Bedload** (step 5) | How much bedload does the river carry past the dam each year? | Daily flow or a DSİ monthly table, grain fractions |
| **Reservoir curve** (step 6) | How do level, volume and surface area relate? | Dam sheet (levels and volumes) |
| **Integration and projection** (step 7) | How much has accumulated so far, and when is the dead storage full? | The three results above, trap efficiency, commissioning and analysis years |

```
 basin table ─┐
 zonal means ─┼─► 4 Suspended ─┐
 dam sheet  ──┘                │
                               ├─► 7 Integration ─► 8 Report ─► run folder
 flow file  ──┐                │    and projection     (results.xlsx, CSVs,
 grain fractions ► 5 Bedload ──┤                        PNG charts, run.json)
                               │
 dam sheet ───► 6 Reservoir ───┘
                   curve
```

**What it does not do**

- It does not compute the RUSLE factors. The zonal means you give it are mean annual soil loss in t/ha/yr, calculated elsewhere (usually in a GIS). The program starts from those means.
- It analyses one dam per run. Dams are independent: sediment trapped by an upstream dam is not removed from a downstream dam (see [limitations](#7-assumptions-and-limitations)).
- It never modifies your files. Every input is copied into the project folder; the original stays as it was.

## 2. Getting started

The program runs from source on Windows with Python 3.14.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

A window titled **Sediment Analysis** opens on step 1. Nothing is loaded at startup: every table comes from a file you choose.

**Moving through the wizard.** The step list on the left and the *Back* / *Next* buttons at the bottom control navigation. A step opens only when every earlier step is complete. If you change something in an earlier step, the later steps are reset and the program tells you which results were lost (for example *"The dam settings changed. Reset: …"*). To analyse another dam, go back to step 3 and pick it; the later steps are reset and each export writes its own run folder.

## 3. Input files

Which files each step needs:

| Step | File | Format guide |
|---|---|---|
| 2 Regional data | Basin table (one row per dam and sub-basin) | [INPUT_FORMAT.md §2.1](INPUT_FORMAT.md#21-basin-table) |
| 2 Regional data | Zonal means (one row per sub-basin) | [INPUT_FORMAT.md §2.2](INPUT_FORMAT.md#22-zonal-means) |
| 2 Regional data | Dam sheet (one per dam: levels, volumes, area, mean flow) | [INPUT_FORMAT.md §2.3](INPUT_FORMAT.md#23-dam-sheet) |
| 5 Bedload | Grain fractions (one file for the project) | [INPUT_FORMAT.md §3.1](INPUT_FORMAT.md#31-grain-fractions) |
| 5 Bedload | Daily flow, **or** the DSİ monthly table (one per dam) | [INPUT_FORMAT.md §3.2 and §3.3](INPUT_FORMAT.md#3-step-5-bedload) |

[INPUT_FORMAT.md](INPUT_FORMAT.md) is the authoritative description of every column label, unit and rule. In short:

- CSV or Excel (first sheet only). Numbers use a decimal **point**; a comma in a number is refused rather than guessed.
- Column labels are exact English labels, matched after ignoring case, spaces and Turkish letters. Only the DSİ monthly table keeps its Turkish layout (`Yıllar`, `Ekim`, `Kasım`, …).
- Names must agree between files (dam names in the basin table and dam sheets, sub-basin names in the basin table and zonal means): [§4](INPUT_FORMAT.md#4-names-that-must-agree-between-files). Turkish names are compared with Turkish-aware rules, so `İ`/`I` and `ı`/`i` do not cause false mismatches.
- Encodings (UTF-8, cp1254, ISO-8859-9 …) are detected automatically.
- If something is wrong the program says what and where: [§5](INPUT_FORMAT.md#5-when-something-is-wrong). A checklist is in [§6](INPUT_FORMAT.md#6-checklist-before-you-import).

Sample files for three dams (Kavşakkaya, Çubuk 1, Çubuk 2) are in the `inputs/` folder.

## 4. The eight steps

Every step below follows the same pattern: what it does, what you enter, what you get, how to read it and which warnings you may see. All warnings are collected in [section 9](#9-warnings-reference).

### Step 1. Project

**What it does.** A project is a folder that holds copies of your inputs and the results of every run. Create one (a name and a folder) or open an existing one.

**What you get.** A summary line, *"Open project: 'name' in folder (N dam(s))."*

**How to read it.** The number of dams is the number the project already knows from the basin table.

### Step 2. Regional data

**What it does.** Imports the basin table, the zonal means and the dam sheets (several sheets at once). The data appears in an editable grid.

**What you enter.** Pick the files with the three *Import* buttons. To correct a value, double-click the cell; *Enter* saves, *Escape* cancels. Edits are kept in the project; your original file is untouched.

**What you get.** Invalid cells are shaded pink and prefixed with `⚠`. Messages appear as *"Not loaded: …"* (a file that could not be used) and *"Warning: …"* (usable, but check it), with one status line per input.

**How to read it.** Fix pink cells or re-import before moving on. A warning here usually points at a name mismatch or a sheet that disagrees with the basin table, for example a dam sheet whose drainage area differs from the sum of its sub-basin areas by more than 1 % (see the expected case under [limitations](#7-assumptions-and-limitations)).

### Step 3. Select dam

**What it does.** Chooses the dam to analyse and records its settings.

**What you enter.**

| Field | Unit | Default | Meaning |
|---|---|---|---|
| Commissioning year (optional) | year | blank | First year sediment starts to accumulate. Required for step 7. |
| Analysis year (blank = current year) | year | current year | The first year **not yet** accumulated. The default excludes the incomplete current year. |
| Trap efficiency | % | 100 | Share of the delivered sediment that stays in the reservoir. 100 is conservative. |
| Minimum operating level Hmin (optional) | m | blank | Top of the dead storage. If blank, step 6 uses a shape class. |

**What you get.** The dam's sub-basins (name, area, slope) and the values read from its sheet: bed elevation (Hbed), crest elevation (Hcrest), maximum level (Hmax), active volume, maximum volume, drainage area and mean annual flow.

**How to read it.** *Use this dam* confirms the choice. Changing the dam or its settings later resets the following steps.

### Step 4. Suspended sediment

**What it does.** Computes the yearly suspended sediment from each sub-basin of the dam and adds them. The **zonal mean** in the input is the RUSLE mean annual soil loss, $E = R \cdot K \cdot LS \cdot C \cdot P$ in t/ha/yr (Renard et al., 1997), worked out outside the program. The program turns that soil loss into delivered sediment.

**What you enter.** Press *Compute*. There is nothing else to enter; the inputs come from step 2.

**The method.** For each sub-basin, with $E$ the zonal mean (t/ha/yr), $A$ the area (km²) and $S$ the slope (m/m):

$$G = E \cdot 100\,A \qquad \text{(gross erosion, t/yr)}$$

$$SIO_{USDA\text{-}SCS} = 0.51\,A^{-0.11} \qquad SIO_{\text{ÇEM}} = \frac{1}{2.05823 + 0.02816\,S^{2}}$$

$$SIO = \tfrac12\left(SIO_{USDA\text{-}SCS} + SIO_{\text{ÇEM}}\right) \qquad Y = G \cdot SIO \qquad V = \frac{Y}{1.3}$$

$SIO$ is the sediment delivery ratio, $Y$ the delivered mass (t/yr) and $V$ the volume (m³/yr) at a deposited bulk density of 1.3 t/m³. The specific yield is $V/A$ (m³/yr/km²). The dam total is the sum of $V$ over **that dam's own sub-basins**.

**What you get.** A grid with one row per sub-basin: *Sub-basin, Area (km²), Slope (m/m), Zonal mean (t/ha/yr), Gross erosion (t/yr), SIO USDA-SCS, SIO ÇEM, SIO average, Yield (t/yr), Volume (m³/yr), Specific yield (m³/yr/km²)*, and a footer *"Dam total: … m³/yr …"*.

**How to read it.**

- *Gross erosion* is what the soil loss would be if all of it reached the stream; *Yield* is what is assumed to arrive after the delivery ratio.
- The delivery ratio falls as area grows, so larger sub-basins deliver a smaller share. Slope changes the ÇEM ratio very little over the usual range of slopes.
- The *Volume* column is what step 7 uses.

**Warnings.** *"Sub-basin 'X' was matched loosely to the zonal entry 'Y'"*: the names did not match exactly, so check that the right zonal mean was used. If several candidates carried different values the program stops with an error instead.

### Step 5. Bedload

**What it does.** Computes the yearly bedload at the dam from daily flow, using the Wilcock & Crowe (2003) fractional transport model on a fixed channel.

**What you enter.**

| Field | Default | Meaning |
|---|---|---|
| Flow file | none | The dam's daily flow, or its DSİ monthly table |
| Grain fractions | none | The bed grain-size classes ([format](INPUT_FORMAT.md#31-grain-fractions)) |
| sigma | 0.6 | Spread of the random split of monthly flow into days. Used only with a monthly table. |
| lag-1 phi | 0 | Day-to-day persistence of that split (0 ≤ phi < 1). Used only with a monthly table. |
| seed | 0 | Random seed, so the split is reproducible. Used only with a monthly table. |

**Fixed channel and sediment constants.** The same for every dam and every flow; they cannot be changed in the program.

| Quantity | Value |
|---|---|
| Flow depth $h$ | 0.5 m |
| Channel width $B$ | 50 m |
| Manning's $n$ | 0.05 |
| Median grain size $D_{50}$ | 0.02 m |
| Sand fraction of the bed $F_s$ | 0.10 |
| Sediment density $\rho_s$ | 2650 kg/m³ |
| Water density $\rho_w$ / gravity $g$ | 1000 kg/m³ / 9.81 m/s² |

**The method.** For each day with discharge $Q$ (m³/s), velocity and shear stress on a rectangular channel:

$$v = \frac{Q}{B\,h} \qquad \tau = \frac{\rho_w\,g\,n^{2}\,v^{2}}{h^{1/3}} \qquad u_* = \sqrt{\tau/\rho_w}$$

For each grain class $i$ of diameter $d_i$ and fraction $F_i$, with $s = \rho_s/\rho_w$:

$$\tau^*_{rm} = 0.021 + 0.015\,e^{-20F_s} \qquad b_i = \frac{0.67}{1 + e^{\,1.5 - d_i/D_{50}}}$$

$$\tau_{ri} = \tau^*_{rm}\left(\frac{d_i}{D_{50}}\right)^{b_i}(s-1)\,\rho_w\,g\,d_i \qquad \phi_i = \frac{\tau}{\tau_{ri}}$$

$$W_i^* = \begin{cases} 0.002\,\phi_i^{7.5} & \phi_i < 1.35 \\[2pt] 14\left(1 - \dfrac{0.894}{\sqrt{\phi_i}}\right)^{4.5} & \phi_i \ge 1.35 \end{cases} \qquad q_{b,i} = \frac{W_i^*\,F_i\,u_*^{3}}{(s-1)\,g}$$

$q_b = \sum_i q_{b,i}$ is the transport per unit width (m²/s). The annual volume is $V_b = \overline{q_b}\cdot B \cdot 31\,557\,600$ s (the mean daily rate over a full year) and the mass is $M_b = 2.65\,V_b$ (t/yr). Results are grouped by water year (October to September) if the flow file has a `Water_Year` column or comes from a DSİ table, otherwise by calendar year.

`bi` and `tau_ri` are always computed from the grain size. If your fractions file supplies them they are only compared, and a difference above 1 % adds a warning.

**Monthly tables become synthetic daily flow.** A DSİ table gives one volume per month. The program splits each month into days with a log-normal pattern: independent random weights, or, when phi > 0, weights that follow a lag-1 autoregressive chain that carries across consecutive months. The weights are rescaled so **each month keeps its volume exactly**. The same sigma, phi and seed always give the same days.

**What you get.**

- Summary line: *"Mean bedload: … m³/yr over N years."*
- **Annual table** tab: *Year* (or *Water year*), *Mean flow (m³/s), Mean transport (m²/s), Volume (m³/yr), Mass (t/yr)*.
- **Trend chart** tab: annual flow and bedload on twin axes.

**How to read it.**

- Bedload rises very steeply with flow (a high power of shear stress), so a few wet years dominate the total.
- When the flow was made from a monthly table, the result is flagged *"⚠ Synthetic daily flow."* and a note names sigma, phi, seed and the number of water years. Bedload depends strongly on how the month is split, so treat the number as an estimate that depends on sigma and phi. The monthly volumes themselves are exact.
- The last year of a daily record may be partial; its annual volume is still the mean daily rate over a full year.
- Fixed channel geometry means the numbers describe a standard channel, not the surveyed cross-section at the dam.

**Warnings.** Rows dropped for a missing or unreadable flow or date (with counts); a supplied `bi` or `tau_ri` that disagrees with the computed value.

### Step 6. Reservoir curve

**What it does.** Builds the relation between level, volume and surface area, which step 7 uses to turn a sediment volume into a bed elevation.

**What you enter.** The inputs are filled in from the dam sheet and can be edited.

| Field | Unit | Meaning |
|---|---|---|
| Bed elevation Hbed | m | Reservoir bed at the dam axis |
| Minimum operating level Hmin (optional) | m | Top of the dead storage |
| Maximum level Hmax | m | Normal maximum operating level |
| Crest elevation Hcrest | m | Dam crest |
| Active volume Vactive | hm³ | Volume between Hmin and Hmax |
| Maximum volume Vmax | hm³ | Volume at Hmax |
| Shape class | | gorge, hill, foothill or lake. Fixes the curve when Hmin is blank |
| Level interval of the table | m | Default 0.5 |

The dead volume is $V_{dead} = V_{max} - V_{active}$.

**The method.** A one-parameter power law, with $x = (H - H_{bed})/(H_{max} - H_{bed})$:

$$V = V_{max}\,x^{m} \qquad A = \frac{m\,V_{max}}{H_{max} - H_{bed}}\,x^{m-1}$$

If you give Hmin, the exponent is fitted so that the curve passes through (Hmin, $V_{dead}$):

$$m = \frac{\ln\left(V_{dead}/V_{max}\right)}{\ln\left[(H_{min}-H_{bed})/(H_{max}-H_{bed})\right]}$$

If you leave Hmin blank, $m$ comes from the shape class, and Hmin is then the level where the curve reaches $V_{dead}$:

| Shape class | gorge | hill | foothill | lake |
|---|---|---|---|---|
| $m$ | 1.25 | 2.0 | 3.0 | 4.0 |

**What you get.** A summary (*"Exponent m = … Hmin … m (given / from the … shape class). Dead volume … hm³. Surface area at Hmax … km²."*), a **Curve table** (*Elevation (m), Volume (hm³), Surface area (km²)* from the bed to the crest) and a **Curve chart** of volume and area with Hmin and Hmax marked. If you changed any value from the sheet, a line *"Changed from the dam sheet: …"* lists the differences.

**How to read it.** The curve is a power law, not a survey, so elevations are indicative; they are only as good as the three points (bed, Hmin or shape class, Hmax) that fix it. A larger $m$ puts more of the volume near the top of the reservoir.

**Warnings.** *m outside the usual range 1 to 4.5*; *Hmax only X m above Hbed, below 10 m* (poorly constrained curve); *surface area at Hmax above the drainage area*. Inputs that are inconsistent (levels out of order, no Hmin and no shape class, a non-positive interval) stop with an error.

### Step 7. Integration and projection

**What it does.** Adds suspended sediment and bedload year by year, converts the total into a bed elevation, accumulates it from the commissioning year, and projects the future. It needs the commissioning year entered in step 3.

**What you enter.** *Years to project* (default 100), then *Compute*.

**The method.** For each year $y$ of the flow record, with $TE$ the trap efficiency in %:

$$T(y) = \frac{TE}{100}\cdot\frac{V_s + V_b(y)}{10^{6}} \quad \text{(hm}^3\text{)}$$

where $V_s$ is the dam's suspended volume from step 4 (the same every year) and $V_b(y)$ the bedload volume from step 5. The sediment elevation is $H(T)$ on the curve of step 6, limited to Hcrest.

- **Accumulation to date**, $S_0$, is the sum of $T$ for the years from the commissioning year $c$ up to but not including the analysis year $a$. Years outside the flow record use the **record mean** of $T$. Record years before commissioning are left out of the sum but still count in the mean.
- **Rates.** The mean, minimum and maximum of $T$ over the record, $r_{mean}$, $r_{min}$, $r_{max}$ (hm³/yr).
- **Projection.** $S(a+k) = S_0 + k\,r$ for $k = 0 \ldots$ years to project, at each of the three rates.
- **Lifespan** at a rate: $a + (V_{dead} - S_0)/r$, as a fractional year.

**What you get.**

- Summary: *"Accumulation to date (span): … hm³, reaching … m. Dead volume … hm³ (Hmin … m). Analysis year …"*
- One line for each rate: *"Lifespan at the mean rate (… hm³/yr): `<year>`, `<n>` years after `<analysis year>`."*, or *"the dead volume was already exceeded in …"*, or *"not reached, because no sediment arrives at this rate."*
- **Annual totals** tab: *Year, Suspended (hm³), Bedload (hm³), Total (hm³), Elevation (m)*.
- **Projection** tab: *Year* and, for the mean, minimum and maximum rates, the cumulative volume (hm³) and the elevation (m).
- **Projection chart** tab.

**How to read it.**

- The three lifespans bracket the answer: the minimum-rate line is the optimistic case (longest life), the maximum-rate line the pessimistic one.
- The projection is a straight line at a constant rate with a fixed trap efficiency. It does not model changes in climate, land use or flushing.
- The lifespan is not cut at the projection horizon. A lifespan beyond the years you projected is still reported, but the table stops at the horizon.
- *Already exceeded* means the accumulation to date has already passed the dead volume.

**Warnings.** Years between commissioning and analysis that are not in the record (the mean was used); years whose volume exceeds the volume at the crest (elevation limited to Hcrest); an accumulation to date or projected values above the crest volume.

### Step 8. Report

**What it does.** Shows the extremes and all warnings and writes the run folder.

**What you get.** The years with the **minimum** and **maximum** annual total (*"Minimum: year, … hm³, elevation … m"*; a tie goes to the earliest year), every warning as *"Phase: text"*, and after *Export* the folder and files written. What is in the folder is described in [section 6](#6-reading-the-run-folder).

**How to read it.** Read the warnings before using any number: the same list is saved in `run.json` and in the workbook's *Warnings* sheet.

## 5. Worked example: Kavşakkaya

The sample files in `inputs/` are enough to run one dam from start to finish.

1. **Project.** Create a project named *Kavsakkaya demo* in an empty folder.
2. **Regional data.** Import `inputs/master_yield.csv` (basin table), `inputs/raw_zonal_means.csv` and the dam sheet `inputs/bathymetry/kavsakkaya_bathymetry.csv`. Kavşakkaya has one sub-basin, *Ankara Alt Havzası*, of 309.2 km² with a slope of 0.23 m/m, and the zonal means file holds its soil loss.
3. **Select dam.** Choose *Kavşakkaya* and enter a commissioning year (the samples do not supply one). Leave trap efficiency at 100 and the analysis year blank. Press *Use this dam*. The sheet shows Hbed 1063 m, Hmax 1122.3 m, Hcrest 1124 m, active volume 74.1 hm³ and maximum volume 80.8 hm³.
4. **Suspended.** Press *Compute* and read the dam total.
5. **Bedload.** Choose `inputs/dam_flow_data/kavsakkaya_flow.csv` and `inputs/fractional_parameters.csv`, keep sigma 0.6, phi 0 and seed 0, press *Compute*. The sample flow is a DSİ monthly table, so the result carries the **Synthetic daily flow** flag.
6. **Reservoir curve.** Leave Hmin blank and select the *foothill* shape class ($m = 3$). The dead volume is $80.8 - 74.1 = 6.7$ hm³. Press *Generate curve*.
7. **Integration and projection.** Keep 100 years and press *Compute*. Read the three lifespans.
8. **Report.** Press *Export*. A folder `outputs/kavsakkaya_<YYYYMMDD_HHMM>/` appears inside your project, with the files described next.

## 6. Reading the run folder

Every export writes a **new** folder, `outputs/<dam-slug>_<YYYYMMDD_HHMM>/` inside the project (`_2`, `_3`, … if the name exists). Earlier runs are never overwritten. If writing fails the half-written folder is removed.

| File | Content |
|---|---|
| `results.xlsx` | All results in one workbook (sheets below) |
| `suspended.csv`, `bedload.csv`, `reservoir_curve.csv`, `integration.csv`, `projection.csv` | One CSV per phase |
| `bedload_trend.png`, `annual_volume.png`, `reservoir_curve.png`, `projection.png` | The charts |
| `run.json` | The audit record |

**`results.xlsx` sheets**

| Sheet | Columns |
|---|---|
| Inputs | Group, Item, Value, Unit, SHA-256. Rows for the run (version, time, project, dam), every parameter, and every input file with its hash |
| Suspended | Sub-basin Name, Area_km2, Slope_m_per_m, Zonal_Mean_t_ha_yr, Gross_Mass_t, SIO_USDA_SCS, SIO_CEM, SIO_Average, Yield_Mass_t, Volume_m3, Specific_Yield_m3_km2, plus a Total row |
| Bedload | Water_Year (or Year), Mean_Flow_m3_s, Mean_Qb_m2_s, Volume_m3_yr, Mass_t_yr |
| Annual | Year, Suspended_hm3, Bedload_hm3, Total_hm3, Elevation_m |
| Curve | Elevation_m, Volume_hm3, Area_km2 |
| Projection | Year, Cumulative_Mean_hm3, Cumulative_Min_hm3, Cumulative_Max_hm3, Elevation_Mean_m, Elevation_Min_m, Elevation_Max_m |
| Extremes | The minimum and maximum year with total and elevation, then accumulated to date and its elevation, the dead volume, the three rates and the three lifespans |
| Warnings | Phase, Warning |

**`run.json`** records the program version (`app_version`), the time, the project and dam, every input file with its **SHA-256** hash, every parameter with its unit, the flags (`synthetic_flow`, `h_min_given`, `shape_class`) and every warning. Anyone can check that a result came from the files they hold by hashing those files and comparing; with the same files and settings (including sigma, phi and seed) the numbers are reproduced.

## 7. Assumptions and limitations

The program states its limits here, and they are carried into the design record. Read them before quoting a number.

**Where the program differs from the published method**

- **Bedload reference stress.** The reference shear stress $\tau_{ri}$ is computed in the form the project hydrologist specified (the hiding function scales the Shields number and each fraction is converted to a stress with its own diameter). This is not the same as Equations 3 and 5 of Wilcock & Crowe (2003), which apply the hiding function to the stress in Pa. For the sample fractions the two forms give different reference stresses. The hydrologist approved the form on 2026-10-26. (D50)
- **Delivery-ratio coefficient.** The USDA-SCS coefficient 0.51 is used with area in km². It is conventionally quoted for mi²; the km² equivalent would be about 0.566, which would raise the ratio by about 11 % and the suspended yield by about 4 %. (AL-04)

**Accepted limitations**

| ID | Limitation |
|---|---|
| AL-01 | Suspended sediment uses a deposited bulk density of 1.3 t/m³ and bedload the solid density 2.65 t/m³, and the two volumes are added. Bedload's share of reservoir volume is therefore understated. |
| AL-02 | Bedload hydraulics use a fixed rectangular channel (depth 0.5 m, width 50 m, n 0.05, D50 0.02 m, Fs 0.10) for every dam and flow. Channel slope is not used. |
| AL-03 | Monthly DSİ flow is split into days at random (log-normal, sigma 0.6 by default, optional lag-1 phi). Bedload depends strongly on sigma and phi. |
| AL-05 | The ÇEM delivery ratio changes by less than 0.1 % across the sample slopes, so slope hardly affects it. The slope column is read as m/m. |
| AL-06 | Dams are independent. Sediment trapped by an upstream dam is not removed from a downstream dam. |
| AL-07 | The elevation-volume curve is a one-parameter power law, not a survey, and sediment fills it as a level pool from the bed up. |
| AL-08 | Years outside the flow record use the record mean for accumulation. |
| AL-09 | $D_{50}$ stands in for the surface-mean grain size in the reference stress. |
| AL-10 | The record's last year may be partial; its annual volume is the mean daily rate times a full year. |

Also worth keeping in mind:

- The projection is linear at a constant rate and uses a fixed trap efficiency.
- Sediment elevations are limited to Hcrest.
- **Expected warning (OI-07).** A downstream dam's table holds the *incremental* catchment while its dam sheet holds the *total* drainage area, so the area check can warn that they differ by more than 1 %. This is a known open question, not a data error.

The full design record is [docs/project_spec.md](docs/project_spec.md).

## 8. How the results are verified

- **Hand calculations.** For each phase (suspended, bedload, reservoir curve, integration) a script in [tests/verification/](tests/verification) writes a workbook of **live formulas** that a hydrologist can open and inspect, together with CSV files worked out with Python's `math` alone. The unit tests compare the program's results with those CSVs, so the check never uses the program's own output.
- **Reference outputs.** [tests/benchmarks/](tests/benchmarks) holds the reviewed outputs for the three sample dams. They are regenerated only by script and merged only after hydrologist sign-off. Each comes with a manifest of the code version, input hashes and settings used.
- **Sign-off.** The suspended-sediment workbook was signed off by the hydrologist. The bedload formulas, oracle and reference outputs were approved on 2026-10-26, as were the reservoir and integration reference outputs. The end-to-end run of the three sample dams was signed off on 2026-10-27.
- The reference outputs for integration use placeholder commissioning and analysis years (1990 and 2020), because the samples do not supply them.

To check a formula yourself, open the workbook for the phase in `tests/verification/` and compare a case with the program's output for the same inputs.

## 9. Warnings reference

Every warning is shown on screen, saved in `run.json` and listed in the workbook's *Warnings* sheet. Messages that stop a step (a missing field, a bad file) are errors, not warnings; see [INPUT_FORMAT.md §5](INPUT_FORMAT.md#5-when-something-is-wrong).

| Where | Message (abridged) | What it means and what to do |
|---|---|---|
| Any import | *"<file>: ignored column(s) …"* | The file has columns the program does not read. Nothing to do unless you expected one to be used; check the label. |
| Zonal means | *"skipped N row(s) with an empty sub-basin name or … non-numeric MEAN"* | Unusable rows were dropped. Correct them if they were meant to count. |
| Dam sheet | *"drainage area X km2 differs from the basin table's Y km2 by more than 1%"* | Sheet and table disagree. Expected on downstream dams (OI-07); otherwise check both files. |
| Dam sheet | *"slope X m/m differs from the basin table's area-weighted Y m/m by more than 1%"* | Same, for the slope. |
| Suspended | *"Sub-basin 'X' was matched loosely to the zonal entry 'Y'"* | Names did not match exactly. Confirm they are the same sub-basin or fix the name. |
| Bedload | *"Fraction n (di = X mm): the supplied bi/tau_ri … differs from the computed … by P%; the computed value is used"* | Your optional column disagrees with the formula. The computed value is used; fix or delete the column. |
| Bedload | *"Dropped N row(s) with missing/non-numeric flow and M row(s) with unparseable dates"* | Those days are missing from the flow series. Check the file if the counts are unexpected. |
| Bedload | *"⚠ Synthetic daily flow. Converted DSI monthly table …"* | Daily flow was invented from monthly volumes. Report sigma, phi and seed with the result. |
| Reservoir curve | *"The fitted exponent m = … is outside the usual range 1 to 4.5"* | The curve is unusually concave or convex. Check Hmin and the volumes. |
| Reservoir curve | *"Hmax is only X m above Hbed, below 10 m: the curve is poorly constrained"* | A shallow range makes the fit sensitive. Check the levels. |
| Reservoir curve | *"The surface area at Hmax (…) is above the drainage area (…)"* | The curve implies a reservoir surface larger than the catchment. Check the levels and volumes. |
| Integration | *"N year(s) between the commissioning year and the analysis year are not in the record; the mean annual total was used for them"* | The record does not cover those years (AL-08). |
| Integration | *"N year(s) of the record deliver more than the volume at the crest …; their elevations are limited to Hcrest"* | The reservoir would be full to the crest in those years. |
| Integration | *"The accumulation to date is above the volume at the crest …"* | The accumulated sediment exceeds the crest volume. The elevation is capped. |
| Integration | *"N projected value(s) are above the volume at the crest …"* | Part of the projection passes the crest volume. Elevations are capped. |

## 10. Glossary

| Symbol / term | Unit | Meaning |
|---|---|---|
| DSİ | | Devlet Su İşleri, the Turkish State Hydraulic Works, whose monthly flow tables are used |
| Water year | | October to September. Water year Y runs from October of Y−1 to September of Y |
| Zonal mean, $E$ | t/ha/yr | Mean annual soil loss of a sub-basin (RUSLE) |
| $A$ | km² | Sub-basin area |
| $S$ | m/m | Sub-basin main waterway slope |
| SIO | | Sediment delivery ratio |
| $V_s$ | m³/yr or hm³/yr | Suspended sediment volume delivered to the dam |
| $V_b$ | m³/yr or hm³/yr | Bedload volume |
| $q_b$ | m²/s | Bedload transport per unit channel width |
| $T$ | hm³/yr | Annual sediment trapped: $TE/100 \cdot (V_s + V_b)$ |
| TE | % | Trap efficiency |
| Hbed | m | Reservoir bed elevation at the dam axis |
| Hmin | m | Minimum operating level, top of the dead storage |
| Hmax | m | Maximum (normal) operating level |
| Hcrest | m | Dam crest elevation |
| $V_{active}$ | hm³ | Active volume |
| $V_{max}$ | hm³ | Volume at Hmax |
| $V_{dead}$ | hm³ | Dead volume, $V_{max} - V_{active}$ |
| $x$ | | Relative height, $(H - H_{bed})/(H_{max} - H_{bed})$ |
| $m$ | | Exponent of the volume–elevation power law |
| $c$ | year | Commissioning year |
| $a$ | year | Analysis year, the first year not yet accumulated |
| $S_0$ | hm³ | Accumulation to date |
| $r$ | hm³/yr | Annual accumulation rate (mean, minimum or maximum) |
| $\sigma$, $\phi$ | | Spread and lag-1 persistence of the monthly-to-daily split |

## 11. References

- Renard, K. G., Foster, G. R., Weesies, G. A., McCool, D. K. and Yoder, D. C. (1997). *Predicting Soil Erosion by Water: A Guide to Conservation Planning with the Revised Universal Soil Loss Equation (RUSLE)*. USDA Agriculture Handbook 703.
- Wilcock, P. R. and Crowe, J. C. (2003). Surface-based transport model for mixed-size sediment. *Journal of Hydraulic Engineering*, 129(2), 120–128.
- Manning's equation for open-channel flow (standard hydraulics texts).

The delivery-ratio formulas (USDA-SCS and ÇEM), the deposited bulk density of 1.3 t/m³, the power-law reservoir curve and its shape classes are used as specified by the project hydrologist; sources are not recorded in the project.

## 12. For developers

- [CLAUDE.md](CLAUDE.md) describes the code layout (`src/ui` → `src/services` → `src/core`) and the working conventions.
- [docs/project_spec.md](docs/project_spec.md) is the design specification: requirements, data contracts, decisions and the roadmap.

```powershell
pytest                                  # the whole suite
ruff check . ; ruff format --check .    # lint and format check
```
