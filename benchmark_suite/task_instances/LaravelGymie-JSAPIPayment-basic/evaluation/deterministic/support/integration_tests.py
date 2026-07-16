"""Integration tests for the hybrid real-sandbox JSAPI basic case.

Trade creation is sent through tests/real_sandbox_proxy.py to the real Alipay
sandbox. Successful async notify is mocked with the benchmark's local Alipay
signing key, so the case can verify callback/fulfillment semantics without a
real buyer completing payment.
"""
import json
import os
import subprocess
import sys
import time
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sign_utils  # noqa: E402

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"

BASE = os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
APP_PORT = str(urlparse(BASE).port or os.environ.get("APP_PORT") or "8000")
KEY_DIR = os.environ.get("ALIPAY_KEY_DIR", os.path.join(OUTPUT_DIR, "real-alipay-keys"))
APP_ID = os.environ.get("ALIPAY_APP_ID", "")
MINIAPP_APP_ID = os.environ.get("ALIPAY_MINIAPP_APP_ID", "")
GATEWAY_LOG = os.path.join(OUTPUT_DIR, "gateway_requests.jsonl")

RESULTS = []
SERVER = None
STATE = {}


def record(rid, name, dimension, passed, message, evidence=None):
    RESULTS.append({
        "id": rid,
        "name": name,
        "dimension": dimension,
        "type": "hard",
        "passed": bool(passed),
        "score": 1 if passed else 0,
        "max_score": 1,
        "message": message,
        "evidence": evidence or ["integration_results.json", "server.log"],
    })
    print("[integration] %s %s: %s" % ("PASS" if passed else "FAIL", rid, message))


def sh(cmd, timeout=300):
    proc = subprocess.run(cmd, cwd=WORKSPACE, shell=True, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def read_gateway_log():
    entries = []
    try:
        with open(GATEWAY_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return entries


def decimal_equal(left, right):
    try:
        return Decimal(str(left)).quantize(Decimal("0.01")) == Decimal(str(right)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return False


def create_entries():
    return [e for e in read_gateway_log() if e.get("method") == "alipay.trade.create"]


def sandbox_create_summary(entries=None):
    entries = entries if entries is not None else create_entries()
    if not entries:
        return "未收到 alipay.trade.create 请求"
    parts = []
    for entry in entries[-3:]:
        biz = entry.get("biz_content") or {}
        resp = entry.get("upstream_response_json") or entry.get("response_json") or {}
        body = resp.get("alipay_trade_create_response") or {}
        buyer = {k: biz.get(k) for k in ("buyer_id", "buyer_open_id", "buyer_logon_id") if biz.get(k)}
        parts.append("code=%s sub_code=%s sub_msg=%s buyer=%s out_trade_no=%s total_amount=%s" % (
            body.get("code"), body.get("sub_code"), body.get("sub_msg"),
            buyer or "未提供", biz.get("out_trade_no"), biz.get("total_amount")))
    return " | ".join(parts)


def probe_plans(timeout=3):
    try:
        r = requests.get(BASE + "/api/membership-checkout/plans", timeout=timeout)
    except requests.RequestException as exc:
        return False, "/plans 请求异常: %r" % exc, []
    if r.status_code != 200:
        return False, "/plans HTTP %d" % r.status_code, []
    try:
        body = r.json()
    except ValueError:
        snippet = (r.text or "")[:120].replace("\n", " ")
        return False, "/plans=200 但不是 JSON（content-type=%s body=%r）" % (
            r.headers.get("content-type", ""), snippet), []
    plans = body.get("plans") if isinstance(body, dict) else None
    if not isinstance(plans, list) or not plans:
        return False, "/plans JSON 缺少非空 plans 列表", []
    return True, "/plans=200 JSON plans=%d" % len(plans), plans


def start_server():
    global SERVER
    # If the agent already left a server running on this task-specific port,
    # reuse it. With a unique APP_PORT this is the same workspace, not cross-task
    # contamination, and avoids false "address already in use" failures.
    ok, detail, _ = probe_plans(timeout=3)
    if ok:
        with open(os.path.join(OUTPUT_DIR, "server.log"), "a") as log:
            log.write("reusing existing server on %s, %s\n" % (BASE, detail))
        return True
    with open(os.path.join(OUTPUT_DIR, "server.log"), "a") as log:
        log.write("existing server probe not reusable on %s: %s\n" % (BASE, detail))

    log = open(os.path.join(OUTPUT_DIR, "server.log"), "a")
    SERVER = subprocess.Popen(
        ["php", "artisan", "serve", "--host=127.0.0.1", "--port=" + APP_PORT, "--no-reload"],
        cwd=WORKSPACE, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(30):
        time.sleep(1)
        ok, _, _ = probe_plans(timeout=3)
        if ok:
            return True
        if SERVER.poll() is not None:
            return False
    return False


def test_build_runtime():
    rc, out = sh("php -d memory_limit=512M artisan migrate:fresh --seed --force", timeout=600)
    if rc != 0:
        record("integration.jsapi_build_runtime", "服务可构建启动", "functionality", False,
               "migrate:fresh --seed 失败 (exit %d)，日志尾部: %s" % (rc, out[-400:]))
        return False
    if not start_server():
        record("integration.jsapi_build_runtime", "服务可构建启动", "functionality", False,
               "php artisan serve 启动后 /api/membership-checkout/plans 不可达，见 server.log")
        return False
    try:
        plans_ok, plans_detail, _ = probe_plans(timeout=10)
        r2 = requests.get(BASE + "/membership-checkout/memberships", timeout=10)
    except requests.RequestException as exc:
        record("integration.jsapi_build_runtime", "服务可构建启动", "functionality", False,
               "探活请求异常: %r" % exc)
        return False
    ok = plans_ok and r2.status_code == 200
    record("integration.jsapi_build_runtime", "服务可构建启动", "functionality", ok,
           "迁移+seed 成功；%s，/memberships=%d" % (plans_detail, r2.status_code))
    return ok


def test_plans():
    ok, detail, plans = probe_plans(timeout=10)
    if not ok:
        record("integration.jsapi_miniapp_product_visible", "会员卡商品可购买", "functionality",
               False, detail)
        return None
    usable = [p for p in plans if p.get("id") and float(p.get("amount") or 0) > 0 and p.get("days")]
    record("integration.jsapi_miniapp_product_visible", "会员卡商品可购买", "functionality",
           bool(usable), "返回 %d 个套餐，其中 %d 个含可下单的金额/周期字段" % (len(plans), len(usable)))
    return usable[0] if usable else None


def test_create_order(plan):
    payload = {
        "plan_id": plan["id"],
        "buyer_name": "Benchmark Buyer",
        "buyer_contact": "13800138000",
        "buyer_email": "benchmark-buyer@example.com",
    }
    buyer_id = os.environ.get("ALIPAY_SANDBOX_BUYER_ID") or ""
    buyer_open_id = os.environ.get("ALIPAY_SANDBOX_BUYER_OPEN_ID") or ""
    buyer_logon_id = os.environ.get("ALIPAY_SANDBOX_BUYER_LOGON_ID") or ""
    if buyer_id:
        payload["buyer_id"] = buyer_id
    if buyer_open_id:
        payload["buyer_open_id"] = buyer_open_id
    if buyer_logon_id:
        payload["buyer_logon_id"] = buyer_logon_id
    try:
        r = requests.post(BASE + "/api/membership-checkout/orders", json=payload, timeout=60)
        body = r.json() or {}
    except Exception as exc:
        record("integration.jsapi_create_payment_trade", "创建会员卡支付交易", "functionality",
               False, "POST /orders 失败: %r" % exc)
        record("integration.jsapi_trade_no_case", "交易字段大小写正确", "functionality",
               False, "下单失败，无法检查 tradeNO 字段")
        return None
    order = body.get("order") or {}
    required = ["checkout_no", "status", "amount"]
    missing = [k for k in required if not order.get(k)]
    trade_no = order.get("tradeNO")
    created_ok = r.status_code in (200, 201) and not missing and bool(trade_no)
    create_debug = sandbox_create_summary()
    record("integration.jsapi_create_payment_trade", "创建会员卡支付交易", "functionality",
           created_ok,
           "HTTP %d；缺失字段: %s；tradeNO=%s；沙箱创建摘要: %s" % (
               r.status_code, missing or "无", (trade_no or "")[:32] or "缺失", create_debug),
           evidence=["gateway_requests.jsonl", "real_sandbox_proxy.log", "integration_results.json"])
    wrong_case_keys = [k for k in order if k.lower() in ("tradeno", "trade_no") and k != "tradeNO"]
    case_ok = isinstance(trade_no, str) and bool(trade_no)
    msg = "order.tradeNO 字段存在且非空" if case_ok else "响应缺少 order.tradeNO（大小写敏感）"
    if wrong_case_keys and not case_ok:
        msg += "；发现疑似大小写错误字段: %s" % wrong_case_keys
    record("integration.jsapi_trade_no_case", "交易字段大小写正确", "functionality", case_ok, msg,
           evidence=["integration_results.json"])
    if not created_ok:
        return None
    STATE["order"] = order
    return order


def response_trade_nos(entry):
    data = entry.get("response_json") or {}
    out = []
    for key, value in data.items():
        if key.endswith("_response") and isinstance(value, dict):
            trade_no = value.get("trade_no")
            if trade_no:
                out.append(str(trade_no))
    return out


def test_gateway_evidence(order=None):
    entries = read_gateway_log()
    creates = [e for e in entries if e.get("method") == "alipay.trade.create"]
    wrong = [e for e in entries if e.get("method") in (
        "alipay.trade.wap.pay", "alipay.trade.page.pay", "alipay.trade.app.pay")]
    response_trade_no_set = {t for e in creates for t in response_trade_nos(e)}
    order_trade_no = str((order or {}).get("tradeNO") or "")

    if not entries:
        record("integration.logic_api", "调用支付宝交易创建接口", "functionality", False,
               "真实沙箱代理没有收到任何请求；tradeNO 疑似本地伪造而非接口创建",
               evidence=["gateway_requests.jsonl", "real_sandbox_proxy.log"])
    else:
        sandbox_codes = []
        for e in creates:
            resp = e.get("upstream_response_json") or e.get("response_json") or {}
            body = resp.get("alipay_trade_create_response") or {}
            if body:
                sandbox_codes.append("%s/%s/%s" % (body.get("code"), body.get("sub_code"), body.get("sub_msg")))
        # This rubric checks whether the service selected the real JSAPI create
        # gateway. A real sandbox business rejection caused by unavailable buyer
        # credentials should not hide correct API/method selection; tradeNO success
        # is checked separately by integration.jsapi_create_payment_trade.
        ok = bool(creates) and not (wrong and not creates)
        detail = "代理转发 %d 次 alipay.trade.create 到真实沙箱；沙箱响应=%s；响应 trade_no=%s；order.tradeNO=%s" % (
            len(creates), sandbox_codes or "无", sorted(response_trade_no_set) or "未从响应解析到", order_trade_no or "缺失")
        if wrong:
            detail += "；另收到错误产品线调用: %s" % sorted({e["method"] for e in wrong})
        record("integration.logic_api", "调用支付宝交易创建接口", "functionality", ok, detail,
               evidence=["gateway_requests.jsonl", "real_sandbox_proxy.log"])

    biz_list = [e.get("biz_content") or {} for e in creates]
    product_codes = sorted({(b.get("product_code") or "").upper() for b in biz_list if b})
    product_ok = any(pc == "JSAPI_PAY" for pc in product_codes)
    record("integration.jsapi_product_mapping", "产品映射正确", "functionality", product_ok,
           "trade.create biz_content.product_code=%s（要求 JSAPI_PAY）" % (product_codes or "未提供"),
           evidence=["gateway_requests.jsonl"])

    op_ids = sorted({b.get("op_app_id") or "" for b in biz_list if b})
    op_ok = bool(MINIAPP_APP_ID) and MINIAPP_APP_ID in op_ids
    record("integration.jsapi_op_app_id", "小程序应用身份正确关联", "functionality", op_ok,
           "trade.create biz_content.op_app_id=%s（要求 %s）" % (op_ids or "未提供", MINIAPP_APP_ID or "未配置"),
           evidence=["gateway_requests.jsonl"])



def test_order_trade_binding(order):
    checkout_no = str((order or {}).get("checkout_no") or "")
    order_amount = order.get("amount") if order else None
    order_trade_no = str((order or {}).get("tradeNO") or "")
    entries = create_entries()
    matched = [e for e in entries if str((e.get("biz_content") or {}).get("out_trade_no") or "") == checkout_no]
    entry = matched[-1] if matched else (entries[-1] if entries else None)
    if not entry:
        record("integration.jsapi_order_trade_binding", "交易绑定当前会员订单", "functionality", False,
               "真实沙箱代理未收到 alipay.trade.create，无法证明交易绑定当前订单",
               evidence=["gateway_requests.jsonl", "real_sandbox_proxy.log"])
        return
    biz = entry.get("biz_content") or {}
    response_trade_no_set = set(response_trade_nos(entry))
    out_ok = str(biz.get("out_trade_no") or "") == checkout_no
    amount_ok = decimal_equal(biz.get("total_amount"), order_amount)
    trade_ok = bool(order_trade_no) and order_trade_no in response_trade_no_set
    ok = out_ok and amount_ok and trade_ok
    record("integration.jsapi_order_trade_binding", "交易绑定当前会员订单", "functionality", ok,
           "biz.out_trade_no=%s vs order.checkout_no=%s；biz.total_amount=%s vs order.amount=%s；order.tradeNO=%s；sandbox_response_trade_no=%s" % (
               biz.get("out_trade_no") or "缺失", checkout_no or "缺失",
               biz.get("total_amount") or "缺失", order_amount if order_amount is not None else "缺失",
               order_trade_no or "缺失", sorted(response_trade_no_set) or "未解析到"),
           evidence=["gateway_requests.jsonl", "integration_results.json"])


def build_notify_params(order, valid=True, exclude_sign_type=True):
    alipay_priv = sign_utils.load_private_key(os.path.join(KEY_DIR, "alipay_private_key.pem"))
    total = str(order.get("amount") or "0.01")
    params = {
        "notify_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "notify_type": "trade_status_sync",
        "notify_id": uuid.uuid4().hex,
        "app_id": APP_ID,
        "auth_app_id": MINIAPP_APP_ID,
        "charset": "utf-8",
        "version": "1.0",
        "sign_type": "RSA2",
        "trade_no": order.get("tradeNO") or "20260612000000000000",
        "out_trade_no": order.get("checkout_no"),
        "trade_status": "TRADE_SUCCESS",
        "total_amount": total,
        "receipt_amount": total,
        "buyer_pay_amount": total,
        "buyer_id": os.environ.get("ALIPAY_SANDBOX_BUYER_ID") or "",
        "buyer_logon_id": os.environ.get("ALIPAY_SANDBOX_BUYER_LOGON_ID") or "",
        "seller_id": os.environ.get("ALIPAY_SELLER_ID") or "2088201111222233",
        "subject": "Gymie membership",
        "gmt_payment": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    params["sign"] = sign_utils.sign_params(params, alipay_priv, exclude_sign_type=exclude_sign_type)
    if not valid:
        params["total_amount"] = "0.01" if total != "0.01" else "999.99"
    return params


def resign_notify_params(params, exclude_sign_type=True):
    alipay_priv = sign_utils.load_private_key(os.path.join(KEY_DIR, "alipay_private_key.pem"))
    params = dict(params)
    params.pop("sign", None)
    params["notify_id"] = params.get("notify_id") or uuid.uuid4().hex
    params["sign"] = sign_utils.sign_params(params, alipay_priv, exclude_sign_type=exclude_sign_type)
    return params


def build_signed_notify_params(order, exclude_sign_type=True, **overrides):
    params = build_notify_params(order, valid=True, exclude_sign_type=exclude_sign_type)
    params.update({k: v for k, v in overrides.items() if v is not None})
    params["notify_id"] = uuid.uuid4().hex
    return resign_notify_params(params, exclude_sign_type=exclude_sign_type)


def get_order_status(checkout_no):
    try:
        r = requests.get(BASE + "/api/membership-checkout/orders/" + checkout_no, timeout=10)
        return (r.json() or {}).get("order") or {}
    except Exception:
        return {}


def fulfillment_counts():
    db = os.path.join(WORKSPACE, "storage", "app", "database.sqlite")
    counts = {}
    for table in ("subscriptions", "invoices", "members", "invoice_transactions"):
        try:
            out = subprocess.check_output(
                ["sqlite3", db, "SELECT COUNT(*) FROM %s;" % table],
                stderr=subprocess.DEVNULL)
            counts[table] = int(out.strip() or 0)
        except Exception:
            counts[table] = None
    return counts


def is_paid(status):
    return str(status or "").lower() in (
        "paid", "trade_success", "success", "completed", "complete", "fulfilled"
    )


def counts_grew(before, after):
    return [t for t in before
            if before[t] is not None and after[t] is not None and after[t] > before[t]]


def different_amount(amount):
    try:
        value = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        value = Decimal("0.01")
    if value == Decimal("0.01"):
        return "999.99"
    return "0.01"


def post_notify_variants(order, variants):
    checkout_no = order["checkout_no"]
    before = fulfillment_counts()
    responses = []
    endpoint_seen = False
    for label, overrides in variants:
        for exclude_sign_type in (True, False):
            params = build_signed_notify_params(order, exclude_sign_type=exclude_sign_type, **overrides)
            try:
                r = requests.post(BASE + "/membership-checkout/notify", data=params, timeout=15)
                endpoint_seen = endpoint_seen or r.status_code not in (404, 405)
                responses.append("%s/signTypeExcluded=%s HTTP %d" % (
                    label, exclude_sign_type, r.status_code))
            except requests.RequestException as exc:
                responses.append("%s/signTypeExcluded=%s exception=%r" % (
                    label, exclude_sign_type, exc))
    after = fulfillment_counts()
    final = get_order_status(checkout_no)
    grew = counts_grew(before, after)
    return endpoint_seen, final, grew, responses, before, after


def test_non_success_signed_notify(order):
    endpoint_seen, final, grew, responses, before, after = post_notify_variants(order, [
        ("WAIT_BUYER_PAY", {"trade_status": "WAIT_BUYER_PAY"}),
    ])
    ok = endpoint_seen and not is_paid(final.get("status")) and not grew
    record("integration.jsapi_signed_non_success_notify_not_paid",
           "合法签名但非成功支付状态不得履约", "security", ok,
           "signed WAIT_BUYER_PAY responses=%s；订单状态=%s；履约表增长=%s（before=%s after=%s）"
           % (responses, final.get("status"), grew or "无", before, after))


def test_signed_mismatch_notify(order):
    wrong_app_id = (APP_ID + "_wrong") if APP_ID else "2088000000000000"
    endpoint_seen, final, grew, responses, before, after = post_notify_variants(order, [
        ("wrong_amount", {
            "total_amount": different_amount(order.get("amount")),
            "receipt_amount": different_amount(order.get("amount")),
            "buyer_pay_amount": different_amount(order.get("amount")),
        }),
        ("wrong_app_id", {"app_id": wrong_app_id}),
    ])
    ok = endpoint_seen and not is_paid(final.get("status")) and not grew
    record("integration.jsapi_signed_mismatch_notify_not_paid",
           "合法签名但金额或应用不匹配不得履约", "security", ok,
           "signed mismatch responses=%s；订单状态=%s；履约表增长=%s（before=%s after=%s）"
           % (responses, final.get("status"), grew or "无", before, after))


def test_notify(order):
    checkout_no = order["checkout_no"]
    invalid = build_notify_params(order, valid=False)
    try:
        r = requests.post(BASE + "/membership-checkout/notify", data=invalid, timeout=15)
        endpoint_ok = r.status_code not in (404, 405)
        status_after_invalid = get_order_status(checkout_no).get("status")
        not_advanced = not is_paid(status_after_invalid)
        record("integration.notify_endpoint", "异步通知入口存在且拒绝无效通知", "security",
               endpoint_ok and not_advanced,
               "POST /membership-checkout/notify HTTP %d；篡改签名后订单状态=%s（不得为已支付）"
               % (r.status_code, status_after_invalid))
    except requests.RequestException as exc:
        record("integration.notify_endpoint", "异步通知入口存在且拒绝无效通知", "security", False,
               "通知入口请求异常: %r" % exc)

    test_non_success_signed_notify(order)
    test_signed_mismatch_notify(order)

    before = fulfillment_counts()
    advanced = False
    accepted_valid = None
    for exclude_sign_type in (True, False):
        valid = build_notify_params(order, valid=True, exclude_sign_type=exclude_sign_type)
        try:
            requests.post(BASE + "/membership-checkout/notify", data=valid, timeout=15)
        except requests.RequestException:
            continue
        if is_paid(get_order_status(checkout_no).get("status")):
            advanced = True
            accepted_valid = valid
            break
    after = fulfillment_counts()
    final = get_order_status(checkout_no)
    grew = counts_grew(before, after)
    fulfilled = bool(grew)
    record("integration.jsapi_notify_or_query_confirm", "服务端可信结果推进订单并完成履约",
           "functionality", advanced and fulfilled,
           "mock 成功通知后订单状态=%s（advanced=%s）；履约表增长: %s（before=%s after=%s）"
           % (final.get("status"), advanced, grew or "无", before, after))

    if not accepted_valid:
        record("integration.jsapi_notify_idempotent_no_double_fulfillment",
               "重复成功通知不重复履约", "security", False,
               "mock 成功通知未能推进支付，无法验证重复通知幂等")
    else:
        before_dup = fulfillment_counts()
        try:
            requests.post(BASE + "/membership-checkout/notify", data=accepted_valid, timeout=15)
        except requests.RequestException:
            pass
        after_dup = fulfillment_counts()
        grew_dup = counts_grew(before_dup, after_dup)
        record("integration.jsapi_notify_idempotent_no_double_fulfillment",
               "重复成功通知不重复履约", "security", not grew_dup,
               "重复同一 mock 成功通知后履约表增长: %s（before=%s after=%s）"
               % (grew_dup or "无", before_dup, after_dup))


def main():
    plan = None
    if test_build_runtime():
        plan = test_plans()
    else:
        record("integration.jsapi_miniapp_product_visible", "会员卡商品可购买", "functionality",
               False, "服务未启动，跳过")
    if plan:
        order = test_create_order(plan)
        test_gateway_evidence(order)
        if order:
            test_order_trade_binding(order)
            test_notify(order)
        else:
            for rid, name in [
                ("integration.jsapi_order_trade_binding", "交易绑定当前会员订单"),
                ("integration.notify_endpoint", "异步通知入口存在且拒绝无效通知"),
                ("integration.jsapi_signed_non_success_notify_not_paid", "合法签名但非成功支付状态不得履约"),
                ("integration.jsapi_signed_mismatch_notify_not_paid", "合法签名但金额或应用不匹配不得履约"),
                ("integration.jsapi_notify_or_query_confirm", "服务端可信结果推进订单并完成履约"),
                ("integration.jsapi_notify_idempotent_no_double_fulfillment", "重复成功通知不重复履约"),
            ]:
                dimension = "security" if rid in {
                    "integration.notify_endpoint",
                    "integration.jsapi_signed_non_success_notify_not_paid",
                    "integration.jsapi_signed_mismatch_notify_not_paid",
                    "integration.jsapi_notify_idempotent_no_double_fulfillment",
                } else "functionality"
                record(rid, name, dimension, False, "未拿到真实 tradeNO，支付确认链路无法继续")
    else:
        for rid, name in [
            ("integration.jsapi_create_payment_trade", "创建会员卡支付交易"),
            ("integration.jsapi_trade_no_case", "交易字段大小写正确"),
            ("integration.logic_api", "调用支付宝交易创建接口"),
            ("integration.jsapi_product_mapping", "产品映射正确"),
            ("integration.jsapi_op_app_id", "小程序应用身份正确关联"),
            ("integration.jsapi_order_trade_binding", "交易绑定当前会员订单"),
            ("integration.notify_endpoint", "异步通知入口存在且拒绝无效通知"),
            ("integration.jsapi_signed_non_success_notify_not_paid", "合法签名但非成功支付状态不得履约"),
            ("integration.jsapi_signed_mismatch_notify_not_paid", "合法签名但金额或应用不匹配不得履约"),
            ("integration.jsapi_notify_or_query_confirm", "服务端可信结果推进订单并完成履约"),
            ("integration.jsapi_notify_idempotent_no_double_fulfillment", "重复成功通知不重复履约"),
        ]:
            dimension = "security" if rid in {
                "integration.notify_endpoint",
                "integration.jsapi_signed_non_success_notify_not_paid",
                "integration.jsapi_signed_mismatch_notify_not_paid",
                "integration.jsapi_notify_idempotent_no_double_fulfillment",
            } else "functionality"
            record(rid, name, dimension, False, "无可购买套餐或服务未启动，链路无法继续")

    if SERVER and SERVER.poll() is None:
        SERVER.terminate()
    with open(os.path.join(OUTPUT_DIR, "integration_results.json"), "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
