"""The independent hand calculations in tests/verification/ as data (B6)."""

import csv
from pathlib import Path
from typing import Dict

VERIFICATION = Path(__file__).parent / "verification"


def suspended_cases() -> Dict[int, dict]:
    """The B3.1 cases by case number: inputs and hand-calculated results as floats, plus the description."""
    with open(VERIFICATION / "suspended_cases.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        int(row["Case"]): {key: value if key == "Description" else float(value) for key, value in row.items()}
        for row in rows
    }
