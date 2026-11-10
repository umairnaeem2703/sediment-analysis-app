"""How an annual bedload record is spread over its years (D74): the share of the largest years, the mean without the
largest year, the years with a negligible load and the rank correlation of the load with the annual mean flow.

These describe a result and change none of its numbers. The thresholds that turn a figure into a flag are below.
"""

from typing import List, NamedTuple, Optional

import pandas as pd

TOP_YEARS = 3  # the number of largest years whose share of the total is reported
CONCENTRATED_SHARE = 0.5  # a share of the total in TOP_YEARS above this is flagged
NEGLIGIBLE_SHARE = 0.01  # a year whose load is below this fraction of the mean counts as negligible
WEAK_RANK_CORRELATION = 0.5  # a rank correlation of load and flow below this is flagged


class RecordStats(NamedTuple):
    top_years: List[int]  # the TOP_YEARS largest years, largest first
    top_share: float  # their share of the total load
    mean: float
    median: float
    largest_year: int
    mean_without_largest: float
    negligible_years: List[int]  # in the order of the record
    rank_correlation: Optional[float]  # Spearman's rho of load and flow; None when either is constant


def record_stats(years: pd.Series, flow: pd.Series, load: pd.Series) -> Optional[RecordStats]:
    """The spread of `load` over `years`, or None when the record has no more than TOP_YEARS years or no load."""
    years, flow, load = (pd.Series(series).reset_index(drop=True) for series in (years, flow, load))
    total = float(load.sum())
    if len(load) <= TOP_YEARS or total <= 0:
        return None
    top = load.nlargest(TOP_YEARS)
    mean = float(load.mean())
    constant = flow.nunique() < 2 or load.nunique() < 2
    rho = None if constant else float(flow.rank().corr(load.rank()))  # Spearman's rho: the correlation of the ranks
    return RecordStats(
        top_years=[int(years[index]) for index in top.index],
        top_share=float(top.sum()) / total,
        mean=mean,
        median=float(load.median()),
        largest_year=int(years[top.index[0]]),
        mean_without_largest=float(load.drop(top.index[0]).mean()),
        negligible_years=[int(year) for year in years[load < NEGLIGIBLE_SHARE * mean]],
        rank_correlation=rho,
    )
