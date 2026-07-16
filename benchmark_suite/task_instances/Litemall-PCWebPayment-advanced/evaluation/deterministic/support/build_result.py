#!/usr/bin/env python3
"""Build result.json for litemall-pc-advanced from all check outputs."""
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

EXPECTED_RUBRICS = [
    {"id": "static.secret_no_hardcode", "name": "无硬编码密钥材料", "type": "static", "dimension": "security"},
    {"id": "static.secret_gitignore", "name": ".gitignore 排除敏感文件", "type": "static", "dimension": "security"},
    {"id": "static.refund_sdk_usage", "name": "退款使用 SDK (AlipayTradeRefundRequest)", "type": "static", "dimension": "security"},
    {"id": "integ.app_boot", "name": "应用构建启动", "type": "integration", "dimension": "functionality"},
    {"id": "integ.prepay_form", "name": "prepay 返回支付宝表单", "type": "integration", "dimension": "functionality"},
    {"id": "integ.prepay_hits_mock", "name": "prepay 请求到达 mock 网关", "type": "integration", "dimension": "functionality"},
    {"id": "integ.notify_rejects_unsigned", "name": "无签名通知被拒", "type": "integration", "dimension": "security"},
    {"id": "integ.notify_rejects_wrong_amount", "name": "金额篡改通知被拒", "type": "integration", "dimension": "security"},
    {"id": "integ.notify_rejects_wrong_appid", "name": "app_id 篡改通知被拒", "type": "integration", "dimension": "security"},
    {"id": "integ.notify_signed_success", "name": "有效签名通知通过", "type": "integration", "dimension": "correctness"},
    {"id": "integ.notify_idempotent", "name": "通知幂等", "type": "integration", "dimension": "correctness"},
    {"id": "integ.terminal_not_downgraded", "name": "终态不被覆盖", "type": "integration", "dimension": "security"},
    {"id": "integ.return_url_not_final", "name": "return_url 不作终态", "type": "integration", "dimension": "security"},
    {"id": "integ.query_endpoint", "name": "查询端点存在", "type": "integration", "dimension": "functionality"},
    {"id": "integ.refund_endpoint", "name": "退款端点存在", "type": "integration", "dimension": "functionality"},
    {"id": "integ.notify_wrong_order", "name": "不存在订单号的通知被拒", "type": "integration", "dimension": "security"},
    {"id": "integ.prepay_out_trade_no_matches", "name": "prepay 使用真实订单号", "type": "integration", "dimension": "correctness"},
    {"id": "integ.refund_idempotent", "name": "退款幂等 (out_request_no)", "type": "integration", "dimension": "correctness"},
    {"id": "integ.refund_partial_sequence", "name": "部分退款请求号与金额", "type": "integration", "dimension": "correctness"},
    {"id": "integ.refund_over_amount_rejected", "name": "超额退款被拒", "type": "integration", "dimension": "security"},
    {"id": "integ.refund_cumulative_over_amount_rejected", "name": "累计超额退款被拒", "type": "integration", "dimension": "security"},
    {"id": "integ.refund_fund_change_n_not_final", "name": "fund_change=N 不作为最终退款", "type": "integration", "dimension": "security"},
    {"id": "integ.query_unknown_not_paid", "name": "查询未知/待支付不入账", "type": "integration", "dimension": "security"},
    {"id": "integ.paid_order_close_rejected", "name": "已支付订单不能关单", "type": "integration", "dimension": "security"},
    {"id": "integ.close_failure_not_cancelled", "name": "关单失败不取消本地订单", "type": "integration", "dimension": "security"},
    {"id": "integ.close_endpoint", "name": "关单端点存在", "type": "integration", "dimension": "functionality"},
    {"id": "E1", "name": "前端支付宝选项", "type": "e2e", "dimension": "frontend"},
    {"id": "E2", "name": "支付跳转", "type": "e2e", "dimension": "frontend"},
    {"id": "L1_notify_signature", "name": "异步通知验签", "type": "llm", "dimension": "security"},
    {"id": "L2_notify_field_validation", "name": "异步通知关键字段校验", "type": "llm", "dimension": "security"},
    {"id": "L3_notify_idempotency_terminal", "name": "通知幂等与终态保护", "type": "llm", "dimension": "correctness"},
    {"id": "L4_return_url_query_compensation", "name": "return_url 不履约与查询补偿", "type": "llm", "dimension": "security"},
    {"id": "L5_refund_request_no", "name": "退款请求号与部分退款", "type": "llm", "dimension": "correctness"},
    {"id": "L6_refund_query_uncertain", "name": "退款查询与不确定状态处理", "type": "llm", "dimension": "correctness"},
    {"id": "L7_close_paid_boundary", "name": "关单与已支付边界", "type": "llm", "dimension": "correctness"},
    {"id": "L8_secret_management", "name": "密钥管理", "type": "llm", "dimension": "security"},
]


def load(name):
    path = os.path.join(OUTPUT_DIR, name)
    try:
        with open(path) as f:
            data = json.load(f)
            return data if isinstance(data, list) else data.get("rubrics", data.get("checks", []))
    except (OSError, ValueError, KeyError):
        return []


def normalize_result(actual, spec):
    if actual is None:
        actual = {
            "passed": False,
            "score": 0,
            "max_score": 1,
            "message": "未产出该检查结果，按失败计入固定分母",
            "evidence": [],
        }
    result = dict(actual)
    result["id"] = spec["id"]
    result["name"] = result.get("name") or spec["name"]
    result["type"] = spec["type"]
    result["dimension"] = result.get("dimension") or spec["dimension"]
    result["passed"] = bool(result.get("passed"))
    result["score"] = 1 if result["passed"] else 0
    result["max_score"] = 1
    return result


def main():
    actual_by_id = {}
    for src in SOURCES:
        for item in load(src):
            rid = item.get("id")
            if rid and rid not in actual_by_id:
                actual_by_id[rid] = item

    all_rubrics = [
        normalize_result(actual_by_id.get(spec["id"]), spec)
        for spec in EXPECTED_RUBRICS
    ]

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
