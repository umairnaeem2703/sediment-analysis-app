"""P-X-01: the inputs a golden manifest records are the sample files in the repository (B6, OI-08)."""

import json
from pathlib import Path

import pytest

from src.utils.paths import resource_path
from tests.benchmarks.regenerate_suspended import fingerprint

BENCHMARKS = Path(__file__).parents[1] / "benchmarks"
PHASES = ["suspended", "reservoir", "bedload", "integration"]


def _sample(name):
    """The sample file `name` in inputs/, or the provisional test input in tests/data/ (OI-11)."""
    found = [*resource_path("inputs").rglob(name), *resource_path("tests", "data").glob(name)]
    assert len(found) == 1, f"{name} is in {len(found)} places under inputs/ and tests/data/"
    return found[0]


@pytest.mark.parametrize("phase", PHASES)
def test_p_x_01_the_inputs_a_manifest_records_are_the_sample_files(phase):
    recorded = json.loads((BENCHMARKS / f"{phase}_manifest.json").read_text(encoding="utf-8"))["inputs"]

    changed = [name for name, digest in recorded.items() if fingerprint(_sample(name)) != digest]

    assert not changed, (
        f"{changed} changed since the {phase} goldens were made: run `python -m tests.benchmarks.regenerate_{phase}` "
        "and have the hydrologist review the golden files it rewrites (B6)."
    )
