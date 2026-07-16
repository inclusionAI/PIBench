#!/usr/bin/env python3
"""Normalize the JS integration test result into checks/integration.json."""
import json
import sys
from pathlib import Path


def main():
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    if src.exists():
        data = json.loads(src.read_text(encoding="utf-8"))
        raw = data.get("rubrics") or data.get("results") or []
        rubrics = []
        for r in raw:
            if str(r.get("id", "")).startswith("harness_") or r.get("id") in ("SEED", "FATAL"):
                continue
            item = dict(r)
            if item.get("status") == "invalid":
                item["status"] = "fail"
                item["passed"] = False
                item["invalid"] = False
            item.setdefault("score", 1 if item.get("passed") else 0)
            item.setdefault("max_score", 1)
            item.setdefault("type", "integration")
            item.setdefault("dimension", "security")
            rubrics.append(item)
    else:
        rubrics = []
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps({"rubrics": rubrics}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[integration] {sum(1 for r in rubrics if r.get('passed'))}/{len(rubrics)} passed")


if __name__ == "__main__":
    main()
