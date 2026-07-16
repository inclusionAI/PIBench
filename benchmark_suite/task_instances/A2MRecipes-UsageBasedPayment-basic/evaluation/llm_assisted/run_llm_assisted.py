#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
RUBRICS = [
    ("a2m_dep_sdk_llm", "L1", "是否接入真实支付客户端能力：没有把 Payment-Proof 字符串当作本地白名单比对，也没有不调用外部验证就固定成功。"),
    ("a2m_verify_proof_llm", "L2", "收到 Payment-Proof 后是否存在服务端验证逻辑，并且验证失败、网关不可达、返回异常或状态不明确时 fail-closed。"),
    ("a2m_confirm_fulfillment_llm", "L3", "付费资源成功返回后是否存在履约确认逻辑：读取网关验证成功返回的交付确认信息，并在资源交付后带回支付网关。"),
]


def read_text(path, fallback=""):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return fallback


def hard_evidence(output_root):
    data = None
    for path in [output_root / "checks" / "integration_results.json", output_root / "integration_results.json"]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            break
        except Exception:
            continue
    items = data.get("rubrics", data if isinstance(data, list) else []) if data is not None else []
    lines = []
    for item in items:
        if isinstance(item, dict):
            status = "PASS" if item.get("passed") else "FAIL"
            lines.append("- %s: %s; %s" % (item.get("id", ""), status, str(item.get("message", ""))[:500]))
    return "\n".join(lines) if lines else "[NO HARD INTEGRATION EVIDENCE AVAILABLE]"


def phase_item(rid, passed, message, infra=False):
    item = {
        "id": rid,
        "name": rid,
        "dimension": "security" if "confirm" not in rid else "functionality",
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


def parse_verdicts(obj):
    if isinstance(obj, dict):
        verdicts = obj.get("verdicts") or obj.get("rubrics") or obj.get("results")
        if isinstance(verdicts, dict):
            verdicts = [dict({"id": rid}, **val) if isinstance(val, dict) else {"id": rid, "passed": bool(val)} for rid, val in verdicts.items()]
        if isinstance(verdicts, list):
            return {str(v.get("id")): v for v in verdicts if isinstance(v, dict) and v.get("id")}
        return {rid: val for rid, val in obj.items() if isinstance(val, dict)}
    return {}


def main():
    workspace = Path(sys.argv[1])
    out = Path(sys.argv[2])
    case_name = sys.argv[3]
    task_instance_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else THIS_DIR.parents[1]
    output_root = Path(os.environ.get("OUTPUT_DIR", str(out.parent.parent)))
    artifacts_dir = Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_root / "artifacts")))
    output_root.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    ids = [rid for rid, _, _ in RUBRICS]

    diff = read_text(artifacts_dir / "patch.diff") or read_text(output_root / "patch.diff")
    if not diff.strip():
        write_phase(out, [phase_item(rid, False, "patch.diff 为空：agent 没有产生任何代码改动，无需 LLM 审查") for rid in ids], {"phase": "llm", "llm_enabled": False})
        return 0
    if len(diff) > 60000:
        diff = diff[:60000] + "\n... (diff truncated at 60KB)"

    if not (os.environ.get("RUBRIC_BASE_URL") and os.environ.get("RUBRIC_API_KEY")):
        reason = "INFRA: RUBRIC_BASE_URL/RUBRIC_API_KEY 未配置，LLM judge 未运行；该项按失败计入固定分母"
        (output_root / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(rid, False, reason, True) for rid in ids], {"phase": "llm", "test_infra_failure": True})
        return 0

    template = (THIS_DIR / "review_prompt.md").read_text(encoding="utf-8")
    prompt = template.replace("{{RUBRIC_LINES}}", "\n".join("- id=%s（%s）：%s" % r for r in RUBRICS))
    prompt = prompt.replace("{{HARD_EVIDENCE}}", hard_evidence(output_root))
    prompt = prompt.replace("{{AGENT_EVIDENCE_JSON}}", read_text(artifacts_dir / "agent_evidence.json", "[agent_evidence.json missing]"))
    prompt = prompt.replace("{{DIFF}}", diff)
    prompt_path = artifacts_dir / "llm_judge_prompt.txt"
    raw_path = artifacts_dir / "llm_judge_raw.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    (output_root / "llm_judge_prompt.txt").write_text(prompt, encoding="utf-8")

    judge_bin = os.environ.get("PAYSKILLS_LLM_JUDGE_BIN") or "payskills-judge"
    proc = subprocess.run([judge_bin, "eval", "--prompt-file", str(prompt_path), "--output", str(raw_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    (artifacts_dir / "llm_judge.stdout.txt").write_text(proc.stdout, encoding="utf-8", errors="replace")
    (artifacts_dir / "llm_judge.stderr.txt").write_text(proc.stderr, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        reason = "INFRA: LLM judge failed with exit %s: %s" % (proc.returncode, proc.stderr[-500:])
        (output_root / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(rid, False, reason, True) for rid in ids], {"phase": "llm", "test_infra_failure": True})
        return 0
    try:
        verdicts = parse_verdicts(json.loads(raw_path.read_text(encoding="utf-8")))
    except Exception as exc:
        reason = "INFRA: LLM judge output invalid: %s" % exc
        (output_root / "llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(rid, False, reason, True) for rid in ids], {"phase": "llm", "test_infra_failure": True})
        return 0
    rubrics = []
    for rid in ids:
        verdict = verdicts.get(rid) or {}
        passed = bool(verdict.get("passed")) if isinstance(verdict.get("passed"), bool) else False
        rubrics.append(phase_item(rid, passed, verdict.get("reason") or verdict.get("message") or "judge 未返回该项"))
    write_phase(out, rubrics, {"phase": "llm", "llm_judge_backend": "payskills-judge"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
