#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORT = Path(__file__).resolve().parent / "support"
META = {
    "a2m_security_runtime": ("服务可构建启动", "functionality"),
    "a2m_no_proof_reject": ("无凭证拒绝访问", "security"),
    "a2m_invalid_proof_reject": ("无效/不可解析凭证拒绝访问", "security"),
    "a2m_verify_fail_closed": ("验证异常默认拒绝（fail-closed）", "security"),
    "a2m_valid_proof_delivers": ("有效 proof 可交付且经过 verify/confirm", "functionality"),
    "a2m_cross_resource_reject": ("跨资源 proof 拒绝", "security"),
    "a2m_amount_mismatch_reject": ("金额不匹配 proof 拒绝", "security"),
    "a2m_confirm_failure_no_deliver": ("履约确认失败不交付", "security"),
    "a2m_client_tamper_reject": ("客户端支付状态字段篡改拒绝", "security"),
    "a2m_replay_proof_idempotent": ("重复 proof 幂等安全", "security"),
    "a2m_identity_mismatch_reject": ("凭证归属不匹配拒绝", "security"),
    "a2m_gateway_error_fail_closed": ("外部确认异常默认拒绝", "security"),
    "a2m_expired_proof_reject": ("过期 proof 拒绝", "security"),
}


def fallback_item(rid, message):
    name, dimension = META[rid]
    return {"id": "integration.%s" % rid, "name": name, "dimension": dimension, "type": "deterministic", "passed": False, "score": 0.0, "max_score": 1.0, "message": message, "evidence": ["build.log", "server.log"]}


def normalize(item):
    rid = str(item.get("id") or "")
    name, dimension = META.get(rid, (rid, "quality"))
    passed = bool(item.get("passed"))
    return {
        "id": "integration.%s" % rid,
        "name": str(item.get("name") or name),
        "dimension": dimension,
        "type": "deterministic",
        "passed": passed,
        "score": 1.0 if passed else 0.0,
        "max_score": 1.0,
        "message": str(item.get("message") or ""),
        "evidence": item.get("evidence", []),
    }


def main():
    base, out = sys.argv[1].rstrip("/"), Path(sys.argv[2])
    raw = Path(tempfile.mkstemp(prefix="a2m-safety-integration-", suffix=".json")[1])
    proc = subprocess.run([sys.executable, str(SUPPORT / "legacy_integration.py"), base, str(raw)], check=False)
    try:
        payload = json.loads(raw.read_text(encoding="utf-8"))
    except Exception:
        payload = {"checks": []}
    finally:
        raw.unlink(missing_ok=True)
    checks = payload.get("checks", payload if isinstance(payload, list) else []) if isinstance(payload, (dict, list)) else []
    rubrics = [normalize(item) for item in checks if isinstance(item, dict) and item.get("id")]
    if not rubrics:
        rubrics = [fallback_item(rid, "服务未构建/启动成功，集成测试无法运行（见 build.log / server.log）") for rid in META]
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": {"phase": "integration", "legacy_exit_code": proc.returncode}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
