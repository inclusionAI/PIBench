#!/usr/bin/env python3
import json
import sys
from pathlib import Path

out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(sys.argv[1])
out.write_text(json.dumps({"rubrics": [], "metadata": {"phase": "e2e", "reason": "no e2e checks in the original task instance"}}, ensure_ascii=False, indent=2), encoding="utf-8")
print("[e2e] no e2e checks in original task instance")
