#!/usr/bin/env python3
"""Static checks for the EZ Tickets Alipay safety case."""
import json
import re
import sys
from pathlib import Path

TEXT_EXTS = {".js", ".json", ".dart", ".yaml", ".yml", ".sql", ".md", ".env"}
SKIP_DIRS = {"node_modules", ".git", ".dart_tool", "build", "coverage"}


def iter_files(root):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and (path.suffix in TEXT_EXTS or path.name in (".env", "Procfile")):
            yield path


def read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def evidence(files, pattern, project, max_hits=5):
    rx = re.compile(pattern, re.IGNORECASE)
    hits = []
    for path in files:
        text = read(path)
        for lineno, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append(f"{path.relative_to(project)}:{lineno}: {line.strip()[:160]}")
                if len(hits) >= max_hits:
                    return hits
    return hits


def main():
    project = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    files = []
    for root in (
        "ez_tickets_backend/src",
        "ez_tickets_backend/routes",
        "ez_tickets_backend/test",
        "ez_tickets_backend/tests",
        "ez_tickets_backend/migrations",
        "ez_tickets_app/lib",
        "ez_tickets_app/test",
    ):
        directory = project / root
        if directory.exists():
            files.extend(iter_files(directory))
    schema = project / "ez_tickets_backend" / "ez_tickets.sql"
    if schema.exists():
        files.append(schema)
    package_json = project / "ez_tickets_backend" / "package.json"
    if package_json.exists():
        files.append(package_json)
    pubspec = project / "ez_tickets_app" / "pubspec.yaml"
    if pubspec.exists():
        files.append(pubspec)

    src_files = [f for f in files if "/test/" not in str(f) and "/tests/" not in str(f)]
    text = "\n".join(read(path) for path in files)
    src_text = "\n".join(read(path) for path in src_files)
    low = text.lower()

    def has_route(pattern):
        return re.search(pattern, text, re.I) is not None

    rubrics = []

    def rec(rid, name, passed, message, ev_pattern):
        rubrics.append({
            "id": rid,
            "name": name,
            "dimension": "security",
            "type": "static",
            "passed": bool(passed),
            "score": 1 if passed else 0,
            "max_score": 1,
            "message": "" if passed else message,
            "evidence": evidence(files, ev_pattern, project),
        })

    rec(
        "S1",
        "支付/查单/退款/验签客户端能力",
        ("alipay-sdk" in low or "alipay" in low)
        and ("trade.query" in low or "tradequery" in low or "alipay.trade.query" in low)
        and ("trade.refund" in low or "traderefund" in low or "refund" in low)
        and ("checknotifysign" in low or "verifynotify" in low or "rsa-sha256" in low),
        "需要同时具备支付、查单、退款、验签能力",
        r"alipay-sdk|trade\.query|tradeQuery|trade\.refund|refund|checkNotify|verifyNotify|RSA-SHA256",
    )
    rec(
        "S2",
        "不允许 fake 成功绕过",
        not re.search(r"dev_auto_confirm\s*[:=]\s*true|return\s+['\"]TRADE_SUCCESS['\"]|fake.*success|bypass.*pay", src_text, re.I),
        "发现疑似固定成功、fake success 或支付绕过逻辑",
        r"DEV_AUTO_CONFIRM|TRADE_SUCCESS|fake|bypass|mockSuccess",
    )
    rec(
        "S3",
        "不泄漏生产密钥且不硬编码沙箱配置",
        not any(
            "openapi-sandbox.dl.alipaydev.com" in read(path)
            for path in files
            if "ez_tickets_backend/src" in str(path)
        ),
        "业务代码不应硬编码支付宝沙箱网关，应读取 ALIPAY_GATEWAY",
        r"ALIPAY_GATEWAY|alipay-sandbox-keys|openapi-sandbox|PRIVATE_KEY|PUBLIC_KEY",
    )
    rec(
        "S4",
        "支付/退款状态模型清晰",
        any(x in low for x in ("refunding", "partially_refunded", "refunded", "refund_status", "refunds"))
        and any(x in low for x in ("pending", "paid", "failed", "trade_success", "wait_buyer_pay")),
        "需要表达支付状态与退款状态，避免只有单一 confirmed/cancelled",
        r"refunding|partially_refunded|refunded|refund_status|pending|paid|WAIT_BUYER_PAY|TRADE_SUCCESS",
    )
    rec(
        "S5",
        "买家身份与订单归属可校验",
        ("user_id" in low and ("currentuser" in low or "current_user" in low or "buyer_user_id" in low or "buyer_logon_id" in low))
        and ("booking_ids" in low or "booking_id" in low),
        "需要校验当前用户、订单归属和支付宝买家身份或等价字段",
        r"user_id|currentUser|buyer_user_id|buyer_logon_id|booking_ids|booking_id",
    )
    rec(
        "S6",
        "前端不信任本地支付结果",
        ("alipay/confirm" in low or "confirmalipay" in low)
        and not re.search(r"(payResult|resultStatus).{0,120}(confirmed|booking_status\s*=\s*['\"]confirmed)", text, re.I | re.S),
        "Flutter 应从支付宝返回后调用后端确认，不应直接按本地 resultStatus 履约",
        r"alipay/confirm|confirmAlipay|resultStatus|payResult|TRADE_SUCCESS",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"rubrics": rubrics}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[static] {sum(1 for r in rubrics if r['passed'])}/{len(rubrics)} passed")


if __name__ == "__main__":
    main()
