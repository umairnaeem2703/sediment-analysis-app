"""Regenerate the integration and projection goldens (B6): run `python -m tests.benchmarks.regenerate_integration`.

The files this writes may land on `main` only after the hydrologist has signed them off (B6, B7 step 7). They depend on
the commissioning and analysis years in `tests.samples`, which are placeholders until the dams' real years are known
(OI-02), and on the placeholder Hmin of each dam (D76); the manifest says so. Only the dams in `tests.samples.CURVE_DAMS`
have a curve. The manifest also records the sigma, seed and lag-1 phi of the monthly split and the SHA-256 of the inputs (line endings normalised);
`tests/pipeline/test_manifests.py` fails when an input no longer matches.
"""

import json
import shutil
import tempfile
from pathlib import Path

from src.core.monthly_flow_preprocessor import DEFAULT_PHI, DEFAULT_SEED, DEFAULT_SIGMA
from src.services.integration import write_integration_csv, write_projection_csv
from tests.benchmarks.regenerate_suspended import fingerprint
from tests.samples import (
    CURVE_DAMS,
    SAMPLE_ANALYSIS_YEAR,
    SAMPLE_BASINS,
    SAMPLE_COMMISSIONING_YEAR,
    SAMPLE_FRACTIONS,
    SAMPLE_H_MIN,
    SAMPLE_ZONAL,
    sample_curve,
    sample_dam_results,
    sample_flow,
    sample_integration_inputs,
)

HERE = Path(__file__).parent


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        data = sample_integration_inputs(Path(scratch) / "project")
        for slug in CURVE_DAMS:
            result = sample_dam_results(data, slug)[-1]
            shutil.copyfile(write_integration_csv(result, scratch), HERE / f"integration_{slug}.csv")
            shutil.copyfile(write_projection_csv(result, scratch), HERE / f"projection_{slug}.csv")
    inputs = [SAMPLE_BASINS, SAMPLE_ZONAL, SAMPLE_FRACTIONS]
    inputs += [path for slug in CURVE_DAMS for path in (sample_flow(slug), sample_curve(slug))]
    manifest = {
        "placeholder_years": {"commissioning_year": SAMPLE_COMMISSIONING_YEAR, "analysis_year": SAMPLE_ANALYSIS_YEAR},
        "placeholder_h_min_m": {slug: SAMPLE_H_MIN[slug] for slug in CURVE_DAMS},
        "flow_split": {"sigma": DEFAULT_SIGMA, "seed": DEFAULT_SEED, "phi": DEFAULT_PHI},
        "inputs": {path.name: fingerprint(path) for path in inputs},
    }
    (HERE / "integration_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
