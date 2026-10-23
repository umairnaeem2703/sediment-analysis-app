"""PostToolUse: src/core must not import Tkinter or UI code."""

import json
import re
import sys
from pathlib import Path

path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
p = Path(path)
if p.suffix != ".py" or p.parent.name != "core" or p.parent.parent.name != "src" or not p.exists():
    sys.exit(0)

banned = re.compile(r"^\s*(?:import|from)\s+(tkinter|src\.ui|src\.services)\b", re.M)
hits = [m.group(0).strip() for m in banned.finditer(p.read_text(encoding="utf-8"))]
if hits:
    print(
        f"Layer rule violated in {path}: src/core must stay free of Tkinter and UI/services code: {hits}",
        file=sys.stderr,
    )
    sys.exit(2)
