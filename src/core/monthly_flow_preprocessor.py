"""Monthly-to-daily synthetic hydrograph preprocessor for DSI dam flow tables.

DSI tables give natural inflow as monthly volumes (hm³) per water year. Spreading a
month evenly over its days flattens flood peaks, and the steep Wilcock & Crowe
threshold (tau > tau_ri) then yields little or no bedload. This module allocates each
monthly volume across its days with a mean-one log-normal multiplier whose log follows
an AR(1) chain, so a day depends partly on the day before (volume is conserved exactly) and returns daily discharge in the Date/Flow Q (m3/s)/Water_Year layout read
by TimeSeriesAggregator, which groups by Water_Year when that column is present.
"""

import math

import numpy as np
import pandas as pd

from src.core.rusle import to_ascii_turkish, turkish_lower
from src.core.wilcock import FLOW_COLUMN, WATER_YEAR_COLUMN

HM3_TO_M3 = 1_000_000.0
SECONDS_PER_DAY = 86_400.0
DEFAULT_SIGMA = 0.6
DEFAULT_SEED = 0
DEFAULT_PHI = 0.0  # lag-1 autocorrelation of the daily log-flow; 0 gives independent days
MAX_SIGMA = 3.0  # above this the largest day of a month carries more than half of its volume on average (D73)
WARN_SIGMA = 1.5  # above this it carries more than a quarter, and the bedload is reported as sensitive (D73)

# Water-year order (Ekim -> Eylül), as the DSİ labels the columns, mapped to calendar month numbers.
WATER_YEAR_MONTHS = (
    ("Ekim", 10),
    ("Kasım", 11),
    ("Aralık", 12),
    ("Ocak", 1),
    ("Şubat", 2),
    ("Mart", 3),
    ("Nisan", 4),
    ("Mayıs", 5),
    ("Haziran", 6),
    ("Temmuz", 7),
    ("Ağustos", 8),
    ("Eylül", 9),
)
YEAR_HEADER = "Yıllar"
SUMMARY_LABELS = {"top", "ort"}


def _summary_key(label: str) -> str:
    """A row label of the TOP. / ORT. summary rows, folded: 'TOP.' -> 'top'."""
    return "".join(to_ascii_turkish(turkish_lower(label)).split()).replace(".", "")


class MonthlyFlowPreprocessor:
    def __init__(self, sigma: float = DEFAULT_SIGMA, seed: int = DEFAULT_SEED, phi: float = DEFAULT_PHI):
        if not math.isfinite(sigma) or not 0 <= sigma <= MAX_SIGMA:
            raise ValueError(f"sigma must be a number from 0 to {MAX_SIGMA:g} (got {sigma:g}).")
        if not math.isfinite(phi) or not 0 <= phi < 1:
            raise ValueError(f"phi must be a number from 0 up to, but not including, 1 (got {phi}).")
        if seed < 0:
            raise ValueError(f"seed must be >= 0 (got {seed}).")
        self.sigma = float(sigma)
        self.seed = int(seed)
        self.phi = float(phi)

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

        year_col = YEAR_HEADER
        if year_col not in df.columns:
            raise KeyError(f"Monthly flow table must contain a '{YEAR_HEADER}' (year) column.")
        month_cols = [name for name, _ in WATER_YEAR_MONTHS]
        missing = [name for name in month_cols if name not in df.columns]
        if missing:
            raise KeyError(f"Monthly flow table missing month columns: {missing}")

        # Blanks and the TOP./ORT. summary rows are skipped; any other label must be a year.
        labels = df[year_col].astype(str).str.strip()
        years = pd.to_numeric(df[year_col], errors="coerce")
        valid = years.notna() & (years % 1 == 0) & years.between(1900, 2100)
        blank = df[year_col].isna() | (labels == "")
        summary = labels.map(_summary_key).isin(SUMMARY_LABELS)
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

        volumes = data[month_cols].apply(lambda s: pd.to_numeric(s.astype(str).str.strip(), errors="coerce"))
        bad = volumes.isna() | (volumes < 0)
        if bad.any().any():
            rows, cols = np.nonzero(bad.to_numpy())
            cells = [f"{data[year_col].iloc[r]} {month_cols[c]}" for r, c in zip(rows, cols, strict=True)]
            raise ValueError(f"Monthly volumes must be non-negative numbers; invalid cells: {cells}")

        records = []
        for label, row in zip(data[year_col], volumes.to_numpy(dtype=float), strict=True):
            for (_, month), volume in zip(WATER_YEAR_MONTHS, row, strict=True):
                records.append((label, self._calendar_year(label, month), month, volume))
        monthly = pd.DataFrame(records, columns=[WATER_YEAR_COLUMN, "Year", "Month", "Volume_hm3"])
        return monthly.sort_values(["Year", "Month"], ignore_index=True)

    def disaggregate(self, monthly: pd.DataFrame) -> pd.DataFrame:
        """Allocate each monthly volume over its days and convert to discharge (m³/s)."""
        if monthly is None or monthly.empty:
            raise ValueError("Monthly volume table is empty.")

        mu = -0.5 * self.sigma**2  # gives the multiplier a mean of one
        innovation = math.sqrt(1.0 - self.phi**2)  # keeps the variance of the standardised log-flow at one
        previous = None  # (year, month, last z) of the month before, so the chain runs on across month boundaries
        frames = []
        columns = [WATER_YEAR_COLUMN, "Year", "Month", "Volume_hm3"]
        for water_year, year, month, volume_hm3 in monthly[columns].itertuples(index=False):
            year, month = int(year), int(month)
            start = pd.Timestamp(year=year, month=month, day=1)
            n_days = start.days_in_month
            # Seeded by (seed, year, month) so each month is reproducible on its own.
            rng = np.random.default_rng(np.random.SeedSequence([self.seed, year, month]))
            eps = rng.standard_normal(n_days)
            follows = previous is not None and previous[0] * 12 + previous[1] + 1 == year * 12 + month
            z = np.empty(n_days)
            z[0] = self.phi * previous[2] + innovation * eps[0] if follows else eps[0]
            for day in range(1, n_days):
                z[day] = self.phi * z[day - 1] + innovation * eps[day]
            previous = (year, month, z[-1])
            weights = np.exp(mu + self.sigma * z)
            daily_m3 = float(volume_hm3) * HM3_TO_M3 * weights / weights.sum()
            frames.append(
                pd.DataFrame(
                    {
                        "Date": pd.date_range(start, periods=n_days, freq="D"),
                        FLOW_COLUMN: daily_m3 / SECONDS_PER_DAY,
                        WATER_YEAR_COLUMN: int(water_year),
                    }
                )
            )

        daily = pd.concat(frames, ignore_index=True).sort_values("Date", ignore_index=True)
        if daily["Date"].duplicated().any():
            raise ValueError("Disaggregated series contains duplicate dates; check for overlapping water years.")
        return daily


def prepare_daily_flow(
    df: pd.DataFrame, sigma: float = DEFAULT_SIGMA, seed: int = DEFAULT_SEED, phi: float = DEFAULT_PHI
):
    """Convert a DSI monthly table to daily flow. Returns (daily_df, notes)."""
    pre = MonthlyFlowPreprocessor(sigma=sigma, seed=seed, phi=phi)
    monthly = pre.parse_table(df)
    daily = pre.disaggregate(monthly)
    n_years = monthly[WATER_YEAR_COLUMN].nunique()
    total_hm3 = monthly["Volume_hm3"].sum()
    if phi == 0:
        split = f"a log-normal split (σ={sigma:g}, seed {seed})"
    else:
        split = f"a log-normal AR(1) split (σ={sigma:g}, φ={phi:g}, seed {seed})"
    notes = [
        f"Converted DSI monthly table ({n_years} water years, total {total_hm3:.2f} hm³) to daily flow "
        f"with {split}; results grouped by water year (Oct–Sep)."
    ]
    return daily, notes
