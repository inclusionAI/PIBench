#!/usr/bin/env python3
"""Integration tests for BookCars Alipay Preauthorization basic (I0-I8).

Tests hit the real Alipay sandbox (basic only verifies endpoint existence and response format).
Booking ID from /output/test_booking_id.txt (seeded by start_services.sh).
"""
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urlparse

import requests

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"

BACKEND_URL = "http://localhost:9102"
TEST_USER_EMAIL = "driver1@bookcars.ma"
TEST_USER_PASSWORD = "B00kC4r5"
MONGO_CONTAINER = "bcpreauth-task-mongo-1"
MONGO_URI = "mongodb://admin:admin@localhost:27017/bookcars?authSource=admin"

SUCCESS_BOOKING_STATUSES = {"deposit", "authorized", "confirmed", "paid", "paidInFull", "reserved", "ready", "ready_for_pickup", "active"}
WAITING_BOOKING_STATUSES = {"", "pending", "draft", "new", "created", "unpaid", "waiting", "waiting_deposit", "requires_deposit", "requires_preauth", "requires_payment"}
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
}
PREAUTH_KEY_RE = re.compile(r"(alipay|preauth|pre_auth|auth|out.?order|out.?request)", re.I)
QUERY_STATUS_KEYS = {"status", "authStatus", "auth_status", "alipayAuthStatus", "depositAuthStatus"}
QUERY_STATUS_PATH_RE = re.compile(r"(alipay|preauth|pre_auth|auth|deposit|freeze).*(status|state)|(status|state).*(alipay|preauth|pre_auth|auth|deposit|freeze)", re.I)

RESULTS = []


def is_valid_alipay_entry(value):
    if not isinstance(value, str):
        return False
    text = value.strip()
    if text.startswith("alipays://"):
        return True
    try:
        parsed = urlparse(text)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and (parsed.hostname or "").lower() == "qr.alipay.com"
        and bool(parsed.path.strip("/"))
    )


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


def extract_query_status(obj):
    """Find a machine-readable preauthorization status without binding to one field name."""
    status = find_first_key(obj, QUERY_STATUS_KEYS)
    if status and status.upper() in QUERY_STATUSES:
        return status

    for path, value in iter_values(obj):
        if value in (None, ""):
            continue
        text = str(value).strip()
        if text.upper() not in QUERY_STATUSES:
            continue
        if path in ("status", "state") or QUERY_STATUS_PATH_RE.search(path):
            return text
    return ""


def collect_preauth_fields(doc):
    fields = []
    if not isinstance(doc, dict):
        return fields
    for path, value in iter_values(doc):
        if not path or value in (None, ""):
            continue
        if PREAUTH_KEY_RE.search(path):
            fields.append(f"{path}={str(value)[:80]}")
    return fields


def collect_preauth_identity_values(doc):
    values = []
    fields = []
    if not isinstance(doc, dict):
        return values, fields
    identity_re = re.compile(
        r"(alipay.*(out.?order|out.?request|auth.?no)|preauth.*(order|request|auth)|"
        r"pre_auth.*(order|request|auth)|out.?order|out.?request|auth.?no)",
        re.I,
    )
    non_identity_re = re.compile(r"(status|state|amount|price|isdeposit|ispayed|paid)", re.I)
    for path, value in iter_values(doc):
        if not path or value in (None, ""):
            continue
        if non_identity_re.search(path):
            continue
        if identity_re.search(path):
            text = str(value)
            values.append(text)
            fields.append(f"{path}={text[:80]}")
    return unique(values), fields


def contains_string_value(doc, target):
    if not target:
        return False
    return any(str(value) == str(target) for _, value in iter_values(doc))


def unique(values):
    seen = set()
    out = []
    for value in values:
        if value in (None, ""):
            continue
        text = str(value)
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def pick_out_order_candidates(freeze_data, booking_doc, booking_id):
    candidates = [
        find_first_key(freeze_data, ("outOrderNo", "out_order_no", "out_order", "outOrder")),
        find_first_key(freeze_data, ("outRequestNo", "out_request_no", "out_request", "outRequest")),
    ]
    if isinstance(booking_doc, dict):
        for path, value in iter_values(booking_doc):
            if value in (None, ""):
                continue
            if re.search(r"(out.?order|out.?request|order.?no|request.?no|preauth|pre_auth|auth)", path, re.I):
                candidates.append(value)
    # Correct implementations often use the booking id itself as out_order_no;
    # older starters used PREAUTH_<bookingId>. Try both before failing notify.
    candidates.extend([booking_id, f"PREAUTH_{booking_id}"])
    return unique(candidates)


def sign_in(session):
    """Best-effort login."""
    for path in ("/api/sign-in/frontend", "/api/sign-in"):
        try:
            resp = session.post(f"{BACKEND_URL}{path}",
                                json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
                                timeout=15)
            if resp.status_code == 200:
                return True, path
        except requests.exceptions.RequestException:
            continue
    return False, None


def get_booking_id():
    path = os.path.join(OUTPUT_DIR, "test_booking_id.txt")
    if os.path.exists(path):
        bid = open(path).read().strip()
        if bid:
            return bid, True
    return "000000000000000000000001", False


def check_app_boot():
    """I0: Backend is reachable."""
    try:
        resp = requests.get(f"{BACKEND_URL}/api/settings", timeout=10)
        ok = resp.status_code in (200, 401, 403, 500)
        record("I0", "应用启动 (backend reachable)", ok,
               f"GET /api/settings -> HTTP {resp.status_code}")
        return ok
    except requests.RequestException as e:
        record("I0", "应用启动 (backend reachable)", False, f"连接失败: {e}")
        return False


def check_login(session):
    """I1: Login succeeds."""
    ok, path = sign_in(session)
    record("I1", "登录成功 (POST /api/sign-in)", ok,
           f"Login via {path}" if ok else "Login failed on all paths")
    return ok


def check_freeze(session, booking_id):
    """I2: /api/alipay/freeze creates a preauth entry and returns an Alipay entry.

    Creating a freeze request is side-effectful. Accept the two common shapes
    under /api/alipay/freeze: bookingId in the path or in the request body.
    """
    path_url = f"{BACKEND_URL}/api/alipay/freeze/{booking_id}"
    body_url = f"{BACKEND_URL}/api/alipay/freeze"
    attempts = []
    for label, call in (
        ("GET /api/alipay/freeze/:bookingId", lambda: session.get(path_url, timeout=60)),
        ("POST /api/alipay/freeze/:bookingId", lambda: session.post(path_url, json={"bookingId": booking_id}, timeout=60)),
        ("POST /api/alipay/freeze", lambda: session.post(body_url, json={"bookingId": booking_id}, timeout=60)),
        ("GET /api/alipay/freeze?bookingId", lambda: session.get(body_url, params={"bookingId": booking_id}, timeout=60)),
    ):
        try:
            resp = call()
        except Exception as e:
            attempts.append(f"{label} error: {e}")
            continue
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                attempts.append(f"{label} 200 but not JSON: {resp.text[:120]}")
                continue
            scheme_url = str(data.get("schemeUrl", data.get("scheme_url", data.get("schemeURL", ""))))
            if is_valid_alipay_entry(scheme_url):
                record("I2", "freeze 端点返回支付宝预授权入口", True,
                       f"{label} 200 OK, entry={scheme_url[:80]}")
                return data
            elif scheme_url:
                attempts.append(
                    f"{label} 200 but entry is not alipays:// or https://qr.alipay.com/: {scheme_url[:80]}"
                )
            else:
                attempts.append(f"{label} 200 but no schemeUrl field: {json.dumps(data)[:160]}")
        else:
            attempts.append(f"{label} HTTP {resp.status_code}: {resp.text[:120]}")
    record("I2", "freeze 端点返回支付宝预授权入口", False, "; ".join(attempts[:4]))
    return {}


def check_freeze_persistence(booking_id, freeze_data):
    """I5: freeze should leave preauthorization order markers on the Booking."""
    booking, err = load_booking(booking_id, "booking_after_freeze.json")
    if err:
        record("I5", "freeze 后保存预授权标识", False, f"无法读取 Booking: {err}")
        return None

    targets = [
        find_first_key(freeze_data, ("outOrderNo", "out_order_no", "out_order", "outOrder")),
        find_first_key(freeze_data, ("outRequestNo", "out_request_no", "out_request", "outRequest")),
    ]
    matched_targets = [t for t in targets if t and contains_string_value(booking, t)]
    marker_fields = collect_preauth_fields(booking)

    if matched_targets or marker_fields:
        bits = []
        if matched_targets:
            bits.append(f"matched returned id(s): {', '.join(matched_targets[:2])}")
        if marker_fields:
            bits.append(f"fields: {', '.join(marker_fields[:3])}")
        record("I5", "freeze 后保存预授权标识", True, "; ".join(bits))
    else:
        record("I5", "freeze 后保存预授权标识", False,
               "freeze 后 Booking 中未发现 alipay/preauth/out_order/out_request/auth 相关持久化字段")
    return booking


def check_query(session, booking_id):
    """I3: /api/alipay/query/:bookingId -> status field."""
    result = {"http_status": None, "status": "", "ok": False, "body": ""}
    url = f"{BACKEND_URL}/api/alipay/query/{booking_id}"
    attempts = []
    for method, call in (
        ("GET", lambda: session.get(url, timeout=30)),
        ("POST", lambda: session.post(url, json={"bookingId": booking_id}, timeout=30)),
    ):
        try:
            resp = call()
        except Exception as e:
            attempts.append(f"{method} error: {e}")
            result["body"] = str(e)
            continue
        result["http_status"] = resp.status_code
        result["body"] = resp.text[:500]
        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                attempts.append(f"{method} 200 but not JSON: {resp.text[:120]}")
                continue
            status = extract_query_status(data)
            result["status"] = status
            if status.upper() in QUERY_STATUSES:
                result["ok"] = True
                record("I3", "query 端点返回 status", True,
                       f"{method} 200 OK, status={status}")
                return result
            if status:
                attempts.append(f"{method} 200 but invalid status='{status}'")
            else:
                attempts.append(f"{method} 200 but no status field: {json.dumps(data)[:160]}")
        else:
            attempts.append(f"{method} HTTP {resp.status_code}: {resp.text[:120]}")
    hint = "query should return a stable PENDING/UNKNOWN/NOT_FOUND style status instead of surfacing SDK/sandbox errors as 500"
    record("I3", "query 端点返回 status", False, "; ".join(attempts[:4]) + f"; {hint}")
    return result

def build_notify_payload(booking_id, out_order_no):
    return {
        "app_id": runtime_sandbox_app_id(),
        "auth_no": "2026061210002001999999999999",
        "out_order_no": out_order_no,
        "operation_id": "OP_TEST_001",
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


def check_notify(session, booking_id, out_order_candidates=None):
    """I4: POST /api/alipay/notify with unsigned preauth fields -> returns success."""
    candidates = unique(out_order_candidates or []) or [f"PREAUTH_{booking_id}"]
    attempts = []
    last_payload = build_notify_payload(booking_id, candidates[0])
    for out_order_no in candidates:
        payload = build_notify_payload(booking_id, out_order_no)
        last_payload = payload
        try:
            resp = session.post(f"{BACKEND_URL}/api/alipay/notify", data=payload, timeout=30)
            body = resp.text.strip()
            attempts.append(f"out_order_no={out_order_no}: HTTP {resp.status_code}, body={body[:80]!r}")
            if resp.status_code == 200 and "success" in body.lower():
                record("I4", "notify 端点处理通知", True,
                       f"200 OK, out_order_no={out_order_no}, body='{body[:80]}'")
                return payload
        except Exception as e:
            attempts.append(f"out_order_no={out_order_no}: Error {e}")
    record("I4", "notify 端点处理通知", False,
           "notify failed for candidates: " + "; ".join(attempts[:4]))
    return last_payload

def check_notify_updates_booking(booking_id, payload):
    """I6: a successful preauth notify should leave success state on the Booking."""
    booking, err = load_booking(booking_id, "booking_after_notify.json")
    if err:
        record("I6", "notify 后更新预授权状态", False, f"无法读取 Booking: {err}")
        return

    status = str(booking.get("status", ""))
    status_l = status.lower()
    auth_no = payload.get("auth_no", "")
    marker_fields = collect_preauth_fields(booking)
    marker_values = [
        str(value).lower()
        for path, value in iter_values(booking)
        if path and value not in (None, "") and PREAUTH_KEY_RE.search(path)
    ]

    status_success = status in SUCCESS_BOOKING_STATUSES or status_l in {s.lower() for s in SUCCESS_BOOKING_STATUSES}
    auth_persisted = contains_string_value(booking, auth_no)
    marker_success = any(value in ("success", "authorized", "freeze") for value in marker_values)

    if status_success or auth_persisted or marker_success:
        evidence = []
        if status_success:
            evidence.append(f"status={status}")
        if auth_persisted:
            evidence.append("auth_no persisted")
        if marker_success:
            evidence.append(f"markers: {', '.join(marker_fields[:3])}")
        record("I6", "notify 后更新预授权状态", True, "; ".join(evidence))
    else:
        record("I6", "notify 后更新预授权状态", False,
               f"notify success 后 Booking 仍无成功状态/auth_no/授权标识；status={status}, markers={marker_fields[:3]}")



def check_freeze_query_notify_binding(booking_id, freeze_data, booking_after_freeze, query_result, notify_payload):
    """I7: freeze/query/notify should share a stable booking authorization identity."""
    booking_after_notify, err = load_booking(booking_id, "booking_after_binding_check.json")
    if err:
        record("I7", "freeze-query-notify 使用同一预授权标识", False, f"无法读取 Booking: {err}")
        return
    freeze_ids = pick_out_order_candidates(freeze_data, booking_after_freeze, booking_id)
    freeze_identity_values, freeze_identity_fields = collect_preauth_identity_values(booking_after_freeze)
    freeze_payload_ids = unique([
        find_first_key(freeze_data, ("outOrderNo", "out_order_no", "out_order", "outOrder")),
        find_first_key(freeze_data, ("outRequestNo", "out_request_no", "out_request", "outRequest")),
        find_first_key(freeze_data, ("authNo", "auth_no")),
    ])
    freeze_identity = unique(freeze_identity_values + freeze_payload_ids)
    notify_ids = unique([
        notify_payload.get("out_order_no"),
        notify_payload.get("out_request_no"),
        notify_payload.get("auth_no"),
    ])
    stored_matches = [value for value in notify_ids if contains_string_value(booking_after_notify, value)]
    freeze_notify_match = bool(set(freeze_identity) & set(notify_ids))
    stored_freeze_identity = [value for value in freeze_identity if contains_string_value(booking_after_notify, value)]
    query_explainable = bool(query_result and query_result.get("http_status") == 200 and query_result.get("status"))
    marker_fields = collect_preauth_fields(booking_after_notify)
    ok = bool(freeze_identity) and query_explainable and bool(freeze_notify_match or stored_freeze_identity)
    record("I7", "freeze-query-notify 使用同一预授权标识", ok,
           f"freeze_ids={freeze_ids[:4]}, freeze_identity={freeze_identity[:3]}, "
           f"notify_ids={notify_ids[:3]}, stored_matches={stored_matches[:2]}, "
           f"freeze_notify_match={freeze_notify_match}, query_status={query_result.get('status') if query_result else None}, "
           f"freeze_fields={freeze_identity_fields[:2]}, stored_freeze_identity={stored_freeze_identity[:2]}, markers={marker_fields[:3]}")


def check_freeze_success_enables_booking(booking_id, notify_payload):
    """I8: after successful auth notify, booking should become usable for the rental flow."""
    booking, err = load_booking(booking_id, "booking_after_business_enable.json")
    if err:
        record("I8", "冻结成功后 booking 进入可服务状态", False, f"无法读取 Booking: {err}")
        return
    status = str(booking.get("status", "")).strip()
    status_l = status.lower()
    marker_fields = collect_preauth_fields(booking)
    auth_no = notify_payload.get("auth_no", "") if isinstance(notify_payload, dict) else ""
    auth_persisted = contains_string_value(booking, auth_no)
    status_success = status in SUCCESS_BOOKING_STATUSES or status_l in {s.lower() for s in SUCCESS_BOOKING_STATUSES}
    still_waiting = status_l in WAITING_BOOKING_STATUSES
    enabled = (status_success or auth_persisted or marker_fields) and not still_waiting
    record("I8", "冻结成功后 booking 进入可服务状态", enabled,
           f"status={status}, still_waiting={still_waiting}, auth_persisted={auth_persisted}, markers={marker_fields[:3]}")

def main():
    print("--- Basic Integration Tests (9 checks) ---")

    if not check_app_boot():
        for rid, name in [("I1", "登录成功"), ("I2", "freeze 端点返回 schemeUrl"),
                          ("I3", "query 端点返回 status"), ("I4", "notify 端点处理通知"),
                          ("I5", "freeze 后保存预授权标识"), ("I6", "notify 后更新预授权状态"),
                          ("I7", "freeze-query-notify 使用同一预授权标识"),
                          ("I8", "冻结成功后 booking 进入可服务状态")]:
            record(rid, name, False, "应用未启动，跳过")
    else:
        session = requests.Session()
        check_login(session)

        booking_id, seeded = get_booking_id()
        print(f"  Using booking_id: {booking_id} (seeded={seeded})")

        freeze_data = check_freeze(session, booking_id)
        booking_after_freeze = check_freeze_persistence(booking_id, freeze_data)
        query_result = check_query(session, booking_id)
        notify_out_order_candidates = pick_out_order_candidates(freeze_data, booking_after_freeze, booking_id)
        notify_payload = check_notify(session, booking_id, notify_out_order_candidates)
        check_notify_updates_booking(booking_id, notify_payload)
        check_freeze_query_notify_binding(booking_id, freeze_data, booking_after_freeze, query_result, notify_payload)
        check_freeze_success_enables_booking(booking_id, notify_payload)

    passed = sum(1 for r in RESULTS if r["passed"])
    print(f"\nIntegration tests: {passed}/{len(RESULTS)} passed")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "integration_results.json"), "w") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
