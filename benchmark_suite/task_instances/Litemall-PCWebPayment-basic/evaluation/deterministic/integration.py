#!/usr/bin/env python3
"""Integration tests for litemall-pc basic (11 checks).

No mock, no signing. Tests that the agent's implementation hits the real sandbox
and processes unsigned notifications (basic instruction says no verification needed).
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from decimal import Decimal, InvalidOperation

import requests

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"
BASE_URL = "http://localhost:8080"
RESULTS = []


def record(rid, name, passed, message):
    RESULTS.append({
        "id": rid, "name": name, "dimension": "functionality",
        "type": "integration", "passed": bool(passed),
        "score": 1 if passed else 0, "max_score": 1,
        "message": str(message)[:1000],
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] {rid}: {name} — {message[:200]}")


def runtime_sandbox_app_id():
    keys_file = os.environ.get("ALIPAY_SANDBOX_KEYS_FILE") or os.path.join(
        WORKSPACE, "alipay-sandbox-keys.json"
    )
    try:
        with open(keys_file, "r", encoding="utf-8") as f:
            app_id = str(json.load(f).get("app_id") or "").strip()
    except (OSError, ValueError, TypeError) as e:
        raise RuntimeError(f"cannot read sandbox app_id from {keys_file}: {e}") from e
    if not app_id:
        raise RuntimeError(f"sandbox runtime input has no app_id: {keys_file}")
    return app_id


def build_notify_payload(out_trade_no, trade_no, total_amount):
    return {
        "out_trade_no": out_trade_no,
        "trade_no": trade_no,
        "trade_status": "TRADE_SUCCESS",
        "total_amount": total_amount,
        "app_id": runtime_sandbox_app_id(),
    }


def mysql_exec(sql):
    subprocess.run(["sudo", "mysql", "-u", "root", "litemall", "-e", sql],
                   capture_output=True, timeout=10)


def mysql_scalar(sql):
    out = subprocess.run(["sudo", "mysql", "-u", "root", "-N", "-B", "litemall", "-e", sql],
                         capture_output=True, text=True, timeout=10)
    if out.returncode != 0:
        return None
    first = out.stdout.strip().splitlines()
    if not first:
        return None
    return first[0].split("\t")[0]


def ensure_address():
    mysql_exec(
        "INSERT IGNORE INTO litemall_address "
        "(id, name, user_id, province, city, county, address_detail, area_code, tel, is_default, add_time, update_time, deleted) "
        "VALUES (1, '测试用户', 1, '浙江省', '杭州市', '余杭区', '文一西路1号', '330110', '13800138000', 1, NOW(), NOW(), 0);"
    )


def login():
    try:
        resp = requests.post(f"{BASE_URL}/wx/auth/login",
                             json={"username": "user123", "password": "user123"}, timeout=10)
        return resp.json().get("data", {}).get("token", "")
    except Exception:
        return ""


def create_order(token):
    s = requests.Session()
    s.headers["X-Litemall-Token"] = token
    s.post(f"{BASE_URL}/wx/cart/add", json={"goodsId": 1006002, "productId": 7, "number": 1}, timeout=10)
    resp = s.post(f"{BASE_URL}/wx/order/submit",
                  json={"cartId": 0, "addressId": 1, "couponId": 0, "grouponRulesId": 0, "message": "eval"},
                  timeout=10)
    data = resp.json().get("data", {})
    order_id = data.get("orderId")
    if not order_id:
        return None, None, None
    detail = s.get(f"{BASE_URL}/wx/order/detail?orderId={order_id}", timeout=10).json()
    info = detail.get("data", {}).get("orderInfo", {})
    return order_id, info.get("orderSn", ""), str(info.get("actualPrice", "899.00"))


def response_payload(resp):
    body = resp.text
    try:
        body = str(resp.json().get("data", body))
    except (ValueError, AttributeError):
        pass
    return body


def expanded_payload(body):
    text = str(body)
    for _ in range(2):
        text = html.unescape(urllib.parse.unquote_plus(text))
    return text


def amount_variants(amount):
    values = {str(amount)}
    try:
        d = Decimal(str(amount))
        values.add(format(d, 'f'))
        values.add(format(d.quantize(Decimal('0.00')), 'f'))
        values.add(str(d.normalize()))
    except (InvalidOperation, ValueError):
        pass
    return {v for v in values if v}


def payment_form_semantics(body):
    text = expanded_payload(body)
    lower = text.lower()
    has_page_api = "alipay.trade.page.pay" in lower or "trade_page_pay" in lower
    has_pc_product = "fast_instant_trade_pay" in lower
    has_form = "<form" in lower and ("openapi" in lower or "alipay" in lower)
    return has_page_api, has_pc_product, has_form, text


def get_order_status(token, order_id):
    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return -1
    value = mysql_scalar(
        f"SELECT order_status FROM litemall_order WHERE id={order_id} AND deleted=0 LIMIT 1;"
    )
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def check_app_boot():
    try:
        resp = requests.get(f"{BASE_URL}/wx/home/index", timeout=10)
        ok = resp.status_code in (200, 401, 500)
        record("integ.app_boot", "应用构建启动", ok, f"GET /wx/home/index → HTTP {resp.status_code}")
        return ok
    except requests.RequestException as e:
        record("integ.app_boot", "应用构建启动", False, f"连接失败: {e}")
        return False


def check_order_flow(token):
    ensure_address()
    order_id, order_sn, price = create_order(token)
    record("integ.order_flow_intact", "下单流程正常", order_id is not None,
           f"orderId={order_id}, orderSn={order_sn}" if order_id else "cart/add 或 submit 失败")
    return order_id, order_sn, price


def check_prepay_form(token):
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.prepay_form", "prepay 返回支付宝表单", False, "无法创建订单")
        return
    resp = requests.post(f"{BASE_URL}/wx/order/alipay-prepay", json={"orderId": order_id},
                         headers={"X-Litemall-Token": token}, timeout=30)
    body = resp.text
    try:
        body = str(resp.json().get("data", body))
    except (ValueError, AttributeError):
        pass
    has_form = "<form" in body.lower()
    has_alipay = "alipay" in body.lower() or "gateway" in body.lower()
    record("integ.prepay_form", "prepay 返回支付宝表单",
           resp.status_code == 200 and has_form and has_alipay,
           f"HTTP {resp.status_code}, form={has_form}, alipay={has_alipay}, body[:80]={body[:80]}")


def check_prepay_gateway_url(token):
    ensure_address()
    order_id, _, _ = create_order(token)
    if not order_id:
        record("integ.prepay_gateway_url", "表单指向支付宝网关", False, "无法创建订单")
        return
    resp = requests.post(f"{BASE_URL}/wx/order/alipay-prepay", json={"orderId": order_id},
                         headers={"X-Litemall-Token": token}, timeout=30)
    body = resp.text
    try:
        body = str(resp.json().get("data", body))
    except (ValueError, AttributeError):
        pass
    has_gateway = "openapi" in body.lower() or "alipaydev" in body.lower() or "alipay.com" in body.lower()
    record("integ.prepay_gateway_url", "表单指向支付宝网关", has_gateway,
           f"gateway_ref={'found' if has_gateway else 'not found'}")


def check_prepay_product_code(token):
    ensure_address()
    order_id, _, _ = create_order(token)
    if not order_id:
        record("integ.prepay_product_code", "产品码正确", False, "无法创建订单")
        return
    resp = requests.post(f"{BASE_URL}/wx/order/alipay-prepay", json={"orderId": order_id},
                         headers={"X-Litemall-Token": token}, timeout=30)
    body = resp.text
    try:
        body = str(resp.json().get("data", body))
    except (ValueError, AttributeError):
        pass
    has_code = "FAST_INSTANT_TRADE_PAY" in body
    record("integ.prepay_product_code", "产品码 FAST_INSTANT_TRADE_PAY", has_code,
           f"FAST_INSTANT_TRADE_PAY {'found' if has_code else 'not found'} in response")


def check_prepay_order_binding(token):
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.prepay_order_binding", "prepay 绑定真实订单", False, "无法创建订单")
        return
    resp = requests.post(f"{BASE_URL}/wx/order/alipay-prepay", json={"orderId": order_id},
                         headers={"X-Litemall-Token": token}, timeout=30)
    body = response_payload(resp)
    expanded = expanded_payload(body)
    has_order = bool(order_sn) and order_sn in expanded
    has_amount = any(v in expanded for v in amount_variants(price))
    has_page_api, has_pc_product, has_form, _ = payment_form_semantics(body)
    passed = resp.status_code == 200 and has_order and has_amount and (has_page_api or (has_pc_product and has_form))
    record("integ.prepay_order_binding", "prepay 绑定真实订单", passed,
           f"HTTP {resp.status_code}, orderSn={order_sn}, price={price}, has_order={has_order}, has_amount={has_amount}, page.pay={has_page_api}, pc_product={has_pc_product}")


def check_prepay_does_not_mark_paid(token):
    ensure_address()
    order_id, order_sn, _ = create_order(token)
    if not order_id:
        record("integ.prepay_does_not_mark_paid", "prepay 不提前履约", False, "无法创建订单")
        return
    before = get_order_status(token, order_id)
    resp = requests.post(f"{BASE_URL}/wx/order/alipay-prepay", json={"orderId": order_id},
                         headers={"X-Litemall-Token": token}, timeout=30)
    time.sleep(1)
    after = get_order_status(token, order_id)
    passed = resp.status_code == 200 and after != 201
    record("integ.prepay_does_not_mark_paid", "prepay 不提前履约", passed,
           f"HTTP {resp.status_code}, orderId={order_id}, orderSn={order_sn}, status_before={before}, status_after={after} (期望仍未支付)")


def check_notify_endpoint():
    path = "/wx/order/alipay-notify"
    try:
        resp = requests.post(f"{BASE_URL}{path}", data={"test": "1"}, timeout=10)
        if resp.status_code != 404:
            record("integ.notify_endpoint_exists", "notify 端点存在", True,
                   f"POST {path} → HTTP {resp.status_code}")
            return path
        record("integ.notify_endpoint_exists", "notify 端点存在", False,
               f"POST {path} → HTTP 404")
        return None
    except requests.RequestException as e:
        record("integ.notify_endpoint_exists", "notify 端点存在", False,
               f"POST {path} 连接失败: {e}")
        return None


def check_notify_processes(token, notify_path):
    if not notify_path:
        record("integ.notify_processes_success", "notify 处理成功", False, "notify 端点不存在")
        return
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.notify_processes_success", "notify 处理成功", False, "无法创建订单")
        return
    params = build_notify_payload(order_sn, "EVAL_T_%d" % int(time.time()), price)
    resp = requests.post(f"{BASE_URL}{notify_path}", data=params, timeout=10)
    body = resp.text.strip()
    time.sleep(1)
    status = get_order_status(token, order_id)
    is_success = "success" in body.lower()
    is_paid = status == 201
    record("integ.notify_processes_success", "notify 处理成功",
           is_success and is_paid,
           f"body='{body[:50]}', order_status={status} (期望 success+201)")


def check_notify_updates_only_target_order(token, notify_path):
    if not notify_path:
        record("integ.notify_updates_only_target", "notify 只更新对应订单", False, "notify 端点不存在")
        return
    ensure_address()
    order_a, sn_a, price_a = create_order(token)
    order_b, sn_b, _ = create_order(token)
    if not order_a or not order_b:
        record("integ.notify_updates_only_target", "notify 只更新对应订单", False,
               f"无法创建双订单: orderA={order_a}, orderB={order_b}")
        return
    params = build_notify_payload(
        sn_a,
        "EVAL_T_TARGET_%d" % int(time.time()),
        price_a,
    )
    resp = requests.post(f"{BASE_URL}{notify_path}", data=params, timeout=10)
    body = resp.text.strip()
    time.sleep(1)
    status_a = get_order_status(token, order_a)
    status_b = get_order_status(token, order_b)
    passed = "success" in body.lower() and status_a == 201 and status_b != 201
    record("integ.notify_updates_only_target", "notify 只更新对应订单", passed,
           f"body='{body[:50]}', orderA={order_a}/{sn_a} status={status_a}, orderB={order_b}/{sn_b} status={status_b} (期望 A=201 且 B≠201)")


def main():
    print("--- Basic Integration Tests (11 checks) ---")

    if not check_app_boot():
        for rid, name in [
            ("integ.order_flow_intact", "下单流程正常"),
            ("integ.prepay_form", "prepay 返回支付宝表单"),
            ("integ.prepay_gateway_url", "表单指向支付宝网关"),
            ("integ.prepay_product_code", "产品码正确"),
            ("integ.prepay_order_binding", "prepay 绑定真实订单"),
            ("integ.prepay_does_not_mark_paid", "prepay 不提前履约"),
            ("integ.notify_endpoint_exists", "notify 端点存在"),
            ("integ.notify_processes_success", "notify 处理成功"),
            ("integ.notify_updates_only_target", "notify 只更新对应订单"),
            ("integ.logic_api", "使用正确的支付宝 API"),
        ]:
            record(rid, name, False, "应用未启动")
    else:
        token = login()
        if not token:
            print("  WARNING: login failed")
        check_order_flow(token)
        check_prepay_form(token)
        check_prepay_gateway_url(token)
        check_prepay_product_code(token)
        check_prepay_order_binding(token)
        check_prepay_does_not_mark_paid(token)
        notify_path = check_notify_endpoint()
        check_notify_processes(token, notify_path)
        check_notify_updates_only_target_order(token, notify_path)
        check_prepay_logic_api(token)

    passed = sum(1 for r in RESULTS if r["passed"])
    print(f"\nIntegration tests: {passed}/{len(RESULTS)} passed")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "integration_results.json"), "w") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)


def check_prepay_logic_api(token):
    """prepay 使用了正确的支付宝 API (alipay.trade.page.pay)。Rubric logic_api"""
    ensure_address()
    order_id, _, _ = create_order(token)
    if not order_id:
        record("integ.logic_api", "使用正确的支付宝 API", False, "无法创建订单")
        return
    resp = requests.post(f"{BASE_URL}/wx/order/alipay-prepay", json={"orderId": order_id},
                         headers={"X-Litemall-Token": token}, timeout=30)
    body = response_payload(resp)
    has_page_api, has_pc_product, has_form, _ = payment_form_semantics(body)
    passed = resp.status_code == 200 and (has_page_api or (has_pc_product and has_form))
    record("integ.logic_api", "使用正确的支付宝 API (page.pay)", passed,
           f"HTTP {resp.status_code}, page.pay={has_page_api}, pc_product={has_pc_product}, form={has_form}")




if __name__ == "__main__":
    main()
