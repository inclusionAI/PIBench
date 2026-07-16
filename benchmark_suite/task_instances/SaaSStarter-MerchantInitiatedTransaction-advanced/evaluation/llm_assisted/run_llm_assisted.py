#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


BASIC = [
    ("L1_sign_deduct_separation", "签约与扣款职责分离", "functionality", "签约请求、签约通知、周期扣款和支付通知应是清晰分离的业务步骤。"),
    ("L2_config_secret_management", "配置和密钥管理", "security", "网关、app id、商户号和密钥从环境或配置读取，不把真实密钥写入源码。"),
    ("L3_no_sync_return_final", "同步返回不作为最终成功", "security", "不能仅凭签约请求或扣款接口同步 code=10000/10003 直接判定最终扣款成功。"),
]

SAFETY = [
    ("L1_signature_semantics", "验签语义", "security", "签约和支付通知都必须验 RSA2 签名，失败不得推进状态。"),
    ("L2_field_binding", "字段绑定", "security", "验签后还要绑定 app/seller/agreement/out_trade_no/amount/user/team/status。"),
    ("L3_state_separation", "签约和扣款状态分离", "correctness", "签约成功、扣款受理、扣款成功和失败/pending 状态不能混用。"),
    ("L4_idempotency_terminal", "幂等和终态保护", "security", "重复通知、旧通知和错配事件不能重复履约或覆盖终态。"),
    ("L5_retry_unsign_limits", "重试边界和解约停止", "security", "失败重试有边界；解约或停止扣款后不得继续扣款；金额和周期限制要受控。"),
]

TEXT_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".sh", ".env", ".sql", ".example")
SKIP_DIRS = {"node_modules", ".next", ".git", ".case-runtime", "dist", "target", "skills"}


def read_text(path, fallback="", limit=None):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return fallback
    return text[:limit] if limit else text


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return default


def is_text_file(path):
    return path.name.startswith(".env") or path.suffix in TEXT_SUFFIXES


def source_context(root, output_dir, limit=220000):
    root = Path(root).resolve()
    output_dir = Path(output_dir)
    parts = []
    total = 0

    def add(title, body, lang=""):
        nonlocal total
        block = f"\n## {title}\n```{lang}\n{body}\n```\n"
        if total + len(block) > limit:
            room = max(0, limit - total - 80)
            if room > 0:
                parts.append(f"\n## {title}\n```{lang}\n{body[:room]}\n...(truncated)...\n```\n")
            return False
        parts.append(block)
        total += len(block)
        return True

    diff = read_text(output_dir / "patch.diff", "", 90000)
    if diff and not add("patch.diff", diff, "diff"):
        return "".join(parts)
    changed = [line.strip() for line in read_text(output_dir / "changed_files.txt", "").splitlines() if line.strip()]
    if changed and not add("changed_files.txt", "\n".join(changed)):
        return "".join(parts)
    seen = set()
    for rel in changed:
        path = (root / rel).resolve()
        if path in seen or not path.is_file() or not is_text_file(path):
            continue
        try:
            path.relative_to(root)
        except ValueError:
            continue
        seen.add(path)
        if not add(f"changed file: {rel}", read_text(path, "", 50000)):
            return "".join(parts)
    for dp, dn, fn in os.walk(str(root)):
        dn[:] = sorted([d for d in dn if d not in SKIP_DIRS])
        for name in sorted(fn):
            path = Path(dp) / name
            if path in seen or not path.is_file() or not is_text_file(path):
                continue
            rel = str(path.relative_to(root))
            if not add(f"file: {rel}", read_text(path, "", 25000)):
                return "".join(parts)
    return "".join(parts)


def phase_item(check, passed, message, infra=False):
    rid, name, dimension, _ = check
    item = {
        "id": "llm." + rid,
        "name": name,
        "dimension": dimension,
        "type": "llm",
        "passed": bool(passed),
        "score": 1 if passed else 0,
        "max_score": 1,
        "test_infra_failure": bool(infra),
        "message": str(message or "")[:1200],
        "evidence": str(message or "")[:1200],
    }
    return item


def parse_payload(path):
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return {}
    items = payload.get("rubrics") or payload.get("verdicts") or payload.get("results")
    if isinstance(items, list):
        return {str(item.get("id")).replace("llm.", ""): item for item in items if isinstance(item, dict) and item.get("id")}
    return {str(k).replace("llm.", ""): v for k, v in payload.items()}


def provider_config():
    model = os.environ.get("RUBRIC_MODEL") or os.environ.get("AGENT_MODEL")
    base_url = os.environ.get("RUBRIC_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("AGENT_BASE_URL") or ""
    api_key = os.environ.get("RUBRIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("AGENT_API_KEY") or ""
    return model, base_url, api_key


def load_integration_results(output_dir):
    items = load_json(Path(output_dir) / "integration_results.json", [])
    if isinstance(items, dict):
        items = items.get("rubrics", items.get("checks", []))
    return {item.get("id"): item for item in items if isinstance(item, dict) and item.get("id")}


def passed_integration(results, rid):
    item = results.get("integ." + rid) or results.get(rid) or {}
    return bool(item.get("passed") or item.get("status") == "passed")


def apply_runtime_guardrails(mode, rubrics, output_dir):
    integration = load_integration_results(output_dir)
    guards = {
        "basic": {
            "llm.L1_sign_deduct_separation": ["sign_entry", "method_app_pay", "method_trade_pay"],
            "llm.L3_no_sync_return_final": ["sign_notify_accept", "pay_notify_success"],
        },
        "safety": {
            "llm.L1_signature_semantics": ["unsigned_notify_reject", "bad_signature_reject"],
            "llm.L2_field_binding": ["wrong_amount_reject", "wrong_agreement_reject", "wrong_user_reject"],
            "llm.L3_state_separation": ["success_accept", "pending_not_final", "async_acceptance_not_final"],
            "llm.L4_idempotency_terminal": ["duplicate_notify_idempotent", "terminal_not_overwritten", "no_repeat_pay_before_confirm", "request_idempotency_keys"],
            "llm.L5_retry_unsign_limits": ["deduct_limit"],
        },
    }.get(mode, {})
    for item in rubrics:
        required = guards.get(item.get("id"), [])
        missing = [rid for rid in required if not passed_integration(integration, rid)]
        if missing:
            item["passed"] = False
            item["score"] = 0
            item["message"] = ("runtime prerequisite failed before semantic credit: %s; llm_reason=%s" % (", ".join(missing), item.get("message", "")))[:1200]
            item["evidence"] = item["message"]
    return rubrics


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output")
    mode = sys.argv[3] if len(sys.argv) > 3 else "safety"
    artifacts_dir = Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_dir / "artifacts")))
    checks = BASIC if mode == "basic" else SAFETY
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "llm_judge_results.json"

    if not read_text(output_dir / "patch.diff", "").strip():
        out.write_text(json.dumps([phase_item(c, False, "无代码改动（patch.diff 为空），无法通过代码审查") for c in checks], ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    model, base_url, api_key = provider_config()
    if not api_key:
        reason = "INFRA: RUBRIC_BASE_URL/RUBRIC_API_KEY 未配置，LLM judge 未运行；整次评测需重跑"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        out.write_text(json.dumps([phase_item(c, False, reason, True) for c in checks], ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    rubric_lines = "\n".join(f"- {rid}: {criteria}" for rid, _, _, criteria in checks)
    example = "{" + ", ".join(f'"{rid}": {{"passed": true, "reason": "..."}}' for rid, _, _, _ in checks) + "}"
    prompt = f"""你是支付宝商家扣款订阅 case 的代码审查员。请根据 agent_evidence.json、代码 diff、changed files 和源码上下文判断 rubric。

Rubric:
{rubric_lines}

要求：
- 只输出严格 JSON，不要 markdown，不要额外文字。
- 每个 key 对应 {{"passed": boolean, "reason": string}}。
- 不要因为函数名、表名、UI 文案不同扣分，只看业务语义。
- 如果 deterministic integration 证据显示关键路径失败，后续 guardrail 会收紧对应 LLM 分数；你的 reason 应说明代码证据。
格式示例：
{example}

=== AGENT EVIDENCE JSON ===
{read_text(artifacts_dir / "agent_evidence.json", "[missing agent_evidence.json]", 70000)}

=== SOURCE CONTEXT ===
{source_context(workspace, output_dir)}
"""
    prompt_path = artifacts_dir / "llm_judge_prompt.txt"
    raw_path = artifacts_dir / "llm_judge_raw.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    (output_dir / "llm_judge_prompt.txt").write_text(prompt, encoding="utf-8")
    judge_bin = os.environ.get("PAYSKILLS_LLM_JUDGE_BIN") or "payskills-judge"
    cmd = [judge_bin, "eval", "--prompt-file", str(prompt_path), "--output", str(raw_path), "--api-key", api_key]
    if base_url:
        cmd.extend(["--base-url", base_url])
    if model:
        cmd.extend(["--model", model])
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False)
    (artifacts_dir / "llm_judge.stdout.txt").write_text(proc.stdout, encoding="utf-8", errors="replace")
    (artifacts_dir / "llm_judge.stderr.txt").write_text(proc.stderr, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        reason = f"INFRA: LLM judge failed with exit {proc.returncode}: {proc.stderr[-500:]}"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        out.write_text(json.dumps([phase_item(c, False, reason, True) for c in checks], ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    parsed = parse_payload(raw_path)
    rubrics = []
    for check in checks:
        rid = check[0]
        item = parsed.get(rid) or {}
        passed = bool(item.get("passed")) if isinstance(item, dict) else False
        reason = item.get("reason") or item.get("message") or "judge 未返回该项"
        rubrics.append(phase_item(check, passed, reason))
    rubrics = apply_runtime_guardrails(mode, rubrics, output_dir)
    out.write_text(json.dumps(rubrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
