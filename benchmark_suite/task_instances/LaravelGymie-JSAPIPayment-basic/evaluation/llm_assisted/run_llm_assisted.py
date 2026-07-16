#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


RUBRICS = [
    ("judge.jsapi_dep_sdk", "接入真实客户端能力", "代码没有用固定交易号、固定成功结果或本地伪造响应代替真实的支付宝交易创建调用；tradeNO 来自网关响应而不是本地随机数/常量。"),
    ("judge.logic_api", "JSAPI 产品参数正确", "实现符合支付宝小程序内支付（JSAPI）语义：使用 alipay.trade.create + product_code=JSAPI_PAY + op_app_id + buyer 标识，没有误用 wap/page/app 支付链路。"),
    ("judge.jsapi_secret_safe", "密钥处理安全", "没有把私钥、公钥、证书内容硬编码进源码；密钥通过文件路径/环境变量引用。"),
    ("judge.jsapi_provider_model", "支付状态与交易标识可持久化", "订单或支付记录中有可持久化的支付平台交易标识、商户订单号和支付完成状态；支付成功与会员履约不是只保存在临时变量、前端状态或一次性响应里。"),
    ("judge.jsapi_stable_endpoint", "保留固定接口入口", "支付接入挂在 POST /api/membership-checkout/orders 上，订单查询仍是 GET /api/membership-checkout/orders/{checkout_no}，没有绕开固定入口另起一套 API 替代原流程。"),
]


def read_text(path, fallback="", limit=None):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return fallback
    return text[:limit] if limit else text


def gather_snippets(workspace: Path):
    paths = [
        "routes/api.php",
        "routes/web.php",
        "app/Http/Controllers/MembershipCheckoutController.php",
        "app/Models/MembershipCheckoutOrder.php",
        "app/Models/Payment.php",
        "database/migrations",
        "miniapp/pages/membership/index.js",
    ]
    chunks = []
    for rel in paths:
        path = workspace / rel
        if path.is_dir():
            for child in sorted(path.iterdir())[:20]:
                if child.is_file() and child.name.endswith(".php"):
                    chunks.append(f"--- {rel}/{child.name} ---\n{read_text(child, limit=4000)}")
        elif path.exists():
            chunks.append(f"--- {rel} ---\n{read_text(path, limit=8000)}")
    return "\n\n".join(chunks)


def phase_item(rid, name, passed, message, infra=False):
    item = {
        "id": rid,
        "name": name,
        "dimension": "code_quality",
        "type": "llm_judge",
        "passed": bool(passed),
        "score": 1 if passed else 0,
        "max_score": 1,
        "message": str(message or "")[:1000],
        "evidence": ["llm_judge_prompt.txt", "llm_judge_raw.json", "agent_evidence.json", "patch.diff"],
    }
    if infra:
        item["test_infra_failure"] = True
        item["infra"] = True
    return item


def write_results(output_dir: Path, rubrics, metadata=None):
    (output_dir / "llm_judge.json").write_text(json.dumps(rubrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "llm_judge_phase.json").write_text(json.dumps({"rubrics": rubrics, "metadata": metadata or {}}, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_payload(path: Path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        items = payload.get("results") or payload.get("rubrics") or payload.get("verdicts")
        if isinstance(items, list):
            return {str(item.get("id")): item for item in items if isinstance(item, dict) and item.get("id")}
        return payload
    return {}


def provider_config():
    model = os.environ.get("RUBRIC_MODEL") or os.environ.get("AGENT_MODEL")
    base_url = os.environ.get("RUBRIC_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("AGENT_BASE_URL") or ""
    api_key = os.environ.get("RUBRIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("AGENT_API_KEY") or ""
    return model, base_url, api_key


def main() -> int:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output")
    artifacts_dir = Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_dir / "artifacts")))
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    diff = read_text(artifacts_dir / "patch.diff", read_text(output_dir / "patch.diff", ""), 60000)
    if not diff.strip():
        write_results(output_dir, [phase_item(rid, name, False, "patch.diff 为空：agent 未做任何代码改动，审查项判 fail") for rid, name, _ in RUBRICS], {"phase": "llm", "llm_enabled": False})
        return 0

    model, base_url, api_key = provider_config()
    if not api_key:
        reason = "RUBRIC_API_KEY/ANTHROPIC_API_KEY 未注入容器，整次评测需重跑"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason, "model": model, "base_url": base_url}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_results(output_dir, [phase_item(rid, name, False, "INFRA: LLM judge 不可用: " + reason, True) for rid, name, _ in RUBRICS], {"phase": "llm", "test_infra_failure": True})
        return 0

    rubric_lines = "\n".join(f"- id={rid}（{name}）：{desc}" for rid, name, desc in RUBRICS)
    prompt = f"""你是一个严格的支付集成代码审查员。下面是一个 Laravel 项目中接入“支付宝小程序 JSAPI 支付”的代码改动、agent_evidence.json 以及部分关键文件内容。

请逐条判断以下审查项，每条输出 pass/fail 和一句中文理由。不要臆测 diff 中不存在的代码；如果证据不足请倾向 fail 并说明缺少什么证据。

审查项：
{rubric_lines}

请只输出 JSON（不要 markdown 代码块），格式：
{{"results": [{{"id": "<rubric id>", "pass": true/false, "reason": "..."}}]}}

=== agent_evidence.json ===
{read_text(artifacts_dir / "agent_evidence.json", "[missing agent_evidence.json]", 80000)}

=== git diff（截断到 60KB） ===
{diff}

=== 关键文件片段 ===
{gather_snippets(workspace)[:30000]}
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
        reason = f"3 次调用均失败: {proc.stderr[-500:]}; 整次评测需重跑"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason, "model": model, "base_url": base_url}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_results(output_dir, [phase_item(rid, name, False, "INFRA: LLM judge 不可用: " + reason, True) for rid, name, _ in RUBRICS], {"phase": "llm", "test_infra_failure": True})
        return 0

    parsed = parse_payload(raw_path)
    rubrics = []
    for rid, name, _ in RUBRICS:
        item = parsed.get(rid) or {}
        passed = bool(item.get("pass") if "pass" in item else item.get("passed")) if isinstance(item, dict) else False
        reason = item.get("reason") or item.get("message") or "judge 输出缺少该 rubric，按失败计入固定分母"
        rubrics.append(phase_item(rid, name, passed, reason))
    write_results(output_dir, rubrics, {"phase": "llm", "llm_judge_backend": "payskills-judge"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
