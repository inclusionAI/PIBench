#!/usr/bin/env python3
"""Static code checks S1-S10 for q1-alipay-basic.

Heuristic grep-style checks over the agent-modified workspace. Each rubric
records the matching file:line evidence so reviewers can audit pass decisions.
"""
import json
import re
import sys
from pathlib import Path

TEXT_EXTS = {
    ".js", ".json", ".dart", ".yaml", ".yml", ".sql", ".md", ".env", ".ts",
    ".kt", ".java", ".gradle", ".kts",
}
SKIP_DIRS = {"node_modules", ".git", ".dart_tool", "build", "google_fonts", "assets"}


def iter_files(root: Path):
    for p in root.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and (p.suffix in TEXT_EXTS or p.name in (".env", "Procfile")):
            yield p


def search(files, pattern, flags=re.IGNORECASE, max_hits=5):
    """Return list of 'relpath:lineno: snippet' for lines matching pattern."""
    rx = re.compile(pattern, flags)
    hits = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith(("//", "#", "*")):
                continue
            if rx.search(line):
                hits.append(f"{f}:{i}: {line.strip()[:160]}")
                if len(hits) >= max_hits:
                    return hits
    return hits


def main():
    workspace = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    backend = workspace / "ez_tickets_backend"
    app = workspace / "ez_tickets_app"

    backend_files = list(iter_files(backend)) if backend.exists() else []
    backend_src = [f for f in backend_files if "src" in f.parts and f.suffix == ".js"]
    app_lib = [f for f in iter_files(app / "lib")] if (app / "lib").exists() else []
    android_files = list(iter_files(app / "android")) if (app / "android").exists() else []
    pubspec = app / "pubspec.yaml"
    pkg_json = backend / "package.json"

    rubrics = []

    def add(rid, name, passed, message, evidence):
        rubrics.append({
            "id": rid, "name": name, "dimension": "functionality", "type": "hard",
            "passed": bool(passed), "score": 1 if passed else 0, "max_score": 1,
            "message": message, "evidence": evidence[:5],
        })

    # S1 backend alipay capability: SDK dep or RSA2 signing code
    dep_hits = search([pkg_json] if pkg_json.exists() else [], r"alipay")
    sign_hits = search(backend_src, r"alipay") and search(
        backend_src, r"RSA2|RSA-SHA256|sha256WithRSA|createSign|\bsign\b")
    add("S1", "后端支付宝能力（SDK 或 RSA2 签名）", bool(dep_hits or sign_hits),
        "" if (dep_hits or sign_hits) else "package.json 无 alipay 依赖，后端 src 也未发现支付宝签名能力",
        dep_hits or (sign_hits if isinstance(sign_hits, list) else []))

    # S2 Flutter can launch Alipay either through a Flutter plugin or a native
    # Android SDK bridge wired with MethodChannel.
    s2_pubspec = search([pubspec] if pubspec.exists() else [], r"tobias|alipay")
    s2_native_sdk = search(android_files, r"com\.alipay\.sdk|alipaysdk-android", max_hits=2)
    s2_native_pay = search(android_files, r"\bPayTask\b|payV2\s*\(", max_hits=2)
    s2_native_bridge = search(android_files, r"\bMethodChannel\b", max_hits=2)
    s2_native = bool(s2_native_sdk and s2_native_pay and s2_native_bridge)
    s2_evidence = s2_pubspec or (s2_native_sdk + s2_native_pay + s2_native_bridge)
    add("S2", "前端支付宝拉起能力（tobias 或原生 SDK 桥接）", bool(s2_pubspec or s2_native),
        "" if (s2_pubspec or s2_native)
        else "pubspec.yaml 未发现 tobias/alipay 依赖，Android 侧也未发现 Alipay SDK + MethodChannel/PayTask 拉起能力",
        s2_evidence)

    # S3 payment method enums updated on both sides
    s3_be = search(backend_src + ([pkg_json] if pkg_json.exists() else []),
                   r"alipay", max_hits=3)
    s3_be_enum = search([f for f in backend_src if "enums" in str(f) or "validator" in str(f).lower()],
                        r"alipay")
    s3_fe_enum = search(app_lib, r"enum\s+\w+|PaymentMethod|payment_method|paymentMethod")
    s3_fe_alipay = search(app_lib, r"alipay")
    s3_ok = bool(s3_be_enum and s3_fe_enum and s3_fe_alipay)
    add("S3", "前后端支付方式枚举包含支付宝", s3_ok,
        "" if s3_ok else f"后端枚举/校验器命中={bool(s3_be_enum)}，Flutter 支付枚举/模型命中={bool(s3_fe_enum)}，Flutter alipay 命中={bool(s3_fe_alipay)}",
        (s3_be_enum + s3_fe_enum + s3_fe_alipay))

    # S4 server-side payment params generation exposed via API
    s4_route = search([f for f in backend_src if "route" in str(f).lower()], r"alipay")
    s4_order = search(backend_src, r"order_?str|orderString|sdkExec|alipay\.trade\.app\.pay|trade\.app\.pay")
    s4_ok = bool(s4_route and s4_order)
    add("S4", "服务端生成支付参数并通过 API 返回", s4_ok,
        "" if s4_ok else f"alipay 路由命中={bool(s4_route)}，orderStr/app.pay 生成代码命中={bool(s4_order)}",
        (s4_route + s4_order))

    # S5 trade status query path
    s5 = search(backend_src, r"trade[._]?query")
    add("S5", "后端具备支付宝交易状态查询路径", bool(s5),
        "" if s5 else "后端 src 未发现 alipay.trade.query / tradeQuery 调用", s5)

    # S6 success -> payment record + booking confirmed code path
    alipay_files = [f for f in backend_src
                    if re.search(r"alipay", f.read_text(encoding="utf-8", errors="replace"), re.I)]
    s6 = search(alipay_files, r"confirm|TRADE_SUCCESS")
    s6b = search(alipay_files, r"[Pp]ayment(Repository|Model|\.create)|[Bb]ooking")
    s6_ok = bool(s6 and s6b)
    add("S6", "支付成功后落库并确认 booking 的代码路径", s6_ok,
        "" if s6_ok else "包含 alipay 的后端文件中未同时发现确认逻辑与 payment/booking 更新调用",
        (s6 + s6b))

    # S7 flutter calls confirm endpoint after a real Alipay SDK/plugin launch.
    plugin_launch = search(
        app_lib,
        r"(Tobias|AlipaySDK|FlutterAlipay)\s*\.\s*(pay|payV2|payOrder)|"
        r"\bpay(V2|Order)?\s*\([^)]*(orderStr|order_str|orderString)",
    )
    channel_bridge = search(app_lib, r"\bMethodChannel\b|\binvokeMethod\b")
    channel_pay_method = search(app_lib, r"['\"](?:pay|payV2|alipay|alipayPay)['\"]|\bpay(V2|Order)?\s*\(")
    channel_order_str = search(app_lib, r"orderStr|order_str|orderString")
    flutter_launch = plugin_launch or (
        channel_bridge and channel_pay_method and channel_order_str
    )
    s7_confirm = search(app_lib, r"alipay.{0,40}confirm|confirm.{0,40}alipay|alipay/confirm")
    s7_ok = bool(flutter_launch and s7_confirm)
    add("S7", "Flutter 从支付宝返回后调用后端确认接口", s7_ok,
        "" if s7_ok else f"Flutter 未发现真实支付宝拉起后再确认（launch={bool(flutter_launch)}，confirm={bool(s7_confirm)}）",
        (flutter_launch + s7_confirm))

    # S8 alipay option present in payment selector UI
    ui_files = [f for f in app_lib if "view" in str(f).lower() or "widget" in str(f).lower()]
    f3 = search(ui_files, r"alipay") or search(
        [f for f in app_lib if "payment_options" in f.name], r"alipay")
    add("S8", "支付方式选择器中包含支付宝选项", bool(f3),
        "" if f3 else "Flutter views/widgets 中未发现支付宝选项", f3 if isinstance(f3, list) else [])

    # S9 flutter wires both backend endpoints
    f4_create = search(app_lib, r"alipay[/_]?create|create.{0,30}alipay")
    f4_confirm = search(app_lib, r"alipay[/_]?confirm|confirm.{0,30}alipay")
    f4_ok = bool(f4_create and f4_confirm)
    add("S9", "Flutter 对接后端创建支付和确认支付接口", f4_ok,
        "" if f4_ok else f"create 接口命中={bool(f4_create)}，confirm 接口命中={bool(f4_confirm)}",
        (f4_create + f4_confirm))

    # S10 result-state handling around alipay flow
    alipay_dart = [f for f in app_lib
                   if re.search(r"alipay", f.read_text(encoding="utf-8", errors="replace"), re.I)]
    f5_result = search(alipay_dart, r"resultStatus|payResult|paymentResult|result\s*\[|memo")
    f5_succ = search(alipay_dart, r"\b9000\b|TRADE_SUCCESS|success")
    f5_fail = search(alipay_dart, r"\b(4000|6001|6002|8000)\b|fail|cancel|pending|processing|error|WAIT_BUYER_PAY|TRADE_CLOSED")
    f5_ok = bool(flutter_launch and f5_result and f5_succ and f5_fail)
    add("S10", "Flutter 处理成功/失败/取消/处理中等支付结果状态", f5_ok,
        "" if f5_ok else "Flutter 未发现真实支付宝拉起结果及成功/失败/取消/处理中状态的完整处理",
        (flutter_launch + f5_result + f5_succ + f5_fail))

    out_path.write_text(json.dumps({"rubrics": rubrics}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    passed = sum(r["passed"] for r in rubrics)
    print(f"[static] {passed}/{len(rubrics)} passed")
    for r in rubrics:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"  [{mark}] {r['id']} {r['name']}" + (f" — {r['message']}" if r["message"] else ""))


if __name__ == "__main__":
    main()
