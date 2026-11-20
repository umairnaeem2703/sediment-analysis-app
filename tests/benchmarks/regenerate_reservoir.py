"""Regenerate the reservoir-curve goldens (B6): run `python -m tests.benchmarks.regenerate_reservoir`.

The files this writes may land on `main` only after the hydrologist has signed them off (B6, B7 step 7). There is one
golden for each dam in `tests.samples.CURVE_DAMS`: its curve sheet. The manifest records the placeholder Hmin of each
dam (D76) and the SHA-256 of the curve sheets (line endings normalised, so a checkout with another `core.autocrlf` gives
the same hash); `tests/pipeline/test_manifests.py` fails when an input no longer matches.
"""

import json
import shutil
import tempfile
from pathlib import Path

from src.services.reservoir import compute_dam_curve, write_reservoir_csv
from tests.benchmarks.regenerate_suspended import fingerprint
from tests.samples import CURVE_DAMS, SAMPLE_H_MIN, sample_curve, sample_curve_inputs

HERE = Path(__file__).parent


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        data = sample_curve_inputs(Path(scratch) / "project")
        for dam in data.project.dams:
            if dam.slug in CURVE_DAMS:
                result = compute_dam_curve(data.project, dam)
                shutil.copyfile(write_reservoir_csv(result, scratch), HERE / f"reservoir_{dam.slug}.csv")
    manifest = {
        "placeholder_h_min_m": {slug: SAMPLE_H_MIN[slug] for slug in CURVE_DAMS},
        "inputs": {sample_curve(slug).name: fingerprint(sample_curve(slug)) for slug in CURVE_DAMS},
    }
    (HERE / "reservoir_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
