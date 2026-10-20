"""Monthly-to-daily synthetic hydrograph preprocessor for DSI dam flow tables.

DSI tables give natural inflow as monthly volumes (hm³) per water year. Spreading a
month evenly over its days flattens flood peaks, and the steep Wilcock & Crowe
threshold (tau > tau_ri) then yields little or no bedload. This module allocates each
monthly volume across its days with a mean-one log-normal multiplier (volume is
conserved exactly) and returns daily discharge in the Date/Flow layout read by
TimeSeriesAggregator.
"""

import argparse
import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from src.core.rusle import to_ascii_turkish, turkish_lower
from src.utils.paths import read_table

HM3_TO_M3 = 1_000_000.0
SECONDS_PER_DAY = 86_400.0
DEFAULT_SIGMA = 0.6
DEFAULT_SEED = 0
TOTAL_TOLERANCE_HM3 = 0.05

# Water-year order (Ekim -> Eylül) mapped to calendar month numbers.
WATER_YEAR_MONTHS = (
    ("ekim", 10), ("kasim", 11), ("aralik", 12),
    ("ocak", 1), ("subat", 2), ("mart", 3),
    ("nisan", 4), ("mayis", 5), ("haziran", 6),
    ("temmuz", 7), ("agustos", 8), ("eylul", 9),
)
YEAR_HEADER = "yillar"
TOTAL_HEADER = "top"


def _normalize(text) -> str:
    return to_ascii_turkish(turkish_lower(text)).replace(".", "").replace(":", "").strip()


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
        """Turn a wide DSI table (Yıllar, Ekim..Eylül, TOP.) into long monthly volumes."""
        if df is None or df.empty:
            raise ValueError("Monthly flow table is empty.")

        lookup = {_normalize(col): col for col in df.columns}
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
        summary = labels.map(_normalize).isin({TOTAL_HEADER, "ort"})
        rejected = ~valid & ~blank & ~summary
        if rejected.any():
            raise ValueError(
                f"Unrecognised year labels (expected a year from 1900 to 2100, TOP. or ORT.): {labels[rejected].tolist()}"
            )
        if not valid.any():
            raise ValueError("Monthly flow table contains no data rows with a valid year.")
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

        total_col = lookup.get(TOTAL_HEADER)
        if total_col is not None:
            totals = pd.to_numeric(data[total_col], errors="coerce")
            diff = (volumes.sum(axis=1) - totals).abs()
            off = data.loc[diff > TOTAL_TOLERANCE_HM3, year_col].tolist()
            if off:
                warnings.warn(f"Monthly volumes do not match the TOP. column for years: {off}", UserWarning)

        records = []
        for label, row in zip(data[year_col], volumes.to_numpy(dtype=float)):
            for (_, month), volume in zip(WATER_YEAR_MONTHS, row):
                records.append((label, self._calendar_year(label, month), month, volume))
        monthly = pd.DataFrame(records, columns=["WaterYear", "Year", "Month", "Volume_hm3"])
        return monthly.sort_values(["Year", "Month"], ignore_index=True)

    def load(self, file_path: str) -> pd.DataFrame:
        if Path(file_path).suffix.lower() != ".csv":
            raise ValueError(f"Monthly flow input must be a CSV file (got {Path(file_path).name}).")
        return self.parse_table(read_table(file_path))

    def disaggregate(self, monthly: pd.DataFrame) -> pd.DataFrame:
        """Allocate each monthly volume over its days and convert to discharge (m³/s)."""
        if monthly is None or monthly.empty:
            raise ValueError("Monthly volume table is empty.")

        mu = -0.5 * self.sigma ** 2  # gives the multiplier a mean of one
        frames = []
        for year, month, volume_hm3 in monthly[["Year", "Month", "Volume_hm3"]].itertuples(index=False):
            year, month = int(year), int(month)
            start = pd.Timestamp(year=year, month=month, day=1)
            n_days = start.days_in_month
            # Seeded by (seed, year, month) so each month is reproducible on its own.
            rng = np.random.default_rng(np.random.SeedSequence([self.seed, year, month]))
            weights = rng.lognormal(mean=mu, sigma=self.sigma, size=n_days)
            daily_m3 = float(volume_hm3) * HM3_TO_M3 * weights / weights.sum()
            frames.append(
                pd.DataFrame({"Date": pd.date_range(start, periods=n_days, freq="D"), "Flow": daily_m3 / SECONDS_PER_DAY})
            )

        daily = pd.concat(frames, ignore_index=True).sort_values("Date", ignore_index=True)
        if daily["Date"].duplicated().any():
            raise ValueError("Disaggregated series contains duplicate dates; check for overlapping water years.")
        return daily

    def run(self, file_path: str) -> pd.DataFrame:
        return self.disaggregate(self.load(file_path))

    @staticmethod
    def export_csv(daily: pd.DataFrame, save_path: str) -> pd.DataFrame:
        out = daily[["Date", "Flow"]].copy()
        out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%d/%m/%Y")
        out.to_csv(save_path, index=False, encoding="utf-8-sig")
        return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert a DSI monthly flow CSV (hm³) to synthetic daily flow (m³/s).")
    parser.add_argument("input", help="Monthly flow CSV with Yıllar, Ekim..Eylül columns")
    parser.add_argument("output", help="Destination CSV with Date, Flow columns")
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
    print("Note: the Wilcock tab groups by calendar year, so the first and last years are partial.")


if __name__ == "__main__":
    main()
