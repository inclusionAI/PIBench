#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

L_RUBRICS = {
    "L1": "llm.wap_no_fake_bypass",
    "L2": "llm.wap_query_compensation",
    "L3": "llm.wap_amount_accounting_rule",
}

KEY_FILES = [
    "lib/payment_repository.php",
    "lib/alipay_h5.php",
    "alipay/h5/notify.php",
    "patient/alipay-h5/return.php",
    "patient/alipay-h5/quit.php",
    "patient/alipay-h5/sync.php",
    "patient/alipay-h5/payment.php",
    "admin/alipay-h5/refund.php",
    "admin/alipay-h5/refund-query.php",
]

PROMPT = """你是支付资金安全方向的资深代码审查员。下面是一个 PHP 医生预约系统支付宝 H5 支付链路加固后的关键源码、改动 diff、hard evidence 和 agent_evidence.json。
请基于代码本身判断以下三条审查项是否通过，只看实现，不要臆测。

[L1] 无支付/通知/退款绕过：不存在"固定成功 / 无条件验签 / return_url 直接 paid / 退款不校验资金变更"等绕过。
[L2] 未知状态补偿：支付或退款的未知/处理中状态有查询、重试或人工处理路径，不会武断地直接成功或失败。
[L3] 金额口径：应付(amount)、实付(paid_amount)、已退(refunded_amount)、可退、部分退款不会混用单一金额字段。

硬证据优先：
- 如果 static.wap_no_fake_bypass 已失败，L1 原则上不能通过；除非源码能明确证明 static 是误报。
- 如果集成测试暴露了通知验签、return/quit、退款资金变更或终态保护失败，对应 L 项不能继续给通过。

请只输出 JSON，格式：
{"l1":{"passed":true/false,"reason":"..."},"l2":{"passed":true/false,"reason":"..."},"l3":{"passed":true/false,"reason":"..."}}

=== hard/static evidence ===
{evidence}

=== agent_evidence.json ===
{agent_evidence}

=== 关键源码 ===
{code}

=== 改动 diff（节选）===
{diff}
"""


def read_text(path, fallback="", limit=None):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return fallback
    return text[:limit] if limit else text


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def read_key_files(workspace: Path):
    parts = []
    for rel in KEY_FILES:
        path = workspace / rel
        if path.is_file():
            parts.append(f"----- FILE: {rel} -----\n{read_text(path)}")
    return "\n\n".join(parts)[:60000]


def evidence_summary(output_dir: Path):
    payload = {}
    for name in ["static_results.json", "integration_results.json"]:
        path = output_dir / "checks" / name
        if path.exists():
            payload[name] = load_json(path, {})
    junit = output_dir / "pytest_junit.xml"
    if junit.exists():
        payload["pytest_junit_xml_excerpt"] = read_text(junit, limit=12000)
    return json.dumps(payload, ensure_ascii=False, indent=2)[:20000], payload.get("static_results.json", {})


def phase_item(rid, spec, passed, message, infra=False):
    item = {
        "id": rid,
        "name": spec.get("name", rid),
        "dimension": spec.get("dimension", "quality"),
        "type": "llm_assisted",
        "passed": bool(passed),
        "score": float(spec.get("max_score", 1) or 1) if passed else 0.0,
        "max_score": float(spec.get("max_score", 1) or 1),
        "message": str(message or "")[:1000],
        "evidence": ["llm_judge_prompt.txt", "llm_judge_raw.json", "agent_evidence.json", "patch.diff"],
    }
    if infra:
        item["test_infra_failure"] = True
    return item


def load_llm_defs(task_instance_dir: Path):
    payload = load_json(task_instance_dir / "evaluation" / "rubrics.json", {"rubrics": []})
    return {item["id"]: item for item in payload.get("rubrics", []) if item.get("group") == "llm"}


def write_phase(out: Path, rubrics, metadata=None):
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": metadata or {}}, ensure_ascii=False, indent=2), encoding="utf-8")


def infra_results(defs, reason):
    return [phase_item(rid, defs.get(rid, {}), False, reason, True) for rid in L_RUBRICS.values()]


def parse_judge_payload(path: Path):
    payload = load_json(path, {})
    if isinstance(payload, dict):
        items = payload.get("rubrics") or payload.get("verdicts") or payload.get("results")
        if isinstance(items, list):
            return {str(x.get("id")): x for x in items if isinstance(x, dict) and x.get("id")}
        return payload
    return {}


def main():
    workspace = Path(sys.argv[1])
    out = Path(sys.argv[2])
    task_instance_dir = Path(sys.argv[3])
    output_dir = Path(os.environ.get("OUTPUT_DIR", str(out.parent.parent)))
    artifacts_dir = Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_dir / "artifacts")))
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    defs = load_llm_defs(task_instance_dir)

    if not (os.environ.get("RUBRIC_BASE_URL") and os.environ.get("RUBRIC_API_KEY")):
        reason = "missing RUBRIC_BASE_URL/RUBRIC_API_KEY; judge not configured"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, infra_results(defs, reason), {"phase": "llm", "test_infra_failure": True})
        return 0

    evidence, static_payload = evidence_summary(output_dir)
    prompt = (
        PROMPT.replace("{evidence}", evidence)
        .replace("{agent_evidence}", read_text(artifacts_dir / "agent_evidence.json", "[missing agent_evidence.json]", 80000))
        .replace("{code}", read_key_files(workspace))
        .replace("{diff}", read_text(artifacts_dir / "patch.diff", "[missing patch.diff]", 40000))
    )
    prompt_path = artifacts_dir / "llm_judge_prompt.txt"
    raw_path = artifacts_dir / "llm_judge_raw.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    (output_dir / "llm_judge_prompt.txt").write_text(prompt, encoding="utf-8")

    judge_bin = os.environ.get("PAYSKILLS_LLM_JUDGE_BIN") or "payskills-judge"
    proc = subprocess.run(
        [judge_bin, "eval", "--prompt-file", str(prompt_path), "--output", str(raw_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    (artifacts_dir / "llm_judge.stdout.txt").write_text(proc.stdout, encoding="utf-8", errors="replace")
    (artifacts_dir / "llm_judge.stderr.txt").write_text(proc.stderr, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        reason = f"judge failed after retries: {proc.stderr[-500:]}"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, infra_results(defs, reason), {"phase": "llm", "test_infra_failure": True})
        return 0

    parsed = parse_judge_payload(raw_path)
    rubrics = []
    for spec_id, rid in L_RUBRICS.items():
        entry = parsed.get(spec_id.lower()) or parsed.get(spec_id) or {}
        passed = bool(entry.get("passed")) if isinstance(entry, dict) else False
        reason = entry.get("reason") or entry.get("message") or "(no reason)" if isinstance(entry, dict) else "judge did not return this item"
        rubrics.append(phase_item(rid, defs.get(rid, {}), passed, reason))

    static_by_id = {item.get("id"): item for item in static_payload.get("rubrics", []) if isinstance(item, dict)}
    bypass_static = static_by_id.get("static.wap_no_fake_bypass")
    if bypass_static and not bypass_static.get("passed"):
        static_msg = str(bypass_static.get("message", ""))[:350]
        for index, item in enumerate(rubrics):
            if item["id"] == "llm.wap_no_fake_bypass":
                item["passed"] = False
                item["score"] = 0.0
                item["message"] = ("hard/static evidence failed static.wap_no_fake_bypass: " + static_msg)[:1000]
                rubrics[index] = item
                break

    write_phase(out, rubrics, {"phase": "llm", "llm_judge_backend": "payskills-judge"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
