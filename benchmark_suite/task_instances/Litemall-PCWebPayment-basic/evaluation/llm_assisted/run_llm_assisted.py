#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


CHECKS = {
    "L1": "SDK 调用模式：下单/prepay 方法使用支付宝 SDK 的页面支付请求类，并通过 SDK 的表单生成方法生成支付表单，而不是自己拼 URL 或直接发 HTTP 请求调用支付宝网关。",
    "L2": "前端表单提交：前端在用户选择支付宝支付后调用后端 prepay 接口，将返回的 HTML 表单插入 DOM 并自动 submit 跳转收银台。",
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
    item = {
        "id": rid,
        "name": CHECKS[rid].split("：", 1)[0],
        "dimension": "functionality",
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


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output")
    artifacts_dir = Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_dir / "artifacts")))
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "llm_judge_results.json"

    diff = read_text(artifacts_dir / "patch.diff", read_text(output_dir / "patch.diff", ""), 70000)
    if not diff.strip():
        out.write_text(json.dumps([phase_item(rid, False, "no code changes available for review") for rid in CHECKS], ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    model, base_url, api_key = provider_config()
    if not api_key:
        reason = "INFRA: RUBRIC_API_KEY/ANTHROPIC_API_KEY not set"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        out.write_text(json.dumps([phase_item(rid, False, reason, True) for rid in CHECKS], ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    rubric_lines = "\n".join(f"- {rid}: {text}" for rid, text in CHECKS.items())
    prompt = f"""你是一名资深 Java/Vue 代码评审员。一个 AI 编码 agent 刚刚在 litemall 电商系统中接入了支付宝电脑网站支付。请根据下面的代码变更和 agent_evidence.json，对审查点逐项判定是否通过。

审查点：
{rubric_lines}

判定要求：
- 只根据给出的代码证据判断，证据不足时判 false 并说明缺什么。
- 不要因为代码风格、注释、异常处理等额外因素扣分；只判定审查点本身。
- 这些审查点只评价 SDK 调用和前端表单提交的代码模式，不评价接口路由是否可访问、返回表单是否绑定真实订单或浏览器是否实际跳转；这些运行正确性由 deterministic evaluation 判定。
- 必须输出严格 JSON 对象，不要 markdown，不要额外文字，格式：
{{"L1": {{"passed": true, "reason": "..."}}, "L2": {{"passed": false, "reason": "..."}}}}

=== AGENT EVIDENCE JSON ===
{read_text(artifacts_dir / "agent_evidence.json", "[missing agent_evidence.json]", 60000)}

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
    rubrics = []
    for rid in CHECKS:
        item = parsed.get(rid) or {}
        passed = bool(item.get("passed")) if isinstance(item, dict) else False
        reason = item.get("reason") or item.get("message") or "judge 未返回该项"
        rubrics.append(phase_item(rid, passed, reason))
    out.write_text(json.dumps(rubrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
