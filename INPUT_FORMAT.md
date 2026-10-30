# Input format

How to organise your data so the program accepts it. The six files below are the only inputs. The files in the `inputs/` folder are working examples of every layout; if you are unsure, copy one and replace the values.

## 1. The rules that apply to every file

| Topic | Rule |
|---|---|
| File type | `.csv`, or Excel `.xlsx` / `.xls` (only the **first sheet** is read) |
| CSV text | Saved as UTF-8 (with or without BOM), Windows-1254 or ISO-8859-9, so Turkish letters survive. Fields separated by commas or by semicolons |
| Numbers | Use a **point** as the decimal separator: `834.7`. A comma inside a number (`834,7`, `1,234`) is **not accepted**: the program cannot tell a decimal comma from a thousands separator, so it refuses the cell. No thousands separators at all |
| Header row | The first row holds the column labels listed below. One label per column, nothing above it |
| Labels | Use the labels exactly as written here. Capital letters, extra spaces, the characters `.` `:` `%` and `²` versus `2` make no difference (`DRAINAGE AREA (KM²)` is read as `Drainage Area (km2)`). **Any other spelling or language is refused**, for example `Alan`, `Havza`, `Eğim`, `Debi`, `Tarih`, `Area`, `Slope` |
| Other columns | Columns that are not listed are ignored, and the program tells you which ones it ignored (one warning per file). A trailing empty column is not reported |
| Blank rows | Allowed and skipped |
| Names | Dam and sub-basin names are text and may be Turkish. They are compared without regard to capitals, spaces, punctuation and Turkish letters (`Çubuk 1` = `CUBUK-1` = `cubuk1`). Two numbers are never joined: `Baraj 1.1` and `Baraj 11` are different names |
| Your files | Nothing is read until you choose a file in the program. The program copies it into your project folder and never changes the original |

## 2. Step 2: Regional data

### 2.1 Basin table

One row per sub-basin. All five columns are required.

| Label | Unit | What to enter |
|---|---|---|
| `Dam Name` | | The dam the sub-basin drains to |
| `Basin Name` | | The river basin |
| `Sub-basin Name` | | Unique within a dam |
| `Drainage Area (km2)` | km² | Number greater than 0. For a dam downstream of another, the *incremental* area between the two |
| `Main Waterway Slope` | m/m | Number. A decimal fraction such as `0.09`, **not** a percentage |

```
Dam Name,Basin Name,Sub-basin Name,Drainage Area (km2),Main Waterway Slope
Kavşakkaya,Sakarya,Ankara Alt Havzası,309.2,0.23
Çubuk 1,Sakarya,Ankara Alt Havzası,834.7,0.09
```

A bad cell (empty, not a number, area of 0 or less, a sub-basin listed twice for one dam) does not stop the import: the cell is marked in the grid and you fix it there.

### 2.2 Zonal means

One row per sub-basin. Both columns are required.

| Label | Unit | What to enter |
|---|---|---|
| `Sub-basin Name` | | The same sub-basin names as in the basin table |
| `MEAN` | t/ha/yr | The zonal mean of the soil-loss raster for that sub-basin |

```
Sub-basin Name,MEAN
Asagi sakarya Alt Havzası,3.230787302
Ankara Alt Havzası,3.148701574
```

Rows with an empty name or a MEAN that is not a number are skipped, with a warning that lists their row numbers. Use the same names as the basin table; small differences in capitals, spaces, punctuation, Turkish letters and a trailing `Alt Havzası` are tolerated, and the program warns when it had to match loosely.

### 2.3 Dam sheet

One file per dam, holding **exactly one dam row**. The dam must already be in the basin table (same name).

| Label | Unit | Required | What to enter |
|---|---|---|---|
| `Dam Name` | | yes | As in the basin table |
| `Bottom Elevation of River` | m | yes | River-bed elevation at the dam axis |
| `Crest Elevation` | m | yes | Elevation of the dam crest |
| `Maximum Reservoir Elevation` | m | yes | Highest water level of the reservoir |
| `Active Volume` | hm³ | yes | Storage that can be used |
| `Maximum Volume` | hm³ | yes | Volume at the maximum reservoir elevation |
| `Drainage Area (km2)` | km² | no | Checked against the basin table |
| `Average Slope` | m/m | no | Decimal fraction, checked against the basin table |
| `Longest River Length (km)` | km | no | Information only |
| `Top Elevation of River` | m | no | Information only |
| `Average Flow` | hm³/yr | no | Shown in step 3 |

```
Dam Name,Drainage Area (km2),Longest River Length (km),Top Elevation of River,Bottom Elevation of River,Average Slope,Crest Elevation,Maximum Reservoir Elevation,Active Volume,Maximum Volume,Average Flow
Çubuk 1,834.7,25.5,1109,888,0.09,908.6,907.6,5.28,5.6,62.6
```

If the area or slope differs from the basin table by more than 1 %, the program warns (it does not stop).

## 3. Step 5: Bedload

### 3.1 Grain fractions

One file for the project. One row per grain-size class.

| Label | Unit | Required | What to enter |
|---|---|---|---|
| `di` | m | yes | Grain diameter, greater than 0 (`0.004` is 4 mm) |
| `Fi` | | yes | Fraction of the bed in that class, 0 or more. The `Fi` column must add up to 1 (within 0.02) |
| `bi` | | no | Hiding exponent. Optional |
| `tau_ri` | Pa | no | Reference shear stress. Optional |

```
di,Fi,bi,tau_ri
0.004,0.1,0.143,1.18
0.01,0.2,0.18,3.29
0.02,0.35,0.253,7.46
0.032,0.25,0.352,14.07
0.05,0.1,0.49,29.2
```

`bi` and `tau_ri` are always computed from the grain size. If you supply them, the program only compares them and warns when one differs by more than 1 %; the computed value is used.

### 3.2 Daily flow

One file per dam. One row per day.

| Label | Unit | Required | What to enter |
|---|---|---|---|
| `Date` | dd/mm/yyyy | yes | `31/12/2010` (`2010-12-31` is accepted too) |
| `Flow Q (m3/s)` | m³/s | yes | Mean daily discharge, 0 or more |
| `Water_Year` | | no | Whole number. When present the results are grouped by this water year (October to September); otherwise by calendar year |

```
Date,Flow Q (m3/s)
30/09/2010,10.0
01/10/2010,80.0
```

Rows with an unreadable date or flow are dropped, and the program warns how many.

### 3.3 DSİ monthly flow

Use this instead of a daily file when you only have the DSİ monthly table. It keeps the layout DSİ publishes (Turkish labels). The program turns it into synthetic daily flow (marked as such in the results).

| Label | Required | What to enter |
|---|---|---|
| `Yıllar` | yes | The water year as four digits (1900 to 2100). A water year Y runs October of Y-1 to September of Y |
| `Ekim`, `Kasım`, `Aralık`, `Ocak`, `Şubat`, `Mart`, `Nisan`, `Mayıs`, `Haziran`, `Temmuz`, `Ağustos`, `Eylül` | yes | Monthly volume in hm³, 0 or more. All twelve columns must be there |
| `TOP.` | no | The yearly total. Ignored |

The `TOP.` and `ORT.` summary rows at the bottom of the DSİ table are skipped; leave them in. A year may appear only once. The ASCII spellings `Yillar`, `Kasim`, `Aralik` and so on are read as the same labels.

```
Yıllar,Ekim,Kasım,Aralık,Ocak,Şubat,Mart,Nisan,Mayıs,Haziran,Temmuz,Ağustos,Eylül,TOP.
1974,0.88,0.45,0.96,0.25,1.47,4.95,3.01,3.66,1.59,0.10,0.00,1.21,18.53
1975,0.84,0.27,1.69,3.02,3.26,16.85,12.14,3.74,4.57,0.91,2.85,2.37,52.51
```

## 4. Names that must agree between files

| Name | Appears in | Rule |
|---|---|---|
| Dam name | Basin table and the dam sheet | Same name (capitals, spaces, punctuation and Turkish letters ignored) |
| Sub-basin name | Basin table and the zonal means | Same name; every sub-basin of the dam you analyse needs one zonal mean |

## 5. When something is wrong

| What you see | What it means | What to do |
|---|---|---|
| `file.csv: required column(s) not found: Drainage Area (km2). Columns present: Alan, ...` | A label is missing or spelled another way. The message lists what the program expected and what your file has | Rename the header to the label in the message and import again |
| `file.csv: columns 'Dam Name' and 'dam name' both mean 'Dam Name'` | Two headers are the same label once capitals and spacing are ignored | Delete or rename one of them |
| `file.csv: ignored column(s) ...` | The file has columns outside this format | Nothing is wrong; the columns are not used. Delete them to silence the warning |
| A cell marked in the basin-table grid, or `... must be a number ..., found '834,7'` | A cell is empty, not a number, or uses a comma as a decimal | Edit the cell in the grid, or fix the file and import again. Write numbers with a point |
| `dam 'X' is not in the basin table` | The dam sheet's name does not match any dam in the basin table | Make the names the same |
| `no zonal mean can be assigned to sub-basin(s): ...` | A sub-basin in the basin table has no matching row in the zonal means (or its name appears twice with different values) | Add the row or correct the name |

## 6. Checklist before you import

1. Every file has its header row first, with the labels from this page.
2. Numbers use a point and have no thousands separators.
3. Slopes are decimal fractions (`0.09`), not percentages.
4. Dam names agree between the basin table and the dam sheets; sub-basin names agree between the basin table and the zonal means.
5. Fractions `Fi` add up to 1.
6. For flow you have either a daily file (`Date`, `Flow Q (m3/s)`) or the DSİ monthly table, not both for the same dam.
