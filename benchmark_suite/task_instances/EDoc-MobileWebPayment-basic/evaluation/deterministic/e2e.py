#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main():
    out = Path(sys.argv[1])
    out.write_text(json.dumps({"rubrics": [], "metadata": {"phase": "e2e", "not_applicable": True}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
