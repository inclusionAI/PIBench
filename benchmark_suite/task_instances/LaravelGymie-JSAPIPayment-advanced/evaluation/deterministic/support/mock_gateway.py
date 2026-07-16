"""Mock Alipay OpenAPI sandbox gateway.

Implements the standard form-encoded OpenAPI protocol with RSA2 signing:
- verifies request signatures with the merchant app public key
- supports alipay.trade.create / alipay.trade.query (+ tolerant aliases)
- signs responses with the mock-Alipay private key
- appends every request to a JSONL evidence log for grading

Admin endpoints (test harness only, never documented to the agent):
- GET  /admin/trades            list created trades
- POST /admin/mark_paid        body: out_trade_no=...  -> sets TRADE_SUCCESS
"""
import json
import os
import sys
import threading
import time
import uuid
try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
except ImportError:  # python < 3.7
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True
from urllib.parse import parse_qsl, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sign_utils  # noqa: E402

KEY_DIR = os.environ.get("ALIPAY_KEY_DIR", "/opt/alipay-keys")
LOG_PATH = os.environ.get("GATEWAY_LOG", "/output/gateway_requests.jsonl")
EXPECTED_APP_ID = os.environ.get("ALIPAY_APP_ID", "2021003100000001")
PORT = int(os.environ.get("GATEWAY_PORT", "8233"))

APP_PUBLIC_KEY = sign_utils.load_public_key(os.path.join(KEY_DIR, "app_public_key.pem"))
ALIPAY_PRIVATE_KEY = sign_utils.load_private_key(os.path.join(KEY_DIR, "alipay_private_key.pem"))

TRADES = {}
REFUND_MODE = "success"
LOCK = threading.Lock()


def log_event(event):
    event["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with LOCK:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def response_node_name(method):
    return method.replace(".", "_") + "_response"


def error_body(method, code, msg, sub_code="", sub_msg=""):
    node = {"code": code, "msg": msg}
    if sub_code:
        node["sub_code"] = sub_code
        node["sub_msg"] = sub_msg
    return sign_utils.signed_gateway_response(response_node_name(method), node, ALIPAY_PRIVATE_KEY)


def handle_trade_create(method, params, biz):
    out_trade_no = biz.get("out_trade_no", "")
    if not out_trade_no:
        return error_body(method, "40002", "Invalid Arguments", "isv.missing-out-trade-no",
                          "biz_content.out_trade_no is required")
    if not biz.get("total_amount"):
        return error_body(method, "40002", "Invalid Arguments", "isv.missing-total-amount",
                          "biz_content.total_amount is required")
    if not biz.get("buyer_id") and not biz.get("buyer_open_id"):
        return error_body(method, "40002", "Invalid Arguments", "isv.missing-buyer",
                          "buyer_id or buyer_open_id is required for JSAPI trade create")
    with LOCK:
        existing = TRADES.get(out_trade_no)
        if existing:
            trade_no = existing["trade_no"]
        else:
            trade_no = "20260612" + uuid.uuid4().hex[:16]
            TRADES[out_trade_no] = {
                "trade_no": trade_no,
                "out_trade_no": out_trade_no,
                "total_amount": biz.get("total_amount"),
                "subject": biz.get("subject", ""),
                "product_code": biz.get("product_code", ""),
                "op_app_id": biz.get("op_app_id", ""),
                "buyer_id": biz.get("buyer_id", ""),
                "buyer_open_id": biz.get("buyer_open_id", ""),
                "status": "WAIT_BUYER_PAY",
            }
    node = {"code": "10000", "msg": "Success", "out_trade_no": out_trade_no, "trade_no": trade_no}
    return sign_utils.signed_gateway_response(response_node_name(method), node, ALIPAY_PRIVATE_KEY)


def find_trade(biz):
    out_trade_no = biz.get("out_trade_no", "")
    trade_no = biz.get("trade_no", "")
    if out_trade_no and out_trade_no in TRADES:
        return TRADES[out_trade_no]
    if trade_no:
        for item in TRADES.values():
            if item["trade_no"] == trade_no:
                return item
    return None


def handle_trade_query(method, params, biz):
    with LOCK:
        trade = find_trade(biz)
    if trade is None:
        return error_body(method, "40004", "Business Failed", "ACQ.TRADE_NOT_EXIST", "Trade not found")
    node = {
        "code": "10000",
        "msg": "Success",
        "trade_no": trade["trade_no"],
        "out_trade_no": trade["out_trade_no"],
        "trade_status": trade["status"],
        "total_amount": trade["total_amount"],
        "buyer_user_id": trade.get("buyer_id") or "2088102100000001",
        "buyer_open_id": trade.get("buyer_open_id") or "bench-open-id-1",
    }
    return sign_utils.signed_gateway_response(response_node_name(method), node, ALIPAY_PRIVATE_KEY)


def handle_trade_refund(method, params, biz):
    with LOCK:
        trade = find_trade(biz)
        mode = REFUND_MODE
    if trade is None:
        return error_body(method, "40004", "Business Failed", "ACQ.TRADE_NOT_EXIST", "Trade not found")
    requested = str(biz.get("refund_amount") or "0.00")
    fund_change = "N" if mode == "fund_change_n" else "Y"
    refund_fee = "0.00" if fund_change == "N" else requested
    node = {
        "code": "10000",
        "msg": "Success",
        "trade_no": trade["trade_no"],
        "out_trade_no": trade["out_trade_no"],
        "refund_fee": refund_fee,
        "send_back_fee": refund_fee,
        "fund_change": fund_change,
        "out_request_no": str(biz.get("out_request_no") or ""),
    }
    return sign_utils.signed_gateway_response(response_node_name(method), node, ALIPAY_PRIVATE_KEY)


HANDLERS = {
    "alipay.trade.create": handle_trade_create,
    "alipay.trade.query": handle_trade_query,
    "alipay.trade.refund": handle_trade_refund,
}

# Wrong-product-line methods still answer (signed) with an explicit business error so
# the agent gets actionable feedback, and the request is still logged as evidence.
WRONG_PRODUCT_METHODS = {
    "alipay.trade.wap.pay": "mobile website (WAP) pay is not available for mini-program cashier",
    "alipay.trade.page.pay": "desktop website pay is not available for mini-program cashier",
    "alipay.trade.app.pay": "App pay is not available for mini-program cashier",
    "alipay.trade.precreate": "qr precreate is not the mini-program JSAPI flow",
}


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "MockAlipayGateway/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, body, content_type="application/json;charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_params(self):
        parsed = urlparse(self.path)
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        ctype = (self.headers.get("Content-Type") or "").lower()
        if raw:
            if "json" in ctype:
                try:
                    body = json.loads(raw)
                    if isinstance(body, dict):
                        params.update({k: (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
                                       for k, v in body.items()})
                except ValueError:
                    pass
            else:
                params.update(dict(parse_qsl(raw, keep_blank_values=True)))
        return params, raw

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/admin/trades":
            with LOCK:
                self._send(200, json.dumps(list(TRADES.values()), ensure_ascii=False))
            return
        if parsed.path in ("/gateway", "/gateway/"):
            self._handle_gateway()
            return
        self._send(404, '{"error":"not found"}')

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/admin/mark_paid":
            params, _ = self._read_params()
            out_trade_no = params.get("out_trade_no", "")
            with LOCK:
                trade = TRADES.get(out_trade_no)
                if trade:
                    trade["status"] = "TRADE_SUCCESS"
            self._send(200, json.dumps({"ok": trade is not None}))
            return
        if parsed.path == "/admin/set_trade_status":
            params, _ = self._read_params()
            out_trade_no = params.get("out_trade_no", "")
            status = params.get("status", "WAIT_BUYER_PAY")
            with LOCK:
                trade = TRADES.get(out_trade_no)
                if trade:
                    trade["status"] = status
            self._send(200, json.dumps({"ok": trade is not None, "status": status}))
            return
        if parsed.path == "/admin/set_refund_mode":
            global REFUND_MODE
            params, _ = self._read_params()
            mode = params.get("mode", "success")
            with LOCK:
                REFUND_MODE = mode
            self._send(200, json.dumps({"ok": True, "mode": mode}))
            return
        if parsed.path in ("/gateway", "/gateway/"):
            self._handle_gateway()
            return
        self._send(404, '{"error":"not found"}')

    def _handle_gateway(self):
        params, raw = self._read_params()
        method = params.get("method", "")
        app_id = params.get("app_id", "")
        sign_ok, sign_mode = sign_utils.verify_params(params, APP_PUBLIC_KEY)
        biz = {}
        if params.get("biz_content"):
            try:
                biz = json.loads(params["biz_content"])
            except ValueError:
                biz = {"_parse_error": params["biz_content"][:500]}

        log_event({
            "kind": "gateway_request",
            "method": method,
            "app_id": app_id,
            "sign_type": params.get("sign_type", ""),
            "sign_valid": sign_ok,
            "sign_mode": sign_mode,
            "biz_content": biz,
            "params_keys": sorted(params.keys()),
            "notify_url": params.get("notify_url", ""),
        })

        if not method:
            self._send(200, error_body("alipay.unknown", "40001", "Missing Required Arguments",
                                       "isv.missing-method", "method is required"))
            return
        if app_id != EXPECTED_APP_ID:
            self._send(200, error_body(method, "40002", "Invalid Arguments",
                                       "isv.invalid-app-id", "app_id mismatch"))
            return
        if not sign_ok:
            self._send(200, error_body(method, "40002", "Invalid Arguments",
                                       "isv.invalid-signature", "request signature verification failed"))
            return
        if method in WRONG_PRODUCT_METHODS:
            self._send(200, error_body(method, "40004", "Business Failed",
                                       "ACQ.WRONG_PRODUCT", WRONG_PRODUCT_METHODS[method]))
            return
        handler = HANDLERS.get(method)
        if handler is None:
            self._send(200, error_body(method, "40004", "Business Failed",
                                       "isv.method-not-supported", "method %s not supported in sandbox" % method))
            return
        self._send(200, handler(method, params, biz))


def main():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), GatewayHandler)
    print("mock alipay gateway listening on 127.0.0.1:%d" % PORT, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
