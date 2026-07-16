#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


RUBRICS = {
    "L1": "产品选择合理：实现使用了适合移动端拉起支付宝的服务端签名 App 支付链路（如 alipay.trade.app.pay 生成 orderStr），而不是网页支付(page/wap)、扫码收款(precreate)或付款码收款(pay)链路。",
    "L2": "签名位置正确：支付参数的 RSA2 签名在服务端完成，私钥只存在于服务端配置，客户端（Flutter）只消费后端返回的支付参数，没有在客户端做签名或持有私钥。",
    "L3": "后端确认闭环：客户端从支付宝返回后通过后端接口确认支付状态，后端向支付宝查询（trade.query 或回调验签），确认成功后创建/更新本地 payment 并把 booking 推进到 confirmed。",
    "L4": "前后端串联：支付宝选项、创建支付请求、真实拉起支付宝能力、确认状态、订单更新形成完整闭环，前端调用的接口与后端实现一致。",
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


def hard_evidence(output_dir: Path):
    lines = []
    interesting = {"S2", "I2", "I3", "I4", "I5", "I6", "I7"}
    for name in ("static.json", "integration.json"):
        data = load_json(output_dir / "checks" / name, {})
        for item in data.get("rubrics", []):
            rid = str(item.get("id") or "")
            if rid not in interesting:
                continue
            status = "PASS" if item.get("passed") else "FAIL"
            msg = str(item.get("message") or "").replace("\n", " ")[:240]
            lines.append(f"- {rid} {item.get('name') or rid}: {status}" + (f"; {msg}" if msg else ""))
    return "\n".join(lines) or "[NO STATIC/INTEGRATION EVIDENCE AVAILABLE]"


def phase_item(rid, passed, message, infra=False):
    item = {
        "id": rid,
        "name": RUBRICS[rid].split("：", 1)[0],
        "dimension": "code_quality",
        "type": "llm_judge",
        "passed": bool(passed),
        "score": 1 if passed else 0,
        "max_score": 1,
        "message": str(message or "")[:1000],
        "invalid": False,
        "evidence": ["llm_judge_prompt.txt", "llm_judge_raw.json", "agent_evidence.json", "patch.diff"],
    }
    if infra:
        item["test_infra_failure"] = True
    return item


def write_phase(out: Path, rubrics, metadata=None):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": metadata or {}}, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_payload(path: Path):
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
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/output/checks/llm.json")
    output_dir = Path(os.environ.get("OUTPUT_DIR", str(out.parent.parent)))
    artifacts_dir = Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_dir / "artifacts")))
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    diff = read_text(artifacts_dir / "patch.diff", read_text(output_dir / "patch.diff", ""), 100000)
    if not diff.strip():
        write_phase(
            out,
            [phase_item(rid, False, "无代码改动（patch.diff 为空），无法通过代码审查") for rid in RUBRICS],
            {"phase": "llm", "llm_enabled": False},
        )
        return 0

    model, base_url, api_key = provider_config()
    if not api_key:
        reason = "INFRA: RUBRIC_BASE_URL/RUBRIC_API_KEY 未配置，LLM judge 未运行；整次评测需重跑"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(rid, False, reason, True) for rid in RUBRICS], {"phase": "llm", "test_infra_failure": True})
        return 0

    rubric_lines = "\n".join(f"- {rid}: {desc}" for rid, desc in RUBRICS.items())
    prompt = f"""你是支付系统代码评审专家。以下是一个 agent 为电影票应用（Node.js/Express 后端 + Flutter 前端）接入支付宝 App 支付所做改动的 diff、hard evidence 和 agent_evidence.json。

请逐项审查以下 4 条标准，每条给出 passed（true/false）和不超过 60 字的 reason：

{rubric_lines}

硬测试摘要（用于约束运行闭环判断；若与 diff 冲突，请在 reason 里说明原因）：
{hard_evidence(output_dir)}

判定注意：
- L4 不能只因为 Dart 里声明了 MethodChannel/抽象类就通过；必须看到真实可用的支付宝拉起能力，例如 Flutter 支付宝插件依赖，或 Android/iOS 侧确实实现了对应原生通道。
- 如果硬测试显示创建支付参数或确认接口完全不可达，L3/L4 不能仅凭静态代码意图给“运行闭环完整”通过，除非 diff 明确证明硬测试只是接口命名兼容性问题且前后端实际一致。

只输出一个 JSON 对象，格式：
{{"L1": {{"passed": true, "reason": "..."}}, "L2": {{...}}, "L3": {{...}}, "L4": {{...}}}}

=== AGENT EVIDENCE JSON ===
{read_text(artifacts_dir / "agent_evidence.json", "[missing agent_evidence.json]", 80000)}

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
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    (artifacts_dir / "llm_judge.stdout.txt").write_text(proc.stdout, encoding="utf-8", errors="replace")
    (artifacts_dir / "llm_judge.stderr.txt").write_text(proc.stderr, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        reason = f"INFRA: LLM judge failed with exit {proc.returncode}: {proc.stderr[-500:]}"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(rid, False, reason, True) for rid in RUBRICS], {"phase": "llm", "test_infra_failure": True})
        return 0

    parsed = parse_payload(raw_path)
    rubrics = []
    for rid in RUBRICS:
        item = parsed.get(rid) or {}
        passed = bool(item.get("passed")) if isinstance(item, dict) else False
        reason = item.get("reason") or item.get("message") or "judge 未返回该项"
        rubrics.append(phase_item(rid, passed, reason))
    write_phase(out, rubrics, {"phase": "llm", "llm_judge_backend": "payskills-judge"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
