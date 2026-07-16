#!/usr/bin/env python3
"""Mock Alipay Gateway for BookCars preauthorization-advanced integration tests.

Handles preauthorization APIs:
  /gateway.do  — routes by `method` param
  /health      — 200 OK
  /mock/log    — request log as JSON
  /mock/send-notify — signs and POSTs a notification to target_url

All responses signed with alipay private key so SDK verification passes.
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sign_utils import load_keys, sign_gateway_response, sign_params

KEYS = {}
REQUEST_LOG = []
LOG_LOCK = Lock()
LOG_FILE = None


def log_request(method, params):
    entry = {"ts": time.time(), "method": method, "params": {k: v for k, v in params.items() if k != "sign"}}
    with LOG_LOCK:
        REQUEST_LOG.append(entry)
        if LOG_FILE:
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def parse_biz(raw):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_params(handler):
    params = {}
    parsed = urllib.parse.urlparse(handler.path)
    params.update(dict(urllib.parse.parse_qsl(parsed.query)))
    cl = int(handler.headers.get("Content-Length", 0))
    if cl > 0:
        body = handler.rfile.read(cl).decode("utf-8", errors="replace")
        ct = handler.headers.get("Content-Type", "")
        if "json" in ct:
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
        elif path == "/mock/send-notify":
            self._handle_send_notify()
        else:
            self._respond(404, "text/plain", "Not Found")

    def _handle_gateway(self):
        params = extract_params(self)
        method = params.get("method", "")
        biz = parse_biz(params.get("biz_content", "{}"))
        log_request(method, {**params, "_biz": biz})

        if method == "alipay.fund.auth.order.app.freeze":
            self._method_freeze(params, biz)
        elif method == "alipay.fund.auth.operation.detail.query":
            self._method_auth_query(params, biz)
        elif method == "alipay.trade.pay":
            self._method_trade_pay(params, biz)
        elif method == "alipay.fund.auth.order.unfreeze":
            self._method_unfreeze(params, biz)
        elif method == "alipay.fund.auth.order.voucher.cancel":
            self._method_cancel(params, biz)
        elif method == "alipay.trade.query":
            self._method_trade_query(params, biz)
        else:
            body = sign_gateway_response(
                (method or "unknown").replace(".", "_") + "_response",
                {"code": "40004", "msg": "Business Failed",
                 "sub_code": "ACQ.INVALID_PARAMETER",
                 "sub_msg": "unknown method: %s" % method},
                KEYS["alipay_private_pem"],
            )
            self._respond(200, "application/json", body)

    def _method_freeze(self, params, biz):
        out_order_no = biz.get("out_order_no", "MOCK_ORDER")
        out_request_no = biz.get("out_request_no", "MOCK_REQ")
        amount = biz.get("amount", "100.00")
        auth_no = "MOCK_AUTH_" + out_order_no[:20]
        scheme_url = "alipays://platformapi/startapp?saId=10000007&clientVersion=3.7.0.0718&orderStr=auth_no=" + auth_no
        body = sign_gateway_response("alipay_fund_auth_order_app_freeze_response", {
            "code": "10000", "msg": "Success",
            "auth_no": auth_no,
            "out_order_no": out_order_no,
            "out_request_no": out_request_no,
            "payer_user_id": "MOCK_USER_2088",
            "total_freeze_amount": amount,
            "operation_id": "MOCK_OP_" + out_order_no[:10],
            "scheme_url": scheme_url,
        }, KEYS["alipay_private_pem"])
        self._respond(200, "application/json", body)

    def _method_auth_query(self, params, biz):
        auth_no = biz.get("auth_no", "MOCK_AUTH")
        out_order_no = biz.get("out_order_no", "")
        status = "SUCCESS"
        if "I17_PENDING" in out_order_no:
            status = "INIT"
        body = sign_gateway_response("alipay_fund_auth_operation_detail_query_response", {
            "code": "10000", "msg": "Success",
            "auth_no": auth_no,
            "out_order_no": out_order_no,
            "total_freeze_amount": "200.00",
            "rest_amount": "200.00",
            "total_pay_amount": "0.00",
            "status": status,
            "payer_user_id": "MOCK_USER_2088",
        }, KEYS["alipay_private_pem"])
        self._respond(200, "application/json", body)

    def _method_trade_pay(self, params, biz):
        body = sign_gateway_response("alipay_trade_pay_response", {
            "code": "10000", "msg": "Success",
            "trade_no": "MOCK_TRADE_%d" % int(time.time()),
            "out_trade_no": biz.get("out_trade_no", ""),
            "total_amount": biz.get("total_amount", "0.01"),
            "buyer_logon_id": "mock***@sandbox.com",
        }, KEYS["alipay_private_pem"])
        self._respond(200, "application/json", body)

    def _method_unfreeze(self, params, biz):
        body = sign_gateway_response("alipay_fund_auth_order_unfreeze_response", {
            "code": "10000", "msg": "Success",
            "auth_no": biz.get("auth_no", "MOCK_AUTH"),
            "out_request_no": biz.get("out_request_no", ""),
            "amount": biz.get("amount", "100.00"),
            "operation_id": "MOCK_UNFREEZE_OP",
            "status": "SUCCESS",
        }, KEYS["alipay_private_pem"])
        self._respond(200, "application/json", body)

    def _method_cancel(self, params, biz):
        body = sign_gateway_response("alipay_fund_auth_order_voucher_cancel_response", {
            "code": "10000", "msg": "Success",
            "auth_no": biz.get("auth_no", "MOCK_AUTH"),
            "out_order_no": biz.get("out_order_no", ""),
            "action": "close",
            "operation_id": "MOCK_CANCEL_OP",
        }, KEYS["alipay_private_pem"])
        self._respond(200, "application/json", body)

    def _method_trade_query(self, params, biz):
        body = sign_gateway_response("alipay_trade_query_response", {
            "code": "10000", "msg": "Success",
            "trade_status": "TRADE_SUCCESS",
            "out_trade_no": biz.get("out_trade_no", ""),
            "trade_no": "MOCK_T_%d" % int(time.time()),
            "total_amount": "0.01",
        }, KEYS["alipay_private_pem"])
        self._respond(200, "application/json", body)

    def _handle_send_notify(self):
        cl = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(cl).decode("utf-8") if cl else "{}"
        try:
            data = json.loads(raw)
        except Exception as e:
            self._respond(400, "application/json", json.dumps({"error": str(e)}))
            return

        target_url = data.get("target_url", "")
        if not target_url:
            self._respond(400, "application/json", json.dumps({"error": "missing target_url"}))
            return

        notify_time = time.strftime("%Y-%m-%d %H:%M:%S")
        notify_type = data.get("notify_type", "trade_status_sync")

        if notify_type == "fund_auth_freeze":
            notify_params = {
                "app_id": data.get("app_id", KEYS.get("app_id", "")),
                "auth_no": data.get("auth_no", ""),
                "out_order_no": data.get("out_order_no", ""),
                "operation_id": data.get("operation_id", "OP_%d" % int(time.time())),
                "out_request_no": data.get("out_request_no", ""),
                "status": data.get("status", "SUCCESS"),
                "total_freeze_amount": data.get("total_freeze_amount", "200.00"),
                "notify_time": notify_time,
                "notify_type": notify_type,
                "notify_id": "mock_notify_%d" % int(time.time() * 1000),
                "charset": "utf-8",
                "version": "1.0",
                "sign_type": "RSA2",
            }
        else:
            notify_params = {
                "app_id": data.get("app_id", KEYS.get("app_id", "")),
                "out_trade_no": data.get("out_trade_no", ""),
                "trade_no": data.get("trade_no", "MOCK%d00001" % int(time.time())),
                "trade_status": data.get("trade_status", "TRADE_SUCCESS"),
                "total_amount": data.get("total_amount", "0.01"),
                "notify_time": notify_time,
                "notify_type": "trade_status_sync",
                "notify_id": "mock_notify_%d" % int(time.time() * 1000),
                "charset": "utf-8",
                "version": "1.0",
                "sign_type": "RSA2",
            }

        notify_params["sign"] = sign_params(notify_params, KEYS["alipay_private_pem"])

        encoded = urllib.parse.urlencode(notify_params).encode("utf-8")
        req = urllib.request.Request(target_url, data=encoded,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            resp_body = resp.read().decode("utf-8", errors="replace")
            resp_code = resp.getcode()
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8", errors="replace")
            resp_code = e.code
        except Exception as e:
            resp_body = str(e)
            resp_code = 0

        self._respond(200, "application/json", json.dumps({
            "status": resp_code, "body": resp_body, "signed_params": notify_params,
        }, ensure_ascii=False))

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
    open(LOG_FILE, "w").close()

    server = HTTPServer(("0.0.0.0", args.port), MockHandler)
    print("Mock Alipay gateway (preauth) on :%d" % args.port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
