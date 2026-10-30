"""X-DOC-01: the names and paths CLAUDE.md gives still exist, so that it does not send a reader to code that is gone."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SOURCE = "\n".join(
    path.read_text(encoding="utf-8", errors="ignore")
    for folder in ("src", "tests")
    for path in (ROOT / folder).rglob("*.py")
)
SPANS = sorted(set(re.findall(r"`([^`\n]+)`", (ROOT / "CLAUDE.md").read_text(encoding="utf-8"))))
IDENTIFIER = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*")
REPO_FOLDERS = ("src/", "tests/", "docs/", ".claude/")
FILE_NAME = re.compile(r"[\w.-]+\.(py|md|toml)")


def _exists(name: str) -> bool:
    if FILE_NAME.fullmatch(name):
        return (ROOT / name).exists() or any(
            path for folder in ("src", "tests", "docs") for path in (ROOT / folder).rglob(name)
        )
    pattern = name.rstrip("/")
    return bool(list(ROOT.glob(pattern))) if "*" in pattern else (ROOT / pattern).exists()


@pytest.mark.parametrize("span", SPANS)
def test_x_doc_01_a_name_or_path_in_claude_md_exists(span):
    token = re.sub(r"\(.*\)$", "", span)  # `invalidate_after(index, reason)` names invalidate_after
    if FILE_NAME.fullmatch(token) or token.startswith(REPO_FOLDERS):
        assert _exists(token), f"CLAUDE.md names `{span}`, which does not exist"
    elif IDENTIFIER.fullmatch(token):
        missing = [part for part in token.split(".") if not re.search(rf"\b{re.escape(part)}\b", SOURCE)]
        assert not missing, f"CLAUDE.md names `{span}`, but {missing} appears nowhere in src/ or tests/"
