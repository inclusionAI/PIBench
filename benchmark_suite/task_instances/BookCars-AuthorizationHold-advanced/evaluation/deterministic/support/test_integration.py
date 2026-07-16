#!/usr/bin/env python3
"""Integration tests for BookCars Alipay Preauthorization Safety (I1-I17).

The checks exercise HTTP routes and a local mock Alipay gateway. Static checks stay
auxiliary; the hard cases below verify the preauthorization money lifecycle.
"""
import json
import os
from decimal import Decimal, InvalidOperation
import re
import subprocess
import sys
import time

import requests

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"
KEYS_DIR = sys.argv[3] if len(sys.argv) > 3 else "/tmp/alipay_keys"
MOCK_LOG = os.environ.get("MOCK_LOG_FILE", "/tmp/mock_gateway_requests.jsonl")

BACKEND_URL = "http://localhost:9102"
MOCK_GATEWAY = "http://localhost:19876"
TEST_USER_EMAIL = "driver1@bookcars.ma"
TEST_USER_PASSWORD = "B00kC4r5"
MERCHANT_USER_EMAIL = "admin@bookcars.ma"
MERCHANT_USER_PASSWORD = "B00kC4r5"
APP_ID = os.environ.get("ALIPAY_APP_ID") or os.environ.get("BC_ALIPAY_APP_ID") or "eval_app_2026"
MONGO_CONTAINER = "bcpreauth-task-mongo-1"
MONGO_URI = "mongodb://admin:admin@localhost:27017/bookcars?authSource=admin"
QUERY_STATUSES = {
    "INIT",
    "PENDING",
    "SUCCESS",
    "FAILED",
    "FAIL",
    "CLOSED",
    "CANCELLED",
    "CANCELED",
    "AUTHORIZED",
    "AUTH_SUCCESS",
    "FREEZE_SUCCESS",
    "FREEZE_CLOSED",
    "FINISH",
}
TERMINAL_BAD_STATUSES = {"CLOSED", "CANCELLED", "CANCELED", "FAILED", "FAIL"}
PREAUTH_KEY_RE = re.compile(r"(alipay|preauth|pre_auth|auth|out.?order|out.?request|freeze)", re.I)
MONEY_STATE_RE = re.compile(r"(alipay|auth|freeze|unfreeze|deposit|paid|payment|amount|status)", re.I)
MONEY_STATE_IGNORE_RE = re.compile(r"(history|log|logs|processed|created|updated|timestamp|time)", re.I)
AUTH_FAILURE_RE = re.compile(r"(no token|unauthorized|invalid token|require .*role|require supplier|require admin)", re.I)
QUERY_SUCCESS_STATUSES = {"SUCCESS", "AUTHORIZED", "AUTH_SUCCESS", "FREEZE_SUCCESS"}
PREAUTH_SUCCESS_STATUSES = QUERY_SUCCESS_STATUSES | {"AUTHORIZATION_SUCCESS", "FREEZE_AUTH_SUCCESS"}
QUERY_AMBIGUOUS_STATUSES = {"", "INIT", "PENDING", "WAIT_BUYER_PAY", "UNKNOWN"}

RESULTS = []

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sign_utils import load_keys


def record(rid, name, passed, message):
    RESULTS.append({
        "id": rid, "name": name,
        "type": "integration",
        "passed": bool(passed),
        "score": 1 if passed else 0, "max_score": 1,
        "message": str(message)[:1000],
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] {rid}: {name} -- {message[:200]}")


def save_json(name, data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def safe_label(label):
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(label or "evidence"))
    return text[:80] or "evidence"


def save_text(name, text):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, name), "w", encoding="utf-8", errors="ignore") as f:
        f.write(text)


def save_backend_logs(label, tail=300):
    """Save backend container logs when a notify request disconnects or returns HTTP 0."""
    name = f"backend_logs_{safe_label(label)}.txt"
    try:
        proc = subprocess.run(
            ["docker", "logs", "--tail", str(tail), "bcpreauth-task-bc-backend-1"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        save_text(name, (proc.stdout or "") + ("\n--- STDERR ---\n" + proc.stderr if proc.stderr else ""))
    except Exception as e:
        save_text(name, f"could not collect backend logs: {e}")


def mongo_eval(js):
    cmd = ["docker", "exec", MONGO_CONTAINER, "mongosh", MONGO_URI, "--quiet", "--eval", js]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def load_booking(booking_id, evidence_name=None):
    js = """
const doc = db.getSiblingDB("bookcars").Booking.findOne({_id: ObjectId(%s)});
print(EJSON.stringify(doc || null, {relaxed: true}));
""" % json.dumps(booking_id)
    code, stdout, stderr = mongo_eval(js)
    if code != 0:
        data = {"error": stderr or stdout or "mongosh failed"}
        if evidence_name:
            save_json(evidence_name, data)
        return None, data["error"]

    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    raw = lines[-1] if lines else "null"
    try:
        data = json.loads(raw)
    except ValueError as e:
        data = {"error": f"cannot parse mongosh output: {e}", "stdout": stdout}
        if evidence_name:
            save_json(evidence_name, data)
        return None, data["error"]

    if evidence_name:
        save_json(evidence_name, data)
    if data is None:
        return None, "booking not found"
    return data, None


def iter_values(obj, path=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            next_path = f"{path}.{key}" if path else key
            yield from iter_values(value, next_path)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from iter_values(value, f"{path}[{idx}]")
    else:
        yield path, obj


def money_state_snapshot(obj):
    """Extract payment/preauth state fields without depending on one exact schema."""
    snapshot = {}
    for path, value in iter_values(obj or {}):
        if MONEY_STATE_RE.search(path) and not MONEY_STATE_IGNORE_RE.search(path):
            snapshot[path] = value
    return snapshot


def find_first_key(obj, keys):
    keys = set(keys)
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys and value not in (None, ""):
                return str(value)
            found = find_first_key(value, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_first_key(value, keys)
            if found:
                return found
    return ""


def extract_booking_preauth_status(booking):
    """Return a preauth-specific status; avoid generic booking.status false positives."""
    direct_keys = (
        "alipayAuthStatus",
        "authStatus",
        "auth_status",
        "preauthStatus",
        "preAuthStatus",
        "depositAuthStatus",
        "alipayStatus",
    )
    status = find_first_key(booking, direct_keys)
    if status:
        return status.upper()
    for path, value in iter_values(booking or {}):
        if value in (None, ""):
            continue
        if re.search(r"(alipay|preauth|pre_auth|auth|deposit).*status|status.*(alipay|preauth|pre_auth|auth|deposit)", path, re.I):
            return str(value).upper()
    return ""


def expand_json_strings(obj):
    if isinstance(obj, dict):
        return {key: expand_json_strings(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [expand_json_strings(value) for value in obj]
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped.startswith(("{", "[")):
            try:
                return expand_json_strings(json.loads(stripped))
            except ValueError:
                return obj
    return obj


def extract_out_request_no(params):
    params = expand_json_strings(params)
    value = find_first_key(
        params,
        ("out_request_no", "outRequestNo", "out_request", "outRequest"),
    )
    if value:
        return value
    text = json.dumps(params, ensure_ascii=False, default=str)
    for pattern in [
        r'"out_request_no"\s*:\s*"([^"]+)"',
        r'"outRequestNo"\s*:\s*"([^"]+)"',
        r"out_request_no=([^&\s,}]+)",
        r"outRequestNo=([^&\s,}]+)",
    ]:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def pick_out_order_no(freeze_data, booking_doc, booking_id):
    out_order_no = find_first_key(freeze_data, ("outOrderNo", "out_order_no", "out_order", "outOrder"))
    if out_order_no:
        return out_order_no
    if isinstance(booking_doc, dict):
        for path, value in iter_values(booking_doc):
            if value in (None, ""):
                continue
            if re.search(r"(out.?order|order.?no)", path, re.I):
                return str(value)
    return f"PREAUTH_{booking_id}"


def pick_freeze_amount(freeze_data, booking_doc, default="200.00"):
    amount = find_first_key(
        freeze_data,
        ("amount", "total_freeze_amount", "totalFreezeAmount", "freezeAmount", "alipayFreezeAmount"),
    )
    if amount:
        return normalize_amount(amount, default)
    if isinstance(booking_doc, dict):
        for path, value in iter_values(booking_doc):
            if value in (None, ""):
                continue
            if re.search(r"(freeze.?amount|deposit)", path, re.I):
                return normalize_amount(value, default)
    return default


def normalize_amount(value, default="200.00"):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return default


def is_explicit_rejection(code, body):
    text = str(body or "").strip().lower()
    if code in (400, 401, 403, 409, 422):
        return True
    if code == 200 and text in ("fail", "failure"):
        return True
    if code == 200 and text:
        try:
            data = json.loads(text)
            success = data.get("success") if isinstance(data, dict) else None
            status = str(data.get("status", "")).lower() if isinstance(data, dict) else ""
            if success is False or status in ("fail", "failed", "failure", "rejected"):
                return True
        except ValueError:
            pass
    return False


def is_auth_failure(code, body):
    return code in (401, 403) and bool(AUTH_FAILURE_RE.search(str(body or "")))


def is_business_rejection(code, body):
    return is_explicit_rejection(code, body) and not is_auth_failure(code, body)


def decimal_amount(value, default=None):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        if default is None:
            return None
        return Decimal(str(default)).quantize(Decimal("0.01"))


def amount_lte(left, right):
    left_d = decimal_amount(left)
    right_d = decimal_amount(right)
    return left_d is not None and right_d is not None and left_d <= right_d


def amount_eq(left, right):
    left_d = decimal_amount(left)
    right_d = decimal_amount(right)
    return left_d is not None and right_d is not None and left_d == right_d


def biz_from_entry(entry):
    params = expand_json_strings(entry.get("params", {}))
    if isinstance(params, dict):
        biz = params.get("_biz")
        if isinstance(biz, dict):
            return expand_json_strings(biz)
        raw = params.get("biz_content")
        if isinstance(raw, str):
            try:
                return expand_json_strings(json.loads(raw))
            except ValueError:
                return {}
    return {}


def entry_amount(entry):
    biz = biz_from_entry(entry)
    return find_first_key(biz, ("amount", "total_amount", "payAmount", "unfreezeAmount", "releaseAmount"))


def entry_auth_confirm_mode(entry):
    biz = biz_from_entry(entry)
    return str(find_first_key(biz, ("auth_confirm_mode", "authConfirmMode")) or "").upper()


def entry_has_auth_no(entry):
    biz = biz_from_entry(entry)
    text = json.dumps({"params": entry.get("params", {}), "biz": biz}, ensure_ascii=False, default=str)
    return bool(find_first_key(biz, ("auth_no", "authNo")) or re.search(r"\bauth_no\b", text))


def method_entries(entries, method_name):
    return [entry for entry in entries if entry.get("method") == method_name]


def cancel_method_entries(entries):
    return [
        entry for entry in entries
        if entry.get("method") in {
            "alipay.fund.auth.order.voucher.cancel",
            "alipay.fund.auth.operation.cancel",
        }
    ]


def prepare_booking_money_state(
    booking_id,
    label,
    *,
    auth_status="AUTHORIZED",
    freeze_amount="200.00",
    paid_amount="0.00",
    unfrozen_amount="0.00",
    booking_status="paid",
    deposit_status=None,
):
    suffix = f"{label}_{booking_id[-8:]}"
    effective_deposit_status = deposit_status
    if effective_deposit_status is None:
        effective_deposit_status = "FROZEN" if str(auth_status).upper() in PREAUTH_SUCCESS_STATUSES else "PENDING"
    js = """
const id = ObjectId(%s);
const update = {
  $set: {
    status: %s,
    paymentStatus: %s,
    alipayAuthNo: %s,
    alipayAuthStatus: %s,
    alipayDepositStatus: %s,
    alipayFreezeAmount: %s,
    alipayPaidAmount: %s,
    alipayTotalPaidAmount: %s,
    alipayUnfrozenAmount: %s,
    alipayTotalUnfreezeAmount: %s,
    alipayConsumedAmount: %s,
    alipayTradeNo: null,
    alipaySettleStatus: %s,
    alipayOutOrderNo: %s,
    alipayOutRequestNo: %s,
    alipayNotifyProcessed: []
  }
};
const result = db.getSiblingDB("bookcars").Booking.updateOne({_id: id}, update);
const doc = db.getSiblingDB("bookcars").Booking.findOne({_id: id});
print(EJSON.stringify({update: result, booking: doc}, {relaxed: true}));
""" % (
        json.dumps(booking_id),
        json.dumps(booking_status),
        json.dumps(booking_status),
        json.dumps("MOCK_AUTH_" + suffix),
        json.dumps(auth_status),
        json.dumps(effective_deposit_status),
        json.dumps(freeze_amount),
        json.dumps(paid_amount),
        json.dumps(paid_amount),
        json.dumps(unfrozen_amount),
        json.dumps(unfrozen_amount),
        json.dumps(paid_amount),
        json.dumps(auth_status),
        json.dumps("ORDER_" + suffix),
        json.dumps("REQ_" + suffix),
    )
    code, stdout, stderr = mongo_eval(js)
    payload = {"returncode": code, "stdout": stdout, "stderr": stderr}
    try:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        payload["parsed"] = json.loads(lines[-1]) if lines else None
    except ValueError:
        pass
    save_json(f"booking_{safe_label(label)}_prepared.json", payload)
    if code != 0:
        return False, stderr or stdout or "mongosh failed"
    parsed = payload.get("parsed") or {}
    matched = ((parsed.get("update") or {}).get("matchedCount") or 0) > 0
    if not matched:
        return False, f"booking not found for {label} setup"
    return True, "booking prepared"


def call_post_candidate(session, path, body, timeout=30):
    try:
        resp = session.post(f"{BACKEND_URL}{path}", json=body, timeout=timeout)
        return {"path": path, "status": resp.status_code, "body": resp.text[:500]}
    except requests.RequestException as e:
        return {"path": path, "status": 0, "body": str(e)}


def call_trade_pay_candidates(session, booking_id, amount="25.00"):
    body = {
        "bookingId": booking_id,
        "amount": amount,
        "payAmount": amount,
        "consumeAmount": amount,
        "consumedAmount": amount,
        "settleAmount": amount,
        "captureAmount": amount,
        "totalAmount": amount,
        "total_amount": amount,
    }
    attempts = []
    for path in [
        f"/api/alipay/pay/{booking_id}",
        f"/api/alipay/trade-pay/{booking_id}",
        f"/api/alipay/confirm/{booking_id}",
        f"/api/alipay/consume/{booking_id}",
        f"/api/alipay/settle/{booking_id}",
        "/api/alipay/pay",
        "/api/alipay/trade-pay",
        "/api/alipay/confirm",
        "/api/alipay/consume",
        "/api/alipay/settle",
    ]:
        payload = dict(body)
        if path.endswith(booking_id):
            payload.pop("bookingId", None)
        attempt = call_post_candidate(session, path, payload, timeout=30)
        attempts.append(attempt)
        if attempt["status"] not in (0, 404, 405):
            break
    return attempts


def call_cancel_candidates(session, booking_id):
    body = {
        "bookingId": booking_id,
        "reason": "authorization pending or unknown",
        "outRequestNo": f"CANCEL_{booking_id[-8:]}",
    }
    attempts = []
    for path in [
        f"/api/alipay/cancel/{booking_id}",
        f"/api/alipay/voucher-cancel/{booking_id}",
        f"/api/alipay/auth-cancel/{booking_id}",
        "/api/alipay/cancel",
        "/api/alipay/voucher-cancel",
        "/api/alipay/auth-cancel",
    ]:
        payload = dict(body)
        if path.endswith(booking_id):
            payload.pop("bookingId", None)
        attempt = call_post_candidate(session, path, payload, timeout=30)
        attempts.append(attempt)
        if attempt["status"] not in (0, 404, 405):
            break
    return attempts


def build_notify_context(booking_id, freeze_data):
    booking_doc, err = load_booking(booking_id, "booking_after_freeze.json")
    if err:
        print(f"  WARNING: could not inspect Booking after freeze: {err}")
        booking_doc = {}
    out_order_no = pick_out_order_no(freeze_data or {}, booking_doc, booking_id)
    amount = pick_freeze_amount(freeze_data or {}, booking_doc)
    return {
        "booking": booking_doc,
        "out_order_no": out_order_no,
        "amount": amount,
        "auth_no": f"MOCK_AUTH_{booking_id[:8]}",
    }


def sign_in(session):
    for path in ("/api/sign-in/frontend", "/api/sign-in"):
        try:
            resp = session.post(f"{BACKEND_URL}{path}",
                                json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
                                timeout=15)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            continue
    return False


def sign_in_mobile_session(email=MERCHANT_USER_EMAIL, password=MERCHANT_USER_PASSWORD):
    session = requests.Session()
    payload = {"email": email, "password": password, "mobile": True}
    attempts = []
    for path in ("/api/sign-in/admin", "/api/sign-in/frontend"):
        try:
            resp = session.post(f"{BACKEND_URL}{path}", json=payload, timeout=15)
            body = resp.text[:300]
            attempts.append({"path": path, "status": resp.status_code, "body": body})
            if resp.status_code != 200:
                continue
            try:
                data = resp.json()
            except ValueError:
                data = {}
            token = data.get("accessToken") if isinstance(data, dict) else None
            if token:
                session.headers.update({"x-access-token": token})
                return session, None
        except requests.RequestException as e:
            attempts.append({"path": path, "status": 0, "body": str(e)[:300]})
    return None, f"merchant mobile sign-in failed: {attempts}"


def get_booking_id():
    path = os.path.join(OUTPUT_DIR, "test_booking_id.txt")
    if os.path.exists(path):
        bid = open(path).read().strip()
        if bid:
            return bid, True
    return "000000000000000000000001", False


def get_mock_log():
    try:
        with open(MOCK_LOG) as f:
            return [json.loads(line) for line in f if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def post_notify_unsigned(session, booking_id, extra=None):
    """POST unsigned notification to backend."""
    payload = {
        "app_id": APP_ID,
        "auth_no": "MOCK_AUTH_001",
        "out_order_no": f"PREAUTH_{booking_id}",
        "operation_id": "OP_001",
        "out_request_no": f"REQ_{booking_id}",
        "status": "SUCCESS",
        "total_freeze_amount": "200.00",
        "notify_time": "2026-06-17 10:00:00",
        "notify_type": "fund_auth_freeze",
        "notify_id": "mock_001",
        "charset": "utf-8",
        "version": "1.0",
        "sign_type": "RSA2",
    }
    if extra:
        payload.update(extra)
    resp = session.post(f"{BACKEND_URL}/api/alipay/notify", data=payload, timeout=30)
    return resp.status_code, resp.text.strip()


def send_signed_notify(booking_id, keys, context=None, extra=None, label=None):
    """Use mock gateway send-notify to send a properly signed notification."""
    context = context or {}
    data = {
        "target_url": f"{BACKEND_URL}/api/alipay/notify",
        "notify_type": "fund_auth_freeze",
        "app_id": APP_ID,
        "out_order_no": context.get("out_order_no") or f"PREAUTH_{booking_id}",
        "auth_no": context.get("auth_no") or f"MOCK_AUTH_{booking_id[:8]}",
        "operation_id": f"OP_{int(time.time())}",
        "out_request_no": f"REQ_{booking_id}",
        "status": "SUCCESS",
        "total_freeze_amount": context.get("amount") or "200.00",
    }
    if extra:
        data.update(extra)
    try:
        resp = requests.post(f"{MOCK_GATEWAY}/mock/send-notify", json=data, timeout=15)
        result = resp.json()
        if label:
            save_json(f"signed_notify_{safe_label(label)}.json", {
                "mock_request": data,
                "mock_http_status": resp.status_code,
                "mock_response": result,
                "signed_params": result.get("signed_params"),
            })
        if int(result.get("status", 0) or 0) == 0:
            save_backend_logs(label or "signed_notify_http0")
        return result.get("status", 0), result.get("body", "")
    except Exception as e:
        if label:
            save_json(f"signed_notify_{safe_label(label)}.json", {
                "mock_request": data,
                "exception": str(e),
            })
        save_backend_logs(label or "signed_notify_exception")
        return 0, str(e)


# ============ Checks ============

def check_app_boot():
    try:
        resp = requests.get(f"{BACKEND_URL}/api/settings", timeout=10)
        ok = resp.status_code in (200, 401, 403, 500)
        record("I1", "应用启动", ok, f"GET /api/settings -> HTTP {resp.status_code}")
        return ok
    except requests.RequestException as e:
        record("I1", "应用启动", False, f"连接失败: {e}")
        return False


def check_freeze_hits_mock(session, booking_id):
    """I2: Freeze endpoint initiates preauthorization through mock or returns an app scheme URL."""
    log_before = len(get_mock_log())
    data = {}
    try:
        resp = session.get(f"{BACKEND_URL}/api/alipay/freeze/{booking_id}", timeout=60)
        time.sleep(1)
        log_after = get_mock_log()
        freeze_hits = [e for e in log_after[log_before:] if "freeze" in e.get("method", "")]
        has_hit = len(freeze_hits) > 0
        scheme_url = ""
        if resp.status_code == 200:
            try:
                data = resp.json()
                scheme_url = str(data.get("schemeUrl", data.get("scheme_url", "")))
            except ValueError:
                pass
        ok = has_hit or scheme_url.startswith("alipays://")
        record("I2", "freeze 发起预授权", ok,
               f"mock hits={len(freeze_hits)}, HTTP {resp.status_code}, schemeUrl={scheme_url[:80]}")
    except Exception as e:
        record("I2", "freeze 发起预授权", False, f"Error: {e}")
    return data


def check_notify_rejects_unsigned(session, booking_id, context=None):
    """I3: Unsigned notify is rejected."""
    extra = {}
    if context:
        extra = {
            "out_order_no": context.get("out_order_no"),
            "auth_no": context.get("auth_no"),
            "total_freeze_amount": context.get("amount"),
        }
    code, body = post_notify_unsigned(session, booking_id, extra)
    rejected = is_explicit_rejection(code, body)
    record("I3", "无签名通知被拒", rejected,
           f"HTTP {code}, body='{body[:80]}' (期望明确 failure/4xx)")


def check_notify_rejects_wrong_appid(session, booking_id, keys, context):
    """I4: Signed notify with wrong app_id is rejected."""
    code, body = send_signed_notify(
        booking_id, keys, context, {"app_id": "EVIL_APP_9999"}, label="I4_wrong_appid"
    )
    rejected = is_explicit_rejection(code, body)
    record("I4", "错误 app_id 通知被拒", rejected,
           f"HTTP {code}, body='{body[:80]}' (期望明确 failure/4xx)")


def check_notify_signed_success(session, booking_id, keys, context):
    """I5: Valid signed notify returns success."""
    code, body = send_signed_notify(booking_id, keys, context, label="I5_signed_success")
    is_success = code == 200 and "success" in body.lower()
    record("I5", "有效签名通知通过", is_success,
           f"HTTP {code}, body='{body[:80]}'")
    return is_success


def check_notify_idempotent(session, booking_id, keys, context):
    """I6: Same notification twice still returns success."""
    idem_extra = {
        "notify_id": f"mock_idem_{booking_id}",
        "operation_id": f"OP_IDEM_{booking_id[-8:]}",
        "out_request_no": f"REQ_IDEM_{booking_id[-8:]}",
    }
    send_signed_notify(booking_id, keys, context, idem_extra, label="I6_idempotent_first")
    time.sleep(1)
    code2, body2 = send_signed_notify(
        booking_id, keys, context, idem_extra, label="I6_idempotent_second"
    )
    is_success = code2 == 200 and "success" in body2.lower()
    record("I6", "通知幂等", is_success,
           f"2nd notify: HTTP {code2}, body='{body2[:80]}'")


def check_terminal_protection(session, booking_id, keys, context):
    """I7: Authorized booking not downgraded by CLOSED notify."""
    code1, body1 = send_signed_notify(booking_id, keys, context, {
        "notify_id": f"mock_terminal_success_{booking_id}",
        "operation_id": f"OP_TERM_OK_{booking_id[-6:]}",
        "status": "SUCCESS",
    }, label="I7_terminal_success")
    time.sleep(1)
    if not (code1 == 200 and "success" in body1.lower()):
        record("I7", "终态保护 (SUCCESS 不被 CLOSED 覆盖)", False,
               f"setup SUCCESS notify failed: HTTP {code1}, body='{body1[:80]}'")
        return

    booking_before, err = load_booking(booking_id, "booking_after_success_notify_i7.json")
    if err:
        record("I7", "终态保护 (SUCCESS 不被 CLOSED 覆盖)", False, f"SUCCESS 后无法读取 Booking: {err}")
        return
    status_before = extract_booking_preauth_status(booking_before)
    if status_before not in PREAUTH_SUCCESS_STATUSES:
        record("I7", "终态保护 (SUCCESS 不被 CLOSED 覆盖)", False,
               f"SUCCESS notify 未持久化授权成功态: stored status={status_before or '<empty>'}")
        return

    code2, body2 = send_signed_notify(booking_id, keys, context, {
        "notify_id": f"mock_terminal_closed_{booking_id}",
        "operation_id": f"OP_TERM_CLOSED_{booking_id[-6:]}",
        "status": "CLOSED",
    }, label="I7_terminal_closed")
    time.sleep(1)

    booking, err = load_booking(booking_id, "booking_after_closed_notify.json")
    if err:
        record("I7", "终态保护 (SUCCESS 不被 CLOSED 覆盖)", False, f"无法读取 Booking: {err}")
        return

    status_after = extract_booking_preauth_status(booking)
    preserved_success = status_after == status_before and status_after in PREAUTH_SUCCESS_STATUSES
    not_downgraded = status_after not in TERMINAL_BAD_STATUSES
    ok = preserved_success and not_downgraded
    record("I7", "终态保护 (SUCCESS 不被 CLOSED 覆盖)", ok,
           f"CLOSED notify HTTP {code2}, body='{body2[:60]}', status before={status_before}, after={status_after or '<empty>'}")


def prepare_booking_for_unfreeze_probe(booking_id):
    """Prepare just enough Alipay state so I8 checks routing, not business preconditions."""
    suffix = booking_id[-8:]
    js = """
const id = ObjectId(%s);
const update = {
  $set: {
    status: "paid",
    paymentStatus: "paid",
    alipayAuthNo: "MOCK_AUTH_I8_%s",
    alipayAuthStatus: "AUTHORIZED",
    alipayDepositStatus: "FROZEN",
    alipayFreezeAmount: "200.00",
    alipayPaidAmount: "50.00",
    alipayUnfrozenAmount: "0.00",
    alipayTotalPaidAmount: "50.00",
    alipayTotalUnfreezeAmount: "0.00",
    alipayOutOrderNo: "I8_ORDER_%s",
    alipayOutRequestNo: "I8_REQ_%s"
  }
};
const result = db.getSiblingDB("bookcars").Booking.updateOne({_id: id}, update);
const doc = db.getSiblingDB("bookcars").Booking.findOne({_id: id});
print(EJSON.stringify({update: result, booking: doc}, {relaxed: true}));
""" % (json.dumps(booking_id), suffix, suffix, suffix)
    code, stdout, stderr = mongo_eval(js)
    payload = {"returncode": code, "stdout": stdout, "stderr": stderr}
    try:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        payload["parsed"] = json.loads(lines[-1]) if lines else None
    except ValueError:
        pass
    save_json("booking_i8_prepared.json", payload)
    if code != 0:
        return False, stderr or stdout or "mongosh failed"
    parsed = payload.get("parsed") or {}
    matched = ((parsed.get("update") or {}).get("matchedCount") or 0) > 0
    if not matched:
        return False, "booking not found for I8 setup"
    return True, "booking prepared"


def check_unfreeze_exists(session, booking_id):
    """I8: Unfreeze endpoint exists. Self-contained: prepare auth state first."""
    prepared, prep_msg = prepare_booking_for_unfreeze_probe(booking_id)
    if not prepared:
        record("I8", "unfreeze 端点存在", False, f"I8 setup failed: {prep_msg}")
        return

    candidates = [
        ("POST", f"/api/alipay/unfreeze/{booking_id}", {
            "bookingId": booking_id,
            "amount": "1.00",
            "unfreezeAmount": "1.00",
            "releaseAmount": "1.00",
            "authConfirmMode": "NOT_COMPLETE",
        }),
        ("POST", f"/api/alipay/release/{booking_id}", {
            "bookingId": booking_id,
            "amount": "1.00",
            "unfreezeAmount": "1.00",
            "releaseAmount": "1.00",
            "authConfirmMode": "NOT_COMPLETE",
        }),
        ("POST", "/api/alipay/unfreeze", {
            "bookingId": booking_id,
            "amount": "1.00",
            "unfreezeAmount": "1.00",
            "releaseAmount": "1.00",
            "authConfirmMode": "NOT_COMPLETE",
        }),
        ("POST", "/api/alipay/release", {
            "bookingId": booking_id,
            "amount": "1.00",
            "unfreezeAmount": "1.00",
            "releaseAmount": "1.00",
            "authConfirmMode": "NOT_COMPLETE",
        }),
        ("GET", f"/api/alipay/unfreeze/{booking_id}", None),
        ("GET", f"/api/alipay/release/{booking_id}", None),
    ]
    attempts = []
    for method, path, payload in candidates:
        log_before = len(get_mock_log())
        try:
            if method == "POST":
                resp = session.post(f"{BACKEND_URL}{path}", json=payload, timeout=30)
            else:
                resp = session.get(f"{BACKEND_URL}{path}", timeout=30)
            time.sleep(1)
            entries = get_mock_log()[log_before:]
            unfreeze_hits = [e for e in entries if "unfreeze" in e.get("method", "")]
            attempt = {
                "method": method,
                "path": path,
                "status": resp.status_code,
                "body": resp.text[:300],
                "unfreeze_hits": len(unfreeze_hits),
            }
            attempts.append(attempt)
            if not is_auth_failure(resp.status_code, resp.text) and (resp.status_code not in (404, 405) or unfreeze_hits):
                save_json("unfreeze_exists_i8.json", {"attempts": attempts})
                record("I8", "unfreeze 端点存在", True,
                       f"{method} {path} -> HTTP {resp.status_code}, mock unfreeze hits={len(unfreeze_hits)}")
                return
        except requests.RequestException as e:
            attempts.append({"method": method, "path": path, "status": 0, "body": str(e)[:300]})
    save_json("unfreeze_exists_i8.json", {"attempts": attempts})
    record("I8", "unfreeze 端点存在", False, f"候选路径均像不存在: {attempts}")


def check_query_hits_mock(session, booking_id):
    """I9: Query endpoint hits mock gateway."""
    log_before = len(get_mock_log())
    try:
        resp = session.get(f"{BACKEND_URL}/api/alipay/query/{booking_id}", timeout=30)
        time.sleep(1)
        log_after = get_mock_log()
        query_hits = [e for e in log_after[log_before:]
                      if "query" in e.get("method", "") or "detail" in e.get("method", "")]
        data = {}
        status = ""
        code = ""
        if resp.status_code == 200:
            try:
                data = resp.json()
                status = find_first_key(data, ("status", "trade_status", "authStatus", "alipayAuthStatus"))
                code = find_first_key(data, ("code", "subCode", "sub_code"))
            except ValueError:
                pass
        status_upper = status.upper()
        business_ok = status_upper in QUERY_SUCCESS_STATUSES
        ambiguous = status_upper in QUERY_AMBIGUOUS_STATUSES
        ok = len(query_hits) > 0 and resp.status_code == 200 and business_ok and not ambiguous
        record("I9", "query 打到 mock gateway", ok,
               f"mock query hits={len(query_hits)}, HTTP {resp.status_code}, status={status}, code={code}")
    except Exception as e:
        record("I9", "query 打到 mock gateway", False, f"Error: {e}")


def check_query_non_success_not_authorized(session, booking_id):
    """I17: code=10000 with a non-success auth status must not authorize or unlock funds."""
    prepared, prep_msg = prepare_booking_money_state(
        booking_id,
        "I17_PENDING",
        auth_status="INIT",
        freeze_amount="200.00",
        paid_amount="0.00",
        unfrozen_amount="0.00",
        booking_status="pending",
    )
    if not prepared:
        record("I17", "query 非成功态不能入账/解锁", False, f"I17 setup failed: {prep_msg}")
        return

    log_before = len(get_mock_log())
    try:
        resp = session.get(f"{BACKEND_URL}/api/alipay/query/{booking_id}", timeout=30)
        time.sleep(1)
        new_entries = get_mock_log()[log_before:]
        query_hits = [e for e in new_entries
                      if "query" in e.get("method", "") or "detail" in e.get("method", "")]
        pay_hits = method_entries(new_entries, "alipay.trade.pay")
        unfreeze_hits = method_entries(new_entries, "alipay.fund.auth.order.unfreeze")

        data = {}
        status = ""
        success = None
        if resp.status_code == 200:
            try:
                data = resp.json()
                status = find_first_key(data, ("status", "trade_status", "authStatus", "alipayAuthStatus"))
                success = find_first_key(data, ("success",))
            except ValueError:
                pass

        booking, err = load_booking(booking_id, "booking_after_query_non_success_i17.json")
        after_status = extract_booking_preauth_status(booking) if not err else ""
        payment_status = str((booking or {}).get("paymentStatus", "")).upper() if isinstance(booking, dict) else ""
        booking_status = str((booking or {}).get("status", "")).upper() if isinstance(booking, dict) else ""

        status_upper = status.upper()
        response_not_success = (
            resp.status_code != 200
            or status_upper not in QUERY_SUCCESS_STATUSES
            or str(success).lower() == "false"
        )
        db_not_authorized = after_status not in PREAUTH_SUCCESS_STATUSES
        not_marked_paid = payment_status not in {"PAID", "SUCCESS"} and booking_status not in {"PAID", "SUCCESS"}
        no_money_side_effect = not pay_hits and not unfreeze_hits
        ok = bool(query_hits) and response_not_success and db_not_authorized and not_marked_paid and no_money_side_effect
        save_json("query_non_success_i17.json", {
            "http_status": resp.status_code,
            "response": data if data else resp.text[:500],
            "query_hits": query_hits,
            "pay_hits": pay_hits,
            "unfreeze_hits": unfreeze_hits,
            "after_status": after_status,
            "payment_status": payment_status,
            "booking_status": booking_status,
            "booking_error": err,
        })
        record(
            "I17",
            "query 非成功态不能入账/解锁",
            ok,
            f"query_hits={len(query_hits)}, HTTP {resp.status_code}, response_status={status or '<empty>'}, "
            f"stored_auth={after_status or '<empty>'}, payment={payment_status or '<empty>'}, "
            f"pay_calls={len(pay_hits)}, unfreeze_calls={len(unfreeze_hits)}",
        )
    except Exception as e:
        record("I17", "query 非成功态不能入账/解锁", False, f"Error: {e}")


# ============ Main ============


def check_pay_has_auth_no(session, booking_id):
    """I10: trade.pay should carry auth_no and be triggered with an explicit consumption amount."""
    prepared, prep_msg = prepare_booking_money_state(
        booking_id, "I10", auth_status="AUTHORIZED", freeze_amount="200.00", paid_amount="0.00"
    )
    if not prepared:
        record("I10", "转支付携带 auth_no", False, f"I10 setup failed: {prep_msg}")
        return

    log_before = len(get_mock_log())
    attempts = call_trade_pay_candidates(session, booking_id, amount="25.00")
    time.sleep(1)
    new_entries = get_mock_log()[log_before:]
    pay_entries = method_entries(new_entries, "alipay.trade.pay")
    has_auth_no = any(entry_has_auth_no(e) for e in pay_entries)
    save_json("trade_pay_i10.json", {"attempts": attempts, "pay_entries": pay_entries})
    record("I10", "转支付携带 auth_no", has_auth_no,
           f"new trade.pay calls={len(pay_entries)}, auth_no 参数: {has_auth_no}")


def prepare_booking_for_unfreeze(booking_id):
    """Make I11 independent from earlier notify/pay side effects."""
    suffix = booking_id[-8:]
    js = """
const id = ObjectId(%s);
const update = {
  $set: {
    status: "paid",
    paymentStatus: "paid",
    alipayAuthNo: "MOCK_AUTH_UNFREEZE_%s",
    alipayAuthStatus: "AUTHORIZED",
    alipayDepositStatus: "FROZEN",
    alipayFreezeAmount: "200.00",
    alipayTotalPaidAmount: "50.00",
    alipayPaidAmount: "50.00",
    alipayTotalUnfreezeAmount: "0.00",
    alipayOutOrderNo: "I11_ORDER_%s",
    alipayOutRequestNo: "I11_REQ_%s",
    alipayNotifyProcessed: []
  }
};
const result = db.getSiblingDB("bookcars").Booking.updateOne({_id: id}, update);
const doc = db.getSiblingDB("bookcars").Booking.findOne({_id: id});
print(EJSON.stringify({update: result, booking: doc}, {relaxed: true}));
""" % (json.dumps(booking_id), suffix, suffix, suffix)
    code, stdout, stderr = mongo_eval(js)
    payload = {"returncode": code, "stdout": stdout, "stderr": stderr}
    try:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        payload["parsed"] = json.loads(lines[-1]) if lines else None
    except ValueError:
        pass
    save_json("booking_i11_prepared.json", payload)
    if code != 0:
        return False, stderr or stdout or "mongosh failed"
    parsed = payload.get("parsed") or {}
    matched = ((parsed.get("update") or {}).get("matchedCount") or 0) > 0
    if not matched:
        return False, "booking not found for I11 setup"
    return True, "booking prepared"


def call_unfreeze_candidate(session, method, path, booking_id, body):
    url = f"{BACKEND_URL}{path}"
    try:
        if method == "POST":
            resp = session.post(url, json=body, timeout=30)
        else:
            resp = session.get(url, timeout=30)
        return {"method": method, "path": path, "status": resp.status_code, "body": resp.text[:500]}
    except requests.RequestException as e:
        return {"method": method, "path": path, "status": 0, "body": str(e)}


def check_unfreeze_has_request_no(session, booking_id):
    """解冻请求含稳定 out_request_no（行为幂等）。instruction C.7."""
    prepared, prep_msg = prepare_booking_for_unfreeze(booking_id)
    if not prepared:
        record("I11", "解冻请求含稳定 out_request_no", False, f"I11 setup failed: {prep_msg}")
        return

    idem_key = f"I11_UNFREEZE_{booking_id[-8:]}"
    body = {
        "bookingId": booking_id,
        "amount": "25.00",
        "unfreezeAmount": "25.00",
        "releaseAmount": "25.00",
        "authConfirmMode": "NOT_COMPLETE",
        "idempotencyKey": idem_key,
        "operationId": idem_key,
    }
    candidates = [
        ("POST", f"/api/alipay/unfreeze/{booking_id}"),
        ("POST", f"/api/alipay/release/{booking_id}"),
        ("POST", "/api/alipay/unfreeze"),
        ("POST", "/api/alipay/release"),
        ("GET", f"/api/alipay/unfreeze/{booking_id}"),
        ("GET", f"/api/alipay/release/{booking_id}"),
    ]

    attempts = []
    for method, path in candidates:
        log_before = len(get_mock_log())
        first = call_unfreeze_candidate(session, method, path, booking_id, body)
        time.sleep(1)
        booking_after_first, first_err = load_booking(booking_id, "booking_i11_after_first.json")
        first_snapshot = money_state_snapshot(booking_after_first)
        second = call_unfreeze_candidate(session, method, path, booking_id, body)
        time.sleep(1)
        booking_after_second, second_err = load_booking(booking_id, "booking_i11_after_second.json")
        second_snapshot = money_state_snapshot(booking_after_second)
        new_entries = get_mock_log()[log_before:]
        unfreeze_entries = [e for e in new_entries if "unfreeze" in e.get("method", "")]
        request_nos = [extract_out_request_no(e.get("params", {})) for e in unfreeze_entries]
        request_nos = [x for x in request_nos if x]
        stable_replay = len(request_nos) >= 2 and request_nos[0] == request_nos[1]
        suppressed_replay = len(request_nos) == 1 and second["status"] in (200, 201, 202, 204, 208, 409)
        server_not_crashed = first["status"] < 500 and second["status"] < 500
        snapshots_available = first_err is None and second_err is None
        local_state_stable = snapshots_available and first_snapshot == second_snapshot
        attempts.append({
            "candidate": {"method": method, "path": path},
            "responses": [first, second],
            "unfreeze_entries": unfreeze_entries,
            "request_nos": request_nos,
            "stable_replay": stable_replay,
            "suppressed_replay": suppressed_replay,
            "server_not_crashed": server_not_crashed,
            "local_state_stable": local_state_stable,
            "snapshot_errors": {"first": first_err, "second": second_err},
            "first_money_state": first_snapshot,
            "second_money_state": second_snapshot,
        })
        if request_nos and (stable_replay or suppressed_replay) and server_not_crashed and local_state_stable:
            save_json("unfreeze_idempotency_i11.json", {"attempts": attempts})
            record("I11", "解冻请求含稳定 out_request_no", True,
                   f"{method} {path}: calls={len(unfreeze_entries)}, request_nos={request_nos[:2]}, local_state_stable={local_state_stable}")
            return
        if not is_auth_failure(first["status"], first["body"]) and (first["status"] not in (0, 404, 405) or unfreeze_entries):
            break

    save_json("unfreeze_idempotency_i11.json", {"attempts": attempts})
    last = attempts[-1] if attempts else {}
    record("I11", "解冻请求含稳定 out_request_no", False,
           f"未观察到稳定 out_request_no 或本地状态幂等; attempts={len(attempts)}, last={last}")


def check_trade_pay_then_unfreeze_remaining(session, booking_id):
    """I14: A normal lifecycle should pay actual consumption, then unfreeze only remaining funds."""
    prepared, prep_msg = prepare_booking_money_state(
        booking_id, "I14", auth_status="AUTHORIZED", freeze_amount="200.00", paid_amount="0.00"
    )
    if not prepared:
        record("I14", "转支付后解冻剩余金额", False, f"I14 setup failed: {prep_msg}")
        return

    log_before = len(get_mock_log())
    pay_attempts = call_trade_pay_candidates(session, booking_id, amount="25.00")
    time.sleep(1)
    unfreeze_body = {
        "bookingId": booking_id,
        "amount": "175.00",
        "unfreezeAmount": "175.00",
        "releaseAmount": "175.00",
        "authConfirmMode": "COMPLETE",
        "operationId": f"I14_UNFREEZE_{booking_id[-8:]}",
    }
    unfreeze_attempts = []
    for method, path in [
        ("POST", f"/api/alipay/unfreeze/{booking_id}"),
        ("POST", f"/api/alipay/release/{booking_id}"),
        ("POST", "/api/alipay/unfreeze"),
        ("POST", "/api/alipay/release"),
        ("GET", f"/api/alipay/unfreeze/{booking_id}"),
        ("GET", f"/api/alipay/release/{booking_id}"),
    ]:
        before_this = len(get_mock_log())
        attempt = call_unfreeze_candidate(session, method, path, booking_id, unfreeze_body)
        unfreeze_attempts.append(attempt)
        time.sleep(1)
        if not is_auth_failure(attempt["status"], attempt["body"]) and (
            attempt["status"] not in (0, 404, 405)
            or method_entries(get_mock_log()[before_this:], "alipay.fund.auth.order.unfreeze")
        ):
            break

    entries = get_mock_log()[log_before:]
    pay_indexes = [i for i, e in enumerate(entries) if e.get("method") == "alipay.trade.pay"]
    pay_entries = [entries[i] for i in pay_indexes]
    unfreeze_indexes = [i for i, e in enumerate(entries) if e.get("method") == "alipay.fund.auth.order.unfreeze"]
    unfreeze_entries = [entries[i] for i in unfreeze_indexes]
    explicit_unfreeze_ok = bool(unfreeze_entries) and all(amount_lte(entry_amount(e), "175.00") for e in unfreeze_entries)
    complete_mode_ok = any(
        amount_eq(entry_amount(e), "25.00") and entry_auth_confirm_mode(e) == "COMPLETE"
        for e in pay_entries
    )
    ordered = bool(pay_indexes and unfreeze_indexes and min(pay_indexes) < min(unfreeze_indexes))
    ok = bool(pay_entries) and (complete_mode_ok or (ordered and explicit_unfreeze_ok))
    save_json("preauth_lifecycle_i14.json", {
        "pay_attempts": pay_attempts,
        "unfreeze_attempts": unfreeze_attempts,
        "pay_indexes": pay_indexes,
        "pay_entries": pay_entries,
        "unfreeze_indexes": unfreeze_indexes,
        "unfreeze_entries": unfreeze_entries,
        "explicit_unfreeze_ok": explicit_unfreeze_ok,
        "complete_mode_ok": complete_mode_ok,
    })
    record("I14", "转支付后解冻剩余金额", ok,
           f"pay_calls={len(pay_indexes)}, unfreeze_calls={len(unfreeze_indexes)}, ordered={ordered}, "
           f"explicit_unfreeze_ok={explicit_unfreeze_ok}, complete_mode_ok={complete_mode_ok}")


def check_unfreeze_before_consumption_rejected(session, booking_id):
    """I15: An authorized-but-unconsumed booking must not release frozen deposit early."""
    prepared, prep_msg = prepare_booking_money_state(
        booking_id, "I15", auth_status="AUTHORIZED", freeze_amount="200.00", paid_amount="0.00", booking_status="confirmed"
    )
    if not prepared:
        record("I15", "未消费前不能解冻", False, f"I15 setup failed: {prep_msg}")
        return

    body = {
        "bookingId": booking_id,
        "amount": "200.00",
        "unfreezeAmount": "200.00",
        "releaseAmount": "200.00",
        "authConfirmMode": "COMPLETE",
        "operationId": f"I15_EARLY_UNFREEZE_{booking_id[-8:]}",
    }
    attempts = []
    log_before = len(get_mock_log())
    for method, path in [
        ("POST", f"/api/alipay/unfreeze/{booking_id}"),
        ("POST", f"/api/alipay/release/{booking_id}"),
        ("POST", "/api/alipay/unfreeze"),
        ("POST", "/api/alipay/release"),
        ("GET", f"/api/alipay/unfreeze/{booking_id}"),
        ("GET", f"/api/alipay/release/{booking_id}"),
    ]:
        attempt = call_unfreeze_candidate(session, method, path, booking_id, body)
        attempts.append(attempt)
        time.sleep(1)
        if not is_auth_failure(attempt["status"], attempt["body"]) and attempt["status"] not in (0, 404, 405):
            break
    entries = get_mock_log()[log_before:]
    unfreeze_entries = method_entries(entries, "alipay.fund.auth.order.unfreeze")
    rejected = any(is_business_rejection(a["status"], a["body"]) or a["status"] in (409, 422) for a in attempts)
    ok = rejected and not unfreeze_entries
    save_json("unfreeze_before_consumption_i15.json", {"attempts": attempts, "unfreeze_entries": unfreeze_entries})
    record("I15", "未消费前不能解冻", ok,
           f"rejected={rejected}, mock_unfreeze_calls={len(unfreeze_entries)}, attempts={attempts[:2]}")


def check_cancel_vs_unfreeze_boundary(session, booking_id):
    """I16: Pending/unknown auth should cancel; successful frozen funds should unfreeze."""
    prepared, prep_msg = prepare_booking_money_state(
        booking_id, "I16_CANCEL", auth_status="INIT", freeze_amount="200.00", paid_amount="0.00", booking_status="pending"
    )
    if not prepared:
        record("I16", "撤销与解冻边界", False, f"I16 cancel setup failed: {prep_msg}")
        return

    cancel_before = len(get_mock_log())
    cancel_attempts = call_cancel_candidates(session, booking_id)
    time.sleep(1)
    cancel_entries = get_mock_log()[cancel_before:]
    cancel_hits = cancel_method_entries(cancel_entries)
    early_unfreeze_hits = method_entries(cancel_entries, "alipay.fund.auth.order.unfreeze")

    prepared, prep_msg = prepare_booking_money_state(
        booking_id, "I16_UNFREEZE", auth_status="AUTHORIZED", freeze_amount="200.00", paid_amount="50.00", booking_status="paid"
    )
    if not prepared:
        record("I16", "撤销与解冻边界", False, f"I16 unfreeze setup failed: {prep_msg}")
        return

    unfreeze_body = {
        "bookingId": booking_id,
        "amount": "150.00",
        "unfreezeAmount": "150.00",
        "releaseAmount": "150.00",
        "consumedAmount": "50.00",
        "authConfirmMode": "COMPLETE",
        "operationId": f"I16_RELEASE_{booking_id[-8:]}",
    }
    unfreeze_before = len(get_mock_log())
    unfreeze_attempts = []
    for method, path in [
        ("POST", f"/api/alipay/settle/{booking_id}"),
        ("POST", "/api/alipay/settle"),
        ("POST", f"/api/alipay/unfreeze/{booking_id}"),
        ("POST", f"/api/alipay/release/{booking_id}"),
        ("POST", "/api/alipay/unfreeze"),
        ("POST", "/api/alipay/release"),
        ("GET", f"/api/alipay/unfreeze/{booking_id}"),
        ("GET", f"/api/alipay/release/{booking_id}"),
    ]:
        attempt = call_unfreeze_candidate(session, method, path, booking_id, unfreeze_body)
        unfreeze_attempts.append(attempt)
        time.sleep(1)
        if not is_auth_failure(attempt["status"], attempt["body"]) and (
            attempt["status"] not in (0, 404, 405)
            or method_entries(get_mock_log()[unfreeze_before:], "alipay.fund.auth.order.unfreeze")
        ):
            break
    release_entries = get_mock_log()[unfreeze_before:]
    release_unfreeze_hits = method_entries(release_entries, "alipay.fund.auth.order.unfreeze")
    release_cancel_hits = cancel_method_entries(release_entries)

    ok = bool(cancel_hits) and not early_unfreeze_hits and bool(release_unfreeze_hits) and not release_cancel_hits
    save_json("cancel_vs_unfreeze_i16.json", {
        "cancel_attempts": cancel_attempts,
        "unfreeze_attempts": unfreeze_attempts,
        "cancel_hits": cancel_hits,
        "early_unfreeze_hits": early_unfreeze_hits,
        "release_unfreeze_hits": release_unfreeze_hits,
        "release_cancel_hits": release_cancel_hits,
    })
    record("I16", "撤销与解冻边界", ok,
           f"pending_cancel={len(cancel_hits)}, pending_unfreeze={len(early_unfreeze_hits)}, release_unfreeze={len(release_unfreeze_hits)}, release_cancel={len(release_cancel_hits)}")


def check_notify_wrong_order(session, booking_id, keys):
    """签名正确但 booking 不存在 -> 拒绝。Rubric notify_verify_fields"""
    code, body = send_signed_notify("000000000000000000000000", keys,
                                    context={"out_order_no": "PREAUTH_NONEXISTENT", "amount": "200.00"},
                                    label="I12_wrong_order")
    rejected = is_explicit_rejection(code, body)
    record("I12", "不存在预订号的通知被拒", rejected,
           f"notify(booking=NONEXISTENT)->HTTP {code}, body='{body[:60]}'")


def prepare_booking_for_notify_field_check(booking_id, context):
    """Give I13 a known expected auth_no/amount to compare against."""
    expected = {
        "out_order_no": context.get("out_order_no") or f"PREAUTH_{booking_id}",
        "auth_no": context.get("auth_no") or f"MOCK_AUTH_{booking_id[:8]}",
        "amount": normalize_amount(context.get("amount") or "200.00"),
    }
    js = """
const id = ObjectId(%s);
const update = {
  $set: {
    alipayOutOrderNo: %s,
    alipayAuthNo: %s,
    alipayAuthStatus: "SUCCESS",
    alipayFreezeAmount: %s,
    alipayTotalPaidAmount: "0.00",
    alipayTotalUnfreezeAmount: "0.00",
    alipayNotifyProcessed: []
  }
};
const result = db.getSiblingDB("bookcars").Booking.updateOne({_id: id}, update);
const doc = db.getSiblingDB("bookcars").Booking.findOne({_id: id});
print(EJSON.stringify({expected: %s, update: result, booking: doc}, {relaxed: true}));
""" % (
        json.dumps(booking_id),
        json.dumps(expected["out_order_no"]),
        json.dumps(expected["auth_no"]),
        json.dumps(expected["amount"]),
        json.dumps(expected),
    )
    code, stdout, stderr = mongo_eval(js)
    payload = {"returncode": code, "stdout": stdout, "stderr": stderr, "expected": expected}
    try:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        payload["parsed"] = json.loads(lines[-1]) if lines else None
    except ValueError:
        pass
    save_json("booking_i13_prepared.json", payload)
    if code != 0:
        return False, stderr or stdout or "mongosh failed", expected
    parsed = payload.get("parsed") or {}
    matched = ((parsed.get("update") or {}).get("matchedCount") or 0) > 0
    if not matched:
        return False, "booking not found for I13 setup", expected
    return True, "booking prepared", expected


def check_notify_rejects_field_mismatch(session, booking_id, keys, context):
    """签名正确但关键业务字段与本地订单不匹配 -> 拒绝。"""
    prepared, prep_msg, expected = prepare_booking_for_notify_field_check(booking_id, context)
    if not prepared:
        record("I13", "签名通知字段错配被拒", False, f"I13 setup failed: {prep_msg}")
        return

    wrong_amount = "999999.99" if expected["amount"] != "999999.99" else "0.01"
    cases = [
        ("amount_mismatch", {
            "notify_id": f"mock_amount_mismatch_{booking_id}",
            "operation_id": f"OP_BAD_AMOUNT_{booking_id[-8:]}",
            "total_freeze_amount": wrong_amount,
        }),
        ("auth_no_mismatch", {
            "notify_id": f"mock_auth_mismatch_{booking_id}",
            "operation_id": f"OP_BAD_AUTH_{booking_id[-8:]}",
            "auth_no": f"WRONG_AUTH_{booking_id[-8:]}",
        }),
    ]

    outcomes = []
    for label, extra in cases:
        code, body = send_signed_notify(
            booking_id,
            keys,
            context,
            extra,
            label=f"I13_{label}",
        )
        outcomes.append({
            "case": label,
            "http_status": code,
            "body": body[:200],
            "rejected": is_explicit_rejection(code, body),
            "extra": extra,
        })
        time.sleep(1)

    save_json("notify_field_mismatch_i13.json", {"expected": expected, "outcomes": outcomes})
    accepted = [o for o in outcomes if not o["rejected"]]
    ok = not accepted
    if ok:
        msg = ", ".join(f"{o['case']} HTTP {o['http_status']} '{o['body'][:40]}'" for o in outcomes)
    else:
        msg = "accepted mismatched signed notify: " + ", ".join(
            f"{o['case']} HTTP {o['http_status']} '{o['body'][:40]}'" for o in accepted
        )
    record("I13", "签名通知字段错配被拒", ok, msg)


def main():
    print("--- Advanced Integration Tests ---")

    if not check_app_boot():
        for rid, name in [
            ("I2", "freeze 打到 mock gateway"),
            ("I3", "无签名通知被拒"),
            ("I4", "错误 app_id 通知被拒"),
            ("I5", "有效签名通知通过"),
            ("I6", "通知幂等"),
            ("I7", "终态保护"),
            ("I8", "unfreeze 端点存在"),
            ("I9", "query 打到 mock gateway"),
            ("I10", "转支付携带 auth_no"),
            ("I11", "解冻请求含稳定 out_request_no"),
            ("I12", "不存在预订号的通知被拒"),
            ("I13", "签名通知字段错配被拒"),
            ("I14", "转支付后解冻剩余金额"),
            ("I15", "未消费前不能解冻"),
            ("I16", "撤销与解冻边界"),
            ("I17", "query 非成功态不能入账/解锁"),
        ]:
            record(rid, name, False, "应用未启动")
    else:
        session = requests.Session()
        sign_in(session)

        booking_id, seeded = get_booking_id()
        print(f"  Using booking_id: {booking_id} (seeded={seeded})")

        keys = {}
        try:
            keys = load_keys(KEYS_DIR)
        except Exception as e:
            print(f"  WARNING: keys load failed: {e}")

        freeze_data = check_freeze_hits_mock(session, booking_id)
        notify_context = build_notify_context(booking_id, freeze_data)
        print(
            "  Notify context: "
            f"out_order_no={notify_context['out_order_no']}, "
            f"amount={notify_context['amount']}, auth_no={notify_context['auth_no']}"
        )
        merchant_session, merchant_auth_error = sign_in_mobile_session()
        if merchant_auth_error:
            print(f"  WARNING: {merchant_auth_error}")

        check_notify_rejects_unsigned(session, booking_id, notify_context)

        if keys:
            check_notify_rejects_wrong_appid(session, booking_id, keys, notify_context)
            check_notify_signed_success(session, booking_id, keys, notify_context)
            check_notify_idempotent(session, booking_id, keys, notify_context)
            check_terminal_protection(session, booking_id, keys, notify_context)
        else:
            for rid, name in [("I4", "错误 app_id 通知被拒"), ("I5", "有效签名通知通过"),
                              ("I6", "通知幂等"), ("I7", "终态保护"),
                              ("I12", "不存在预订号的通知被拒"),
                              ("I13", "签名通知字段错配被拒")]:
                record(rid, name, False, "密钥加载失败")

        check_query_hits_mock(session, booking_id)
        check_query_non_success_not_authorized(session, booking_id)
        if merchant_session is None:
            for rid, name in [
                ("I8", "unfreeze 端点存在"),
                ("I10", "转支付携带 auth_no"),
                ("I11", "解冻请求含稳定 out_request_no"),
                ("I14", "转支付后解冻剩余金额"),
                ("I15", "未消费前不能解冻"),
                ("I16", "撤销与解冻边界"),
            ]:
                record(rid, name, False, merchant_auth_error or "商家鉴权准备失败")
        else:
            check_unfreeze_exists(merchant_session, booking_id)
            check_pay_has_auth_no(merchant_session, booking_id)
            check_unfreeze_has_request_no(merchant_session, booking_id)
        if keys:
            check_notify_wrong_order(session, booking_id, keys)
            check_notify_rejects_field_mismatch(session, booking_id, keys, notify_context)

        if merchant_session is not None:
            check_trade_pay_then_unfreeze_remaining(merchant_session, booking_id)
            check_unfreeze_before_consumption_rejected(merchant_session, booking_id)
            check_cancel_vs_unfreeze_boundary(merchant_session, booking_id)

    passed = sum(1 for r in RESULTS if r["passed"])
    print(f"\nIntegration tests: {passed}/{len(RESULTS)} passed")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "integration_results.json"), "w") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
