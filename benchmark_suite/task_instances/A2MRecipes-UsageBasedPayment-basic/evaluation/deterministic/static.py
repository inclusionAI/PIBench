#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORT = Path(__file__).resolve().parent / "support"
META = {
    "a2m_config_env": ("S2 支付配置来自运行时配置", "security"),
    "a2m_secret_safe": ("S3 不提交真实密钥", "security"),
    "a2m_stable_endpoint": ("S4 保留固定 API 入口", "compatibility"),
}


def normalize(item):
    rid = str(item.get("id") or "")
    name, dimension = META.get(rid, (rid, "quality"))
    passed = bool(item.get("passed"))
    return {
        "id": rid,
        "name": str(item.get("name") or name),
        "dimension": str(item.get("dimension") or dimension),
        "type": "deterministic",
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "max_score": 1.0,
        "message": str(item.get("message") or ""),
        "evidence": item.get("evidence", []),
    }


def main():
    workspace = Path(sys.argv[1])
    out = Path(sys.argv[2])
    raw = Path(tempfile.mkstemp(prefix="a2m-basic-static-", suffix=".json")[1])
    proc = subprocess.run([sys.executable, str(SUPPORT / "legacy_static_checks.py"), str(workspace), str(raw)], check=False)
    try:
        payload = json.loads(raw.read_text(encoding="utf-8"))
    except Exception:
        payload = []
    finally:
        raw.unlink(missing_ok=True)
    rubrics = [normalize(item) for item in payload if isinstance(item, dict) and item.get("id")]
    if proc.returncode != 0 and not rubrics:
        rubrics = [
            {"id": rid, "name": name, "dimension": dim, "type": "deterministic", "passed": False, "score": 0.0, "max_score": 1.0, "message": "legacy static check crashed", "evidence": ["logs/test_output.txt"]}
            for rid, (name, dim) in META.items()
        ]
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": {"phase": "static", "legacy_exit_code": proc.returncode}}, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in rubrics:
        print("[static] %-30s %s  %s" % (r["id"], "PASS" if r["passed"] else "FAIL", r["message"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
