"""The M3 before-and-after table for the hydrologist (OI-04): the sample dams' bedload with and without D35 and D36.

Run `python -m tests.benchmarks.before_after_bedload` to rewrite `bedload_before_after.csv` next to this script. Every dam
uses the same synthetic daily flow (the DSİ monthly table split with the default sigma and seed) and the sample grain
fractions. The columns are the annual bedload in m³/yr by water year:

- `Before`: the code before M3.1. W* has no square root (D35) and tau_ri is the sample file's column (D36).
- `D36_only`: tau_ri computed from the grain size, W* as before. The computed values reproduce the file's column to its
  rounding (D50), so this column differs from `Before` by under 0.01% in the mean (2.3% in the worst single year).
- `D35_only`: W* with the square root, tau_ri from the file.
- `After`: both fixes, as computed by `TimeSeriesAggregator` in `src`.

The other three columns come from a copy of the old formulas kept here for review, which is checked against `src` for the
`After` case on every run. Nothing reads this file.
"""

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from src.core.monthly_flow_preprocessor import prepare_daily_flow
from src.core.wilcock import PHI_BREAK, SECONDS_PER_YEAR, WATER_YEAR_COLUMN, FractionalModel, TimeSeriesAggregator
from src.utils.paths import read_table, resource_path

HERE = Path(__file__).parent
FLOW_FILES = ("cubuk_1_flow.csv", "cubuk_2_flow.csv", "kavsakkaya_flow.csv")


def annual_volumes(daily: pd.DataFrame, model: FractionalModel, tau_ri: np.ndarray, square_root: bool) -> pd.Series:
    """Annual bedload (m³/yr) by water year with the given tau_ri and the W* high branch with or without the root."""
    q = daily["Flow"].to_numpy(dtype=float)
    velocity = q / (model.bed_width * model.depth)
    tau = model.rho_w * model.g * model.manning_n**2 * velocity**2 / model.depth ** (1.0 / 3.0)
    u_star = np.sqrt(tau / model.rho_w)
    phi = tau[:, None] / tau_ri[None, :]
    root = np.sqrt(phi) if square_root else phi
    high = 14.0 * np.power(np.maximum(1.0 - 0.894 / np.where(phi > 0, root, 1.0), 0.0), 4.5)
    w_star = np.where(phi < PHI_BREAK, 0.002 * np.power(phi, 7.5), high)
    qb = (w_star * model._fi[None, :] * u_star[:, None] ** 3).sum(axis=1) / ((model.s - 1.0) * model.g)
    mean_rate = daily.assign(qb=np.where(q > 0, qb, 0.0)).groupby(WATER_YEAR_COLUMN)["qb"].mean()
    return mean_rate * model.bed_width * SECONDS_PER_YEAR


def main() -> None:
    fractions = read_table(resource_path("inputs", "fractional_parameters.csv"))
    model = FractionalModel()
    model.load_fractional_parameters(fractions)
    file_tau_ri = pd.to_numeric(fractions["tau_ri"]).to_numpy(dtype=float)
    computed_tau_ri = model._tau_ri

    rows = []
    for name in FLOW_FILES:
        daily, _ = prepare_daily_flow(read_table(resource_path("inputs", "dam_flow_data", name)))
        after = TimeSeriesAggregator(model).process_annual_averages(daily)["Annual_Total_Bedload_m3_yr"]
        columns = {
            "Before": annual_volumes(daily, model, file_tau_ri, square_root=False),
            "D36_only": annual_volumes(daily, model, computed_tau_ri, square_root=False),
            "D35_only": annual_volumes(daily, model, file_tau_ri, square_root=True),
            "After": after,
        }
        replica = annual_volumes(daily, model, computed_tau_ri, square_root=True)
        assert np.allclose(replica, after, rtol=1e-9, atol=0), f"{name}: the copy of the formulas drifted from src"
        mean_flow = daily.groupby(WATER_YEAR_COLUMN)["Flow"].mean()
        for year in mean_flow.index:
            rows.append(
                [name.removesuffix("_flow.csv"), year, mean_flow[year], *(column[year] for column in columns.values())]
            )
    with open(HERE / "bedload_before_after.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["Dam", "Water_Year", "Mean_Flow_m3_s", "Before_m3_yr", "D36_only_m3_yr", "D35_only_m3_yr", "After_m3_yr"]
        )
        writer.writerows(rows)


if __name__ == "__main__":
    main()
