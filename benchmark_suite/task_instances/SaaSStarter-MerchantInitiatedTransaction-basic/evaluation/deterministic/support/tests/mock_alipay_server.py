#!/usr/bin/env python3
import argparse
import base64
import json
import subprocess
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_PRIVATE_KEY = ROOT / "test_keys" / "mock_alipay_private_key.pem"

state = {
    "scenario": {},
    "agreements": {},
    "trades": {},
    "sign_requests": {},
    "pay_requests": {},
    "notify_counter": 0,
}


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def today_plus(days=30):
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + days * 86400))


def response_key(method):
    return f"{method.replace('.', '_')}_response"


def parse_body(handler):
    length = int(handler.headers.get("content-length") or "0")
    raw = handler.rfile.read(length) if length else b""
    ctype = handler.headers.get("content-type", "")
    if "application/json" in ctype:
        return json.loads(raw.decode() or "{}")
    parsed = urllib.parse.parse_qs(raw.decode(), keep_blank_values=True)
    return {k: v[-1] for k, v in parsed.items()}


def parse_biz(params):
    biz = params.get("biz_content") or params.get("bizContent") or {}
    if isinstance(biz, dict):
        return biz
    if not biz:
        return {}
    return json.loads(biz)


def canonical(params):
    return "&".join(f"{k}={params[k]}" for k in sorted(params) if k not in {"sign", "sign_type"} and params[k] is not None)


def sign_params(params):
    key_path = Path(state.get("private_key") or DEFAULT_PRIVATE_KEY)
    if not key_path.exists():
      return "MOCK_SIGNATURE_NO_KEY"
    proc = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
        input=canonical(params).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return base64.b64encode(proc.stdout).decode()


def signed_response(method, data):
    payload = {response_key(method): data}
    payload["sign"] = sign_params({response_key(method): json.dumps(data, separators=(",", ":"), ensure_ascii=False)})
    return payload


def scenario_for(kind, key):
    by_key = state["scenario"].get(key)
    if by_key:
        return by_key
    return state["scenario"].get(kind, "success")


def gateway_app_pay(params, biz):
    sign_params_obj = biz.get("agreement_sign_params") or {}
    external = sign_params_obj.get("external_agreement_no")
    out_trade_no = biz.get("out_trade_no")
    amount = str(biz.get("total_amount"))
    notify_url = biz.get("notify_url") or params.get("notify_url") or params.get("notifyUrl")
    sign_notify_url = sign_params_obj.get("sign_notify_url")
    scenario = scenario_for("sign", external or out_trade_no)
    if scenario in {"gateway_error", "sign_fail"}:
        return signed_response("alipay.trade.app.pay", {
            "code": "40004" if scenario == "sign_fail" else "20000",
            "msg": "Business Failed" if scenario == "sign_fail" else "Service Currently Unavailable",
            "sub_code": "mock.sign-failed" if scenario == "sign_fail" else "isp.unknow-error",
            "sub_msg": "mock sign failed" if scenario == "sign_fail" else "mock gateway error",
        })
    state["sign_requests"][external] = {
        "app_id": params.get("app_id", "case_mock_app"),
        "external_agreement_no": external,
        "out_trade_no": out_trade_no,
        "total_amount": amount,
        "notify_url": notify_url,
        "sign_notify_url": sign_notify_url,
        "buyer_user_id": "2088000000000000",
    }
    return signed_response("alipay.trade.app.pay", {
        "code": "10000",
        "msg": "Success",
        "out_trade_no": out_trade_no,
        "external_agreement_no": external,
        "total_amount": amount,
        "order_string": f"mock_order_string:{out_trade_no}:{external}",
        "qr_code_content": f"alipays://platformapi/startApp?appId=60000157&orderStr=mock_order_string:{out_trade_no}:{external}",
    })


def gateway_agreement_query(params, biz):
    external = biz.get("external_agreement_no")
    agreement_no = biz.get("agreement_no")
    agreement = None
    if agreement_no:
        agreement = state["agreements"].get(agreement_no)
    if not agreement and external:
        agreement = next((v for v in state["agreements"].values() if v["external_agreement_no"] == external), None)
    scenario = scenario_for("agreement_query", agreement_no or external)
    if scenario == "gateway_error":
        return signed_response("alipay.user.agreement.query", {"code": "20000", "msg": "Service Currently Unavailable", "sub_code": "isp.unknow-error", "sub_msg": "mock gateway error"})
    if scenario == "query_timeout":
        time.sleep(15)
    if not agreement:
        return signed_response("alipay.user.agreement.query", {"code": "40004", "msg": "Business Failed", "sub_code": "mock.agreement-not-found", "sub_msg": "agreement not found"})
    return signed_response("alipay.user.agreement.query", {
        "code": "10000",
        "msg": "Success",
        "principal_id": agreement["buyer_user_id"],
        "principal_open_id": agreement["buyer_open_id"],
        "status": agreement["status"],
        "agreement_no": agreement["agreement_no"],
        "external_agreement_no": agreement["external_agreement_no"],
        "sign_time": agreement["sign_time"],
        "valid_time": agreement["sign_time"],
        "invalid_time": "2117-05-24 00:00:00",
        "next_deduct_time": agreement["next_deduct_time"],
        "personal_product_code": "GENERAL_WITHHOLDING_P",
        "sign_scene": "INDUSTRY|DIGITAL_MEDIA",
    })


def gateway_trade_pay(params, biz):
    agreement_no = (biz.get("agreement_params") or {}).get("agreement_no")
    out_trade_no = biz.get("out_trade_no")
    amount = str(biz.get("total_amount"))
    scenario = scenario_for("deduct", out_trade_no)
    agreement = state["agreements"].get(agreement_no)
    if scenario == "gateway_error":
        return signed_response("alipay.trade.pay", {"code": "20000", "msg": "Service Currently Unavailable", "sub_code": "isp.unknow-error", "sub_msg": "mock gateway error"})
    if not agreement:
        return signed_response("alipay.trade.pay", {"code": "40004", "msg": "Business Failed", "sub_code": "mock.agreement-not-found", "sub_msg": "agreement not found"})
    trade_no = f"MOCKTRADE{int(time.time() * 1000)}"
    status = "TRADE_SUCCESS" if scenario == "success" else "WAIT_BUYER_PAY"
    code = "10000" if scenario == "success" else "10003"
    msg = "Success" if code == "10000" else "Accepted"
    if scenario == "deduct_fail":
        code, msg, status = "40004", "Business Failed", "TRADE_CLOSED"
    state["trades"][out_trade_no] = {
        "out_trade_no": out_trade_no,
        "trade_no": trade_no,
        "total_amount": amount,
        "agreement_no": agreement_no,
        "buyer_user_id": agreement["buyer_user_id"],
        "buyer_open_id": agreement["buyer_open_id"],
        "trade_status": status,
        "notify_url": biz.get("notify_url") or params.get("notify_url") or params.get("notifyUrl"),
        "seller_id": biz.get("seller_id"),
        "product_code": biz.get("product_code"),
    }
    state["pay_requests"][out_trade_no] = state["trades"][out_trade_no]
    payload = {"code": code, "msg": msg, "out_trade_no": out_trade_no, "trade_no": trade_no, "total_amount": amount, "product_code": "GENERAL_WITHHOLDING", "buyer_user_id": agreement["buyer_user_id"], "async_payment_mode": "NORMAL_ASYNC_PAY"}
    if code == "40004":
        payload.update({"sub_code": "mock.deduct-failed", "sub_msg": "mock deduct failed"})
    return signed_response("alipay.trade.pay", payload)


def gateway_trade_query(params, biz):
    out_trade_no = biz.get("out_trade_no")
    trade_no = biz.get("trade_no")
    scenario = scenario_for("trade_query", out_trade_no or trade_no)
    if scenario == "gateway_error":
        return signed_response("alipay.trade.query", {"code": "20000", "msg": "Service Currently Unavailable", "sub_code": "isp.unknow-error", "sub_msg": "mock gateway error"})
    if scenario == "query_timeout":
        time.sleep(15)
    trade = state["trades"].get(out_trade_no) or next((v for v in state["trades"].values() if v["trade_no"] == trade_no), None)
    if not trade:
        return signed_response("alipay.trade.query", {"code": "40004", "msg": "Business Failed", "sub_code": "mock.trade-not-found", "sub_msg": "trade not found"})
    return signed_response("alipay.trade.query", {
        "code": "10000",
        "msg": "Success",
        "trade_no": trade["trade_no"],
        "out_trade_no": trade["out_trade_no"],
        "buyer_user_id": trade["buyer_user_id"],
        "buyer_open_id": trade["buyer_open_id"],
        "trade_status": trade["trade_status"],
        "total_amount": trade["total_amount"],
        "send_pay_date": now(),
    })


METHODS = {
    "alipay.trade.app.pay": gateway_app_pay,
    "alipay.user.agreement.query": gateway_agreement_query,
    "alipay.trade.pay": gateway_trade_pay,
    "alipay.trade.query": gateway_trade_query,
}


def next_notify_id():
    state["notify_counter"] += 1
    return f"mock_notify_{state['notify_counter']}"


def post_form(url, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode()


def build_signed_notify(params, sign=True, bad_signature=False):
    params = {k: str(v) for k, v in params.items() if v is not None}
    params["sign_type"] = "RSA2"
    if sign:
        params["sign"] = sign_params(params)
        if bad_signature:
            params["sign"] = "BAD_" + params["sign"]
    return params


def handle_sign_notify(body):
    external = body.get("external_agreement_no")
    req = state["sign_requests"].get(external)
    if not req:
        raise ValueError("unknown external_agreement_no")
    scenario = body.get("scenario") or scenario_for("sign_notify", external)
    status = "NORMAL" if scenario in {"success", "unsigned", "bad_signature", "wrong_user", "wrong_agreement"} else "CLOSED"
    agreement_no = body.get("agreement_no") or f"AGR-{external}"
    buyer_user_id = body.get("buyer_user_id") or ("2088000099999999" if scenario == "wrong_user" else req["buyer_user_id"])
    params = {
        "notify_time": now(),
        "notify_type": "dut_user_sign",
        "notify_id": body.get("notify_id") or next_notify_id(),
        "app_id": body.get("app_id") or req["app_id"],
        "external_agreement_no": external if scenario != "wrong_agreement" else f"WRONG-{external}",
        "agreement_no": agreement_no,
        "status": status,
        "alipay_user_id": buyer_user_id,
        "alipay_open_id": body.get("buyer_open_id") or "074a1CcTG1LelxKe4xQC0zgNdId0nxi95b5lsNpazWYoCo5",
        "sign_scene": "INDUSTRY|DIGITAL_MEDIA",
        "personal_product_code": "GENERAL_WITHHOLDING_P",
        "next_deduct_time": body.get("next_deduct_time") or today_plus(),
    }
    if status == "NORMAL" and scenario != "wrong_agreement":
        state["agreements"][agreement_no] = {
            "agreement_no": agreement_no,
            "external_agreement_no": external,
            "buyer_user_id": buyer_user_id,
            "buyer_open_id": params["alipay_open_id"],
            "status": "NORMAL",
            "sign_time": now(),
            "next_deduct_time": params["next_deduct_time"],
        }
    signed = build_signed_notify(params, sign=scenario != "unsigned", bad_signature=scenario == "bad_signature")
    return post_form(body.get("notify_url") or req["sign_notify_url"], signed)


def handle_pay_notify(body):
    out_trade_no = body.get("out_trade_no")
    trade = state["trades"].get(out_trade_no)
    if not trade:
        raise ValueError("unknown out_trade_no")
    scenario = body.get("scenario") or scenario_for("pay_notify", out_trade_no)
    trade_status = "TRADE_SUCCESS" if scenario not in {"deduct_fail", "pending"} else ("WAIT_BUYER_PAY" if scenario == "pending" else "TRADE_CLOSED")
    total_amount = body.get("total_amount") or ("0.01" if scenario == "wrong_amount" else trade["total_amount"])
    agreement_no = body.get("agreement_no") or ("WRONG-AGREEMENT" if scenario == "wrong_agreement" else trade["agreement_no"])
    buyer_user_id = body.get("buyer_user_id") or ("2088000099999999" if scenario == "wrong_user" else trade["buyer_user_id"])
    params = {
        "notify_time": now(),
        "notify_type": "trade_status_sync",
        "notify_id": body.get("notify_id") or next_notify_id(),
        "app_id": body.get("app_id") or "case_mock_app",
        "out_trade_no": out_trade_no,
        "trade_no": body.get("trade_no") or trade["trade_no"],
        "trade_status": trade_status,
        "total_amount": total_amount,
        "seller_id": body.get("seller_id") or trade.get("seller_id") or "case_mock_pid",
        "buyer_user_id": buyer_user_id,
        "buyer_open_id": trade["buyer_open_id"],
        "agreement_no": agreement_no,
    }
    signed = build_signed_notify(params, sign=scenario != "unsigned", bad_signature=scenario == "bad_signature")
    return post_form(body.get("notify_url") or trade["notify_url"], signed)


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            body = parse_body(self)
            if self.path == "/gateway.do":
                method = body.get("method")
                if method not in METHODS:
                    self.send_json(400, {"error": f"unsupported method {method}"})
                    return
                self.send_json(200, METHODS[method](body, parse_biz(body)))
                return
            if self.path == "/__mock/reset":
                state["scenario"].clear()
                state["agreements"].clear()
                state["trades"].clear()
                state["sign_requests"].clear()
                state["pay_requests"].clear()
                state["notify_counter"] = 0
                self.send_json(200, {"ok": True})
                return
            if self.path == "/__mock/scenario":
                key = body.get("key") or body.get("kind")
                scenario = body.get("scenario")
                if not key or not scenario:
                    self.send_json(400, {"error": "key/kind and scenario are required"})
                    return
                state["scenario"][key] = scenario
                self.send_json(200, {"ok": True, "scenario": state["scenario"]})
                return
            if self.path == "/__mock/notify/sign":
                status, text = handle_sign_notify(body)
                self.send_json(200, {"ok": True, "status": status, "body": text})
                return
            if self.path == "/__mock/notify/pay":
                status, text = handle_pay_notify(body)
                self.send_json(200, {"ok": True, "status": status, "body": text})
                return
            self.send_json(404, {"error": "not found"})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def do_GET(self):
        if self.path == "/__mock/state":
            self.send_json(200, state)
            return
        self.send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        print(f"[mock-alipay] {self.address_string()} {fmt % args}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4100)
    parser.add_argument("--private-key", default=str(DEFAULT_PRIVATE_KEY))
    args = parser.parse_args()
    state["private_key"] = args.private_key
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"MOCK_ALIPAY_READY=http://{args.host}:{args.port}/gateway.do", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
