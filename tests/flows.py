"""DSİ monthly flow tables built in memory, for the flow tests."""

import numpy as np
import pandas as pd

TURKISH_HEADER = [
    "Yıllar",
    "Ekim",
    "Kasım",
    "Aralık",
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "TOP.",
]


ASCII_HEADER = [
    "Yillar",
    "Ekim",
    "Kasim",
    "Aralik",
    "Ocak",
    "Subat",
    "Mart",
    "Nisan",
    "Mayis",
    "Haziran",
    "Temmuz",
    "Agustos",
    "Eylul",
    "TOP.",
]


def dsi_table(values_by_year, header=TURKISH_HEADER, summary_rows=True):
    """Build a wide DSI table: one row per water year plus TOP./ORT. summary rows."""
    rows = [[year, *vals, round(sum(vals), 2)] for year, vals in values_by_year.items()]
    if summary_rows:
        months = np.array([vals for vals in values_by_year.values()], dtype=float)
        rows.append(["TOP.", *months.sum(axis=0).round(2), round(months.sum(), 2)])
        rows.append(["ORT.", *months.mean(axis=0).round(2), round(months.sum(axis=1).mean(), 2)])
    return pd.DataFrame(rows, columns=header)


def sample_values(years=(1974, 1975)):
    rng = np.random.default_rng(123)
    return {year: rng.uniform(0.0, 20.0, 12).round(2).tolist() for year in years}
