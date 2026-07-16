#!/usr/bin/env python3
"""LLM-assisted semantic review for Bill Express POS payment task instances."""
import json
import os
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
DETERMINISTIC_SUPPORT = THIS_DIR.parent / "deterministic" / "support"
sys.path.insert(0, str(DETERMINISTIC_SUPPORT))

from common import case_kind, rubric, write_phase  # noqa: E402


BASE_URL = (os.environ.get("RUBRIC_BASE_URL") or "").rstrip("/")
API_KEY = os.environ.get("RUBRIC_API_KEY") or ""
MODEL = os.environ.get("RUBRIC_MODEL") or ""
MAX_FILE_CHARS = 50000
MAX_TOTAL_CHARS = 500000

CHECKS = {
    "qrcode_basic": [
        ("llm.product_mapping", "是否语义上选择订单码支付/当面付主扫，由后端为当前账单创建支付宝商家二维码，而不是泛电商网页支付、APP 支付、付款码被扫或纯前端假二维码。"),
        ("llm.success_criteria", "是否没有把二维码展示、创建接口同步返回或 code=10000 当成最终支付成功；并且设计了支付宝查询或验签异步通知来确认最终状态。"),
    ],
    "barcode_basic": [
        ("llm.product_mapping", "是否语义上选择当面付付款码/条码支付，使用 alipay.trade.pay 和 scene=bar_code/auth_code，而不是订单码或网页支付。"),
        ("llm.success_criteria", "是否没有把客户端输入 auth_code 或同步非终态响应直接当最终成功；至少说明要处理 WAIT/失败并可查询确认。"),
    ],
    "qrcode_safety": [
        ("llm.notify_security_semantics", "是否在验签之后绑定 app/订单号/金额/交易状态等关键字段，坏签名/错字段通知不能推进状态。"),
        ("llm.pending_fail_closed_semantics", "是否对 WAIT/未知/失败/网关异常保持 fail-closed，并通过查询补偿确认，而不是直接置 paid。"),
        ("llm.idempotency_terminal_semantics", "是否处理重复通知、重复查询和终态保护，已支付状态不被旧事件覆盖。"),
        ("llm.refund_reverse_semantics", "是否正确实现退款、部分退款、重复退款请求号、退款未知结果查询，以及关闭/撤销/退款边界。"),
        ("llm.secret_management_semantics", "是否避免真实密钥硬编码、日志输出或混用测试 mock key 与真实沙箱 key。"),
    ],
    "barcode_safety": [
        ("llm.notify_security_semantics", "是否校验 alipay.trade.pay/query 响应签名和订单/金额/状态字段，不能只看 code=10000。"),
        ("llm.pending_fail_closed_semantics", "是否正确处理 10003/WAIT_BUYER_PAY、失败、关闭和网关异常，不能把处理中当成功。"),
        ("llm.idempotency_terminal_semantics", "是否防止同一 invoice 重复扣款/重复入账，并保持终态不被旧响应覆盖。"),
        ("llm.refund_reverse_semantics", "是否正确实现退款、部分退款、重复退款请求号、退款未知结果查询，以及关闭/撤销/退款边界。"),
        ("llm.secret_management_semantics", "是否保护 auth_code，只存 hash/后四位且不打印完整付款码；密钥也不能硬编码。"),
    ],
}

TEXT_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".sh", ".env")
SKIP_DIRS = set(["node_modules", ".git", ".case-runtime", "dist", ".next", "target", "skills"])


def gather_code_context(workspace, artifacts_dir):
    workspace = Path(workspace).resolve()
    artifacts_dir = Path(artifacts_dir)
    parts = []
    total = 0
    seen = set()

    def is_under(path, parent):
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def is_text_file(path):
        return path.name.startswith(".env") or path.name.endswith(TEXT_SUFFIXES)

    def add_block(title, body, lang=""):
        nonlocal total
        block = "## %s\n```%s\n%s\n```" % (title, lang, body)
        if total + len(block) > MAX_TOTAL_CHARS:
            remaining = MAX_TOTAL_CHARS - total
            if remaining <= 120:
                return False
            overhead = len("## %s\n```%s\n\n...(truncated due to LLM judge input limit)...\n```" % (title, lang))
            body_limit = max(0, remaining - overhead)
            body = body[:body_limit] + "\n...(truncated due to LLM judge input limit)..."
            block = "## %s\n```%s\n%s\n```" % (title, lang, body)
            parts.append(block)
            total += len(block)
            return False
        parts.append(block)
        total += len(block)
        return True

    def add_file(fp):
        try:
            rp = fp.resolve()
        except Exception:
            return True
        if rp in seen or not is_under(rp, workspace) or not rp.is_file() or not is_text_file(rp):
            return True
        if any(part in SKIP_DIRS for part in rp.parts):
            return True
        content = rp.read_text(encoding="utf-8", errors="replace")
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS] + "\n...(file truncated due to LLM judge per-file limit)..."
        rel = str(rp.relative_to(workspace))
        seen.add(rp)
        return add_block("文件: %s" % rel, content)

    diff_path = artifacts_dir / "patch.diff"
    if diff_path.exists():
        diff = diff_path.read_text(encoding="utf-8", errors="replace")
        if len(diff) > MAX_TOTAL_CHARS:
            diff = diff[:MAX_TOTAL_CHARS] + "\n...(patch truncated due to LLM judge input limit)..."
        if not add_block("代码 diff", diff, "diff"):
            return "\n\n".join(parts)

    changed_path = artifacts_dir / "changed_files.txt"
    if changed_path.exists():
        changed = [line.strip() for line in changed_path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        if changed:
            if not add_block("changed_files.txt", "\n".join(changed)):
                return "\n\n".join(parts)
        for rel in changed:
            if not add_file(workspace / rel):
                return "\n\n".join(parts)

    roots = [workspace / "server.ts", workspace / "src", workspace / "package.json"]
    for root in roots:
        if root.is_file():
            files = [root]
        elif root.is_dir():
            files = sorted([p for p in root.rglob("*") if p.is_file()])
        else:
            files = []
        for fp in files:
            if not add_file(fp):
                parts.append("...(更多文件因长度限制省略)...")
                return "\n\n".join(parts)
    return "\n\n".join(parts)


def read_optional_text(path, label):
    path = Path(path)
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return "(failed to read %s: %s)" % (label, exc)
    return "(missing %s)" % label


def build_prompt(task_instance_dir, kind, context, agent_evidence_text):
    checks_text = "\n".join(["- %s: %s" % (rid, desc) for rid, desc in CHECKS[kind]])
    schema = ",\n".join(['  "%s": {"passed": false, "reason": "..."}' % rid for rid, _ in CHECKS[kind]])
    template = (Path(task_instance_dir) / "evaluation" / "llm_assisted" / "review_prompt.md").read_text(
        encoding="utf-8",
        errors="replace",
    )
    replacements = {
        "{{CHECKS_TEXT}}": checks_text,
        "{{JSON_SCHEMA}}": schema,
        "{{CODE_CONTEXT}}": context,
        "{{AGENT_EVIDENCE_JSON}}": agent_evidence_text,
    }
    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)
    return prompt


def infra_results(ids, evidence):
    return [rubric(rid, False, evidence, "llm", test_infra_failure=True) for rid in ids]


def load_phase_results(output_root, name):
    for path in [Path(output_root) / "checks" / name, Path(output_root) / name]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = data.get("rubrics", data) if isinstance(data, dict) else data
        if isinstance(items, list):
            return {item.get("id"): item for item in items if isinstance(item, dict) and item.get("id")}
    return {}


def passed(results, rid):
    item = results.get(rid) or {}
    return bool(item.get("passed") or item.get("status") == "passed")


def apply_runtime_guardrails(kind, rubrics, output_root):
    if kind.endswith("_basic"):
        return rubrics
    integration = load_phase_results(output_root, "integration_results.json") or {}
    guards = {
        "qrcode_safety": {
            "llm.notify_security_semantics": ["integ.valid_notify_accept", "integ.bad_signature_reject", "integ.unsigned_reject", "integ.wrong_amount_reject", "integ.wrong_out_trade_no_reject"],
            "llm.pending_fail_closed_semantics": ["integ.wait_not_paid", "integ.query_compensation"],
            "llm.idempotency_terminal_semantics": ["integ.duplicate_idempotent", "integ.terminal_state_protected", "integ.no_repeat_pay_before_confirm", "integ.request_idempotency_key"],
            "llm.refund_reverse_semantics": ["integ.partial_refund_success", "integ.full_refund_terminal", "integ.refund_same_request_idempotent", "integ.refund_multi_request_distinct", "integ.refund_fund_change_required", "integ.refund_unknown_query"],
        },
        "barcode_safety": {
            "llm.notify_security_semantics": ["integ.barcode_pay_success", "integ.wrong_amount_reject", "integ.unsigned_reject"],
            "llm.pending_fail_closed_semantics": ["integ.wait_not_paid", "integ.fail_not_paid", "integ.query_compensation", "integ.f2f_10003_polling"],
            "llm.idempotency_terminal_semantics": ["integ.duplicate_idempotent", "integ.terminal_state_protected", "integ.request_idempotency_key"],
            "llm.refund_reverse_semantics": ["integ.partial_refund_success", "integ.full_refund_terminal", "integ.refund_same_request_idempotent", "integ.refund_multi_request_distinct", "integ.refund_fund_change_required", "integ.refund_unknown_query"],
            "llm.secret_management_semantics": ["integ.auth_code_not_plaintext"],
        },
    }.get(kind, {})
    for item in rubrics:
        required = guards.get(item.get("id"), [])
        missing = [rid for rid in required if not passed(integration, rid)]
        if missing:
            item["passed"] = False
            item["score"] = 0.0
            item["status"] = "failed"
            item["message"] = "runtime prerequisite failed before semantic credit: %s; llm_reason=%s" % (", ".join(missing), item.get("message", ""))
            item["evidence"] = item["message"]
    return rubrics


def run_platform_judge(prompt_path, result_path, artifacts_dir):
    judge_bin = os.environ.get("PAYSKILLS_LLM_JUDGE_BIN") or "payskills-judge"
    stdout_path = Path(artifacts_dir) / "llm_judge.stdout.txt"
    stderr_path = Path(artifacts_dir) / "llm_judge.stderr.txt"
    cmd = [
        judge_bin,
        "eval",
        "--prompt-file",
        str(prompt_path),
        "--output",
        str(result_path),
    ]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )
    stdout_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
    stderr_path.write_text(proc.stderr, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stderr


def main():
    workspace = Path(sys.argv[1])
    out = Path(sys.argv[2])
    case_name = sys.argv[3]
    task_instance_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else THIS_DIR.parents[1]
    kind = case_kind()
    ids = [rid for rid, _ in CHECKS[kind]]
    output_root = Path(os.environ.get("OUTPUT_DIR", str(out.parent.parent)))
    artifacts_dir = Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_root / "artifacts")))
    output_root.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    if not BASE_URL or not API_KEY or not MODEL:
        (output_root / "llm_judge_infra_failure.json").write_text(
            json.dumps({"error": "RUBRIC_BASE_URL/RUBRIC_API_KEY/RUBRIC_MODEL not configured"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_phase(out, case_name, "llm", infra_results(ids, "LLM judge provider is not fully configured"), {"kind": kind, "llm_enabled": False, "test_infra_failure": True})
        return

    context = gather_code_context(workspace, artifacts_dir)
    if not context.strip():
        (output_root / "llm_judge_infra_failure.json").write_text(
            json.dumps({"error": "no code context"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_phase(out, case_name, "llm", infra_results(ids, "no code context available for LLM judge"), {"kind": kind, "llm_enabled": True, "test_infra_failure": True})
        return

    agent_evidence = read_optional_text(artifacts_dir / "agent_evidence.json", "agent_evidence.json")
    prompt = build_prompt(task_instance_dir, kind, context, agent_evidence)
    prompt_path = artifacts_dir / "llm_judge_prompt.md"
    result_path = artifacts_dir / "llm_judge_raw.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    (output_root / "llm_judge_prompt.txt").write_text(prompt, encoding="utf-8")

    rc, stderr = run_platform_judge(prompt_path, result_path, artifacts_dir)
    if rc != 0:
        message = "LLM judge failed with exit %s: %s" % (rc, stderr[-500:])
        (output_root / "llm_judge_infra_failure.json").write_text(
            json.dumps({"error": message}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_phase(out, case_name, "llm", infra_results(ids, message[:300]), {"kind": kind, "llm_enabled": True, "llm_error": message[:500], "test_infra_failure": True})
        return

    try:
        verdict = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        message = "LLM judge output invalid: %s" % exc
        (output_root / "llm_judge_infra_failure.json").write_text(
            json.dumps({"error": message}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_phase(out, case_name, "llm", infra_results(ids, message), {"kind": kind, "llm_enabled": True, "test_infra_failure": True})
        return

    rubrics = []
    for rid in ids:
        item = verdict.get(rid, {})
        item = item if isinstance(item, dict) else {}
        passed_value = item.get("passed")
        passed_flag = bool(passed_value) if isinstance(passed_value, bool) else False
        reason = str(item.get("reason", ""))[:1000] if item else "missing verdict"
        rubrics.append(rubric(rid, passed_flag, reason, "llm"))
    rubrics = apply_runtime_guardrails(kind, rubrics, output_root)
    write_phase(out, case_name, "llm", rubrics, {"kind": kind, "llm_enabled": True, "model": MODEL, "llm_judge_backend": "payskills-judge"})


if __name__ == "__main__":
    main()
