#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

SUPPORT = Path(__file__).resolve().parent / "support"
sys.path.insert(0, str(SUPPORT))

from integration_checks import run_integration_checks  # noqa: E402


def load_defs(task_instance_dir: Path):
    payload = json.loads((task_instance_dir / "evaluation" / "rubrics.json").read_text(encoding="utf-8"))
    return [item for item in payload.get("rubrics", []) if item.get("type") == "deterministic" and item.get("id", "").startswith("wap_") and item.get("id") not in {"wap_dep_sdk", "wap_config_env", "wap_secret_safe", "wap_stable_endpoint"}]


def phase_item(spec, result=None, infra_message=None):
    max_score = float(spec.get("max_score", 1) or 1)
    if infra_message is not None:
        return {
            "id": spec["id"],
            "name": spec.get("name", spec["id"]),
            "dimension": spec.get("dimension", "quality"),
            "type": "deterministic",
            "passed": False,
            "score": 0.0,
            "max_score": max_score,
            "message": infra_message,
            "test_infra_failure": True,
        }
    result = result or {}
    passed = bool(result.get("passed"))
    item = {
        "id": spec["id"],
        "name": spec.get("name", spec["id"]),
        "dimension": spec.get("dimension", "quality"),
        "type": "deterministic",
        "passed": passed,
        "score": max_score if passed else 0.0,
        "max_score": max_score,
        "message": result.get("message", ""),
    }
    if result.get("evidence"):
        item["evidence"] = result["evidence"]
    if result.get("infra_failure"):
        item["test_infra_failure"] = True
        item["passed"] = False
        item["score"] = 0.0
    return item


def main():
    out = Path(sys.argv[1])
    task_instance_dir = Path(sys.argv[2])
    app_started = sys.argv[3].lower() == "true"
    base_url = os.environ.get("EDOC_BASE_URL", "http://localhost:8136")
    specs = load_defs(task_instance_dir)
    if not app_started:
        rubrics = [phase_item(spec, infra_message="app under test failed to start (infra); counted as failed") for spec in specs]
    else:
        actual = run_integration_checks(base_url)
        rubrics = [phase_item(spec, actual.get(spec["id"])) for spec in specs]
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": {"phase": "integration", "app_started": app_started}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
