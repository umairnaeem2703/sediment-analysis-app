"""Regenerate the reservoir-curve goldens (B6): run `python -m tests.benchmarks.regenerate_reservoir`.

The files this writes may land on `main` only after the hydrologist has signed them off (B6, B7 step 7). The curves are
those of the worked examples of B3.3: the sample dam sheets, no Hmin, and the shape class in
`tests.samples.SAMPLE_SHAPE_CLASSES`. The manifest records the shape classes and the SHA-256 of the sample inputs
(line endings normalised, so a checkout with another `core.autocrlf` gives the same hash);
`tests/pipeline/test_manifests.py` fails when an input no longer matches.
"""

import json
import shutil
import tempfile
from pathlib import Path

from src.services.reservoir import compute_dam_curve, write_reservoir_csv
from tests.benchmarks.regenerate_suspended import fingerprint
from tests.samples import SAMPLE_BASINS, SAMPLE_SHAPE_CLASSES, SAMPLE_ZONAL, sample_curve_inputs, sample_sheet

HERE = Path(__file__).parent


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        data = sample_curve_inputs(Path(scratch) / "project")
        for dam in data.project.dams:
            result = compute_dam_curve(data.dam_sheet(dam).data, dam)
            written = write_reservoir_csv(result, scratch)
            shutil.copyfile(written, HERE / f"reservoir_{dam.slug}.csv")
        sheets = [sample_sheet(dam.slug) for dam in data.project.dams]
    manifest = {
        "shape_classes": SAMPLE_SHAPE_CLASSES,
        "inputs": {path.name: fingerprint(path) for path in (SAMPLE_BASINS, SAMPLE_ZONAL, *sheets)},
    }
    (HERE / "reservoir_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
