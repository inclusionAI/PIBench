#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORT = Path(__file__).resolve().parent / "support"


def load_defs(task_instance_dir: Path):
    payload = json.loads((task_instance_dir / "evaluation" / "rubrics.json").read_text(encoding="utf-8"))
    return {item["id"]: item for item in payload.get("rubrics", []) if item.get("group") == "static"}


def main():
    workspace = Path(sys.argv[1])
    out = Path(sys.argv[2])
    task_instance_dir = Path(sys.argv[3])
    defs = load_defs(task_instance_dir)
    tmp = Path(tempfile.mkdtemp(prefix="edoc-static-")) / "static_results.json"
    proc = subprocess.run([sys.executable, str(SUPPORT / "static_checks.py"), str(workspace), str(tmp)], check=False)
    try:
        actual = json.loads(tmp.read_text(encoding="utf-8"))
    except Exception:
        actual = {}
    rubrics = []
    for rid, spec in defs.items():
        result = actual.get(rid)
        max_score = float(spec.get("max_score", 1) or 1)
        if result is None:
            rubrics.append(
                {
                    "id": rid,
                    "name": spec.get("name", rid),
                    "dimension": spec.get("dimension", "quality"),
                    "type": "deterministic",
                    "passed": False,
                    "score": 0.0,
                    "max_score": max_score,
                    "message": "static check produced no result (infra); counted as failed",
                    "test_infra_failure": True,
                }
            )
            continue
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
            }
        )
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": {"phase": "static", "legacy_exit_code": proc.returncode}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
