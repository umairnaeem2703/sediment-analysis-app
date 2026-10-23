"""PostToolUse: format and lint an edited Python file with ruff; report what ruff cannot fix."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
PY = str(VENV_PY) if VENV_PY.exists() else sys.executable

path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
if not path.endswith(".py"):
    sys.exit(0)

subprocess.run([PY, "-m", "ruff", "format", path], cwd=ROOT, capture_output=True)
check = subprocess.run([PY, "-m", "ruff", "check", "--fix", path], cwd=ROOT, capture_output=True, text=True)
if check.returncode != 0:
    print(check.stdout + check.stderr, file=sys.stderr)
    sys.exit(2)
