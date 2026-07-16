#!/usr/bin/env python3
"""Lightweight mock Alipay gateway for litemall-pc-advanced integration tests.

Handles:
  /gateway.do  — routes by `method` param (page.pay, trade.query, trade.refund, trade.close)
  /health      — returns 200 OK
  /mock/log    — returns request log as JSON (for test assertions)

All responses are signed with the alipay private key so the agent's SDK
verification (rsaCheckV1 / rsaCheck) passes.

Usage:
    python3 mock_alipay_gateway.py --keys-dir /tmp/alipay_keys --port 19876

Writes request log to --log-file (default: /tmp/mock_gateway_requests.jsonl).
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock

# Add parent dir so we can import sign_utils from tests/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sign_utils import load_keys, sign_gateway_response

KEYS = {}
REQUEST_LOG = []
LOG_LOCK = Lock()
LOG_FILE = None

# Counters for stateful responses
QUERY_COUNTER = {}
REFUND_RECORDS = {}


def log_request(method, params):
    entry = {"ts": time.time(), "method": method, "params": {k: v for k, v in params.items() if k != "sign"}}
    with LOG_LOCK:
        REQUEST_LOG.append(entry)
        if LOG_FILE:
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def parse_biz_content(raw):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_params(handler):
    content_type = handler.headers.get("Content-Type", "")
    params = {}
    # Query string
    parsed = urllib.parse.urlparse(handler.path)
    params.update(dict(urllib.parse.parse_qsl(parsed.query)))
    # POST body
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length > 0:
        body = handler.rfile.read(content_length).decode("utf-8", errors="replace")
        if "json" in content_type:
            try:
                params.update(json.loads(body))
            except json.JSONDecodeError:
                pass
        else:
            params.update(dict(urllib.parse.parse_qsl(body)))
    return params


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if LOG_FILE:
            with open(LOG_FILE + ".http", "a") as f:
                f.write("[mock] %s %s\n" % (self.client_address[0], fmt % args))

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            self._respond(200, "text/plain", "OK")
        elif path == "/mock/log":
            with LOG_LOCK:
                self._respond(200, "application/json", json.dumps(REQUEST_LOG, ensure_ascii=False))
        elif path == "/gateway.do":
            self._handle_gateway()
        else:
            self._respond(404, "text/plain", "Not Found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/gateway.do":
            self._handle_gateway()
        else:
            self._respond(404, "text/plain", "Not Found")

    def _handle_gateway(self):
        params = extract_params(self)
        method = params.get("method", "")
        biz = parse_biz_content(params.get("biz_content", "{}"))
        log_request(method, {**params, "_biz": biz})

        if method == "alipay.trade.page.pay":
            self._method_page_pay(params, biz)
        elif method == "alipay.trade.query":
            self._method_query(params, biz)
        elif method == "alipay.trade.refund":
            self._method_refund(params, biz)
        elif method == "alipay.trade.fastpay.refund.query":
            self._method_refund_query(params, biz)
        elif method == "alipay.trade.close":
            self._method_close(params, biz)
        else:
            body = sign_gateway_response(
                (method or "unknown").replace(".", "_") + "_response",
                {"code": "40004", "msg": "Business Failed", "sub_code": "ACQ.INVALID_PARAMETER",
                 "sub_msg": "unknown method: %s" % method},
                KEYS["alipay_private_pem"],
            )
            self._respond(200, "application/json", body)

    def _method_page_pay(self, params, biz):
        out_trade_no = biz.get("out_trade_no", "MOCK_ORDER")
        total_amount = biz.get("total_amount", "0.01")
        form_html = (
            '<form id="alipay_submit" name="alipaysubmit" '
            'action="http://localhost:19876/mock/cashier" method="POST">'
            '<input type="hidden" name="out_trade_no" value="%s"/>'
            '<input type="hidden" name="total_amount" value="%s"/>'
            '<input type="hidden" name="product_code" value="%s"/>'
            '<input type="submit" value="pay" style="display:none"/>'
            '</form><script>document.forms["alipaysubmit"].submit();</script>'
        ) % (out_trade_no, total_amount, biz.get("product_code", "FAST_INSTANT_TRADE_PAY"))
        # page.pay returns HTML form directly (not JSON), matching real SDK behavior
        self._respond(200, "text/html", form_html)

    def _method_query(self, params, biz):
        out_trade_no = biz.get("out_trade_no", params.get("out_trade_no", ""))
        trade_status = "TRADE_SUCCESS"
        if str(out_trade_no).startswith("EVAL_QUERY_UNKNOWN"):
            trade_status = "WAIT_BUYER_PAY"
        elif str(out_trade_no).startswith("EVAL_CLOSE_WAIT"):
            trade_status = "WAIT_BUYER_PAY"
        elif str(out_trade_no).startswith("EVAL_CLOSE_FAIL"):
            trade_status = "WAIT_BUYER_PAY"
        elif str(out_trade_no).startswith("EVAL_QUERY_RESULT_UNKNOWN"):
            trade_status = "UNKNOWN"
        body = sign_gateway_response("alipay_trade_query_response", {
            "code": "10000", "msg": "Success",
            "trade_no": "MOCK_T_%s" % out_trade_no[:20],
            "out_trade_no": out_trade_no,
            "trade_status": trade_status,
            "total_amount": biz.get("total_amount", "0.01"),
            "buyer_logon_id": "mock***@sandbox.com",
            "buyer_user_id": "MOCK_BUYER_2088",
        }, KEYS["alipay_private_pem"])
        self._respond(200, "application/json", body)

    def _method_refund(self, params, biz):
        out_trade_no = str(biz.get("out_trade_no", ""))
        out_request_no = str(biz.get("out_request_no", ""))
        refund_amount = str(biz.get("refund_amount", "0.01"))
        fund_change = "N" if (
            out_trade_no.startswith("EVAL_FUND_CHANGE_N")
            or out_request_no.startswith("EVAL_FUND_CHANGE_N")
            or refund_amount in {"0.77", "7.77"}
        ) else "Y"
        if out_trade_no and out_request_no:
            REFUND_RECORDS[(out_trade_no, out_request_no)] = {
                "refund_amount": refund_amount,
                "refund_status": "REFUND_SUCCESS" if fund_change == "Y" else "REFUND_PROCESSING",
            }
        body = sign_gateway_response("alipay_trade_refund_response", {
            "code": "10000", "msg": "Success",
            "trade_no": "MOCK_T_%s" % out_trade_no[:20],
            "out_trade_no": out_trade_no,
            "refund_fee": refund_amount,
            "fund_change": fund_change,
            "buyer_logon_id": "mock***@sandbox.com",
            "buyer_user_id": "MOCK_BUYER_2088",
        }, KEYS["alipay_private_pem"])
        self._respond(200, "application/json", body)

    def _method_refund_query(self, params, biz):
        out_trade_no = str(biz.get("out_trade_no", params.get("out_trade_no", "")))
        out_request_no = str(biz.get("out_request_no", params.get("out_request_no", "")))
        record = REFUND_RECORDS.get((out_trade_no, out_request_no))
        if record:
            response = {
                "code": "10000", "msg": "Success",
                "out_trade_no": out_trade_no,
                "out_request_no": out_request_no,
                "refund_amount": record.get("refund_amount", "0.01"),
                "refund_status": record.get("refund_status", "REFUND_PROCESSING"),
            }
        else:
            response = {
                "code": "40004", "msg": "Business Failed",
                "sub_code": "ACQ.TRADE_NOT_EXIST",
                "sub_msg": "refund request not found",
                "out_trade_no": out_trade_no,
                "out_request_no": out_request_no,
            }
        body = sign_gateway_response(
            "alipay_trade_fastpay_refund_query_response",
            response,
            KEYS["alipay_private_pem"],
        )
        self._respond(200, "application/json", body)

    def _method_close(self, params, biz):
        out_trade_no = str(biz.get("out_trade_no", ""))
        if out_trade_no.startswith("EVAL_CLOSE_FAIL"):
            body = sign_gateway_response("alipay_trade_close_response", {
                "code": "40004", "msg": "Business Failed",
                "sub_code": "ACQ.SYSTEM_ERROR",
                "sub_msg": "mock close failed",
                "out_trade_no": out_trade_no,
            }, KEYS["alipay_private_pem"])
            self._respond(200, "application/json", body)
            return
        body = sign_gateway_response("alipay_trade_close_response", {
            "code": "10000", "msg": "Success",
            "trade_no": "MOCK_T_%s" % out_trade_no[:20],
            "out_trade_no": out_trade_no,
        }, KEYS["alipay_private_pem"])
        self._respond(200, "application/json", body)

    def _respond(self, code, content_type, body):
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)


def main():
    global KEYS, LOG_FILE
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys-dir", required=True)
    parser.add_argument("--port", type=int, default=19876)
    parser.add_argument("--log-file", default="/tmp/mock_gateway_requests.jsonl")
    args = parser.parse_args()

    KEYS = load_keys(args.keys_dir)
    LOG_FILE = args.log_file

    # Clear log
    open(LOG_FILE, "w").close()
    open(LOG_FILE + ".http", "w").close()

    server = HTTPServer(("0.0.0.0", args.port), MockHandler)
    print("Mock Alipay gateway listening on :%d" % args.port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
