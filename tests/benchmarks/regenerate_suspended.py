"""Regenerate the suspended-sediment goldens (B6): run `python -m tests.benchmarks.regenerate_suspended`.

The files this writes may land on `main` only after the hydrologist has signed them off (B6, B7 step 7). The manifest
records the code version and the SHA-256 of the sample inputs (line endings normalised, so a checkout with another
`core.autocrlf` gives the same hash); a version ending in `-dirty` means `src/` had uncommitted changes.
"""

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.services.suspended import compute_suspended, write_suspended_csv
from tests.samples import SAMPLE_BASINS, SAMPLE_ZONAL, sample_regional

HERE = Path(__file__).parent
ROOT = HERE.parents[1]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def code_version() -> str:
    return _git("rev-parse", "--short", "HEAD") + ("-dirty" if _git("status", "--porcelain", "--", "src") else "")


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        data = sample_regional(Path(scratch) / "project")
        for dam in data.project.dams:
            result = compute_suspended(data.sub_basins(dam), data.zonal, SAMPLE_ZONAL.name)
            written = write_suspended_csv(result, scratch)
            shutil.copyfile(written, HERE / f"suspended_{dam.slug}.csv")
    manifest = {
        "code_version": code_version(),
        "inputs": {path.name: fingerprint(path) for path in (SAMPLE_BASINS, SAMPLE_ZONAL)},
    }
    (HERE / "suspended_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
