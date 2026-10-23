"""UserPromptSubmit / PreToolUse: block once the session has used 40% of the context window.

Usage is read from the last assistant turn in the transcript. Set CONTEXT_WINDOW_TOKENS if the
window is not 200000 (for example 1000000).
"""

import json
import os
import sys

LIMIT = 0.40
WINDOW = int(os.environ.get("CONTEXT_WINDOW_TOKENS", "200000"))

data = json.load(sys.stdin)
used = 0
try:
    with open(data["transcript_path"], encoding="utf-8") as f:
        for line in f:
            usage = (json.loads(line).get("message") or {}).get("usage")
            if usage:
                used = (
                    usage.get("input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0)
                )
except (KeyError, OSError, ValueError):
    sys.exit(0)

if used / WINDOW < LIMIT:
    sys.exit(0)

reason = (
    f"Context is at {used / WINDOW:.0%} of {WINDOW:,} tokens (limit {LIMIT:.0%}). Start a fresh session or /compact."
)
if data.get("hook_event_name") == "PreToolUse":
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
else:
    out = {"decision": "block", "reason": reason}
print(json.dumps(out))
