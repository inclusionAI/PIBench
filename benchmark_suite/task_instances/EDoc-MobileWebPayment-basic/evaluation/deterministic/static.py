#!/usr/bin/env python3
import json
import sys
from pathlib import Path

SUPPORT = Path(__file__).resolve().parent / "support"
sys.path.insert(0, str(SUPPORT))

from static_checks import run_static_checks  # noqa: E402


def load_defs(task_instance_dir: Path):
    payload = json.loads((task_instance_dir / "evaluation" / "rubrics.json").read_text(encoding="utf-8"))
    return {item["id"]: item for item in payload.get("rubrics", []) if item.get("id")}


def main():
    workspace = Path(sys.argv[1])
    out = Path(sys.argv[2])
    task_instance_dir = Path(sys.argv[3])
    defs = load_defs(task_instance_dir)
    actual = run_static_checks(str(workspace))
    rubrics = []
    for rid, result in actual.items():
        spec = defs.get(rid, {})
        max_score = float(spec.get("max_score", 1) or 1)
        passed = bool(result.get("passed"))
        rubrics.append(
            {
                "id": rid,
                "name": spec.get("name", rid),
                "dimension": spec.get("dimension", "quality"),
                "type": "deterministic",
                "passed": passed,
                "score": max_score if passed else 0.0,
                "max_score": max_score,
                "message": result.get("message", ""),
                "evidence": result.get("evidence", []),
            }
        )
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": {"phase": "static"}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
