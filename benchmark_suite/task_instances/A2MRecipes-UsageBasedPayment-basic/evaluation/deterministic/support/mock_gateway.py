#!/usr/bin/env python3
"""Mock A2M payment gateway used by integration tests.

OpenAPI-style behaviour:
- Any request whose URL or body mentions verify/validate  -> verify call
- Non-verify requests are still logged, and fulfillment is judged by whether
  the service sends back the token returned by a successful verify response.

Response control:
- Mode file (A2M_MOCK_MODE_FILE) content "success" / "fail" / "ambiguous"
  decides whether verify-like calls succeed. Confirm calls always succeed.
- Responses carry both `code` ("10000"/"40004") and `payment_status`
  ("SUCCESS"/"FAIL") so different client conventions can be satisfied.

Every request is appended to A2M_MOCK_LOG (JSONL).
"""
import json
import hashlib
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG_PATH = os.environ.get("A2M_MOCK_LOG", "/output/gateway_requests.jsonl")
MODE_FILE = os.environ.get("A2M_MOCK_MODE_FILE", "/tmp/a2m_mock_mode")
PORT = int(os.environ.get("A2M_MOCK_PORT", "18402"))

VERIFY_KEYWORDS = (
    "verify",
    "payment.verify",
    "validate",
    "payment.validate",
    "proofs/validate",
    "proof/validate",
)
CONFIRM_KEYWORDS = ("confirm", "fulfil", "fulfill", "fulfillment", "deliver", "delivery", "delivered")


def parse_body(body):
    try:
        data = json.loads(body)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def fulfillment_token_for(path, body):
    data = parse_body(body)
    proof = str(data.get("proof") or data.get("payment_proof") or data.get("paymentProof") or "")
    resource = str(data.get("resource") or data.get("path") or data.get("url") or path)
    raw = ("%s|%s" % (proof, resource)).encode("utf-8", errors="replace")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return "MOCK_FULFILLMENT_%s" % digest


def current_mode():
    try:
        with open(MODE_FILE) as f:
            return f.read().strip() or "success"
    except OSError:
        return "success"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _classify(self, body):
        parsed = parse_body(body)
        action = str(parsed.get("action") or parsed.get("method") or parsed.get("type") or "").lower()
        if action:
            if any(k in action for k in CONFIRM_KEYWORDS) or "settle" in action or "ack" in action:
                return "confirm"
            if any(k in action for k in VERIFY_KEYWORDS):
                return "verify"
        haystack = (self.path + " " + body).lower()
        if any(k in haystack for k in CONFIRM_KEYWORDS):
            return "confirm"
        if any(k in haystack for k in VERIFY_KEYWORDS):
            return "verify"
        return "other"

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
        kind = self._classify(body)
        mode = current_mode()
        fulfillment_token = fulfillment_token_for(self.path, body) if kind == "verify" and mode == "success" else None

        entry = {
            "ts": time.time(),
            "method": self.command,
            "path": self.path,
            "kind": kind,
            "mode": mode,
            "body": body[:4000],
            "headers": {
                k: v for k, v in self.headers.items()
                if k.lower().startswith(("x-", "payment-", "authorization"))
            },
        }
        if fulfillment_token:
            entry["response_fulfillment_token"] = fulfillment_token
        try:
            with open(LOG_PATH, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

        if kind == "verify" and mode == "fail":
            payload = {
                "code": "40004",
                "msg": "Business Failed",
                "sub_code": "PAYMENT_PROOF_INVALID",
                "payment_status": "FAIL",
                "status": "FAIL",
                "success": False,
                "valid": False,
                "verified": False,
                "data": {"success": False, "valid": False, "verified": False},
            }
        elif kind == "verify" and mode == "ambiguous":
            payload = {
                "code": "10000",
                "msg": "Success",
                "sub_code": "",
                "payment_status": "UNKNOWN",
                "status": "UNKNOWN",
                "data": {
                    "code": "10000",
                    "payment_status": "UNKNOWN",
                    "status": "UNKNOWN",
                },
            }
        else:
            payload = {
                "code": "10000",
                "msg": "Success",
                "payment_status": "SUCCESS",
                "status": "SUCCESS",
                "success": True,
                "valid": True,
                "verified": True,
                "trade_no": "MOCK_TRADE_20260612_0001",
                "transactionId": "MOCK_TRADE_20260612_0001",
                "transaction_id": "MOCK_TRADE_20260612_0001",
                "payment_id": "MOCK_TRADE_20260612_0001",
                "id": "MOCK_TRADE_20260612_0001",
                "verified_at": "2026-06-12T00:00:00Z",
                "fulfillment_id": fulfillment_token,
                "fulfillment_token": fulfillment_token,
            }
            payload["data"] = {
                "code": payload["code"],
                "payment_status": payload["payment_status"],
                "success": True,
                "valid": True,
                "verified": True,
                "trade_no": payload["trade_no"],
                "transactionId": payload["transactionId"],
                "transaction_id": payload["transaction_id"],
                "payment_id": payload["payment_id"],
                "id": payload["id"],
                "fulfillment_id": payload["fulfillment_id"],
                "fulfillment_token": payload["fulfillment_token"],
            }
        # OpenAPI-style envelope so generic SDK clients can parse it too.
        wrapped = dict(payload)
        wrapped["alipay_aipay_agent_payment_verify_response"] = payload
        wrapped["alipay_aipay_agent_fulfillment_confirm_response"] = payload
        data = json.dumps(wrapped, ensure_ascii=False).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def log_message(self, fmt, *args):
        sys.stderr.write("[mock-gateway] " + fmt % args + "\n")


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    sys.stderr.write("[mock-gateway] listening on 127.0.0.1:%d\n" % PORT)
    server.serve_forever()
