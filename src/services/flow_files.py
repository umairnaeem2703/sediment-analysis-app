"""Flow files on disk (FR-M3-01): read a DSİ monthly CSV and write the synthetic daily series made from it.

These steps were part of `src/core/monthly_flow_preprocessor.py`, which must do no file I/O (B2). Run as
`python -m src.services.flow_files monthly.csv daily.csv [--sigma S] [--seed N]`.
"""

import argparse
from pathlib import Path

import pandas as pd

from src.core.monthly_flow_preprocessor import (
    DEFAULT_SEED,
    DEFAULT_SIGMA,
    HM3_TO_M3,
    SECONDS_PER_DAY,
    MonthlyFlowPreprocessor,
)
from src.core.wilcock import WATER_YEAR_COLUMN
from src.utils.paths import read_table


def load_monthly_flow(file_path) -> pd.DataFrame:
    """The monthly volumes (Water_Year, Year, Month, Volume_hm3) of a DSİ monthly CSV."""
    if Path(file_path).suffix.lower() != ".csv":
        raise ValueError(f"Monthly flow input must be a CSV file (got {Path(file_path).name}).")
    return MonthlyFlowPreprocessor().parse_table(read_table(file_path))


def export_daily_csv(daily: pd.DataFrame, save_path) -> pd.DataFrame:
    """Write the Date (dd/mm/yyyy), Flow and Water_Year columns of a daily series (UTF-8 with BOM, for Excel)."""
    out = daily[["Date", "Flow", WATER_YEAR_COLUMN]].copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%d/%m/%Y")
    out.to_csv(save_path, index=False, encoding="utf-8-sig")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert a DSI monthly flow CSV (hm³) to synthetic daily flow (m³/s).")
    parser.add_argument("input", help="Monthly flow CSV with Yıllar, Ekim..Eylül columns")
    parser.add_argument("output", help="Destination CSV with Date, Flow, Water_Year columns")
    parser.add_argument("--sigma", type=float, default=DEFAULT_SIGMA, help="Log-normal sigma (0 = uniform split)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Base random seed")
    args = parser.parse_args(argv)

    monthly = load_monthly_flow(args.input)
    daily = MonthlyFlowPreprocessor(sigma=args.sigma, seed=args.seed).disaggregate(monthly)
    export_daily_csv(daily, args.output)

    total_hm3 = (daily["Flow"] * SECONDS_PER_DAY).sum() / HM3_TO_M3
    print(f"Wrote {len(daily)} days ({daily['Date'].min():%d/%m/%Y} - {daily['Date'].max():%d/%m/%Y}) to {args.output}")
    print(f"Total volume: {total_hm3:.2f} hm³ (input {monthly['Volume_hm3'].sum():.2f} hm³)")
    print("Note: the Water_Year column makes the bedload step group results by water year (Oct–Sep).")


if __name__ == "__main__":
    main()
