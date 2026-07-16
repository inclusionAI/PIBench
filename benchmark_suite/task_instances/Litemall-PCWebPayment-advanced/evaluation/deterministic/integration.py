#!/usr/bin/env python3
"""Integration tests for litemall-pc-advanced (23 checks).

Groups:
  A. Functionality (3): app_boot, prepay_form, prepay_hits_mock
  B. Notify Security (5): rejects_unsigned, rejects_wrong_amount, rejects_wrong_appid,
                           signed_success, idempotent
  C. Terminal Protection (2): terminal_not_downgraded, return_url_not_final
  D. Endpoint Existence (3): query_endpoint, refund_endpoint, close_endpoint
  E. Advanced Correctness (9): notify_wrong_order, prepay_out_trade_no_matches,
                               refund_idempotent, refund_partial_sequence,
                               refund_over_amount_rejected, refund_cumulative_over_amount_rejected,
                               refund_fund_change_n_not_final, query_unknown_not_paid,
                               paid_order_close_rejected, close_failure_not_cancelled

Each check creates its own fixture via API. No dependency on hardcoded IDs.
"""
import json
import os
import re
import subprocess
import sys
import time
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"
KEYS_DIR = sys.argv[3] if len(sys.argv) > 3 else "/tmp/alipay_keys"
MOCK_LOG = os.environ.get("MOCK_LOG_FILE", "/tmp/mock_gateway_requests.jsonl")

BASE_URL = "http://localhost:8080"
APP_ID = os.environ.get("ALIPAY_APP_ID", "9021000162655457")
SELLER_ID = os.environ.get("ALIPAY_SELLER_ID") or "2088000000000001"

RESULTS = []

EXPECTED_INTEGRATION = [
    ("integ.app_boot", "应用构建启动", "functionality"),
    ("integ.prepay_form", "prepay 返回支付宝表单", "functionality"),
    ("integ.prepay_hits_mock", "prepay 请求到达 mock 网关", "functionality"),
    ("integ.notify_rejects_unsigned", "无签名通知被拒", "security"),
    ("integ.notify_rejects_wrong_amount", "金额篡改通知被拒", "security"),
    ("integ.notify_rejects_wrong_appid", "app_id 篡改通知被拒", "security"),
    ("integ.notify_signed_success", "有效签名通知通过", "correctness"),
    ("integ.notify_idempotent", "通知幂等", "correctness"),
    ("integ.terminal_not_downgraded", "终态不被覆盖", "security"),
    ("integ.return_url_not_final", "return_url 不作终态", "security"),
    ("integ.query_endpoint", "查询端点存在", "functionality"),
    ("integ.refund_endpoint", "退款端点存在", "functionality"),
    ("integ.notify_wrong_order", "不存在订单号的通知被拒", "security"),
    ("integ.prepay_out_trade_no_matches", "prepay 使用真实订单号", "correctness"),
    ("integ.refund_idempotent", "退款幂等 (out_request_no)", "correctness"),
    ("integ.refund_partial_sequence", "部分退款请求号与金额", "correctness"),
    ("integ.refund_over_amount_rejected", "超额退款被拒", "security"),
    ("integ.refund_cumulative_over_amount_rejected", "累计超额退款被拒", "security"),
    ("integ.refund_fund_change_n_not_final", "fund_change=N 不作为最终退款", "security"),
    ("integ.query_unknown_not_paid", "查询未知/待支付不入账", "security"),
    ("integ.paid_order_close_rejected", "已支付订单不能关单", "security"),
    ("integ.close_failure_not_cancelled", "关单失败不取消本地订单", "security"),
    ("integ.close_endpoint", "关单端点存在", "functionality"),
]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sign_utils import load_keys, build_signed_notify


def record(rid, name, dimension, passed, message, evidence=None):
    RESULTS.append({
        "id": rid, "name": name, "dimension": dimension,
        "type": "integration", "passed": bool(passed),
        "score": 1 if passed else 0, "max_score": 1,
        "message": str(message)[:1000],
        "evidence": evidence or [],
    })
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {rid}: {name} — {message[:200]}")


# ============ Helpers ============

def mysql_exec(sql):
    subprocess.run(
        ["sudo", "mysql", "-u", "root", "litemall", "-e", sql],
        capture_output=True, timeout=10,
    )


def mysql_scalar(sql):
    result = subprocess.run(
        ["sudo", "mysql", "-u", "root", "-N", "-B", "litemall", "-e", sql],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return out.splitlines()[0].strip() if out else None


def ensure_address():
    mysql_exec(
        "INSERT IGNORE INTO litemall_address "
        "(id, name, user_id, province, city, county, address_detail, area_code, tel, is_default, add_time, update_time, deleted) "
        "VALUES (1, '测试用户', 1, '浙江省', '杭州市', '余杭区', '文一西路1号', '330110', '13800138000', 1, NOW(), NOW(), 0);"
    )


def login():
    resp = requests.post(f"{BASE_URL}/wx/auth/login",
                         json={"username": "user123", "password": "user123"}, timeout=10)
    return resp.json().get("data", {}).get("token", "")


def create_order(token):
    """Create a pending order via API, return (order_id, order_sn, actual_price)."""
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


def mark_paid(order_id):
    mysql_exec(
        f"UPDATE litemall_order SET order_status=201, pay_time=NOW(), "
        f"pay_id='MOCK_TRADE_001' WHERE id={order_id}"
    )


def get_order_status(token, order_id):
    try:
        oid = int(order_id)
    except (TypeError, ValueError):
        return -1
    status = mysql_scalar(
        f"SELECT order_status FROM litemall_order "
        f"WHERE id={oid} AND deleted=0 LIMIT 1;"
    )
    try:
        return int(status)
    except (TypeError, ValueError):
        return -1


def get_order_refund_amount(order_id):
    try:
        oid = int(order_id)
    except (TypeError, ValueError):
        return Decimal("0.00")
    value = mysql_scalar(
        f"SELECT refund_amount FROM litemall_order "
        f"WHERE id={oid} AND deleted=0 LIMIT 1;"
    )
    if value in (None, "", "NULL"):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def get_mock_log():
    try:
        with open(MOCK_LOG) as f:
            return [json.loads(line) for line in f if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def post_notify(params):
    """POST form-urlencoded to notify endpoint, return (status_code, body)."""
    for path in ["/wx/order/alipay-notify", "/wx/alipay/notify", "/alipay/notify"]:
        try:
            resp = requests.post(f"{BASE_URL}{path}", data=params, timeout=10)
            if resp.status_code != 404:
                return resp.status_code, resp.text.strip(), path
        except requests.RequestException:
            continue
    return 404, "", ""


def is_failure_response(code, body):
    body_l = body.strip().lower()
    return code in (400, 401, 403) or body_l in ("fail", "failure")


class PaymentFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_form = False
        self.seen_form = False
        self.action = ""
        self.method = "get"
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag_l = tag.lower()
        if tag_l == "form" and not self.seen_form:
            self.in_form = True
            self.seen_form = True
            self.action = attrs.get("action", "")
            self.method = attrs.get("method", "get").lower()
        elif self.in_form and tag_l == "input":
            name = attrs.get("name")
            if name:
                self.fields[name] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag.lower() == "form" and self.in_form:
            self.in_form = False


def find_form_html(value):
    if isinstance(value, str):
        return value if "<form" in value.lower() else None
    if isinstance(value, dict):
        preferred = (
            "paymentForm", "payment_form", "form", "html", "body",
            "data", "result",
        )
        for key in preferred:
            found = find_form_html(value.get(key))
            if found:
                return found
        for item in value.values():
            found = find_form_html(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_form_html(item)
            if found:
                return found
    return None


def extract_prepay_form(resp):
    body = resp.text
    try:
        parsed = resp.json()
        body = find_form_html(parsed) or body
    except (ValueError, AttributeError):
        pass
    parser = PaymentFormParser()
    try:
        parser.feed(body)
    except Exception:
        pass
    return {
        "html": body,
        "action": parser.action,
        "method": parser.method,
        "fields": parser.fields,
    }


def alipay_form_params(form):
    parsed = urlparse(form.get("action", ""))
    params = {k: v[-1] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
    params.update(form.get("fields", {}))
    biz = {}
    raw_biz = params.get("biz_content", "")
    if raw_biz:
        try:
            biz = json.loads(raw_biz)
        except (TypeError, ValueError):
            biz = {}
    return params, biz


def prepay_form_out_trade_no(form):
    params, biz = alipay_form_params(form)
    return str(biz.get("out_trade_no") or params.get("out_trade_no") or "")


def prepay_form_method(form):
    params, _ = alipay_form_params(form)
    return params.get("method", "")


def is_mock_gateway_action(action):
    lowered = (action or "").lower()
    return "gateway.do" in lowered and (
        "localhost:19876" in lowered or "127.0.0.1:19876" in lowered
    )


def submit_payment_form(form):
    action = form.get("action", "")
    fields = form.get("fields", {})
    if not action:
        return None
    try:
        if form.get("method", "get").lower() == "post":
            return requests.post(action, data=fields, timeout=10)
        return requests.get(action, params=fields, timeout=10)
    except requests.RequestException:
        return None


def request_prepay_form(token, order_id):
    resp = requests.post(f"{BASE_URL}/wx/order/alipay-prepay",
                         json={"orderId": order_id},
                         headers={"X-Litemall-Token": token}, timeout=30)
    return resp, extract_prepay_form(resp)


def extract_page_pay_out_trade_nos(entries):
    out_trade_nos = []
    for entry in entries:
        if "page.pay" not in entry.get("method", ""):
            continue
        params = entry.get("params", {})
        biz = params.get("_biz") or {}
        if isinstance(biz, str):
            try:
                biz = json.loads(biz)
            except json.JSONDecodeError:
                biz = {}
        if not isinstance(biz, dict):
            biz = {}
        if not biz and params.get("biz_content"):
            try:
                biz = json.loads(params.get("biz_content", "{}"))
            except json.JSONDecodeError:
                biz = {}
        out_trade_no = biz.get("out_trade_no") or params.get("out_trade_no")
        if out_trade_no:
            out_trade_nos.append(str(out_trade_no))
    return out_trade_nos


MAPPING_ANNOTATIONS = (
    "RequestMapping", "GetMapping", "PostMapping", "PutMapping",
    "DeleteMapping", "PatchMapping",
)

CAPABILITY_SPECS = {
    "query": {
        "method": "trade.query",
        "path_keywords": (
            "alipayquery", "querypay", "querypayment", "queryorderpay",
            "querystatus", "paystatus", "paymentstatus", "tradequery",
            "query", "status", "sync",
        ),
        "source_keywords": (
            "alipaytradequeryrequest", "alipay.trade.query", "trade.query",
        ),
        "domain_keywords": ("alipay", "pay", "payment", "trade", "order"),
        "exclude": ("notify", "prepay", "return", "refund", "close", "cancel", "submit", "cart", "login", "auth"),
        "fixed_paths": ("/wx/order/alipay-query",),
        "fallback_paths": ("/wx/order/alipay-query",),
    },
    "refund": {
        "method": "trade.refund",
        "path_keywords": (
            "alipayrefund", "refundpayment", "refundorder", "refund",
        ),
        "source_keywords": (
            "alipaytraderefundrequest", "alipay.trade.refund", "trade.refund",
        ),
        "domain_keywords": ("alipay", "pay", "payment", "trade", "order", "refund"),
        "exclude": ("notify", "prepay", "return", "query", "close", "cancel", "submit", "cart", "login", "auth"),
        "fixed_paths": ("/wx/order/alipay-refund",),
        "fallback_paths": ("/wx/order/alipay-refund",),
    },
    "close": {
        "method": "trade.close",
        "path_keywords": (
            "alipayclose", "closepayment", "closeorder", "closepay", "cancelpay", "cancelorder", "close", "cancel",
            "timeout", "expire", "expired",
        ),
        "source_keywords": (
            "alipaytradecloserequest", "alipay.trade.close", "trade.close",
        ),
        "domain_keywords": ("alipay", "pay", "payment", "trade", "order", "close", "timeout", "expire"),
        "exclude": ("notify", "prepay", "return", "query", "refund", "submit", "cart", "login", "auth"),
        "fixed_paths": ("/wx/order/alipay-close",),
        "fallback_paths": ("/wx/order/alipay-close",),
    },
}


def _java_files():
    primary_roots = [
        Path(WORKSPACE) / "litemall-wx-api" / "src" / "main" / "java",
    ]
    roots = [root for root in primary_roots if root.exists()] or [Path(WORKSPACE)]
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.java"):
            if any(part in ("target", ".git", "node_modules") for part in path.parts):
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def _mapping_paths(annotation):
    values = []
    for value in re.findall(r'"([^"]*)"', annotation):
        lowered = value.lower()
        if lowered.startswith("application/") or lowered.startswith("text/"):
            continue
        if lowered.startswith("${"):
            continue
        values.append(value)
    return values or [""]


def _join_paths(prefix, suffix):
    parts = []
    for part in (prefix, suffix):
        if part:
            parts.append(str(part).strip("/"))
    return "/" + "/".join(p for p in parts if p)


def _candidate_score(spec, route):
    text = f"{route['path']} {route['method_name']} {route['source']}".lower()
    path_text = f"{route['path']} {route['method_name']}".lower()
    if route["path"].startswith("/admin/"):
        return 0
    if any(bad in path_text for bad in spec["exclude"]):
        return 0
    path_hit = any(kw in path_text for kw in spec["path_keywords"])
    source_hit = any(kw in text for kw in spec["source_keywords"])
    domain_hit = source_hit or any(kw in path_text for kw in spec["domain_keywords"])
    if not path_hit and not source_hit:
        return 0
    if not domain_hit:
        return 0
    score = 0
    for kw in spec["path_keywords"]:
        if kw in path_text:
            score += 5
    for kw in spec["source_keywords"]:
        if kw in text:
            score += 3
    if "alipay" in path_text:
        score += 2
    return score


def _parse_java_routes():
    routes = []
    for path in _java_files():
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue

        class_paths = [""]
        pending = []
        collecting = None
        collect_start = 0

        for idx, raw in enumerate(lines):
            line = raw.strip()
            if collecting is not None:
                collecting += " " + line
                if collecting.count("(") <= collecting.count(")"):
                    pending.append((collecting, collect_start))
                    collecting = None
                continue

            m_ann = re.match(r"@(" + "|".join(MAPPING_ANNOTATIONS) + r")\b(.*)", line)
            if m_ann:
                collecting = line
                collect_start = idx
                if collecting.count("(") <= collecting.count(")"):
                    pending.append((collecting, collect_start))
                    collecting = None
                    ann_end = line.find(")")
                    if ann_end >= 0 and re.search(r"\b(?:public|protected|private)\b", line[ann_end + 1:]):
                        line = line[ann_end + 1:].strip()
                    else:
                        continue
                else:
                    continue

            if re.search(r"\bclass\s+\w+", line):
                if pending:
                    class_paths = []
                    for ann, _ in pending:
                        class_paths.extend(_mapping_paths(ann))
                    pending = []
                continue

            m_method = re.search(
                r"\b(?:public|protected|private)\b[^{;=]*?\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
                line,
            )
            if m_method and pending:
                method_name = m_method.group(1)
                window = "\n".join(lines[max(0, idx - 6): min(len(lines), idx + 90)])
                for class_path in class_paths:
                    for ann, ann_idx in pending:
                        for method_path in _mapping_paths(ann):
                            routes.append({
                                "path": _join_paths(class_path, method_path),
                                "method_name": method_name,
                                "source": window,
                                "file": str(path),
                                "line": ann_idx + 1,
                            })
                pending = []
            elif line and not line.startswith("@") and not line.startswith("//") and not line.startswith("*"):
                # Keep mapping annotations across validation/security annotations, but drop stale ones
                # once unrelated executable or field declarations start.
                if pending and not line.endswith("(") and ";" in line:
                    pending = []
    return routes


def discover_candidate_routes(workspace, capability):
    global WORKSPACE
    old_workspace = WORKSPACE
    WORKSPACE = str(workspace)
    try:
        spec = CAPABILITY_SPECS[capability]
        if spec.get("fixed_paths"):
            return list(spec["fixed_paths"])
        ranked = []
        for route in _parse_java_routes():
            score = _candidate_score(spec, route)
            if score > 0:
                ranked.append((score, route))
        ranked.sort(key=lambda item: (-item[0], item[1]["path"]))
        paths = []
        seen = set()
        for _, route in ranked:
            if route["path"] not in seen:
                seen.add(route["path"])
                paths.append(route["path"])
        for path in spec["fallback_paths"]:
            if path not in seen:
                paths.append(path)
        return paths[:16]
    finally:
        WORKSPACE = old_workspace


def _resolve_path(path, order_id, order_sn):
    replacements = {
        "orderId": str(order_id),
        "id": str(order_id),
        "orderSn": str(order_sn),
        "order_sn": str(order_sn),
        "outTradeNo": str(order_sn),
        "out_trade_no": str(order_sn),
    }

    def repl(match):
        key = match.group(1)
        return replacements.get(key, str(order_id))

    return re.sub(r"\{([A-Za-z0-9_]+)\}", repl, path)


def _capability_payload(capability, order_id, order_sn, price):
    request_no = "EVAL_REFUND_%d" % int(time.time())
    payload = {
        "id": order_id,
        "orderId": order_id,
        "order_id": order_id,
        "orderSn": order_sn,
        "order_sn": order_sn,
        "outTradeNo": order_sn,
        "out_trade_no": order_sn,
        "tradeNo": "MOCK_TRADE_001",
        "trade_no": "MOCK_TRADE_001",
    }
    if capability == "refund":
        payload.update({
            "amount": "1.00",
            "refundAmount": "1.00",
            "refund_amount": "1.00",
            "refundFee": "1.00",
            "refund_fee": "1.00",
            "outRequestNo": request_no,
            "out_request_no": request_no,
            "reason": "eval",
            "refundReason": "eval",
        })
    elif capability == "close":
        payload.update({
            "reason": "eval close",
            "closeReason": "eval close",
        })
    return payload


def _biz_from_entry(entry):
    params = entry.get("params", {})
    biz = params.get("_biz") or {}
    if isinstance(biz, str):
        try:
            biz = json.loads(biz)
        except json.JSONDecodeError:
            biz = {}
    if not isinstance(biz, dict):
        biz = {}
    if not biz and params.get("biz_content"):
        try:
            biz = json.loads(params.get("biz_content", "{}"))
        except json.JSONDecodeError:
            biz = {}
    return params, biz


def mock_hits_for_capability(log_before, capability, order_sn, trade_no="MOCK_TRADE_001"):
    method = CAPABILITY_SPECS[capability]["method"]
    hits = []
    for entry in get_mock_log()[log_before:]:
        if method not in entry.get("method", ""):
            continue
        params, biz = _biz_from_entry(entry)
        refs = {
            str(biz.get("out_trade_no", "")),
            str(biz.get("trade_no", "")),
            str(params.get("out_trade_no", "")),
            str(params.get("trade_no", "")),
        }
        if str(order_sn) in refs or str(trade_no) in refs:
            hits.append(entry)
    return hits


def probe_capability_endpoint(token, capability, order_id, order_sn, price):
    ok, routes, responses, hits = probe_capability_with_payload(
        token, capability, order_id, order_sn, price
    )
    attempts = [f"{item.get('mode')}:{item.get('path')}:{item.get('status')}" for item in responses]
    return ok, routes, attempts, hits


def set_order_sn(order_id, new_sn):
    mysql_exec(
        f"UPDATE litemall_order SET order_sn='{new_sn}' WHERE id={int(order_id)} AND deleted=0"
    )


def money_plus(value, increment):
    try:
        return format((Decimal(str(value)) + Decimal(str(increment))).quantize(Decimal("0.01")), "f")
    except (InvalidOperation, TypeError, ValueError):
        return "99999999.99"


def money_minus(value, decrement):
    try:
        result = Decimal(str(value)) - Decimal(str(decrement))
        if result <= 0:
            return "0.01"
        return format(result.quantize(Decimal("0.01")), "f")
    except (InvalidOperation, TypeError, ValueError):
        return "0.01"


def money_normalize(value):
    try:
        return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")
    except (InvalidOperation, TypeError, ValueError):
        return str(value)


def response_looks_rejected(responses):
    reject_tokens = (
        "fail", "failure", "reject", "denied", "invalid", "error",
        "already paid", "paid order", "cannot close", "over amount",
        "已支付", "不能", "不允许", "拒绝", "失败", "超额", "超过",
    )
    for item in responses:
        status = item.get("status")
        body = str(item.get("body", "")).lower()
        if status in (400, 401, 403, 409, 422):
            return True
        if status in (200, 201) and any(token in body for token in reject_tokens):
            return True
    return False


def response_looks_gateway_failure(responses):
    if response_looks_rejected(responses):
        return True
    for item in responses:
        status = item.get("status")
        body = str(item.get("body", "")).lower()
        if isinstance(status, int) and 500 <= status < 600:
            return True
        if "business failed" in body or "system_error" in body or "关单失败" in body:
            return True
    return False


def refund_request_nos(hits):
    values = []
    for entry in hits:
        params, biz = _biz_from_entry(entry)
        value = (
            biz.get("out_request_no") or biz.get("outRequestNo")
            or params.get("out_request_no") or params.get("outRequestNo")
        )
        if value:
            values.append(str(value))
    return values


def refund_amounts(hits):
    values = []
    for entry in hits:
        params, biz = _biz_from_entry(entry)
        value = (
            biz.get("refund_amount") or biz.get("refundAmount")
            or params.get("refund_amount") or params.get("refundAmount")
            or biz.get("refund_fee") or params.get("refund_fee")
        )
        if value:
            values.append(money_normalize(value))
    return values


def _send_payload(url, mode, payload, headers):
    if mode == "json":
        return requests.post(url, json=payload, headers=headers, timeout=15)
    if mode == "form":
        return requests.post(url, data=payload, headers=headers, timeout=15)
    return requests.get(url, params=payload, headers=headers, timeout=15)


def _refund_payload(order_id, order_sn, price, amount, request_no):
    payload = _capability_payload("refund", order_id, order_sn, price)
    payload.update({
        "amount": amount,
        "refundAmount": amount,
        "refund_amount": amount,
        "refundFee": amount,
        "refund_fee": amount,
        "outRequestNo": request_no,
        "out_request_no": request_no,
    })
    return payload


def _find_refund_route_and_mode(token, order_id, order_sn, price, amount, request_no):
    routes = discover_candidate_routes(WORKSPACE, "refund")
    headers = {"X-Litemall-Token": token}
    responses = []
    log_before = len(get_mock_log())
    payload = _refund_payload(order_id, order_sn, price, amount, request_no)
    for raw_path in routes:
        path = _resolve_path(raw_path, order_id, order_sn)
        url = f"{BASE_URL}{path}"
        for mode in ("json", "form"):
            try:
                resp = _send_payload(url, mode, payload, headers)
                responses.append({"mode": mode, "path": path, "status": resp.status_code, "body": resp.text[:300]})
            except requests.RequestException as exc:
                responses.append({"mode": mode, "path": path, "status": None, "body": type(exc).__name__})
            hits = mock_hits_for_capability(log_before, "refund", order_sn)
            if hits:
                return path, mode, responses, hits
    return None, None, responses, mock_hits_for_capability(log_before, "refund", order_sn)


def _call_refund_path(token, path, mode, order_id, order_sn, price, amount, request_no):
    headers = {"X-Litemall-Token": token}
    payload = _refund_payload(order_id, order_sn, price, amount, request_no)
    url = f"{BASE_URL}{_resolve_path(path, order_id, order_sn)}"
    log_before = len(get_mock_log())
    try:
        resp = _send_payload(url, mode, payload, headers)
        response = {"mode": mode, "path": path, "status": resp.status_code, "body": resp.text[:300]}
    except requests.RequestException as exc:
        response = {"mode": mode, "path": path, "status": None, "body": type(exc).__name__}
    return response, mock_hits_for_capability(log_before, "refund", order_sn)


def probe_capability_with_payload(token, capability, order_id, order_sn, price, payload_update=None, modes=("json", "form", "params")):
    payload = _capability_payload(capability, order_id, order_sn, price)
    if payload_update:
        payload.update(payload_update)
    routes = discover_candidate_routes(WORKSPACE, capability)
    responses = []
    log_before = len(get_mock_log())
    headers = {"X-Litemall-Token": token}
    for raw_path in routes:
        path = _resolve_path(raw_path, order_id, order_sn)
        url = f"{BASE_URL}{path}"
        for mode in modes:
            try:
                if mode == "json":
                    resp = requests.post(url, json=payload, headers=headers, timeout=15)
                elif mode == "form":
                    resp = requests.post(url, data=payload, headers=headers, timeout=15)
                else:
                    resp = requests.get(url, params=payload, headers=headers, timeout=15)
                responses.append({"mode": mode, "path": path, "status": resp.status_code, "body": resp.text[:300]})
            except requests.RequestException as exc:
                responses.append({"mode": mode, "path": path, "status": None, "body": type(exc).__name__})
            hits = mock_hits_for_capability(log_before, capability, order_sn)
            if hits:
                return True, routes, responses, hits
    return False, routes, responses, mock_hits_for_capability(log_before, capability, order_sn)


# ============ Checks ============

def check_app_boot():
    """A1: App builds and starts."""
    try:
        resp = requests.get(f"{BASE_URL}/wx/home/index", timeout=10)
        ok = resp.status_code in (200, 401, 403)
        record("integ.app_boot", "应用构建启动", "functionality", ok,
               f"GET /wx/home/index → HTTP {resp.status_code}")
        return ok
    except requests.RequestException as e:
        record("integ.app_boot", "应用构建启动", "functionality", False, f"连接失败: {e}")
        return False


def check_prepay_form(token):
    """A2: Prepay returns HTML form."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.prepay_form", "prepay 返回支付宝表单", "functionality", False,
               "无法创建订单（cart/add 或 submit 失败）")
        return
    resp = requests.post(f"{BASE_URL}/wx/order/alipay-prepay",
                         json={"orderId": order_id},
                         headers={"X-Litemall-Token": token}, timeout=30)
    body = resp.text
    # Extract from JSON wrapper if needed
    try:
        d = resp.json()
        body = str(d.get("data", body))
    except (ValueError, AttributeError):
        pass
    has_form = "<form" in body.lower()
    has_alipay = "alipay" in body.lower() or "gateway" in body.lower()
    record("integ.prepay_form", "prepay 返回支付宝表单", "functionality",
           resp.status_code == 200 and has_form and has_alipay,
           f"HTTP {resp.status_code}, has_form={has_form}, has_alipay={has_alipay}, body[:100]={body[:100]}")


def check_prepay_hits_mock(token):
    """A3: Prepay form can be submitted to the mock gateway."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.prepay_hits_mock", "prepay 请求到达 mock 网关", "functionality", False,
               "无法创建订单")
        return
    resp, form = request_prepay_form(token, order_id)
    action = form.get("action", "")
    method = prepay_form_method(form)
    action_ok = is_mock_gateway_action(action)
    if resp.status_code != 200 or not action_ok:
        record("integ.prepay_hits_mock", "prepay 请求到达 mock 网关", "functionality", False,
               f"prepay_http={resp.status_code}, action={action[:120]}, method={method}")
        return
    log_before = len(get_mock_log())
    submit_resp = submit_payment_form(form)
    time.sleep(1)
    log_after = get_mock_log()
    new_entries = log_after[log_before:]
    page_pay = [e for e in new_entries if "page.pay" in e.get("method", "")]
    record("integ.prepay_hits_mock", "prepay 请求到达 mock 网关", "functionality",
           len(page_pay) > 0,
           f"action={action[:120]}, method={method}, submit_http="
           f"{getattr(submit_resp, 'status_code', None)}, mock_page_pay={len(page_pay)}, "
           f"new_entries={len(new_entries)}")


def check_notify_rejects_unsigned(token):
    """B1: Unsigned notify is rejected."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.notify_rejects_unsigned", "无签名通知被拒", "security", False, "无法创建订单")
        return
    params = {"out_trade_no": order_sn, "trade_status": "TRADE_SUCCESS",
              "total_amount": price, "trade_no": "FAKE_T_001", "app_id": APP_ID}
    code, body, path = post_notify(params)
    status_after = get_order_status(token, order_id)
    # Should NOT return success, and order should NOT be paid (201)
    not_success = "success" not in body.lower()
    not_paid = status_after != 201
    record("integ.notify_rejects_unsigned", "无签名通知被拒", "security",
           not_success and not_paid,
           f"notify→HTTP {code} body='{body[:60]}', order_status={status_after} (期望≠201)")


def check_notify_rejects_wrong_amount(token, keys):
    """B2: Signed notify with wrong amount is rejected."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.notify_rejects_wrong_amount", "金额篡改通知被拒", "security", False, "无法创建订单")
        return
    wrong_amount = "1.00" if str(price) != "1.00" else "2.00"
    # Sign with correct key but wrong amount
    notify = build_signed_notify({
        "app_id": APP_ID, "out_trade_no": order_sn, "trade_no": "MOCK_T_002",
        "trade_status": "TRADE_SUCCESS", "total_amount": wrong_amount, "seller_id": SELLER_ID,
    }, keys["alipay_private_pem"])
    code, body, path = post_notify(notify)
    status_after = get_order_status(token, order_id)
    rejected = is_failure_response(code, body)
    not_paid = status_after != 201
    record("integ.notify_rejects_wrong_amount", "金额篡改通知被拒", "security", rejected and not_paid,
           f"notify(amount={wrong_amount} vs actual={price})→HTTP {code} body='{body[:60]}', "
           f"rejected={rejected}, status={status_after}")


def check_notify_rejects_wrong_appid(token, keys):
    """B3: Signed notify with wrong app_id is rejected."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.notify_rejects_wrong_appid", "app_id 篡改通知被拒", "security", False, "无法创建订单")
        return
    notify = build_signed_notify({
        "app_id": "EVIL_APP_9999", "out_trade_no": order_sn, "trade_no": "MOCK_T_003",
        "trade_status": "TRADE_SUCCESS", "total_amount": price, "seller_id": SELLER_ID,
    }, keys["alipay_private_pem"])
    code, body, path = post_notify(notify)
    status_after = get_order_status(token, order_id)
    rejected = is_failure_response(code, body)
    not_paid = status_after != 201
    record("integ.notify_rejects_wrong_appid", "app_id 篡改通知被拒", "security", rejected and not_paid,
           f"notify(app_id=EVIL)→HTTP {code} body='{body[:60]}', rejected={rejected}, status={status_after}")


def check_notify_signed_success(token, keys):
    """B4: Valid signed notify updates order to paid."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.notify_signed_success", "有效签名通知通过", "correctness", False, "无法创建订单")
        return
    notify = build_signed_notify({
        "app_id": APP_ID, "out_trade_no": order_sn,
        "trade_no": "MOCK_T_SUCCESS_%d" % int(time.time()),
        "trade_status": "TRADE_SUCCESS", "total_amount": price,
        "seller_id": SELLER_ID, "buyer_id": "2088000000000002",
    }, keys["alipay_private_pem"])
    code, body, path = post_notify(notify)
    time.sleep(1)
    status_after = get_order_status(token, order_id)
    is_success = "success" in body.lower()
    is_paid = status_after == 201
    record("integ.notify_signed_success", "有效签名通知通过", "correctness",
           is_success and is_paid,
           f"notify→HTTP {code} body='{body[:60]}', status={status_after} (期望=201)")


def check_notify_idempotent(token, keys):
    """B5: Same notify twice → still success but no double processing."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.notify_idempotent", "通知幂等", "correctness", False, "无法创建订单")
        return
    notify = build_signed_notify({
        "app_id": APP_ID, "out_trade_no": order_sn,
        "trade_no": "MOCK_T_IDEMP_%d" % int(time.time()),
        "trade_status": "TRADE_SUCCESS", "total_amount": price, "seller_id": SELLER_ID,
    }, keys["alipay_private_pem"])
    # Send twice
    code1, body1, _ = post_notify(notify)
    time.sleep(1)
    code2, body2, _ = post_notify(notify)
    status_after = get_order_status(token, order_id)
    # Both should return success, order should be paid (not errored)
    both_success = "success" in body1.lower() and "success" in body2.lower()
    is_paid = status_after == 201
    record("integ.notify_idempotent", "通知幂等", "correctness",
           both_success and is_paid,
           f"1st: {body1[:30]}, 2nd: {body2[:30]}, status={status_after}")


def check_terminal_not_downgraded(token, keys):
    """C1: Paid order cannot be downgraded by TRADE_CLOSED notify."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.terminal_not_downgraded", "终态不被覆盖", "security", False, "无法创建订单")
        return
    mark_paid(order_id)
    notify = build_signed_notify({
        "app_id": APP_ID, "out_trade_no": order_sn, "trade_no": "MOCK_T_CLOSE",
        "trade_status": "TRADE_CLOSED", "total_amount": price, "seller_id": SELLER_ID,
    }, keys["alipay_private_pem"])
    post_notify(notify)
    time.sleep(1)
    status_after = get_order_status(token, order_id)
    still_paid = status_after == 201
    record("integ.terminal_not_downgraded", "终态不被覆盖", "security", still_paid,
           f"paid 订单收到 TRADE_CLOSED 后 status={status_after} (期望仍=201)")


def check_return_url_not_final(token):
    """C2: Accessing return_url does not mark order as paid."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.return_url_not_final", "return_url 不作终态", "security", False, "无法创建订单")
        return
    # Try common return URL patterns
    for path in ["/wx/order/alipay-return", "/wx/alipay/return", "/alipay/return"]:
        try:
            requests.get(f"{BASE_URL}{path}", params={"out_trade_no": order_sn},
                         headers={"X-Litemall-Token": token}, timeout=10)
        except requests.RequestException:
            pass
    time.sleep(1)
    status_after = get_order_status(token, order_id)
    not_paid = status_after != 201
    record("integ.return_url_not_final", "return_url 不作终态", "security", not_paid,
           f"访问 return_url 后 status={status_after} (期望≠201)")


def check_query_endpoint(token):
    """D1: Trade query endpoint exists and hits mock."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.query_endpoint", "查询端点存在", "functionality", False, "无法创建订单")
        return
    ok, routes, attempts, query_hits = probe_capability_endpoint(
        token, "query", order_id, order_sn, price
    )
    record("integ.query_endpoint", "查询端点存在", "functionality",
           ok,
           f"candidates={routes[:8]}, attempts={len(attempts)}, mock_query_hits={len(query_hits)}")


def check_refund_endpoint(token):
    """D2: Refund endpoint exists and hits mock."""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.refund_endpoint", "退款端点存在", "functionality", False, "无法创建订单")
        return
    mark_paid(order_id)
    ok, routes, attempts, refund_hits = probe_capability_endpoint(
        token, "refund", order_id, order_sn, price
    )
    record("integ.refund_endpoint", "退款端点存在", "functionality",
           ok,
           f"candidates={routes[:8]}, attempts={len(attempts)}, mock_refund_hits={len(refund_hits)}")



def check_notify_wrong_order(token, keys):
    """签名正确但订单号不存在 → 拒绝。instruction A.2: out_trade_no 对应的订单在系统中存在"""
    notify = build_signed_notify({
        "app_id": APP_ID, "out_trade_no": "NONEXISTENT_ORDER_99999",
        "trade_no": "MOCK_T_NOORDER", "trade_status": "TRADE_SUCCESS", "total_amount": "100.00",
        "seller_id": SELLER_ID,
    }, keys["alipay_private_pem"])
    code, body, path = post_notify(notify)
    not_success = "success" not in body.lower()
    record("integ.notify_wrong_order", "不存在订单号的通知被拒", "security", not_success,
           f"notify(out_trade_no=NONEXISTENT)→body='{body[:60]}' (期望不返回 success)")


def check_prepay_out_trade_no_matches(token):
    """两个不同订单 prepay 请求里的 out_trade_no 必须分别等于各自订单号。"""
    ensure_address()
    oid1, sn1, _ = create_order(token)
    oid2, sn2, _ = create_order(token)
    if not oid1 or not oid2:
        record("integ.prepay_out_trade_no_matches", "prepay 使用真实订单号", "correctness",
               False, "无法创建两个订单")
        return
    seen = []
    messages = []
    for oid in (oid1, oid2):
        try:
            resp, form = request_prepay_form(token, oid)
            out_trade_no = prepay_form_out_trade_no(form)
            seen.append(out_trade_no)
            messages.append(
                f"oid={oid}, http={resp.status_code}, action={form.get('action', '')[:80]}, "
                f"out_trade_no={out_trade_no}"
            )
        except requests.RequestException:
            seen.append("")
            messages.append(f"oid={oid}, request_exception")
    seen_set = set(seen)
    ok = sn1 in seen_set and sn2 in seen_set and len(seen_set) >= 2
    record("integ.prepay_out_trade_no_matches", "prepay 使用真实订单号", "correctness", ok,
           f"expected=[{sn1}, {sn2}], form_seen={seen[:5]}, details={messages[:2]}")


def check_refund_idempotent(token):
    """同一 out_request_no 退两次，不能生成不同退款请求号。"""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.refund_idempotent", "退款幂等 (out_request_no)", "correctness", False, "无法创建订单")
        return
    mark_paid(order_id)
    request_no = "EVAL_REFUND_%d" % int(time.time())
    payload_update = {"outRequestNo": request_no, "out_request_no": request_no}
    routes = discover_candidate_routes(WORKSPACE, "refund")
    headers = {"X-Litemall-Token": token}
    attempts = []
    log_before = len(get_mock_log())
    for raw_path in routes:
        path = _resolve_path(raw_path, order_id, order_sn)
        url = f"{BASE_URL}{path}"
        payload = _capability_payload("refund", order_id, order_sn, price)
        payload.update(payload_update)
        for mode in ("json", "form"):
            try:
                if mode == "json":
                    r1 = requests.post(url, json=payload, headers=headers, timeout=15)
                    r2 = requests.post(url, json=payload, headers=headers, timeout=15)
                else:
                    r1 = requests.post(url, data=payload, headers=headers, timeout=15)
                    r2 = requests.post(url, data=payload, headers=headers, timeout=15)
                attempts.append(f"{mode}:{path}:{r1.status_code}/{r2.status_code}")
                refund_hits = mock_hits_for_capability(log_before, "refund", order_sn)
                request_nos = refund_request_nos(refund_hits)
                stable_no = bool(request_nos) and all(no == request_no for no in request_nos)
                ok_status = r1.status_code in (200, 201) and r2.status_code in (200, 201)
                if ok_status and stable_no:
                    record("integ.refund_idempotent", "退款幂等 (out_request_no)", "correctness", True,
                           f"route={path}, mode={mode}, 1st={r1.status_code}, 2nd={r2.status_code}, "
                           f"mock_refund_calls={len(refund_hits)}, out_request_no={request_nos}")
                    return
            except requests.RequestException:
                attempts.append(f"{mode}:{path}:request_exception")
                continue
    refund_hits = mock_hits_for_capability(log_before, "refund", order_sn)
    request_nos = refund_request_nos(refund_hits)
    record("integ.refund_idempotent", "退款幂等 (out_request_no)", "correctness", False,
           f"重复退款未保持稳定 out_request_no，candidates={routes[:8]}, attempts={attempts[:8]}, "
           f"mock_refund_calls={len(refund_hits)}, out_request_no={request_nos}")


def check_refund_partial_sequence(token):
    """两次不同部分退款必须使用不同 out_request_no，并按请求金额调用网关。"""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.refund_partial_sequence", "部分退款请求号与金额", "correctness", False, "无法创建订单")
        return
    mark_paid(order_id)
    ts = int(time.time())
    req1 = f"EVAL_REFUND_PART1_{ts}"
    req2 = f"EVAL_REFUND_PART2_{ts}"
    path, mode, first_responses, first_hits = _find_refund_route_and_mode(
        token, order_id, order_sn, price, "1.00", req1
    )
    if not first_hits or not path:
        record("integ.refund_partial_sequence", "部分退款请求号与金额", "correctness", False,
               f"首笔部分退款未打到网关，responses={first_responses[:3]}")
        return
    second_response, second_hits = _call_refund_path(
        token, path, mode, order_id, order_sn, price, "2.00", req2
    )
    hits = first_hits + second_hits
    request_nos = refund_request_nos(hits)
    amounts = refund_amounts(hits)
    first_status_ok = bool(first_responses) and first_responses[-1].get("status") in (200, 201)
    second_status_ok = second_response.get("status") in (200, 201)
    ok = (
        first_status_ok and second_status_ok
        and bool(second_hits)
        and req1 in request_nos and req2 in request_nos
        and len({req1, req2}) == 2
        and "1.00" in amounts and "2.00" in amounts
    )
    record("integ.refund_partial_sequence", "部分退款请求号与金额", "correctness", ok,
           f"route={path}, mode={mode}, mock_refund_calls={len(hits)}, "
           f"out_request_no={request_nos}, refund_amounts={amounts}, second={second_response}")


def check_refund_over_amount_rejected(token):
    """超过订单金额的退款不能触发网关退款成功路径。"""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.refund_over_amount_rejected", "超额退款被拒", "security", False, "无法创建订单")
        return
    mark_paid(order_id)
    over_amount = money_plus(price, "1.00")
    request_no = "EVAL_REFUND_OVER_%d" % int(time.time())
    ok, routes, responses, refund_hits = probe_capability_with_payload(
        token, "refund", order_id, order_sn, price,
        {"amount": over_amount, "refundAmount": over_amount, "refund_amount": over_amount,
         "refundFee": over_amount, "refund_fee": over_amount,
         "outRequestNo": request_no, "out_request_no": request_no},
        modes=("json", "form"),
    )
    status_after = get_order_status(token, order_id)
    rejected_before_gateway = not refund_hits and response_looks_rejected(responses)
    record("integ.refund_over_amount_rejected", "超额退款被拒", "security",
           rejected_before_gateway and status_after == 201,
           f"amount={over_amount}, order_amount={price}, mock_refund_hits={len(refund_hits)}, "
           f"status={status_after}, responses={responses[:3]}")


def check_refund_cumulative_over_amount_rejected(token):
    """已发生部分退款后，累计超过订单金额的下一笔退款必须在网关前被拒绝。"""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.refund_cumulative_over_amount_rejected", "累计超额退款被拒", "security", False, "无法创建订单")
        return
    mark_paid(order_id)
    ts = int(time.time())
    first_amount = money_minus(price, "1.00")
    first_req = f"EVAL_REFUND_CUM_OK_{ts}"
    path, mode, first_responses, first_hits = _find_refund_route_and_mode(
        token, order_id, order_sn, price, first_amount, first_req
    )
    if not first_hits or not path:
        record("integ.refund_cumulative_over_amount_rejected", "累计超额退款被拒", "security", False,
               f"首笔有效部分退款未打到网关，amount={first_amount}, responses={first_responses[:3]}")
        return
    second_req = f"EVAL_REFUND_CUM_OVER_{ts}"
    second_response, second_hits = _call_refund_path(
        token, path, mode, order_id, order_sn, price, "2.00", second_req
    )
    first_amounts = refund_amounts(first_hits)
    first_status_ok = bool(first_responses) and first_responses[-1].get("status") in (200, 201)
    ok = (
        first_status_ok
        and first_req in refund_request_nos(first_hits)
        and first_amount in first_amounts
        and not second_hits
        and response_looks_rejected([second_response])
    )
    record("integ.refund_cumulative_over_amount_rejected", "累计超额退款被拒", "security", ok,
           f"route={path}, mode={mode}, first_amount={first_amount}, first_hits={len(first_hits)}, "
           f"second_hits={len(second_hits)}, second={second_response}")


def check_refund_fund_change_n_not_final(token):
    """退款接口 code=10000 但 fund_change=N 时，不能当作实际退款完成。"""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.refund_fund_change_n_not_final", "fund_change=N 不作为最终退款", "security", False, "无法创建订单")
        return
    mark_paid(order_id)
    marker_sn = "EVAL_FUND_CHANGE_N_%s" % order_sn[-12:]
    set_order_sn(order_id, marker_sn)
    refund_before = get_order_refund_amount(order_id)
    request_no = "EVAL_FUND_CHANGE_N_%d" % int(time.time())
    ok, routes, responses, refund_hits = probe_capability_with_payload(
        token, "refund", order_id, marker_sn, price,
        {"amount": "0.77", "refundAmount": "0.77", "refund_amount": "0.77",
         "refundFee": "0.77", "refund_fee": "0.77",
         "outRequestNo": request_no, "out_request_no": request_no},
        modes=("json", "form"),
    )
    status_after = get_order_status(token, order_id)
    refund_after = get_order_refund_amount(order_id)
    not_final_refund = status_after in (201, 202)
    refund_amount_unchanged = refund_after == refund_before
    record("integ.refund_fund_change_n_not_final", "fund_change=N 不作为最终退款", "security",
           bool(refund_hits) and not_final_refund and refund_amount_unchanged,
           f"mock_refund_hits={len(refund_hits)} (mock returns fund_change=N), status={status_after}, "
           f"not_final_refund={not_final_refund}, refund_amount_before={refund_before}, "
           f"refund_amount_after={refund_after}, refund_amount_unchanged={refund_amount_unchanged}, "
           f"responses={responses[:3]}")


def check_query_unknown_not_paid(token):
    """查询返回 WAIT_BUYER_PAY/UNKNOWN 时不能推进订单为已支付。"""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.query_unknown_not_paid", "查询未知/待支付不入账", "security", False, "无法创建订单")
        return
    marker_sn = "EVAL_QUERY_UNKNOWN_%s" % order_sn[-12:]
    set_order_sn(order_id, marker_sn)
    ok, routes, responses, query_hits = probe_capability_with_payload(
        token, "query", order_id, marker_sn, price, {}, modes=("json", "form", "params")
    )
    status_after = get_order_status(token, order_id)
    record("integ.query_unknown_not_paid", "查询未知/待支付不入账", "security",
           bool(query_hits) and status_after != 201,
           f"mock_query_hits={len(query_hits)} (mock returns WAIT_BUYER_PAY), status={status_after}, "
           f"responses={responses[:3]}")


def check_paid_order_close_rejected(token):
    """已支付订单不能触发关单网关或覆盖本地已支付状态。"""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.paid_order_close_rejected", "已支付订单不能关单", "security", False, "无法创建订单")
        return
    mark_paid(order_id)
    ok, routes, responses, close_hits = probe_capability_with_payload(
        token, "close", order_id, order_sn, price, {}, modes=("json", "form", "params")
    )
    status_after = get_order_status(token, order_id)
    record("integ.paid_order_close_rejected", "已支付订单不能关单", "security",
           not close_hits and status_after == 201 and response_looks_rejected(responses),
           f"mock_close_hits={len(close_hits)}, status={status_after}, responses={responses[:3]}")


def check_close_failure_not_cancelled(token):
    """关单网关返回失败时，不能把本地未支付订单改为取消。"""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.close_failure_not_cancelled", "关单失败不取消本地订单", "security",
               False, "无法创建订单")
        return
    marker_sn = "EVAL_CLOSE_FAIL_%s" % order_sn[-12:]
    set_order_sn(order_id, marker_sn)
    status_before = get_order_status(token, order_id)
    ok, routes, responses, close_hits = probe_capability_with_payload(
        token, "close", order_id, marker_sn, price, {}, modes=("json", "form", "params")
    )
    time.sleep(1)
    status_after = get_order_status(token, order_id)
    not_cancelled = status_after == status_before == 101
    rejected = response_looks_gateway_failure(responses)
    record("integ.close_failure_not_cancelled", "关单失败不取消本地订单", "security",
           bool(close_hits) and not_cancelled and rejected,
           f"mock_close_hits={len(close_hits)} (mock returns close failure), "
           f"status_before={status_before}, status_after={status_after}, "
           f"not_cancelled={not_cancelled}, rejected={rejected}, responses={responses[:3]}")


def check_close_endpoint(token):
    """关单端点存在且打到 mock。instruction C.8: 未支付订单超时关闭"""
    ensure_address()
    order_id, order_sn, price = create_order(token)
    if not order_id:
        record("integ.close_endpoint", "关单端点存在", "functionality", False, "无法创建订单")
        return
    marker_sn = "EVAL_CLOSE_WAIT_%s" % order_sn[-12:]
    set_order_sn(order_id, marker_sn)
    ok, routes, attempts, close_hits = probe_capability_endpoint(
        token, "close", order_id, marker_sn, price
    )
    record("integ.close_endpoint", "关单端点存在", "functionality",
           ok,
           f"candidates={routes[:8]}, attempts={len(attempts)}, mock_close_hits={len(close_hits)}")


# ============ Main ============

def main():
    print("--- Advanced Integration Tests (23 checks) ---")

    if not check_app_boot():
        # If app isn't up, mark all others failed
        for rid, name, dim in EXPECTED_INTEGRATION[1:]:
            record(rid, name, dim, False, "应用未启动，跳过")
    else:
        token = login()
        if not token:
            print("  WARNING: login failed, some checks may fail")
            token = ""

        keys = {}
        try:
            keys = load_keys(KEYS_DIR)
        except Exception as e:
            print(f"  WARNING: cannot load keys from {KEYS_DIR}: {e}")

        check_prepay_form(token)
        check_prepay_hits_mock(token)
        check_notify_rejects_unsigned(token)
        if keys:
            check_notify_rejects_wrong_amount(token, keys)
            check_notify_rejects_wrong_appid(token, keys)
            check_notify_signed_success(token, keys)
            check_notify_idempotent(token, keys)
            check_terminal_not_downgraded(token, keys)
        else:
            for rid, name in [
                ("integ.notify_rejects_wrong_amount", "金额篡改通知被拒"),
                ("integ.notify_rejects_wrong_appid", "app_id 篡改通知被拒"),
                ("integ.notify_signed_success", "有效签名通知通过"),
                ("integ.notify_idempotent", "通知幂等"),
                ("integ.terminal_not_downgraded", "终态不被覆盖"),
                ("integ.notify_wrong_order", "不存在订单号的通知被拒"),
            ]:
                record(rid, name, "security", False, "密钥加载失败，无法执行签名测试")
        check_return_url_not_final(token)
        check_query_endpoint(token)
        check_refund_endpoint(token)
        if keys:
            check_notify_wrong_order(token, keys)
        check_prepay_out_trade_no_matches(token)
        check_refund_idempotent(token)
        check_refund_partial_sequence(token)
        check_refund_over_amount_rejected(token)
        check_refund_cumulative_over_amount_rejected(token)
        check_refund_fund_change_n_not_final(token)
        check_query_unknown_not_paid(token)
        check_paid_order_close_rejected(token)
        check_close_failure_not_cancelled(token)
        check_close_endpoint(token)

    # Write results
    passed = sum(1 for r in RESULTS if r["passed"])
    print(f"\nIntegration tests: {passed}/{len(RESULTS)} passed")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "integration_results.json"), "w") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
