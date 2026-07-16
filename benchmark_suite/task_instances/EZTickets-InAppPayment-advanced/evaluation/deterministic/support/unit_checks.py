#!/usr/bin/env python3
"""Summarize unit-level coverage expectations for the safety case.

The backend's npm test result is reported as its own rubric. The five safety
unit rubrics below stay diagnostic: they check whether targeted unit coverage
exists for each safety concern instead of all failing behind one global gate.
"""
import json
import re
import sys
from pathlib import Path


def iter_test_files(project):
    for root in ("ez_tickets_backend/test", "ez_tickets_backend/tests", "ez_tickets_app/test"):
        directory = project / root
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix in (".js", ".dart"):
                    yield path


def main():
    project = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    npm_passed = sys.argv[3].lower() == "true" if len(sys.argv) > 3 else False
    files = list(iter_test_files(project))
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in files)
    low = text.lower()

    checks = [
        ("U2", "通知字段校验单元覆盖", "notify|notification|sign|signature|seller_id|app_id|total_amount"),
        ("U3", "订单归属校验单元覆盖", "user_id|owner|booking_ids|buyer_user_id|buyer_logon_id"),
        ("U4", "终态状态机单元覆盖", "terminal|final|confirmed|refunded|trade_closed|trade_finished"),
        ("U5", "退款请求号策略单元覆盖", "refund_request_no|out_request_no|refund.*idempot"),
        ("U6", "退款金额计算单元覆盖", "refund.*amount|partial.*refund|remaining.*amount"),
    ]

    evidence = [str(path.relative_to(project)) for path in files[:8]]
    rubrics = [{
        "id": "U1",
        "name": "后端 npm test 基础回归",
        "dimension": "functionality",
        "type": "unit",
        "passed": npm_passed,
        "score": 1 if npm_passed else 0,
        "max_score": 1,
        "message": "" if npm_passed else "npm test 未通过，见 npm_test.log；该项单独扣分，不再导致所有安全单元覆盖项清零",
        "evidence": ["npm_test.log"] + evidence[:4],
    }]
    for rid, name, pattern in checks:
        matched = bool(re.search(pattern, low, re.I))
        passed = matched
        if passed and npm_passed:
            message = ""
        elif passed:
            message = "检测到对应单元覆盖关键词，但 npm test 未通过；基础单测失败已由 U1 单独记录"
        else:
            message = "未在单元测试中发现对应安全逻辑覆盖"
        rubrics.append({
            "id": rid,
            "name": name,
            "dimension": "security",
            "type": "unit",
            "passed": passed,
            "score": 1 if passed else 0,
            "max_score": 1,
            "message": message,
            "evidence": evidence,
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"rubrics": rubrics}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[unit] {sum(1 for r in rubrics if r['passed'])}/{len(rubrics)} passed")


if __name__ == "__main__":
    main()
