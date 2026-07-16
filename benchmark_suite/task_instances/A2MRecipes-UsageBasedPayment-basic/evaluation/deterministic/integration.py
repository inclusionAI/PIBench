#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORT = Path(__file__).resolve().parent / "support"
META = {
    "a2m_dep_sdk": ("S1 接入支付客户端能力", "functionality"),
    "a2m_public_list_unchanged": ("I2 食谱列表仍公开", "compatibility"),
    "a2m_402_challenge": ("I3 无凭证返回 402 且不泄露内容", "functionality"),
    "a2m_payment_needed_header": ("I4 Payment-Needed 可被客户端使用", "functionality"),
    "a2m_verify_proof": ("I5 服务端调用网关验证凭证", "security"),
    "a2m_verify_challenge_binding": ("I5b 验证绑定本次支付请求", "security"),
    "a2m_release_resource": ("I6 验证成功后返回完整资源", "functionality"),
    "a2m_confirm_fulfillment": ("I7 履约成功后确认", "functionality"),
    "a2m_payment_challenge_shape": ("U1 支付要求结构完整", "functionality"),
    "a2m_multi_resource_basic": ("I8 多个付费资源均受保护", "functionality"),
    "a2m_multi_resource_release": ("I9 多资源验证成功后可交付", "functionality"),
    "a2m_verify_failure_rejects": ("U2 验证失败 fail-closed", "security"),
    "a2m_ambiguous_verify_rejects": ("U3 状态不明确时 fail-closed", "security"),
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
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(sys.argv[1])
    raw = Path(tempfile.mkstemp(prefix="a2m-basic-integration-", suffix=".json")[1])
    proc = subprocess.run([sys.executable, str(SUPPORT / "legacy_integration_test.py"), str(raw)], check=False)
    try:
        payload = json.loads(raw.read_text(encoding="utf-8"))
    except Exception:
        payload = []
    finally:
        raw.unlink(missing_ok=True)
    rubrics = [normalize(item) for item in payload if isinstance(item, dict) and item.get("id")]
    if proc.returncode != 0 and not rubrics:
        rubrics = [
            {"id": rid, "name": name, "dimension": dim, "type": "deterministic", "passed": False, "score": 0.0, "max_score": 1.0, "message": "legacy integration check crashed", "evidence": ["logs/test_output.txt"]}
            for rid, (name, dim) in META.items()
        ]
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": {"phase": "integration", "legacy_exit_code": proc.returncode}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
