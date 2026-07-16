#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def normalize(item):
    old = item.get("type")
    if old and old not in {"deterministic", "llm_assisted"}:
        item.setdefault("legacy_type", old)
    item["type"] = "llm_assisted" if str(item.get("id", "")).startswith("judge.") or old in {"llm", "llm_judge"} else "deterministic"
    item.setdefault("score", 1 if item.get("passed") else 0)
    item.setdefault("max_score", 1)
    return item


def main() -> int:
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/output")
    path = output_dir / "result.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rubrics"] = [normalize(dict(item)) for item in data.get("rubrics", [])]
    data.setdefault("metadata", {})["result_type_normalized"] = True
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
