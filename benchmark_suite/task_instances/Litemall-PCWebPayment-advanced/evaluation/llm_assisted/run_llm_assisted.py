#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


CHECKS = {
    "L1_notify_signature": ("异步通知验签", "异步通知入口使用支付宝 SDK 验签能力校验 RSA2 签名；验签失败时返回 failure/错误响应，且不会推进订单状态。", "security"),
    "L2_notify_field_validation": ("异步通知关键字段校验", "验签通过后还校验 app_id、out_trade_no 对应订单存在、total_amount 与订单实付金额一致，并且只把 TRADE_SUCCESS 作为首次支付成功。", "security"),
    "L3_notify_idempotency_terminal": ("通知幂等与终态保护", "重复成功通知不会重复扣减库存/重复写副作用；已支付等终态订单不会被 TRADE_CLOSED、失败或其他通知降级。", "correctness"),
    "L4_return_url_query_compensation": ("return_url 不履约与查询补偿", "同步 return_url 只用于展示或触发查询，不直接把订单置为已支付；系统提供支付查询能力确认支付结果。", "security"),
    "L5_refund_request_no": ("退款请求号与部分退款", "退款调用支付宝退款能力；使用 out_request_no 表示退款请求，同一次重试保持相同 out_request_no，不同部分退款使用不同 out_request_no，并校验可退金额。", "correctness"),
    "L6_refund_query_uncertain": ("退款查询与不确定状态处理", "实现退款查询能力；退款结果未知、超时或处理中时，不会固定判成功/失败，而是通过查询、重试、保持 pending 或人工处理路径确认。", "correctness"),
    "L7_close_paid_boundary": ("关单与已支付边界", "未支付订单关闭调用支付宝关单能力；已支付订单不会被关闭，只能走退款或保持已支付状态；关闭后的订单号不会再次用于发起支付。", "correctness"),
    "L8_secret_management": ("密钥管理", "支付宝完整私钥/公钥等密钥材料不能硬编码在 Java/Vue 源码或提交的配置默认值中；本地敏感配置有 .gitignore 或等价机制避免提交。", "security"),
}


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


def phase_item(rid, passed, message, infra=False):
    name, _, dimension = CHECKS[rid]
    item = {
        "id": rid,
        "name": name,
        "dimension": dimension,
        "type": "llm",
        "passed": bool(passed),
        "score": 1 if passed else 0,
        "max_score": 1,
        "message": str(message or "")[:1000],
        "invalid": False,
        "evidence": str(message or "")[:1000],
    }
    if infra:
        item["infra"] = True
    return item


def parse_payload(path):
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return {}
    items = payload.get("rubrics") or payload.get("verdicts") or payload.get("results")
    if isinstance(items, list):
        return {str(item.get("id")): item for item in items if isinstance(item, dict) and item.get("id")}
    return payload


def provider_config():
    model = os.environ.get("RUBRIC_MODEL") or os.environ.get("AGENT_MODEL")
    base_url = (
        os.environ.get("RUBRIC_BASE_URL")
        or os.environ.get("ANTHROPIC_BASE_URL")
        or os.environ.get("AGENT_BASE_URL")
        or ""
    )
    api_key = (
        os.environ.get("RUBRIC_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("AGENT_API_KEY")
        or ""
    )
    return model, base_url, api_key


def hard_evidence(output_dir):
    lines = []
    for name in ("static_results.json", "integration_results.json"):
        data = load_json(output_dir / name, [])
        items = data if isinstance(data, list) else data.get("rubrics", data.get("checks", []))
        for item in items:
            rid = str(item.get("id") or "")
            if not rid.startswith(("static.", "integ.")):
                continue
            status = "PASS" if item.get("passed") else "FAIL"
            msg = str(item.get("message", ""))[:500].replace("\n", " ")
            lines.append(f"- {rid}: {status}; {msg}")
    return "\n".join(lines[:120]) or "[NO STATIC/INTEGRATION EVIDENCE AVAILABLE]"


def static_secret_failure(output_dir):
    data = load_json(output_dir / "static_results.json", [])
    items = data if isinstance(data, list) else data.get("rubrics", data.get("checks", []))
    failures = []
    for item in items:
        if item.get("id") in {"static.secret_no_hardcode", "static.secret_gitignore"} and not item.get("passed"):
            failures.append(f"{item.get('id')}: {item.get('message', '')}")
    return "; ".join(failures)[:1000]


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output")
    artifacts_dir = Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_dir / "artifacts")))
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "llm_judge_results.json"

    diff = read_text(artifacts_dir / "patch.diff", read_text(output_dir / "patch.diff", ""), 90000)
    if not diff.strip():
        out.write_text(json.dumps([phase_item(rid, False, "no code changes available for review") for rid in CHECKS], ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    model, base_url, api_key = provider_config()
    if not api_key:
        reason = "INFRA: RUBRIC_API_KEY/ANTHROPIC_API_KEY not set"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        out.write_text(json.dumps([phase_item(rid, False, reason, True) for rid in CHECKS], ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    rubric_lines = "\n".join(f"- {rid}（{name}）：{criteria}" for rid, (name, criteria, _) in CHECKS.items())
    example = "{\n" + ",\n".join(f'  "{rid}": {{"passed": true, "reason": "一句中文理由"}}' for rid in CHECKS) + "\n}"
    prompt = f"""你是支付宝电脑网站支付安全接入的代码审查员。请只根据下面的 agent_evidence.json、agent diff 和 deterministic evidence，判断 litemall advanced/safety case 的 8 个 rubric 是否通过。

这个 case 的 starter 已具备基础支付链路，agent 的任务是加固异步通知、退款、查询补偿、关单和密钥管理。允许测试环境 mock 网关、沙箱密钥、不同但合理的内部 service 分层；外部可测接口以 instruction 中的 query/refund/close 契约为准。不要因为内部命名、注释、代码风格、前端未改动而扣分。边界按宽松、业务可接受判断，但不能接受固定成功、跳过验签、直接信任客户端结果、明显放过篡改通知。

审查点：
{rubric_lines}

判定要求：
- 只根据代码证据和 hard static/integration evidence 判断，证据不足时判 false 并说明缺什么。
- hard static/integration evidence 是实际运行证据；当它证明某条关键路径失败时，不要仅凭代码里出现了校验分支就判通过。
- 如果实现方式与示例类名不同，但语义等价且业务上可接受，可以判 true。
- 必须输出严格 JSON 对象，不要 markdown，不要额外文字，格式：
{example}

=== DETERMINISTIC EVIDENCE ===
{hard_evidence(output_dir)}

=== AGENT EVIDENCE JSON ===
{read_text(artifacts_dir / "agent_evidence.json", "[missing agent_evidence.json]", 70000)}

=== DIFF ===
{diff}
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
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    (artifacts_dir / "llm_judge.stdout.txt").write_text(proc.stdout, encoding="utf-8", errors="replace")
    (artifacts_dir / "llm_judge.stderr.txt").write_text(proc.stderr, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        reason = f"INFRA: LLM judge failed with exit {proc.returncode}: {proc.stderr[-500:]}"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        out.write_text(json.dumps([phase_item(rid, False, reason, True) for rid in CHECKS], ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    parsed = parse_payload(raw_path)
    secret_failure = static_secret_failure(output_dir)
    rubrics = []
    for rid in CHECKS:
        item = parsed.get(rid) or {}
        passed = bool(item.get("passed")) if isinstance(item, dict) else False
        reason = item.get("reason") or item.get("message") or "judge 未返回该项"
        if rid == "L8_secret_management" and secret_failure:
            passed = False
            reason = "hard static evidence failed: " + secret_failure
        rubrics.append(phase_item(rid, passed, reason))
    out.write_text(json.dumps(rubrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
