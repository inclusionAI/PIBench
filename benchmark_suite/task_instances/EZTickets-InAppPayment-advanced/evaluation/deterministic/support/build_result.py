#!/usr/bin/env python3
"""Merge phase check files for the EZTickets In-App Payment advanced task.

The rubric definitions are intentionally kept in this script so the tests/
directory matches the EZ Tickets case layout without an extra rubric file.
Some spec rubric IDs intentionally appear in more than one phase, so merging is
phase-aware instead of using a single global id map.
"""
import json
import os
import sys
from pathlib import Path

RUBRIC_DEFS = {
    "static": [
        {
            "id": "S1",
            "name": "支付 SDK 与网关配置能力",
            "dimension": "security",
            "weight": 1,
            "desc": "项目依赖或代码中存在支付宝支付、查单、退款、退款查询、验签所需能力，并能从运行期环境变量读取网关和密钥配置。"
        },
        {
            "id": "S2",
            "name": "禁止固定成功或绕过验签",
            "dimension": "security",
            "weight": 1,
            "desc": "代码中不存在无条件验签成功、固定查询成功、固定退款成功、客户端回调直接 paid 等绕过。"
        },
        {
            "id": "S3",
            "name": "密钥与生产配置不泄漏",
            "dimension": "security",
            "weight": 1,
            "desc": "仓库中不包含生产私钥、生产证书、真实 token 或生产 .env，业务代码不得硬编码密钥或网关。"
        },
        {
            "id": "S4",
            "name": "支付与退款状态模型",
            "dimension": "security",
            "weight": 1,
            "desc": "订单、支付请求、退款请求或等价状态记录能表达 pending、paid、failed、refunding、partially_refunded、refunded 等状态。"
        },
        {
            "id": "S5",
            "name": "买家身份与订单归属模型",
            "dimension": "security",
            "weight": 1,
            "desc": "订单记录或支付记录中保存可用于比对的买家身份、支付宝用户标识或等价 owner 信息。"
        },        {
            "id": "S6",
            "name": "客户端结果仅触发服务端确认",
            "dimension": "security",
            "weight": 1,
            "desc": "Flutter 从支付宝返回后只能调用后端 confirm/sync 获取最终状态，不得仅凭客户端 resultStatus 直接履约。"
        }
    ],
    "integration": [
        {
            "id": "I1",
            "name": "基础接口契约与支付查询",
            "dimension": "functionality",
            "weight": 1,
            "desc": "后端可启动，movies、支付创建、支付查询和通知入口可访问，并使用 ALIPAY_GATEWAY。"
        },
        {
            "id": "I2",
            "name": "客户端成功回调不能直接履约",
            "dimension": "security",
            "weight": 1,
            "desc": "支付不能仅凭客户端结果变为 paid。"
        },
        {
            "id": "I3",
            "name": "失败或取消回调不能覆盖终态",
            "dimension": "security",
            "weight": 1,
            "desc": "已 paid 支付收到取消、失败或超时前端结果后终态不被覆盖。"
        },
        {
            "id": "I4",
            "name": "无效签名通知必须拒绝",
            "dimension": "security",
            "weight": 1,
            "desc": "伪造签名、缺少签名或验签失败通知不得推进状态。"
        },
        {
            "id": "I5",
            "name": "通知关键字段不匹配必须拒绝",
            "dimension": "security",
            "weight": 1,
            "desc": "签名通过但关键字段不匹配的通知不得推进状态。"
        },
        {
            "id": "I6",
            "name": "跨用户订单操作必须拒绝",
            "dimension": "security",
            "weight": 1,
            "desc": "A 用户支付信息不能推进 B 用户订单。"
        },
        {
            "id": "I7",
            "name": "有效通知推进支付成功",
            "dimension": "security",
            "weight": 1,
            "desc": "签名有效且字段匹配的支付成功通知推进支付与订单，且幂等。"
        },
        {
            "id": "I8",
            "name": "查单补偿推进支付成功",
            "dimension": "security",
            "weight": 1,
            "desc": "未收到通知时 sync 查询成功可推进支付状态。"
        },
        {
            "id": "I9",
            "name": "处理中状态保持 pending",
            "dimension": "security",
            "weight": 1,
            "desc": "处理中/未知状态保持 pending。"
        },
        {
            "id": "I10",
            "name": "待支付订单防重复支付",
            "dimension": "security",
            "weight": 1,
            "desc": "同一 pending 订单重复支付创建不生成第二笔有效支付。"
        },
        {
            "id": "I11",
            "name": "终态不被旧通知覆盖",
            "dimension": "security",
            "weight": 1,
            "desc": "已 paid/refunded 后旧失败通知、取消回调或旧查询结果不能覆盖终态。"
        },
        {
            "id": "I12",
            "name": "重复通知或查单幂等",
            "dimension": "security",
            "weight": 1,
            "desc": "重复通知、查单或履约只产生一次业务效果。"
        },
        {
            "id": "I13",
            "name": "退款请求调用支付宝网关",
            "dimension": "security",
            "weight": 1,
            "desc": "已支付订单退款通过支付宝退款 service/client 向运行期 ALIPAY_GATEWAY 发起退款请求。"
        },
        {
            "id": "I14",
            "name": "退款请求号幂等策略",
            "dimension": "security",
            "weight": 1,
            "desc": "同一次退款重试保持同一请求号；多次部分退款使用不同请求号。"
        },
        {
            "id": "I15",
            "name": "部分退款与全额退款状态",
            "dimension": "security",
            "weight": 1,
            "desc": "部分退款后不误标全额退款；全额退款后进入正确终态。"
        },
        {
            "id": "I16",
            "name": "金额一致性与超额退款防护",
            "dimension": "security",
            "weight": 1,
            "desc": "系统区分金额口径，拒绝金额不一致通知和超额退款。"
        },
        {
            "id": "I17",
            "name": "通知 app/seller 身份错配必须拒绝",
            "dimension": "security",
            "weight": 1,
            "desc": "签名有效但 app_id、seller_id 或等价收款方身份与服务端配置不一致时，不得推进支付成功。"
        },
        {
            "id": "I18",
            "name": "通知买家身份错配必须拒绝",
            "dimension": "security",
            "weight": 1,
            "desc": "签名有效但买家身份与本地订单归属不一致时，不得推进支付成功。"
        },
        {
            "id": "I19",
            "name": "paid 终态不被后续查单降级",
            "dimension": "security",
            "weight": 1,
            "desc": "支付已确认成功后，后续查询返回等待、关闭或未知状态时，不得覆盖 paid 终态。"
        },
        {
            "id": "I20",
            "name": "fund_change=N 不得当作最终退款成功",
            "dimension": "security",
            "weight": 1,
            "desc": "退款接口 code=10000 但 fund_change=N 时，不得累计已退金额或推进为最终退款状态。"
        },
        {
            "id": "I21",
            "name": "退款查询不确定时保持 pending/refunding",
            "dimension": "security",
            "weight": 1,
            "desc": "退款查询返回处理中、未知或资金未变化时，应保持非终态并继续确认，不得直接视为退款完成。"
        },
        {
            "id": "I22",
            "name": "同一退款请求号不同金额必须拒绝",
            "dimension": "security",
            "weight": 1,
            "desc": "同一个 out_request_no 被复用为不同退款金额时，应拒绝或保持原请求语义，不能覆盖原退款记录。"
        },
        {
            "id": "I23",
            "name": "多次部分退款累计不得超过已付金额",
            "dimension": "security",
            "weight": 1,
            "desc": "多次部分退款必须使用可区分请求号并受已付金额上限约束，累计超过已付金额必须拒绝。"
        },
        {
            "id": "I24",
            "name": "未支付订单禁止退款",
            "dimension": "security",
            "weight": 1,
            "desc": "pending/WAIT_BUYER_PAY 等未支付订单调用退款应被业务拒绝，且不得调用 alipay.trade.refund。"
        },
        {
            "id": "I25",
            "name": "跨用户禁止退款",
            "dimension": "security",
            "weight": 1,
            "desc": "非订单归属用户对已支付订单发起退款应被业务拒绝，且不得调用 alipay.trade.refund。"
        }
    ],
    "unit": [
        {
            "id": "U1",
            "name": "后端 npm test 基础回归",
            "dimension": "functionality",
            "weight": 1,
            "desc": "ez_tickets_backend 的 npm test 能通过；该项单独记录基础回归健康度，不作为所有安全单元覆盖项的一票否决条件。"
        },
        {
            "id": "U2",
            "name": "通知字段校验单元覆盖",
            "dimension": "security",
            "weight": 1,
            "desc": "能拒绝订单号、交易号、买家、金额、应用身份、收款方或交易状态不匹配的通知。"
        },
        {
            "id": "U3",
            "name": "订单归属校验单元覆盖",
            "dimension": "security",
            "weight": 1,
            "desc": "能拒绝买家身份与订单 owner 不匹配的支付结果。"
        },
        {
            "id": "U4",
            "name": "终态状态机单元覆盖",
            "dimension": "security",
            "weight": 1,
            "desc": "paid/refunded 等终态不会被旧通知、失败查询或客户端回调覆盖。"
        },
        {
            "id": "U5",
            "name": "退款请求号策略单元覆盖",
            "dimension": "security",
            "weight": 1,
            "desc": "同一次退款重试请求号不变，多次部分退款请求号不同。"
        },
        {
            "id": "U6",
            "name": "退款金额计算单元覆盖",
            "dimension": "security",
            "weight": 1,
            "desc": "能正确计算可退、已退、部分退款比例和超额退款拒绝。"
        }
    ],
    "llm": [
        {
            "id": "L1",
            "name": "无固定成功或绕过",
            "dimension": "security",
            "weight": 1,
            "desc": "没有固定成功、无条件验签、客户端回调直接 paid、退款不调用外部能力等实现。"
        },
        {
            "id": "L2",
            "name": "未知状态补偿",
            "dimension": "security",
            "weight": 1,
            "desc": "支付或退款未知状态有查询、重试或人工处理路径，且使用运行期支付宝网关配置。"
        },
        {
            "id": "L3",
            "name": "金额口径",
            "dimension": "security",
            "weight": 1,
            "desc": "实付、商户实收、可退、已退、部分退款不会混用单一金额字段。"
        },
        {
            "id": "L4",
            "name": "客户端结果不直接履约",
            "dimension": "security",
            "weight": 1,
            "desc": "APP 支付回调返回结果不会直接驱动最终履约，只能触发服务端确认流程。"
        }
    ]
}

PHASE_FILES = {
    "static": "static.json",
    "integration": "integration.json",
    "unit": "unit.json",
    "llm": "llm.json",
}

CATEGORY_NAMES = {
    "static": "静态测试",
    "integration": "集成测试",
    "unit": "单元测试",
    "llm": "LLM Judge",
}


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def load_phase_results(checks_dir, filename):
    data = load_json(checks_dir / filename, {"rubrics": []})
    by_id = {}
    for rubric in data.get("rubrics", []):
        by_id.setdefault(rubric.get("id"), []).append(rubric)
    return by_id


def main():
    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/output")
    checks_dir = output_dir / "checks"
    rubric_defs = RUBRIC_DEFS

    phase_results = {
        phase: load_phase_results(checks_dir, filename)
        for phase, filename in PHASE_FILES.items()
    }
    phase_offsets = {phase: {} for phase in PHASE_FILES}

    rubrics = []
    for phase in ("static", "integration", "unit", "llm"):
        for definition in rubric_defs.get(phase, []):
            rid = definition["id"]
            candidates = phase_results.get(phase, {}).get(rid, [])
            idx = phase_offsets[phase].get(rid, 0)
            phase_offsets[phase][rid] = idx + 1
            if idx < len(candidates):
                rubric = dict(candidates[idx])
            else:
                rubric = {
                    "id": rid,
                    "name": definition.get("name", rid),
                    "dimension": definition.get("dimension", "security"),
                    "type": phase,
                    "passed": False,
                    "score": 0,
                    "max_score": definition.get("weight", 1),
                    "message": f"{PHASE_FILES[phase]} 阶段未产出该项结果，见 test_output.txt",
                    "evidence": ["test_output.txt"],
                }

            max_score = definition.get("weight", rubric.get("max_score", 1))
            rubric["id"] = rid
            rubric["name"] = definition.get("name", rid)
            rubric.setdefault("dimension", definition.get("dimension", "security"))
            rubric.setdefault("type", phase)
            rubric["max_score"] = max_score
            if rubric.get("status") == "invalid" or rubric.get("invalid"):
                msg = rubric.get("message", "")
                prefix = "测试前置条件未满足，按失败计入分母"
                rubric["message"] = f"{prefix}: {msg}" if msg else prefix
                rubric["passed"] = False
            rubric["invalid"] = False
            rubric["score"] = max_score if rubric.get("passed") else 0
            rubric["phase"] = phase
            rubric["category"] = phase
            rubric["category_name"] = CATEGORY_NAMES.get(phase, phase)
            rubric.setdefault("spec_desc", definition.get("desc", ""))
            rubrics.append(rubric)

    valid = [r for r in rubrics if not r.get("invalid")]
    passed = sum(1 for r in valid if r.get("passed"))
    total = len(valid)
    earned = sum(float(r.get("score", 0)) for r in valid)
    max_total = sum(float(r.get("max_score", 1)) for r in valid)
    invalid_count = len(rubrics) - len(valid)
    score = round(earned / max_total, 4) if max_total else 0.0

    usage_path = output_dir / "agent_usage.json"
    agent = load_json(usage_path, {
        "usage_available": False,
        "reason": "agent_usage.json missing",
    })

    infra_flags = {
        "agent": (output_dir / ".infra_failure_agent").exists()
        or (output_dir / "agent_infra_failure.json").exists(),
        "env": (output_dir / ".infra_failure_env").exists(),
        "network": (output_dir / ".infra_failure_network").exists(),
        "llm_judge": (output_dir / "llm_judge_infra_failure.json").exists(),
    }

    summary = f"{passed}/{total} passed"
    if invalid_count:
        summary += f" ({invalid_count} invalid converted to failures)"
    if any(infra_flags.values()):
        summary += " [infra flag present]"
    if infra_flags["llm_judge"]:
        summary += " [LLM judge failure, rerun required]"

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
            "weighted_earned": earned,
            "weighted_valid_total": max_total,
            "invalid_rubrics": invalid_count,
            "retryable_infra_failure": any(infra_flags.values()),
            "llm_judge_infra_failure": infra_flags["llm_judge"],
            "infra_flags": infra_flags,
            "case": os.environ.get("PAYSKILLS_CASE_NAME", "EZTickets-InAppPayment-advanced"),
            "rubric_source": "tests/build_result.py",
            "groups": {
                "static": [r["id"] for r in rubrics if r.get("category") == "static"],
                "integration": [r["id"] for r in rubrics if r.get("category") == "integration"],
                "unit": [r["id"] for r in rubrics if r.get("category") == "unit"],
                "llm_judge": [r["id"] for r in rubrics if r.get("category") == "llm"],
            },
            "group_names": CATEGORY_NAMES,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[result] {summary}; score={score}")


if __name__ == "__main__":
    main()
