#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
THIS_DIR = Path(__file__).resolve().parent
CRITERIA = [
  {
    "id": "L1",
    "name": "真实预授权链路设计 (非纯 UI/mock)",
    "prompt": "代码是否设计了真实的后端支付宝预授权链路：至少包含 freeze/query/notify 的后端业务入口、签名 SDK 或等价 OpenAPI 请求能力、通过环境/本地配置接入支付宝参数，并避免只在前端画二维码、固定返回假 alipays://、或把 mock/sandbox fallback 当作生产成功?"
  },
  {
    "id": "L2",
    "name": "预授权身份绑定与状态模型",
    "prompt": "代码是否有清晰的预授权身份和状态模型：freeze 生成的 out_order_no/out_request_no/auth_no 能与 Booking 稳定关联，query/notify 共享同一套身份信息，状态能区分 INIT/PENDING/SUCCESS/AUTHORIZED/CLOSED/FAILED 等语义，并且不会把 unknown、网关错误或异常直接当成授权成功?"
  }
]

def read_text(path, fallback=""):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return fallback

def collect_code(workspace, max_chars=100000):
    workspace = Path(workspace)
    parts=[]
    for root in [workspace/"backend/src", workspace/"frontend/src", workspace/"packages"]:
        if not root.exists():
            continue
        for fp in sorted(root.rglob("*")):
            if fp.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            text = read_text(fp)
            if any(k in text.lower() for k in ["alipay", "preauth", "freeze", "unfreeze", "trade.pay", "auth_no"]):
                parts.append("===== %s =====\n%s" % (fp.relative_to(workspace), text[:20000]))
    return "\n\n".join(parts)[:max_chars]

def hard_evidence(output_root):
    lines=[]
    for name in ["integration_results.json", "e2e_results.json", "static_results.json"]:
        path=Path(output_root)/"checks"/name
        try:
            data=json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item in data.get("rubrics", []):
            status="PASS" if item.get("passed") else "FAIL"
            lines.append("- %s: %s; %s" % (item.get("id"), status, str(item.get("message", ""))[:400]))
    return "\n".join(lines) if lines else "[NO HARD EVIDENCE AVAILABLE]"

def phase_item(rid, name, passed, message, infra=False):
    item={"id": rid, "name": name, "dimension": "quality", "type": "llm_assisted", "passed": bool(passed), "score": 1.0 if passed else 0.0, "max_score": 1.0, "message": str(message or "")[:1000], "evidence": ["llm_judge_prompt.txt", "llm_judge_raw.json", "agent_evidence.json", "patch.diff"]}
    if infra:
        item["test_infra_failure"] = True
    return item

def write_phase(out, rubrics, metadata=None):
    out.write_text(json.dumps({"rubrics": rubrics, "metadata": metadata or {}}, ensure_ascii=False, indent=2), encoding="utf-8")

def parse(obj):
    if not isinstance(obj, dict):
        return {}
    items = obj.get("rubrics") or obj.get("verdicts") or obj.get("results")
    if isinstance(items, list):
        return {str(x.get("id")): x for x in items if isinstance(x, dict) and x.get("id")}
    return {rid: val for rid, val in obj.items() if isinstance(val, dict)}

def main():
    workspace=Path(sys.argv[1])
    out=Path(sys.argv[2])
    case_name=sys.argv[3]
    task_instance_dir=Path(sys.argv[4]) if len(sys.argv)>4 else THIS_DIR.parents[1]
    output_root=Path(os.environ.get("OUTPUT_DIR", str(out.parent.parent)))
    artifacts_dir=Path(os.environ.get("PAYSKILLS_ARTIFACTS_DIR", str(output_root/"artifacts")))
    output_root.mkdir(parents=True, exist_ok=True); artifacts_dir.mkdir(parents=True, exist_ok=True)
    ids=[c["id"] for c in CRITERIA]
    code=collect_code(workspace)
    if not code.strip():
        write_phase(out, [phase_item(c["id"], c["name"], False, "no relevant alipay/preauth code found") for c in CRITERIA], {"phase":"llm", "llm_enabled": False})
        return 0
    if not (os.environ.get("RUBRIC_BASE_URL") and os.environ.get("RUBRIC_API_KEY")):
        reason="INFRA: RUBRIC_BASE_URL/RUBRIC_API_KEY 未配置，LLM judge 未运行；无 heuristic fallback"
        (output_root/"llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(c["id"], c["name"], False, reason, True) for c in CRITERIA], {"phase":"llm", "test_infra_failure": True})
        return 0
    criteria_text="\n".join("- %s: %s" % (c["id"], c["prompt"]) for c in CRITERIA)
    prompt=("你是严格的代码审查员。请只根据代码语义、hard evidence 和 agent_evidence.json 逐项判断。\n"
            "不要替 deterministic/e2e 判定运行正确性；不要因为注释或变量名出现就给通过。\n\n"
            + criteria_text + "\n\n只输出 JSON：{\"L1\": {\"passed\": true/false, \"reason\": \"...\"}, \"L2\": {...}}\n\n"
            + "===== HARD EVIDENCE =====\n" + hard_evidence(output_root) + "\n\n"
            + "===== AGENT EVIDENCE JSON =====\n" + read_text(artifacts_dir/"agent_evidence.json", "[missing]") + "\n\n"
            + "===== DIFF =====\n" + read_text(artifacts_dir/"patch.diff", "[missing patch.diff]")[:50000] + "\n\n"
            + "===== CODE =====\n" + code)
    prompt_path=artifacts_dir/"llm_judge_prompt.txt"; raw_path=artifacts_dir/"llm_judge_raw.json"
    prompt_path.write_text(prompt, encoding="utf-8"); (output_root/"llm_judge_prompt.txt").write_text(prompt, encoding="utf-8")
    judge_bin=os.environ.get("PAYSKILLS_LLM_JUDGE_BIN") or "payskills-judge"
    proc=subprocess.run([judge_bin,"eval","--prompt-file",str(prompt_path),"--output",str(raw_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    (artifacts_dir/"llm_judge.stdout.txt").write_text(proc.stdout, encoding="utf-8", errors="replace")
    (artifacts_dir/"llm_judge.stderr.txt").write_text(proc.stderr, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        reason="INFRA: LLM judge failed with exit %s: %s" % (proc.returncode, proc.stderr[-500:])
        (output_root/"llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(c["id"], c["name"], False, reason, True) for c in CRITERIA], {"phase":"llm", "test_infra_failure": True})
        return 0
    try:
        verdicts=parse(json.loads(raw_path.read_text(encoding="utf-8")))
    except Exception as exc:
        reason="INFRA: LLM judge output invalid: %s" % exc
        (output_root/"llm_judge_infra_failure.json").write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_phase(out, [phase_item(c["id"], c["name"], False, reason, True) for c in CRITERIA], {"phase":"llm", "test_infra_failure": True})
        return 0
    rubrics=[]
    for c in CRITERIA:
        v=verdicts.get(c["id"]) or {}
        rubrics.append(phase_item(c["id"], c["name"], bool(v.get("passed")) if isinstance(v.get("passed"), bool) else False, v.get("reason") or v.get("message") or "judge 未返回该项"))
    write_phase(out, rubrics, {"phase":"llm", "llm_judge_backend":"payskills-judge"})
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
