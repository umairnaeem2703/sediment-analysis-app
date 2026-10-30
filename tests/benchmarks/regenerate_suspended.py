"""Regenerate the suspended-sediment goldens (B6): run `python -m tests.benchmarks.regenerate_suspended`.

The files this writes may land on `main` only after the hydrologist has signed them off (B6, B7 step 7). The manifest
records the SHA-256 of the sample inputs (line endings normalised, so a checkout with another `core.autocrlf` gives
the same hash), and `tests/pipeline/test_manifests.py` fails when an input no longer matches it. It records no
commit: a branch commit does not survive a squash-merge, and the history of the manifest says when the goldens were
made.
"""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from src.services.suspended import compute_suspended, write_suspended_csv
from tests.samples import SAMPLE_BASINS, SAMPLE_ZONAL, sample_regional

HERE = Path(__file__).parent


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        data = sample_regional(Path(scratch) / "project")
        for dam in data.project.dams:
            result = compute_suspended(data.sub_basins(dam), data.zonal, SAMPLE_ZONAL.name)
            written = write_suspended_csv(result, scratch)
            shutil.copyfile(written, HERE / f"suspended_{dam.slug}.csv")
    manifest = {
        "inputs": {path.name: fingerprint(path) for path in (SAMPLE_BASINS, SAMPLE_ZONAL)},
    }
    (HERE / "suspended_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
