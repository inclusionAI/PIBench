#!/usr/bin/env python3
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SUPPORT = Path(__file__).resolve().parent / "support"


def load_defs(task_instance_dir: Path):
    payload = json.loads((task_instance_dir / "evaluation" / "rubrics.json").read_text(encoding="utf-8"))
    return [item for item in payload.get("rubrics", []) if item.get("group") == "integration"]


def parse_junit(path: Path):
    results = {}
    if not path.is_file():
        return results
    try:
        tree = ET.parse(str(path))
    except Exception:
        return results
    for testcase in tree.iter("testcase"):
        name = testcase.get("name", "")
        failure = testcase.find("failure")
        error = testcase.find("error")
        skipped = testcase.find("skipped")
        if failure is not None or error is not None:
            node = failure if failure is not None else error
            results[name] = (False, (node.get("message") or "test failed")[:500])
        elif skipped is not None:
            results[name] = (False, "test skipped")
        else:
            results[name] = (True, "")
    return results


def rubric_from_spec(spec, junit, app_started):
    max_score = float(spec.get("max_score", 1) or 1)
    if not app_started:
        return {
            "id": spec["id"],
            "name": spec.get("name", spec["id"]),
            "dimension": spec.get("dimension", "quality"),
            "type": "deterministic",
            "passed": False,
            "score": 0.0,
            "max_score": max_score,
            "message": "app under test failed to start (infra); counted as failed",
            "test_infra_failure": True,
        }
    test_name = spec.get("test")
    result = junit.get(test_name)
    if result is None:
        return {
            "id": spec["id"],
            "name": spec.get("name", spec["id"]),
            "dimension": spec.get("dimension", "quality"),
            "type": "deterministic",
            "passed": False,
            "score": 0.0,
            "max_score": max_score,
            "message": f"integration test '{test_name}' produced no result (pytest crash/missing); counted as failed",
            "test_infra_failure": True,
        }
    passed, message = result
    return {
        "id": spec["id"],
        "name": spec.get("name", spec["id"]),
        "dimension": spec.get("dimension", "quality"),
        "type": "deterministic",
        "passed": passed,
        "score": max_score if passed else 0.0,
        "max_score": max_score,
        "message": message,
        "evidence": ["pytest_junit.xml", "php_server.log"],
    }


def main():
    out = Path(sys.argv[1])
    task_instance_dir = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    app_started = sys.argv[4].lower() == "true"
    specs = load_defs(task_instance_dir)
    junit_path = output_dir / "pytest_junit.xml"
    if app_started:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(SUPPORT),
                "-p",
                "no:cacheprovider",
                "-o",
                "cache_dir=/tmp/pytest_cache",
                f"--junitxml={junit_path}",
                "-v",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    junit = parse_junit(junit_path)
    rubrics = [rubric_from_spec(spec, junit, app_started) for spec in specs]
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": {"phase": "integration", "app_started": app_started}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
