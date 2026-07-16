#!/usr/bin/env python3
"""Merge phase check files into the final /output/result.json (engine contract)."""
import json
import sys
from pathlib import Path

EXPECTED = [
    # (rubric_id, default name, phase file)
    ("S1", "后端支付宝能力（SDK 或 RSA2 签名）", "static.json"),
    ("S2", "前端支付宝拉起能力（tobias 或等效插件）", "static.json"),
    ("S3", "前后端支付方式枚举包含支付宝", "static.json"),
    ("S4", "服务端生成支付参数并通过 API 返回", "static.json"),
    ("S5", "后端具备支付宝交易状态查询路径", "static.json"),
    ("S6", "支付成功后落库并确认 booking 的代码路径", "static.json"),
    ("S7", "Flutter 从支付宝返回后调用后端确认接口", "static.json"),
    ("I1", "后端基础测试（npm test）", "integration.json"),
    ("I2", "创建支付宝支付请求", "integration.json"),
    ("I3", "支付状态确认", "integration.json"),
    ("I4", "支付宝未成功时不确认订单", "integration.json"),
    ("I5", "支付成功后确认绑定 booking", "integration.json"),
    ("I6", "支付确认不误确认其他 booking", "integration.json"),
    ("I7", "App 支付金额来自服务端 booking", "integration.json"),
    ("S8", "支付方式选择器中包含支付宝选项", "static.json"),
    ("S9", "Flutter 对接后端创建支付和确认支付接口", "static.json"),
    ("S10", "Flutter 处理成功/失败/取消/处理中等支付结果状态", "static.json"),
    ("L1", "产品选择合理", "llm.json"),
    ("L2", "签名位置正确", "llm.json"),
    ("L3", "后端确认闭环", "llm.json"),
    ("L4", "前后端串联", "llm.json"),
]


def main():
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/output")
    checks_dir = output_dir / "checks"

    found = {}
    llm_judge_infra_failure = False
    for fname in ("static.json", "integration.json", "llm.json"):
        path = checks_dir / fname
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if fname == "llm.json" and data.get("infra_failure"):
                llm_judge_infra_failure = True
            for r in data.get("rubrics", []):
                found[r["id"]] = r
        except Exception as exc:  # noqa: BLE001
            print(f"[result] WARN: cannot parse {fname}: {exc}")
    if (output_dir / "llm_judge_infra_failure.json").exists():
        llm_judge_infra_failure = True

    rubrics = []
    for rid, name, phase_file in EXPECTED:
        if rid in found:
            r = dict(found[rid])
            r.setdefault("name", name)
        else:
            r = {"id": rid, "name": name, "dimension": "functionality",
                 "type": "hard", "passed": False, "score": 0, "max_score": 1,
                 "message": f"评分阶段（{phase_file}）未产出该项结果，见 test_output.txt",
                 "evidence": ["test_output.txt"]}
        rubrics.append(r)

    invalid_count = sum(1 for r in rubrics if r.get("invalid"))
    for r in rubrics:
        if r.get("invalid"):
            r["invalid"] = False
            r["passed"] = False
            r["score"] = 0
            r["message"] = (r.get("message", "") + "；" if r.get("message") else "") + "invalid result counted as failed"
    passed = sum(1 for r in rubrics if r.get("passed"))
    total = len(rubrics)
    score = round(passed / total, 4) if total else 0.0

    # agent usage
    usage_path = output_dir / "agent_usage.json"
    if usage_path.exists():
        try:
            agent = json.loads(usage_path.read_text(encoding="utf-8"))
        except Exception:
            agent = {"usage_available": False, "reason": "agent_usage.json unparsable"}
    else:
        agent = {"usage_available": False, "reason": "agent_usage.json missing"}

    infra_agent = (output_dir / ".infra_failure_agent").exists()
    infra_env = (output_dir / ".infra_failure_env").exists()
    infra_network = (output_dir / ".infra_failure_network").exists()
    retryable = infra_agent or infra_env or infra_network or llm_judge_infra_failure

    summary = f"{passed}/{total} passed"
    if invalid_count:
        summary += f" ({invalid_count} invalid counted as failed)"
    if llm_judge_infra_failure:
        summary += " [INFRA: LLM judge failure, rerun required]"
    if infra_agent:
        summary += " [INFRA: agent runtime failure, see run_error.log]"
    elif infra_env:
        summary += " [INFRA: environment failure, see test_output.txt]"
    elif infra_network:
        summary += " [INFRA: network failure during dependency install]"

    result = {
        "version": "1.0",
        "score": score,
        "max_score": 1.0,
        "summary": summary,
        "rubrics": rubrics,
        "agent": agent,
        "metadata": {
            "raw_score": passed,
            "raw_max_score": total,
            "invalid_rubrics": invalid_count,
            "llm_judge_infra_failure": llm_judge_infra_failure,
            "retryable_infra_failure": retryable,
            "infra_flags": {"agent": infra_agent, "env": infra_env,
                            "network": infra_network},
            "groups": {
                "static": [r["id"] for r in rubrics if r["id"].startswith("S")],
                "integration": [r["id"] for r in rubrics if r["id"].startswith("I")],
                "llm_review": [r["id"] for r in rubrics if r["id"].startswith("L")],
            },
        },
    }
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[result] score={score} ({summary})")
    for r in rubrics:
        mark = "INVALID" if r.get("invalid") else ("PASS" if r.get("passed") else "FAIL")
        msg = f" — {r.get('message')}" if r.get("message") else ""
        print(f"  [{mark}] {r['id']} {r.get('name')}{msg}")


if __name__ == "__main__":
    main()
