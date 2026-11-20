"""Write the verification oracle for the measured reservoir curve (B3.3, D75, D76).

Run `python tests/verification/make_reservoir_oracle.py` to rewrite these files next to this script:

- `reservoir_verification.xlsx`: the hand calculation as live spreadsheet formulas, for the hydrologist to open and
  review. Each case has its own sheet: Hmin, the curve's rows, the values read from the curve (Hbed, Hcrest, Vmax and
  Vdead), and the curve read at four levels by linear interpolation between the two rows around each level.
- `reservoir_cases.csv`, `reservoir_tables.csv`, `reservoir_points.csv`: the same cases with the results worked out
  below using only plain Python. The unit tests read these files, so the oracle never depends on `src`.

Case 1 is the Kavşakkaya curve sheet in `inputs/reservoir_curves/` with the placeholder Hmin of `tests/samples.py`
(the level the old dam sheet's Vdead gave, until the hydrologist confirms it). Change a case here, review the workbook,
and only then commit the files.
"""

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

HERE = Path(__file__).parent
KAVSAKKAYA_CURVE = HERE.parents[1] / "inputs" / "reservoir_curves" / "kavsakkaya_reservoir_curve.csv"


def read_curve(path):
    """The rows of a curve sheet as (level m, volume hm3, area km2)."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [tuple(float(value) for value in row) for row in list(csv.reader(handle))[1:] if row]


# (case, description, curve rows, Hmin m, a level between the rows)
CASES = [
    (1, "Kavsakkaya curve sheet, placeholder Hmin", read_curve(KAVSAKKAYA_CURVE), 1071.99, 1099.0),  # no row at 1099 m
    (2, "Round numbers", [(100.0, 0.0, 0.5), (110.0, 10.0, 1.5), (120.0, 30.0, 2.5), (130.0, 60.0, 3.5)], 110.0, 115.0),
]

POINTS = ["Hbed", "Hmin", "Between rows", "Hcrest"]


def interpolate(x, xs, ys):
    """The straight line between the two rows of xs around x."""
    i = max(position for position in range(len(xs) - 1) if xs[position] <= x)
    return ys[i] + (x - xs[i]) * (ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i])


def worked(case):
    """Hbed, Hcrest, Vmax, Vdead = V(Hmin) and the levels of the four points."""
    _, _, rows, h_min, between = case
    levels, volumes = [row[0] for row in rows], [row[1] for row in rows]
    return (
        levels[0],
        levels[-1],
        volumes[-1],
        interpolate(h_min, levels, volumes),
        [levels[0], h_min, between, levels[-1]],
    )


def write_csv():
    with open(HERE / "reservoir_cases.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Case", "Description", "Hmin_m", "Hbed_m", "Hcrest_m", "Vmax_hm3", "Vdead_hm3"])
        for case in CASES:
            number, description, _, h_min, _ = case
            bed, crest, v_max, dead, _ = worked(case)
            writer.writerow([number, description, h_min, bed, crest, v_max, dead])

    with open(HERE / "reservoir_tables.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Case", "Elevation_m", "Volume_hm3", "Area_km2"])
        for case in CASES:
            writer.writerows([case[0], *row] for row in case[2])

    with open(HERE / "reservoir_points.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Case", "Point", "H_m", "V_hm3", "A_km2"])
        for case in CASES:
            rows = case[2]
            levels, volumes, areas = ([row[column] for row in rows] for column in range(3))
            for name, h in zip(POINTS, worked(case)[4], strict=True):
                writer.writerow([case[0], name, h, interpolate(h, levels, volumes), interpolate(h, levels, areas)])


def interpolate_formula(x, xs, ys, count):
    """`interpolate` as a spreadsheet formula, for ranges xs and ys of `count` rows."""
    row = f"MIN(MATCH({x},{xs},1),{count - 1})"
    return (
        f"=INDEX({ys},{row})+({x}-INDEX({xs},{row}))*(INDEX({ys},{row}+1)-INDEX({ys},{row}))"
        f"/(INDEX({xs},{row}+1)-INDEX({xs},{row}))"
    )


def case_sheet(book, case):
    number, description, rows, h_min, between = case
    sheet = book.create_sheet(f"Case {number}")
    sheet["A1"] = f"Case {number}: {description}"
    sheet["A1"].font = Font(bold=True)
    count = len(rows)
    levels, volumes, areas = (f"${column}$3:${column}${2 + count}" for column in "HIJ")

    inputs = [
        ("Hmin (m), entered", h_min),
        ("Hbed (m) = the first level of the curve", "=H3"),
        ("Hcrest (m) = the last level of the curve", f"=H{2 + count}"),
        ("Vmax (hm3) = the last volume of the curve", f"=I{2 + count}"),
        ("Vdead (hm3) = V(Hmin), read from the curve", interpolate_formula("B3", levels, volumes, count)),
    ]
    for row, (label, value) in enumerate(inputs, start=3):
        sheet.cell(row=row, column=1, value=label)
        sheet.cell(row=row, column=2, value=value)

    headers = ["Point", "H (m)", "V (hm3)", "A (km2)", "H back from V (m)"]
    for column, text in enumerate(headers, start=1):
        sheet.cell(row=14, column=column, value=text).font = Font(bold=True)
    point_levels = ["=B4", "=B3", between, "=B5"]
    for row, (name, level) in enumerate(zip(POINTS, point_levels, strict=True), start=15):
        sheet.cell(row=row, column=1, value=name)
        sheet.cell(row=row, column=2, value=level)
        sheet.cell(row=row, column=3, value=interpolate_formula(f"B{row}", levels, volumes, count))
        sheet.cell(row=row, column=4, value=interpolate_formula(f"B{row}", levels, areas, count))
        sheet.cell(row=row, column=5, value=interpolate_formula(f"C{row}", volumes, levels, count))

    for column, text in enumerate(["Curve: level (m)", "Volume (hm3)", "Surface area (km2)"], start=8):
        sheet.cell(row=2, column=column, value=text).font = Font(bold=True)
    for row, values in enumerate(rows, start=3):
        for column, value in enumerate(values, start=8):
            sheet.cell(row=row, column=column, value=value)
    for column, width in zip("ABCDEFGHIJ", (44, 14, 14, 14, 18, 4, 4, 16, 14, 18), strict=True):
        sheet.column_dimensions[column].width = width


def write_workbook():
    book = Workbook()
    book.remove(book.active)
    for case in CASES:
        case_sheet(book, case)
    book.calculation.fullCalcOnLoad = True  # openpyxl stores no results, so Excel works them out on opening
    book.save(HERE / "reservoir_verification.xlsx")


if __name__ == "__main__":
    write_csv()
    write_workbook()
