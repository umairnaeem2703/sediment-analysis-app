"""Regenerate the bedload goldens (B6): run `python -m tests.benchmarks.regenerate_bedload`.

The files this writes may land on `main` only after the hydrologist has signed them off (B6, B7 step 7). The manifest
records the code version, the sigma and seed of the monthly split, and the SHA-256 of the sample inputs (line endings
normalised); a version ending in `-dirty` means `src/` had uncommitted changes.
"""

import json
import shutil
import tempfile
from pathlib import Path

from src.core.monthly_flow_preprocessor import DEFAULT_SEED, DEFAULT_SIGMA
from src.services.bedload import compute_dam_bedload, write_bedload_csv
from tests.benchmarks.regenerate_suspended import code_version, fingerprint
from tests.samples import SAMPLE_FRACTIONS, sample_bedload_inputs, sample_flow

HERE = Path(__file__).parent


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        data = sample_bedload_inputs(Path(scratch) / "project")
        slugs = [dam.slug for dam in data.project.dams]
        for dam in data.project.dams:
            written = write_bedload_csv(compute_dam_bedload(data.project, dam), scratch)
            shutil.copyfile(written, HERE / f"bedload_{dam.slug}.csv")
    manifest = {
        "code_version": code_version(),
        "flow_split": {"sigma": DEFAULT_SIGMA, "seed": DEFAULT_SEED},
        "inputs": {path.name: fingerprint(path) for path in (SAMPLE_FRACTIONS, *(sample_flow(slug) for slug in slugs))},
    }
    (HERE / "bedload_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
