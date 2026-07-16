#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path
SUPPORT = Path(__file__).resolve().parent / "support"
PHASE = "integration"
SCRIPT = "test_integration.py"
OUTFILE = "integration_results.json"

def load_items(path):
    src = Path(path) / OUTFILE
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("rubrics") or data.get("checks") or []
    return []

def normalize(item):
    passed = bool(item.get("passed"))
    max_score = float(item.get("max_score", 1) or 1)
    score = float(item.get("score", 1 if passed else 0) or 0)
    out = {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or item.get("id") or ""),
        "dimension": str(item.get("dimension") or "quality"),
        "type": "deterministic",
        "passed": passed,
        "score": score,
        "max_score": max_score,
        "message": str(item.get("message") or "")[:1000],
        "evidence": item.get("evidence", []),
    }
    if item.get("infra") or item.get("test_infra_failure"):
        out["test_infra_failure"] = True
    return out

def main():
    workspace = Path(sys.argv[1])
    out = Path(sys.argv[2])
    case_name = sys.argv[3] if len(sys.argv) > 3 else ""
    extra = sys.argv[4:]
    tmp = Path(tempfile.mkdtemp(prefix="bookcars-" + PHASE + "-"))
    for name in ["test_booking_id.txt", "test_ids.json"]:
        src = Path(os.environ.get("OUTPUT_DIR", str(out.parent.parent))) / name
        if src.exists():
            (tmp / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    cmd = [sys.executable, str(SUPPORT / SCRIPT), str(workspace), str(tmp)] + extra
    proc = subprocess.run(cmd, check=False)
    items = [normalize(item) for item in load_items(tmp) if isinstance(item, dict) and item.get("id")]
    out.write_text(json.dumps({"rubrics": items, "metadata": {"phase": PHASE, "legacy_exit_code": proc.returncode}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
