#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
JUDGE_IDS = [
    "a2m_no_fake_bypass",
    "a2m_verify_fail_closed",
    "a2m_resource_binding",
    "a2m_confirm_before_deliver",
    "a2m_terminal_state_guard",
]
DIM = {
    "a2m_no_fake_bypass": "security",
    "a2m_verify_fail_closed": "security",
    "a2m_resource_binding": "security",
    "a2m_confirm_before_deliver": "security",
    "a2m_terminal_state_guard": "security",
}


def read_text(path, fallback=""):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return fallback


def load_hard_evidence(output_root):
    path = output_root / "checks" / "integration_results.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "[NO HARD INTEGRATION EVIDENCE AVAILABLE]"
    items = payload.get("rubrics", payload if isinstance(payload, list) else [])
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id", "")).replace("integration.", "")
        status = "PASS" if item.get("passed") else "FAIL"
        lines.append("- %s: %s; %s" % (rid, status, str(item.get("message", ""))[:500]))
    return "\n".join(lines) if lines else "[NO HARD INTEGRATION EVIDENCE AVAILABLE]"


def phase_item(rid, passed, message, infra=False):
    item = {
        "id": "judge.%s" % rid,
        "name": rid,
        "dimension": DIM.get(rid, "security"),
        "type": "llm_assisted",
        "passed": bool(passed),
        "score": 1.0 if passed else 0.0,
        "max_score": 1.0,
        "message": str(message or ""),
        "evidence": ["llm_judge_prompt.txt", "llm_judge_raw.json", "agent_evidence.json", "patch.diff"],
    }
    if infra:
        item["test_infra_failure"] = True
    return item


def write_phase(out, rubrics, metadata=None):
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": metadata or {}}, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_judge_json(obj):
    rubrics = obj.get("rubrics") or obj.get("verdicts") or obj.get("results") or [] if isinstance(obj, dict) else []
    if isinstance(rubrics, dict):
        rubrics = [dict({"id": rid}, **val) if isinstance(val, dict) else {"id": rid, "passed": bool(val)} for rid, val in rubrics.items()]
    by_id = {}
    for item in rubrics:
        if isinstance(item, dict) and item.get("id") in JUDGE_IDS:
            by_id[item["id"]] = item
    return by_id


def main():
    workspace = Path(sys.argv[1])
    out = Path(sys.argv[2])
    case_name = sys.argv[3]
    task_instance_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else THIS_DIR.parents[1]
    output_root = Path(os.environ.get("OUTPUT_DIR", str(out.parent.parent)))
    artifacts_dir = Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_root / "artifacts")))
    output_root.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    diff = read_text(artifacts_dir / "patch.diff") or read_text(output_root / "patch.diff")
    if not diff.strip():
        write_phase(out, [phase_item(rid, False, "patch.diff 为空：agent 未产出代码改动，judge 无内容可审查") for rid in JUDGE_IDS], {"phase": "llm", "llm_enabled": False})
        return 0
    if len(diff) > 60000:
        diff = diff[:60000] + "\n... [diff truncated] ..."
    if not (os.environ.get("RUBRIC_BASE_URL") and os.environ.get("RUBRIC_API_KEY")):
        reason = "INFRA: 缺少 RUBRIC_BASE_URL/RUBRIC_API_KEY，无法调用 judge；整次评测需重跑"
        (output_root / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(rid, False, reason, True) for rid in JUDGE_IDS], {"phase": "llm", "test_infra_failure": True})
        return 0

    template = (THIS_DIR / "review_prompt.md").read_text(encoding="utf-8")
    user = template + "\n\n补充判定要求：hard integration evidence 是实际 HTTP/mock 网关运行证据；如果它证明金额不匹配、归属错配、过期 proof、confirm 失败或其他关键路径仍然放行，不要只因为 diff 中出现相关关键词就判通过。"
    user += "\n\n===== HARD INTEGRATION EVIDENCE =====\n" + load_hard_evidence(output_root) + "\n===== END HARD INTEGRATION EVIDENCE =====\n"
    user += "\n\n===== AGENT EVIDENCE JSON =====\n" + read_text(artifacts_dir / "agent_evidence.json", "[agent_evidence.json missing]") + "\n===== END AGENT EVIDENCE JSON =====\n"
    user += "\n\n===== BEGIN DIFF =====\n" + diff + "\n===== END DIFF =====\n"
    prompt_path = artifacts_dir / "llm_judge_prompt.txt"
    raw_path = artifacts_dir / "llm_judge_raw.json"
    prompt_path.write_text(user, encoding="utf-8")
    (output_root / "llm_judge_prompt.txt").write_text(user, encoding="utf-8")

    judge_bin = os.environ.get("PAYSKILLS_LLM_JUDGE_BIN") or "payskills-judge"
    proc = subprocess.run([judge_bin, "eval", "--prompt-file", str(prompt_path), "--output", str(raw_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    (artifacts_dir / "llm_judge.stdout.txt").write_text(proc.stdout, encoding="utf-8", errors="replace")
    (artifacts_dir / "llm_judge.stderr.txt").write_text(proc.stderr, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        reason = "INFRA: LLM judge failed with exit %s: %s" % (proc.returncode, proc.stderr[-500:])
        (output_root / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(rid, False, reason, True) for rid in JUDGE_IDS], {"phase": "llm", "test_infra_failure": True})
        return 0
    try:
        by_id = parse_judge_json(json.loads(raw_path.read_text(encoding="utf-8")))
    except Exception as exc:
        reason = "INFRA: LLM judge output invalid: %s" % exc
        (output_root / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(rid, False, reason, True) for rid in JUDGE_IDS], {"phase": "llm", "test_infra_failure": True})
        return 0
    rubrics = []
    for rid in JUDGE_IDS:
        item = by_id.get(rid) or {}
        passed = bool(item.get("passed")) if isinstance(item.get("passed"), bool) else False
        rubrics.append(phase_item(rid, passed, item.get("reason") or item.get("message") or "judge 未返回该项"))
    write_phase(out, rubrics, {"phase": "llm", "llm_judge_backend": "payskills-judge"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
