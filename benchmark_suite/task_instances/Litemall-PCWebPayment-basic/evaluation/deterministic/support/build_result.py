#!/usr/bin/env python3
"""Build result.json for Litemall-PCWebPayment-basic from all check outputs."""
import json
import os
import sys

OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/output"

WEIGHTS = {
    "static": 1.0,
    "integration": 2.0,
    "e2e": 1.0,
    "llm": 1.0,
}

SOURCES = [
    "static_results.json",
    "integration_results.json",
    "e2e_results.json",
    "llm_judge_results.json",
]

EXPECTED = [
    ("static.sdk_dependency", "SDK 依赖 (alipay-sdk-java)", "static"),
    ("static.secret_no_hardcode", "无硬编码私钥", "static"),
    ("static.secret_gitignore", ".gitignore 排除敏感文件", "static"),
    ("integ.app_boot", "应用构建启动", "integration"),
    ("integ.order_flow_intact", "下单流程正常", "integration"),
    ("integ.prepay_form", "prepay 返回支付宝表单", "integration"),
    ("integ.prepay_gateway_url", "表单指向支付宝网关", "integration"),
    ("integ.prepay_product_code", "产品码正确", "integration"),
    ("integ.prepay_order_binding", "prepay 绑定真实订单", "integration"),
    ("integ.prepay_does_not_mark_paid", "prepay 不提前履约", "integration"),
    ("integ.notify_endpoint_exists", "notify 端点存在", "integration"),
    ("integ.notify_processes_success", "notify 处理成功", "integration"),
    ("integ.notify_updates_only_target", "notify 只更新对应订单", "integration"),
    ("integ.logic_api", "使用正确的支付宝 API (page.pay)", "integration"),
    ("E1", "Payment page shows Alipay option", "e2e"),
    ("E2", "Alipay payment redirect", "e2e"),
    ("L1", "SDK 调用模式", "llm"),
    ("L2", "前端表单提交", "llm"),
]


def load(name):
    path = os.path.join(OUTPUT_DIR, name)
    try:
        with open(path) as f:
            data = json.load(f)
            return data if isinstance(data, list) else data.get("rubrics", data.get("checks", []))
    except (OSError, ValueError, KeyError):
        return []


def main():
    found = {}
    for src in SOURCES:
        for rubric in load(src):
            rid = rubric.get("id")
            if rid:
                found[rid] = rubric

    all_rubrics = []
    for rid, name, rtype in EXPECTED:
        if rid in found:
            rubric = dict(found[rid])
            rubric.setdefault("name", name)
            rubric.setdefault("dimension", "functionality")
            rubric.setdefault("score", 1 if rubric.get("passed") else 0)
            rubric.setdefault("max_score", 1)
            rubric.setdefault("message", "")
        else:
            rubric = {
                "id": rid,
                "name": name,
                "dimension": "functionality",
                "type": rtype,
                "passed": False,
                "score": 0,
                "max_score": 1,
                "message": "评分阶段未产出该项结果，按失败计入分母",
            }
        rubric["id"] = rid
        rubric["type"] = rtype
        all_rubrics.append(rubric)

    weighted_score = 0.0
    weighted_max = 0.0
    for r in all_rubrics:
        rtype = r.get("type", "integration")
        w = WEIGHTS.get(rtype, 1.0)
        weighted_max += w
        if r.get("passed"):
            weighted_score += w

    score = round(weighted_score / weighted_max, 4) if weighted_max > 0 else 0.0
    passed = sum(1 for r in all_rubrics if r.get("passed"))
    total = len(all_rubrics)
    summary = f"{passed}/{total} passed (weighted score {score:.2f})"
    llm_judge_infra_failure = (
        os.path.exists(os.path.join(OUTPUT_DIR, "llm_judge_infra_failure.json"))
        or any(r.get("type") == "llm" and r.get("infra") for r in all_rubrics)
    )
    if llm_judge_infra_failure:
        summary += "; LLM judge infra failure, rerun required"

    result = {
        "version": "1.0",
        "score": score,
        "max_score": 1.0,
        "summary": summary,
        "rubrics": all_rubrics,
        "agent": {"usage_available": False},
        "metadata": {"raw_passed": passed, "raw_total": total,
                     "weighted_score": weighted_score, "weighted_max": weighted_max,
                     "retryable_infra_failure": llm_judge_infra_failure,
                     "llm_judge_infra_failure": llm_judge_infra_failure},
    }

    # Try to load usage
    usage_path = os.path.join(OUTPUT_DIR, "agent_usage.json")
    if os.path.exists(usage_path):
        try:
            result["agent"] = json.load(open(usage_path))
        except (ValueError, OSError):
            pass

    with open(os.path.join(OUTPUT_DIR, "result.json"), "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Result written: score={score} ({summary})")


if __name__ == "__main__":
    main()
