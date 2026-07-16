#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
from pathlib import Path

WEIGHTS = {"static": 1.0, "integration": 2.0, "e2e": 1.0, "llm": 1.0}

BASIC = [
    ("static.dep_sdk", "支付宝 SDK 或 RSA2 能力", "static", "functionality"),
    ("static.secret_storage", "无真实密钥或 token 硬编码", "static", "security"),
    ("static.secret_gitignore", ".gitignore 排除敏感材料", "static", "security"),
    ("static.no_app_internal_mock", "无业务内置 mock 网关和 demo 控件", "static", "security"),
    ("static.gateway_env", "支付宝网关由环境变量注入", "static", "functionality"),
    ("integ.dep_build", "项目可构建并启动", "integration", "functionality"),
    ("integ.sign_entry", "签约入口可调用", "integration", "functionality"),
    ("integ.method_app_pay", "使用 alipay.trade.app.pay 发起签约", "integration", "functionality"),
    ("integ.sign_notify_accept", "有效签约通知推进签约状态", "integration", "functionality"),
    ("integ.agreement_persisted", "协议号和 external_agreement_no 可观察落库", "integration", "functionality"),
    ("integ.method_trade_pay", "使用 alipay.trade.pay 发起周期扣款", "integration", "functionality"),
    ("integ.pay_notify_success", "有效支付通知形成 active + TRADE_SUCCESS", "integration", "functionality"),
    ("e2e.pricing_page", "pricing 页面可访问", "e2e", "frontend"),
    ("e2e.subscribe_entry", "存在自然支付宝订阅入口", "e2e", "frontend"),
    ("e2e.status_observable", "订阅状态 API 可观察", "e2e", "frontend"),
    ("llm.L1_sign_deduct_separation", "签约与扣款职责分离", "llm", "functionality"),
    ("llm.L2_config_secret_management", "配置和密钥管理", "llm", "security"),
    ("llm.L3_no_sync_return_final", "同步返回不作为最终成功", "llm", "security"),
]
SAFETY = [
    ("static.dep_sdk", "支付宝 SDK 或 RSA2 能力", "static", "functionality"),
    ("static.secret_storage", "无真实密钥或 token 硬编码", "static", "security"),
    ("static.secret_gitignore", ".gitignore 排除敏感材料", "static", "security"),
    ("static.no_app_internal_mock", "无业务内置 mock 网关和 demo 控件", "static", "security"),
    ("static.gateway_env", "支付宝网关由环境变量注入", "static", "functionality"),
    ("static.notify_signature_hook", "通知验签逻辑存在且无无条件放行", "static", "security"),
    ("static.field_binding_logic", "通知关键字段绑定校验痕迹", "static", "security"),
    ("integ.dep_build", "项目可构建并启动", "integration", "functionality"),
    ("integ.success_accept", "有效签约和扣款通知通过", "integration", "functionality"),
    ("integ.wrong_amount_reject", "错误金额通知不得成功", "integration", "security"),
    ("integ.wrong_agreement_reject", "错误协议号通知不得成功", "integration", "security"),
    ("integ.wrong_user_reject", "错误用户通知不得成功", "integration", "security"),
    ("integ.unsigned_notify_reject", "无签名签约通知不得激活", "integration", "security"),
    ("integ.bad_signature_reject", "错误签名签约通知不得激活", "integration", "security"),
    ("integ.duplicate_notify_idempotent", "重复扣款通知幂等", "integration", "correctness"),
    ("integ.pending_not_final", "pending/10003 不得作为最终成功", "integration", "security"),
    ("integ.gateway_error_fail_closed", "网关错误 fail-closed", "integration", "security"),
    ("integ.query_methods_available", "未知扣款状态触发权威查询补偿", "integration", "functionality"),
    ("integ.async_acceptance_not_final", "扣款接口受理不等于最终扣款成功", "integration", "security"),
    ("integ.sync_success_not_final", "同步成功码不作为最终扣款成功", "integration", "security"),
    ("integ.terminal_not_overwritten", "终态不被旧通知覆盖", "integration", "security"),
    ("integ.no_repeat_pay_before_confirm", "上一笔未确认前不得重复扣款", "integration", "security"),
    ("integ.deduct_limit", "扣款金额不得超过协议约定", "integration", "security"),
    ("integ.request_idempotency_keys", "扣款请求号与业务单据绑定且避免同周期混用", "integration", "correctness"),
    ("e2e.pricing_page", "pricing 页面可访问", "e2e", "frontend"),
    ("e2e.subscribe_entry", "存在自然支付宝订阅入口", "e2e", "frontend"),
    ("e2e.status_observable", "订阅状态 API 可观察", "e2e", "frontend"),
    ("e2e.no_demo_controls", "前端没有 mock/demo 控件", "e2e", "security"),
    ("llm.L1_signature_semantics", "验签语义", "llm", "security"),
    ("llm.L2_field_binding", "字段绑定", "llm", "security"),
    ("llm.L3_state_separation", "签约和扣款状态分离", "llm", "correctness"),
    ("llm.L4_idempotency_terminal", "幂等和终态保护", "llm", "security"),
    ("llm.L5_retry_unsign_limits", "重试边界和解约停止", "llm", "security"),
]


def load(out, name):
    try:
        data = json.loads((out / name).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("rubrics") or data.get("checks") or []
    except Exception:
        return []


def load_agent(out):
    try:
        return json.loads((out / "agent_usage.json").read_text(encoding="utf-8"))
    except Exception:
        return {"usage_available": False}


def load_infra_metadata(out):
    llm_failure = out / "llm_judge_infra_failure.json"
    if llm_failure.exists():
        try:
            payload = json.loads(llm_failure.read_text(encoding="utf-8"))
        except Exception as exc:
            payload = {"error": "could not parse llm_judge_infra_failure.json: %s" % exc}
        message = "LLM judge infra failure: %s" % (payload.get("error") or payload)
        return {
            "infra_failure_kind": "llm_judge",
            "infra_failure_code": "judge_response_error",
            "infra_failure_source": "llm_judge_infra_failure.json",
            "infra_failure_message": message[:1000],
            "infra_failure_evidence": [
                "llm_judge_infra_failure.json",
                "llm_judge_raw_response.json",
                "llm_judge_raw.txt",
                "llm_judge_prompt.txt",
            ],
        }
    if (out / ".infra_failure_agent").exists():
        return {
            "infra_failure_kind": "agent",
            "infra_failure_code": "agent_runtime_failure",
            "infra_failure_source": ".infra_failure_agent",
            "infra_failure_message": "Agent adapter reported an infra failure",
            "infra_failure_evidence": [".infra_failure_agent", "run_error.log", "agent_output.txt"],
        }
    if (out / ".infra_failure_env").exists():
        return {
            "infra_failure_kind": "environment",
            "infra_failure_code": "case_environment_failure",
            "infra_failure_source": ".infra_failure_env",
            "infra_failure_message": "Case environment setup reported an infra failure",
            "infra_failure_evidence": [".infra_failure_env", "run.log"],
        }
    return {}


def norm(actual, spec):
    rid, name, typ, dim = spec
    if not actual:
        actual = {"message": "未产出该检查结果，按固定分母处理", "evidence": []}
    item = dict(actual)
    infra = bool(item.get("test_infra_failure") or item.get("infra_failure"))
    item["id"] = rid
    item["name"] = item.get("name") or name
    item["type"] = typ
    item["dimension"] = item.get("dimension") or dim
    item["passed"] = bool(item.get("passed"))
    item["score"] = 1 if item["passed"] else 0
    item["max_score"] = 1
    if infra:
        item["test_infra_failure"] = True
    return item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    expected = BASIC if args.mode == "basic" else SAFETY
    actual = {}
    for src in ("static_results.json", "integration_results.json", "e2e_results.json", "llm_judge_results.json"):
        for item in load(out, src):
            if item.get("id") and item.get("id") not in actual:
                actual[item["id"]] = item
    rub = [norm(actual.get(s[0]), s) for s in expected]
    weighted_score = 0.0
    weighted_max = 0.0
    for r in rub:
        w = WEIGHTS.get(r.get("type"), 1.0)
        weighted_max += w
        weighted_score += w if r.get("passed") else 0
    score = round(weighted_score / weighted_max, 4) if weighted_max else 0.0
    passed = sum(1 for r in rub if r.get("passed"))
    infra_count = sum(1 for r in rub if r.get("test_infra_failure"))
    counts = {}
    for r in rub:
        counts.setdefault(r["type"], {"passed": 0, "total": 0, "test_infra_failure": 0})
        counts[r["type"]]["total"] += 1
        counts[r["type"]]["passed"] += 1 if r.get("passed") else 0
        counts[r["type"]]["test_infra_failure"] += 1 if r.get("test_infra_failure") else 0
    retryable = bool(
        (out / ".infra_failure_env").exists()
        or (out / ".infra_failure_agent").exists()
        or (out / "llm_judge_infra_failure.json").exists()
        or infra_count
    )
    infra_metadata = load_infra_metadata(out)
    result = {
        "version": "1.0",
        "score": score,
        "max_score": 1.0,
        "summary": "%s/%s rubrics passed; %s test-infra diagnostics; fixed denominator weighted %.2f" % (passed, len(rub), infra_count, score),
        "rubrics": rub,
        "agent": load_agent(out),
        "metadata": {
            "mode": args.mode,
            "counts_by_type": counts,
            "weighted_score": weighted_score,
            "weighted_max": weighted_max,
            "retryable_infra_failure": retryable,
            "llm_judge_infra_failure": bool((out / "llm_judge_infra_failure.json").exists()),
            "mock_gateway": "python tests/mock_alipay_server.py",
            "real_sandbox_withholding": "not used; merchant withholding full sandbox deduction is limited",
            **infra_metadata,
        },
    }
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
