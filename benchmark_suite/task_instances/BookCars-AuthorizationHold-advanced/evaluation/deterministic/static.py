#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path
SUPPORT = Path(__file__).resolve().parent / "support"
STATIC_MAX = {
    "integ_notify_reject": 10,
    "notify_verify_fields": 5,
    "unique_id_check": 10,
    "close_cancel_boundary": 5,
    "secret_storage": 5,
    "secret_gitignore": 5,
    "preauth_pay_auth_no": 15,
    "preauth_freeze_amount": 5,
    "gateway_business_success_check": 5,
    "preauth_unfreeze_required": 15,
    "preauth_confirm_mode": 5,
    "preauth_init_poll_cancel": 10,
    "preauth_cancel_vs_unfreeze": 5,
}

def load_items(path, filename):
    src = Path(path) / filename
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("rubrics", data.get("checks", []))
    return []

def normalize(item, safety):
    rid = str(item.get("id") or "")
    if safety:
        max_score = float(STATIC_MAX.get(rid.lower(), item.get("score", 1) or 1))
        passed = bool(item.get("passed"))
        score = max_score if passed else 0.0
    else:
        max_score = float(item.get("max_score", 1) or 1)
        passed = bool(item.get("passed"))
        score = float(item.get("score", 1 if passed else 0) or 0)
    out = {
        "id": rid,
        "name": str(item.get("name") or rid),
        "dimension": str(item.get("dimension") or "quality"),
        "type": "deterministic",
        "passed": passed,
        "score": score,
        "max_score": max_score,
        "message": str(item.get("message") or item.get("evidence") or "")[:1000],
        "evidence": item.get("evidence", []),
    }
    if item.get("infra") or item.get("test_infra_failure"):
        out["test_infra_failure"] = True
    return out

def main():
    workspace, out, case_name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else ""
    scenario = os.environ.get("PAYSKILLS_SCENARIO", "")
    if scenario not in ("basic", "advanced"):
        raise ValueError("unsupported BookCars evaluation scenario: %r" % scenario)
    safety = scenario == "advanced"
    tmp = Path(tempfile.mkdtemp(prefix="bookcars-static-"))
    script = SUPPORT / "test_static.py"
    proc = subprocess.run([sys.executable, str(script), str(workspace), str(tmp)], check=False)
    items = [normalize(item, safety) for item in load_items(tmp, "static_results.json") if isinstance(item, dict) and item.get("id")]
    out.write_text(json.dumps({"rubrics": items, "metadata": {"phase": "static", "legacy_exit_code": proc.returncode}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
