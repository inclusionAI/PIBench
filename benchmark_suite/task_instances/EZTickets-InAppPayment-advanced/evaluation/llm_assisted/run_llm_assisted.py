#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path


RUBRICS = [
    {
        "id": "L1",
        "name": "无固定成功或绕过",
        "desc": "没有固定成功、无条件验签、客户端回调直接 paid、退款不调用外部能力等实现。测试桩可以存在，但必须通过同一 service/client 抽象，并使用运行期网关、密钥或测试网关配置。",
    },
    {
        "id": "L2",
        "name": "未知状态补偿",
        "desc": "支付或退款未知、处理中、关闭等状态有查单、退款查询、重试、保持 pending 或人工处理路径，并使用运行期支付宝网关配置，而不是写死固定成功。",
    },
    {
        "id": "L3",
        "name": "金额口径",
        "desc": "实付、商户实收、可退、已退、部分退款不会混用单一金额字段，并拒绝金额不一致或超额退款。",
    },
    {
        "id": "L4",
        "name": "客户端结果不直接履约",
        "desc": "APP 支付回调返回结果不会直接驱动最终履约，只能触发服务端 confirm/sync/notify 查询确认流程。",
    },
]

SOURCE_SUFFIXES = {".js", ".dart", ".sql", ".json", ".yaml", ".yml"}
SOURCE_ROOTS = (
    "ez_tickets_backend/src",
    "ez_tickets_backend/test",
    "ez_tickets_backend/tests",
    "ez_tickets_backend/package.json",
    "ez_tickets_backend/ez_tickets.sql",
    "ez_tickets_app/lib",
    "ez_tickets_app/pubspec.yaml",
)


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


def collect_source(project: Path, max_chars=90000):
    chunks = []
    total = 0
    for rel in SOURCE_ROOTS:
        root = project / rel
        if root.is_file():
            paths = [root]
        elif root.is_dir():
            paths = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES)
        else:
            paths = []
        for path in paths:
            if total >= max_chars:
                break
            text = read_text(path)
            if not text:
                continue
            rel_path = str(path.relative_to(project))
            remaining = max_chars - total
            chunk = f"\n\n===== FILE: {rel_path} =====\n{text[:remaining]}"
            chunks.append(chunk)
            total += len(chunk)
    if total >= max_chars:
        chunks.append("\n\n[SOURCE TRUNCATED]\n")
    return "".join(chunks)


def hard_evidence(output_dir: Path):
    lines = []
    for name in ("integration.json", "integration_results.json"):
        data = load_json(output_dir / "checks" / name, load_json(output_dir / name, {}))
        items = data.get("rubrics") or data.get("results") or []
        for item in items:
            rid = str(item.get("id") or "")
            if not rid.startswith("I"):
                continue
            status = "PASS" if item.get("passed") or item.get("status") == "pass" else "FAIL"
            message = str(item.get("message") or "")[:240]
            lines.append(f"- {rid} {status}: {message}")
    return "\n".join(lines[:80]) or "[NO HARD INTEGRATION EVIDENCE AVAILABLE]"


def phase_item(rubric, passed, message, infra=False):
    item = {
        "id": rubric["id"],
        "name": rubric["name"],
        "dimension": "security",
        "type": "llm",
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

    model, base_url, api_key = provider_config()
    if not api_key:
        reason = "INFRA: RUBRIC_BASE_URL/RUBRIC_API_KEY 未配置，LLM judge 未运行；整次评测需重跑"
        (output_dir / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(r, False, reason, True) for r in RUBRICS], {"phase": "llm", "test_infra_failure": True})
        return 0

    rubric_text = "\n".join(f"- {item['id']}: {item['desc']}" for item in RUBRICS)
    prompt = f"""你是支付宝 App Pay 安全接入的代码审查员。请只根据下面的 agent diff、关键源码片段、hard integration evidence 和 agent_evidence.json，判断 4 个安全 rubric 是否通过。

这是一个已经具备基础支付宝支付能力的 starter，agent 的任务是实现更高级的安全版本。不要因为基础支付链路已经存在就自动给分；重点看 agent 是否补上安全增强。允许测试环境 mock 网关和沙箱密钥，但不能接受业务代码固定成功、跳过验签或直接信任客户端结果。

Hard integration evidence 是已经跑出来的确定性反例结果。若 hard evidence 证明有效通知/查单无法进入 paid、字段错配没有被拒绝、退款 fund_change=N 被当作成功、退款不确定态被终态化，相关 L2/L3/L4 应保守判失败；不要只因为代码里出现关键词或接口名就判通过。

请严格输出 JSON 对象，不要输出 Markdown。格式：
{{
  "L1": {{"passed": true/false, "reason": "一句中文理由"}},
  "L2": {{"passed": true/false, "reason": "一句中文理由"}},
  "L3": {{"passed": true/false, "reason": "一句中文理由"}},
  "L4": {{"passed": true/false, "reason": "一句中文理由"}}
}}

Rubrics:
{rubric_text}

Hard integration evidence:
{hard_evidence(output_dir)}

Agent evidence:
{read_text(artifacts_dir / "agent_evidence.json", "[missing agent_evidence.json]", 80000)}

Agent diff:
{read_text(artifacts_dir / "patch.diff", read_text(output_dir / "patch.diff", "[NO PATCH DIFF AVAILABLE]"), 120000)}

Key source snippets:
{collect_source(workspace)}
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
        write_phase(out, [phase_item(r, False, reason, True) for r in RUBRICS], {"phase": "llm", "test_infra_failure": True})
        return 0

    parsed = parse_payload(raw_path)
    rubrics = []
    for rubric in RUBRICS:
        item = parsed.get(rubric["id"]) or {}
        passed = bool(item.get("passed")) if isinstance(item, dict) else False
        reason = item.get("reason") or item.get("message") or "judge 未返回该项"
        rubrics.append(phase_item(rubric, passed, reason))
    write_phase(out, rubrics, {"phase": "llm", "llm_judge_backend": "payskills-judge"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
