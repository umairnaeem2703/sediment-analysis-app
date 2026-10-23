"""Monthly-to-daily synthetic hydrograph preprocessor for DSI dam flow tables.

DSI tables give natural inflow as monthly volumes (hm³) per water year. Spreading a
month evenly over its days flattens flood peaks, and the steep Wilcock & Crowe
threshold (tau > tau_ri) then yields little or no bedload. This module allocates each
monthly volume across its days with a mean-one log-normal multiplier (volume is
conserved exactly) and returns daily discharge in the Date/Flow/Water_Year layout read
by TimeSeriesAggregator, which groups by Water_Year when that column is present.
"""

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.core.rusle import normalize_header
from src.core.wilcock import WATER_YEAR_COLUMN
from src.utils.paths import read_table

HM3_TO_M3 = 1_000_000.0
SECONDS_PER_DAY = 86_400.0
DEFAULT_SIGMA = 0.6
DEFAULT_SEED = 0

# Water-year order (Ekim -> Eylül) mapped to calendar month numbers.
WATER_YEAR_MONTHS = (
    ("ekim", 10),
    ("kasim", 11),
    ("aralik", 12),
    ("ocak", 1),
    ("subat", 2),
    ("mart", 3),
    ("nisan", 4),
    ("mayis", 5),
    ("haziran", 6),
    ("temmuz", 7),
    ("agustos", 8),
    ("eylul", 9),
)
YEAR_HEADER = "yillar"
SUMMARY_LABELS = {"top", "ort"}


class MonthlyFlowPreprocessor:
    def __init__(self, sigma: float = DEFAULT_SIGMA, seed: int = DEFAULT_SEED):
        if not math.isfinite(sigma) or sigma < 0:
            raise ValueError(f"sigma must be a finite number >= 0 (got {sigma}).")
        if seed < 0:
            raise ValueError(f"seed must be >= 0 (got {seed}).")
        self.sigma = float(sigma)
        self.seed = int(seed)

    @staticmethod
    def _calendar_year(label: int, month: int) -> int:
        # A water year labelled Y runs Oct (Y-1) to Sep (Y), so Ekim-Aralık fall in Y-1.
        return label - 1 if month >= 10 else label

    def parse_table(self, df: pd.DataFrame) -> pd.DataFrame:
        """Turn a wide DSI table (Yıllar, Ekim..Eylül) into long monthly volumes.

        TOP./ORT. summary rows and the TOP. column are ignored.
        """
        if df is None or df.empty:
            raise ValueError("Monthly flow table is empty.")

        lookup = {normalize_header(col): col for col in df.columns}
        year_col = lookup.get(YEAR_HEADER)
        if year_col is None:
            raise KeyError("Monthly flow table must contain a 'Yıllar' (year) column.")
        missing = [name for name, _ in WATER_YEAR_MONTHS if name not in lookup]
        if missing:
            raise KeyError(f"Monthly flow table missing month columns: {missing}")
        month_cols = [lookup[name] for name, _ in WATER_YEAR_MONTHS]

        # Blanks and the TOP./ORT. summary rows are skipped; any other label must be a year.
        labels = df[year_col].astype(str).str.strip()
        years = pd.to_numeric(df[year_col], errors="coerce")
        valid = years.notna() & (years % 1 == 0) & years.between(1900, 2100)
        blank = df[year_col].isna() | (labels == "")
        summary = labels.map(normalize_header).isin(SUMMARY_LABELS)
        rejected = ~valid & ~blank & ~summary
        if rejected.any():
            raise ValueError(
                f"Unrecognised year labels (expected a year from 1900 to 2100, TOP. or ORT.): {labels[rejected].tolist()}"
            )
        if not valid.any():
            raise ValueError("Monthly flow table contains no data rows with a valid year.")
        # A blank-year row that still carries volumes would otherwise vanish silently.
        populated = df[month_cols].apply(lambda s: s.map(lambda v: pd.notna(v) and str(v).strip() != ""))
        orphan = blank & populated.any(axis=1)
        if orphan.any():
            rows = (np.flatnonzero(orphan.to_numpy()) + 1).tolist()
            raise ValueError(f"Monthly flow table has rows with volumes but no year label (data row numbers: {rows}).")
        data = df.loc[valid].copy()
        data[year_col] = years[valid].astype(int)
        if data[year_col].duplicated().any():
            dupes = sorted(data.loc[data[year_col].duplicated(), year_col].unique().tolist())
            raise ValueError(f"Monthly flow table has duplicate years: {dupes}")

        volumes = data[month_cols].apply(
            lambda s: pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False).str.strip(), errors="coerce")
        )
        bad = volumes.isna() | (volumes < 0)
        if bad.any().any():
            rows, cols = np.nonzero(bad.to_numpy())
            cells = [f"{data[year_col].iloc[r]} {month_cols[c]}" for r, c in zip(rows, cols)]
            raise ValueError(f"Monthly volumes must be non-negative numbers; invalid cells: {cells}")

        records = []
        for label, row in zip(data[year_col], volumes.to_numpy(dtype=float)):
            for (_, month), volume in zip(WATER_YEAR_MONTHS, row):
                records.append((label, self._calendar_year(label, month), month, volume))
        monthly = pd.DataFrame(records, columns=[WATER_YEAR_COLUMN, "Year", "Month", "Volume_hm3"])
        return monthly.sort_values(["Year", "Month"], ignore_index=True)

    def load(self, file_path: str) -> pd.DataFrame:
        if Path(file_path).suffix.lower() != ".csv":
            raise ValueError(f"Monthly flow input must be a CSV file (got {Path(file_path).name}).")
        return self.parse_table(read_table(file_path))

    def disaggregate(self, monthly: pd.DataFrame) -> pd.DataFrame:
        """Allocate each monthly volume over its days and convert to discharge (m³/s)."""
        if monthly is None or monthly.empty:
            raise ValueError("Monthly volume table is empty.")

        mu = -0.5 * self.sigma**2  # gives the multiplier a mean of one
        frames = []
        columns = [WATER_YEAR_COLUMN, "Year", "Month", "Volume_hm3"]
        for water_year, year, month, volume_hm3 in monthly[columns].itertuples(index=False):
            year, month = int(year), int(month)
            start = pd.Timestamp(year=year, month=month, day=1)
            n_days = start.days_in_month
            # Seeded by (seed, year, month) so each month is reproducible on its own.
            rng = np.random.default_rng(np.random.SeedSequence([self.seed, year, month]))
            weights = rng.lognormal(mean=mu, sigma=self.sigma, size=n_days)
            daily_m3 = float(volume_hm3) * HM3_TO_M3 * weights / weights.sum()
            frames.append(
                pd.DataFrame(
                    {
                        "Date": pd.date_range(start, periods=n_days, freq="D"),
                        "Flow": daily_m3 / SECONDS_PER_DAY,
                        WATER_YEAR_COLUMN: int(water_year),
                    }
                )
            )

        daily = pd.concat(frames, ignore_index=True).sort_values("Date", ignore_index=True)
        if daily["Date"].duplicated().any():
            raise ValueError("Disaggregated series contains duplicate dates; check for overlapping water years.")
        return daily

    def run(self, file_path: str) -> pd.DataFrame:
        return self.disaggregate(self.load(file_path))

    @staticmethod
    def export_csv(daily: pd.DataFrame, save_path: str) -> pd.DataFrame:
        out = daily[["Date", "Flow", WATER_YEAR_COLUMN]].copy()
        out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%d/%m/%Y")
        out.to_csv(save_path, index=False, encoding="utf-8-sig")
        return out


def is_monthly_flow_table(df: pd.DataFrame) -> bool:
    """True if the table looks like a DSI monthly table rather than a Date/Flow daily series.

    Deliberately broad: a malformed DSI file (e.g. a missing month column) still routes to
    parse_table, which reports the specific problem instead of a generic Date/Flow error.
    """
    if df is None or df.empty:
        return False
    names = {normalize_header(col) for col in df.columns}
    if names & {"date", "tarih"}:
        return False
    return YEAR_HEADER in names or any(month in names for month, _ in WATER_YEAR_MONTHS)


def prepare_daily_flow(df: pd.DataFrame, sigma: float = DEFAULT_SIGMA, seed: int = DEFAULT_SEED):
    """Convert a DSI monthly table to daily flow. Returns (daily_df, notes)."""
    pre = MonthlyFlowPreprocessor(sigma=sigma, seed=seed)
    monthly = pre.parse_table(df)
    daily = pre.disaggregate(monthly)
    n_years = monthly[WATER_YEAR_COLUMN].nunique()
    total_hm3 = monthly["Volume_hm3"].sum()
    notes = [
        f"Converted DSI monthly table ({n_years} water years, total {total_hm3:.2f} hm³) to daily flow "
        f"with a log-normal split (σ={sigma:g}, seed {seed}); results grouped by water year (Oct–Sep)."
    ]
    return daily, notes


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert a DSI monthly flow CSV (hm³) to synthetic daily flow (m³/s).")
    parser.add_argument("input", help="Monthly flow CSV with Yıllar, Ekim..Eylül columns")
    parser.add_argument("output", help="Destination CSV with Date, Flow, Water_Year columns")
    parser.add_argument("--sigma", type=float, default=DEFAULT_SIGMA, help="Log-normal sigma (0 = uniform split)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Base random seed")
    args = parser.parse_args(argv)

    pre = MonthlyFlowPreprocessor(sigma=args.sigma, seed=args.seed)
    monthly = pre.load(args.input)
    daily = pre.disaggregate(monthly)
    pre.export_csv(daily, args.output)

    total_hm3 = (daily["Flow"] * SECONDS_PER_DAY).sum() / HM3_TO_M3
    print(f"Wrote {len(daily)} days ({daily['Date'].min():%d/%m/%Y} - {daily['Date'].max():%d/%m/%Y}) to {args.output}")
    print(f"Total volume: {total_hm3:.2f} hm³ (input {monthly['Volume_hm3'].sum():.2f} hm³)")
    print("Note: the Water_Year column makes the Wilcock tab group results by water year (Oct–Sep).")


if __name__ == "__main__":
    main()
