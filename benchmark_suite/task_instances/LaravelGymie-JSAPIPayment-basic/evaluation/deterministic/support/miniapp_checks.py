"""Mini-program frontend checks (rubrics E1-E3) via static analysis of miniapp/.

E1: membership purchase page still renders plans + order form.
E2: after order creation the page calls my.tradePay with the backend tradeNO.
E3: the tradePay client callback must not directly mark the order paid; it
    should trigger a server-side status refresh instead.
Writes /output/miniapp_checks.json.
"""
import json
import os
import re
import sys

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"
MINIAPP = os.path.join(WORKSPACE, "miniapp")


def read_all(exts):
    blobs = {}
    for root, dirs, files in os.walk(MINIAPP):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for name in files:
            if any(name.endswith(e) for e in exts):
                path = os.path.join(root, name)
                try:
                    with open(path, errors="replace") as f:
                        blobs[os.path.relpath(path, WORKSPACE)] = f.read()
                except OSError:
                    pass
    return blobs


def check_purchase_page():
    js = read_all([".js"])
    axml = read_all([".axml"])
    has_plans = any("plans" in c for c in list(js.values()) + list(axml.values()))
    has_order_post = any(re.search(r"/orders", c) for c in js.values())
    ok = bool(axml) and has_plans and has_order_post
    return ok, ("会员购买页保留：axml 页面 %d 个，plans 渲染=%s，下单请求=%s"
                % (len(axml), has_plans, has_order_post))


def check_trade_pay():
    js = read_all([".js"])
    pay_files = {p: c for p, c in js.items() if re.search(r"my\.tradePay|\btradePay\s*\(", c)}
    if not pay_files:
        return False, "miniapp 中未发现 my.tradePay（或等价原生支付）调用"
    uses_trade_no = {p for p, c in pay_files.items() if "tradeNO" in c}
    if not uses_trade_no:
        return False, "发现 tradePay 调用（%s）但未使用后端返回的 tradeNO 字段" % list(pay_files)[:2]
    return True, "tradePay 调用并使用 tradeNO: %s" % sorted(uses_trade_no)[:3]


def check_client_result_not_final():
    js = read_all([".js"])
    pay_files = {p: c for p, c in js.items() if re.search(r"my\.tradePay|\btradePay\s*\(", c)}
    if not pay_files:
        return False, "无 tradePay 调用，无法验证前端回调行为"
    suspicious = []
    refresh = []
    for path, content in pay_files.items():
        # Flag local finalization only when the callback writes a final payment
        # state into local page data. Reading data.order.status returned by the
        # server is allowed and should not be treated as client-side finality.
        local_final_patterns = [
            r"setData\(\s*\{[^}]*\b(status|paymentStatus|payment_status)\s*:\s*['\"](paid|success|TRADE_SUCCESS)['\"]",
            r"setData\(\s*\{[^}]*\border\s*:\s*\{[^}]*\bstatus\s*:\s*['\"](paid|success|TRADE_SUCCESS)['\"]",
        ]
        if any(re.search(pattern, content, re.I | re.S) for pattern in local_final_patterns):
            suspicious.append(path)
        if re.search(r"/orders/|loadOrder|refresh|queryOrder|fetchStatus|checkout_no", content):
            refresh.append(path)
    if suspicious:
        return False, "前端疑似在支付回调中直接把订单写成已支付: %s" % suspicious
    if not refresh:
        return False, "支付回调后未发现向服务端查询/刷新订单状态的逻辑"
    return True, "支付回调走服务端状态刷新（%s），未发现本地直接判定已支付" % sorted(refresh)[:3]


CHECKS = [
    ("miniapp.jsapi_miniapp_product_visible", "会员卡购买页保留", "functionality", check_purchase_page),
    ("miniapp.jsapi_my_trade_pay", "小程序端可唤起支付", "functionality", check_trade_pay),
    ("miniapp.jsapi_client_result_not_final", "前端结果不做终态", "security", check_client_result_not_final),
]


def main():
    results = []
    for rid, name, dimension, fn in CHECKS:
        try:
            passed, message = fn()
        except Exception as exc:
            passed, message = False, "miniapp check 自身异常（test 实现问题）: %r" % exc
        results.append({
            "id": rid, "name": name, "dimension": dimension, "type": "hard",
            "passed": bool(passed), "score": 1 if passed else 0, "max_score": 1,
            "message": message, "evidence": ["code_files/miniapp", "patch.diff"],
        })
        print("[miniapp] %s %s: %s" % ("PASS" if passed else "FAIL", rid, message))
    with open(os.path.join(OUTPUT_DIR, "miniapp_checks.json"), "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
