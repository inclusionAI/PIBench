#!/usr/bin/env python3
"""Logging proxy that forwards OpenAPI form requests to real Alipay sandbox.

It is not a fake trade gateway: requests are forwarded to REAL_ALIPAY_GATEWAY_URL
and upstream business response data is preserved. For deterministic local grading,
the JSON response is re-signed with the benchmark's mock-Alipay key so the app can
use the same public key for sandbox response verification and mocked async notify.
"""
import json
import os
import sys
try:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
except ImportError:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn

    class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True
from urllib.parse import parse_qs

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sign_utils  # noqa: E402

PORT = int(os.environ.get("ALIPAY_PROXY_PORT", "8233"))
REAL_GATEWAY = os.environ.get("REAL_ALIPAY_GATEWAY_URL", "https://openapi-sandbox.dl.alipaydev.com/gateway.do")
LOG_PATH = os.environ.get("GATEWAY_LOG", "/output/gateway_requests.jsonl")
KEY_DIR = os.environ.get("ALIPAY_KEY_DIR", "/output/real-alipay-keys")
TIMEOUT = int(os.environ.get("REAL_ALIPAY_TIMEOUT", "45"))
ALIPAY_PRIVATE_KEY = sign_utils.load_private_key(os.path.join(KEY_DIR, "alipay_private_key.pem"))


def one(values):
    if not values:
        return ""
    return values[0] if isinstance(values, list) else values


def parse_biz(text):
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {"_raw": text}


def append_log(item):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def resign_gateway_json(text):
    """Return (content_bytes, returned_json) after re-signing response node if possible."""
    try:
        data = json.loads(text)
    except Exception:
        return text.encode("utf-8"), None
    node_name = None
    node = None
    for key, value in data.items():
        if key.endswith("_response") or key == "error_response":
            if isinstance(value, dict):
                node_name, node = key, value
                break
    if not node_name:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), data
    signed = sign_utils.signed_gateway_response(node_name, node, ALIPAY_PRIVATE_KEY)
    try:
        returned = json.loads(signed)
    except Exception:
        returned = {node_name: node}
    return signed.encode("utf-8"), returned


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path.startswith("/__health"):
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(405, "POST form requests only")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length)
        params = {k: one(v) for k, v in parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True).items()}
        method = params.get("method", "")
        entry = {
            "kind": "real_sandbox_proxy_request",
            "method": method,
            "params": params,
            "biz_content": parse_biz(params.get("biz_content", "")),
            "upstream": REAL_GATEWAY,
        }
        try:
            resp = requests.post(
                REAL_GATEWAY,
                data=body,
                headers={"Content-Type": self.headers.get("Content-Type", "application/x-www-form-urlencoded")},
                timeout=TIMEOUT,
            )
            returned_content, returned_json = resign_gateway_json(resp.text)
            entry["response_status"] = resp.status_code
            entry["upstream_response_text"] = resp.text[:4000]
            try:
                entry["upstream_response_json"] = resp.json()
            except Exception:
                pass
            if returned_json is not None:
                entry["response_json"] = returned_json
            append_log(entry)
            self.send_response(resp.status_code)
            self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json; charset=utf-8"))
            self.send_header("Content-Length", str(len(returned_content)))
            self.end_headers()
            self.wfile.write(returned_content)
        except Exception as exc:
            entry["error"] = repr(exc)
            append_log(entry)
            payload = json.dumps({"error_response": {"code": "PROXY_ERROR", "msg": repr(exc)}}, ensure_ascii=False).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)


def main():
    print(f"real sandbox proxy forwarding to {REAL_GATEWAY} on 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
