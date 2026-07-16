#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main() -> int:
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output/llm_judge_phase.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rubrics": [], "metadata": {"phase": "llm", "not_applicable": True}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
