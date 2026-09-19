"""Print a Kaggle kernel log (JSON array of {stream_name, data}) as plain text.

Kernel failures are otherwise invisible to CI: the workflow only sees the status
"error" with no reason.
"""
import json, sys
from pathlib import Path

logs = sorted(Path(sys.argv[1] if len(sys.argv) > 1 else "artifact").glob("*.log"))
if not logs:
    print("(no kernel log found)"); raise SystemExit(0)
for f in logs:
    print("=" * 20, f.name, "=" * 20)
    raw = f.read_text(encoding="utf-8", errors="replace")
    try:
        for r in json.loads(raw):
            print(r.get("stream_name", ""), r.get("data", "").rstrip())
    except json.JSONDecodeError:
        print(raw)
