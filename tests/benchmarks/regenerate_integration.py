"""Regenerate the integration and projection goldens (B6): run `python -m tests.benchmarks.regenerate_integration`.

The files this writes may land on `main` only after the hydrologist has signed them off (B6, B7 step 7). They depend on
the commissioning and analysis years in `tests.samples`, which are placeholders until the dams' real years are known
(OI-02); the manifest says so. It also records the sigma, seed and lag-1 phi of the monthly split, the shape classes,
and the SHA-256 of the sample inputs (line endings normalised); `tests/pipeline/test_manifests.py` fails when an
input no longer matches.
"""

import json
import shutil
import tempfile
from pathlib import Path

from src.core.monthly_flow_preprocessor import DEFAULT_PHI, DEFAULT_SEED, DEFAULT_SIGMA
from src.services.bedload import compute_dam_bedload
from src.services.integration import compute_dam_integration, write_integration_csv, write_projection_csv
from src.services.reservoir import compute_dam_curve
from src.services.suspended import compute_suspended
from tests.benchmarks.regenerate_suspended import fingerprint
from tests.samples import (
    SAMPLE_ANALYSIS_YEAR,
    SAMPLE_BASINS,
    SAMPLE_COMMISSIONING_YEAR,
    SAMPLE_FRACTIONS,
    SAMPLE_SHAPE_CLASSES,
    SAMPLE_ZONAL,
    sample_flow,
    sample_integration_inputs,
    sample_sheet,
)

HERE = Path(__file__).parent


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        data = sample_integration_inputs(Path(scratch) / "project")
        slugs = [dam.slug for dam in data.project.dams]
        for dam in data.project.dams:
            suspended = compute_suspended(data.sub_basins(dam), data.zonal)
            bedload = compute_dam_bedload(data.project, dam)
            curve = compute_dam_curve(data.dam_sheet(dam).data, dam)
            result = compute_dam_integration(suspended, bedload, curve, dam)
            shutil.copyfile(write_integration_csv(result, scratch), HERE / f"integration_{dam.slug}.csv")
            shutil.copyfile(write_projection_csv(result, scratch), HERE / f"projection_{dam.slug}.csv")
    inputs = [SAMPLE_BASINS, SAMPLE_ZONAL, SAMPLE_FRACTIONS]
    inputs += [path for slug in slugs for path in (sample_flow(slug), sample_sheet(slug))]
    manifest = {
        "placeholder_years": {"commissioning_year": SAMPLE_COMMISSIONING_YEAR, "analysis_year": SAMPLE_ANALYSIS_YEAR},
        "flow_split": {"sigma": DEFAULT_SIGMA, "seed": DEFAULT_SEED, "phi": DEFAULT_PHI},
        "shape_classes": SAMPLE_SHAPE_CLASSES,
        "inputs": {path.name: fingerprint(path) for path in inputs},
    }
    (HERE / "integration_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
