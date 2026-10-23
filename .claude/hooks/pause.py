"""PreToolUse: ask for confirmation on the first write/execute call of a session, so the model
and effort can be switched before implementation starts."""

import json
import sys
import tempfile
from pathlib import Path

data = json.load(sys.stdin)
marker = Path(tempfile.gettempdir()) / f"claude-pause-{data.get('session_id', 'x')}"
if marker.exists():
    sys.exit(0)
marker.touch()

print(
    json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "Pause before implementation: switch model/effort now, then approve.",
            }
        }
    )
)
