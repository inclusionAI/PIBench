#!/usr/bin/env python3
"""Integration tests I2-I9 + unit-path checks U1-U2 against the running service.

Test naming convention: a2m-basic-access__{rubric_id}__{scenario}
Writes integration_results.json; prints human-readable diagnostics to stdout.
"""
import base64
import json
import os
import re
import sys
import time

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
except ImportError:  # pragma: no cover
    sys.exit(2)

BASE_URL = os.environ.get("SERVICE_BASE_URL", "http://127.0.0.1:5000")
MOCK_LOG = os.environ.get("A2M_MOCK_LOG", "/output/gateway_requests.jsonl")
MODE_FILE = os.environ.get("A2M_MOCK_MODE_FILE", "/tmp/a2m_mock_mode")
PAYMENT_REQUEST_ID_KEYS = (
    "paymentrequestid", "requestid", "orderid", "outtradeno",
    "tradeno", "paymentid", "billid", "receiptid",
    "challengeid", "sessionid", "nonce",
)

# Full-content markers: ingredients/steps fragments that never appear in public preview payloads.
FULL_MARKERS = {
    1: ["高铁米粉 20g", "顺时针搅拌至均匀无颗粒", "静置30秒"],
    2: ["南瓜 100g", "放入蒸锅蒸15分钟至软烂", "如太干可加少量温水调至合适稠度"],
}

results = []


def add(rid, scenario, passed, message, evidence=None):
    name = "a2m-basic-access__%s__%s" % (rid, scenario)
    results.append({"id": rid, "name": name, "passed": passed,
                    "message": message, "evidence": evidence or []})
    state = "PASS" if passed else ("FAIL" if passed is False else "SKIP")
    print("[integration] %-60s %s" % (name, state))
    if message and passed is not True:
        print("              -> %s" % message)


def http_get(path, headers=None, timeout=30):
    req = Request(BASE_URL + path)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        resp = urlopen(req, timeout=timeout)
        body = resp.read().decode("utf-8", errors="replace")
        return resp.getcode(), dict(resp.headers), body, None
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, dict(e.headers), body, None
    except (URLError, OSError) as e:
        return None, {}, "", str(e)


def header_get(headers, name):
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v
    return None


def set_mock_mode(mode):
    with open(MODE_FILE, "w") as f:
        f.write(mode)


def gateway_entries():
    entries = []
    try:
        with open(MOCK_LOG) as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return entries


def gateway_counts():
    verify = confirm = 0
    for entry in gateway_entries():
        if entry.get("kind") == "verify":
            verify += 1
        elif entry.get("kind") == "confirm":
            confirm += 1
    return verify, confirm


def entry_text(entry):
    return " ".join([
        str(entry.get("path") or ""),
        str(entry.get("body") or ""),
        json.dumps(entry.get("headers") or {}, ensure_ascii=False),
    ])


def entry_body_json(entry):
    try:
        body = entry.get("body") or ""
        data = json.loads(body)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def entry_action(entry):
    data = entry_body_json(entry)
    return str(data.get("action") or data.get("method") or data.get("type") or "").lower()


def is_verify_request(entry):
    action = entry_action(entry)
    if action:
        if any(k in action for k in ("confirm", "fulfil", "fulfill", "delivery", "deliver", "settle", "ack")):
            return False
        if any(k in action for k in ("verify", "validate")):
            return True
    text = entry_text(entry).lower()
    return entry.get("kind") == "verify" and ("proof" in text or "payment-proof" in text)


def latest_verify_token(entries):
    for entry in reversed(entries):
        if is_verify_request(entry) and entry.get("mode") == "success":
            token = entry.get("response_fulfillment_token")
            if token:
                return str(token)
    return None


def fulfillment_ack_observed(entries, token, resource):
    if not token:
        return False
    for entry in entries:
        text = entry_text(entry)
        if token in text and entry_targets_recipe(entry, 1, "高铁米粉糊"):
            return True
    return False


def has_full_content(body, recipe_id=1):
    return any(m in body for m in FULL_MARKERS.get(recipe_id, []))


def decode_payment_needed(value):
    """Try JSON, standard base64(JSON), base64url(JSON), then raw string."""
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        pass

    padded = value + "=" * (-len(value) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            decoded = decoder(padded).decode("utf-8", "replace")
            return json.loads(decoded)
        except Exception:
            pass
    return value  # raw string fallback; substring checks still possible


def flat_text(obj):
    return json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj


def is_structured(obj):
    return isinstance(obj, (dict, list))


def normalize_name(value):
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def scalar_items(obj, prefix=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = ("%s.%s" % (prefix, key)) if prefix else str(key)
            for item in scalar_items(value, path):
                yield item
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            path = "%s[%d]" % (prefix, idx)
            for item in scalar_items(value, path):
                yield item
    else:
        yield prefix, obj


def structured_challenge_checks(obj):
    checks = {
        "resource": False,
        "amount": False,
        "currency": False,
        "challenge_or_order": False,
        "seller_or_service": False,
    }
    if not is_structured(obj):
        return checks

    for path, value in scalar_items(obj):
        key = normalize_name(path)
        raw_value = str(value).strip()
        val = normalize_name(value)
        if not raw_value:
            continue
        if any(k in key for k in ("resource", "recipe", "url", "path", "asset")):
            checks["resource"] = True
        if any(k in key for k in ("amount", "price", "total")):
            checks["amount"] = True
        if "currency" in key or "ccy" in key or val in ("cny", "rmb", "usd", "usdc", "eur"):
            checks["currency"] = True
        if any(k in key for k in PAYMENT_REQUEST_ID_KEYS):
            checks["challenge_or_order"] = True
        if any(k in key for k in ("seller", "merchant", "service", "payee", "appid", "app", "mchid")):
            checks["seller_or_service"] = True
    return checks


def challenge_request_ids(obj):
    """Return stable payment/challenge ids from Payment-Needed.

    Very short values such as "1" are resource ids in practice, not payment
    request identifiers, so they are not strong enough for binding checks.
    """
    values = []
    seen = set()
    if not is_structured(obj):
        return values
    for path, value in scalar_items(obj):
        key = normalize_name(path)
        raw_value = str(value).strip()
        compact_value = normalize_name(raw_value)
        if not raw_value or len(compact_value) < 6:
            continue
        if any(k in key for k in PAYMENT_REQUEST_ID_KEYS):
            if raw_value not in seen:
                values.append(raw_value)
                seen.add(raw_value)
    return values


def carries_payment_request_id_field(obj, values):
    if not is_structured(obj):
        return False
    value_set = set(str(value) for value in values)
    ignored_key_tokens = (
        "proof", "token", "signature", "authorization", "credential",
        "secret", "receipt", "delivery",
    )
    for path, value in scalar_items(obj):
        key = normalize_name(path)
        if any(token in key for token in ignored_key_tokens):
            continue
        if not any(token in key for token in PAYMENT_REQUEST_ID_KEYS):
            continue
        if str(value).strip() in value_set:
            return True
    return False


def entries_carry_any_value(entries, values, recipe_id, recipe_name):
    if not values:
        return False
    for entry in entries:
        if not is_verify_request(entry):
            continue
        if not entry_targets_recipe(entry, recipe_id, recipe_name):
            continue

        body = entry_body_json(entry)
        if carries_payment_request_id_field(body, values):
            return True

        headers = entry.get("headers") or {}
        if carries_payment_request_id_field(headers, values):
            return True
    return False


def value_mentions_recipe(value, recipe_id, recipe_name):
    raw = str(value)
    if recipe_name in raw:
        return True
    if re.search(r"/api/recipes/%d(?!\d)" % recipe_id, raw):
        return True
    if re.search(r"recipes?[-_:/ ]?%d(?!\d)" % recipe_id, raw, re.I):
        return True
    compact = normalize_name(raw)
    return (
        ("recipe%d" % recipe_id) in compact or
        ("recipes%d" % recipe_id) in compact or
        ("recipedetail%d" % recipe_id) in compact
    )


def key_has_any(key, tokens):
    return any(token in key for token in tokens)


def challenge_targets_recipe(obj, recipe_id, recipe_name):
    text = flat_text(obj)
    if recipe_name in text:
        return True
    if re.search(r"/api/recipes/%d(?!\d)" % recipe_id, text):
        return True
    if re.search(r"recipes?[-_:/ ]?%d(?!\d)" % recipe_id, text, re.I):
        return True
    if value_mentions_recipe(text, recipe_id, recipe_name):
        return True

    has_recipe_type = False
    has_recipe_id = False
    for path, value in scalar_items(obj):
        key = normalize_name(path)
        val = normalize_name(value)
        resource_key = key_has_any(key, ("resource", "recipe", "asset", "item", "content"))
        type_key = key_has_any(key, ("type", "kind", "category", "class"))
        id_key = key_has_any(key, ("id", "identifier", "resourceid", "recipeid", "itemid", "contentid"))

        if resource_key and value_mentions_recipe(value, recipe_id, recipe_name):
            return True
        if (resource_key or type_key) and "recipe" in val:
            has_recipe_type = True
        if (resource_key or id_key) and val == str(recipe_id):
            has_recipe_id = True
        if key_has_any(key, ("recipeid", "resourceid")) and val == str(recipe_id):
            return True
        if key_has_any(key, ("recipe", "resource")) and val.endswith(str(recipe_id)) and value_mentions_recipe(value, recipe_id, recipe_name):
            return True
    return has_recipe_type and has_recipe_id


def entry_targets_recipe(entry, recipe_id, recipe_name):
    body = entry.get("body") or ""
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    if parsed is not None and challenge_targets_recipe(parsed, recipe_id, recipe_name):
        return True
    text = entry_text(entry)
    return (
        ("/api/recipes/%d" % recipe_id) in text or
        ("recipe:%d" % recipe_id) in text or
        value_mentions_recipe(text, recipe_id, recipe_name) or
        ('"resourceId":%d' % recipe_id) in text or
        ('"resourceId":"%d"' % recipe_id) in text or
        ('"recipeId":%d' % recipe_id) in text or
        ('"recipeId":"%d"' % recipe_id) in text
    )


def challenge_checks(text):
    return {
        "resource": bool(re.search(r"resource|recipe|url|path|asset", text, re.I)),
        "amount": bool(re.search(r"amount|price|total", text, re.I)),
        "currency": bool(re.search(r"currency|CNY|RMB", text, re.I)),
        # Basic access should accept either a payment/order id or a challenge/receipt
        # id. The key requirement is that the client receives a stable payment
        # challenge identifier, not that it uses a specific provider field name.
        "challenge_or_order": bool(re.search(
            r"order|trade|out_trade_no|payment_id|request_id|bill|receipt|challenge|session|nonce",
            text, re.I)),
    }


def main():
    out_path = sys.argv[1]

    # Precondition: service reachable (I1 is scored by test.sh build/start phase).
    status, _, _, err = http_get("/api/recipes", timeout=10)
    if status is None:
        for rid, scen in [("a2m_dep_sdk", "server_uses_gateway_client"),
                          ("a2m_public_list_unchanged", "list_returns_200"),
                          ("a2m_402_challenge", "no_proof_returns_402"),
                          ("a2m_payment_needed_header", "contains_resource_and_amount"),
                          ("a2m_verify_proof", "server_calls_gateway_verify"),
                          ("a2m_verify_challenge_binding", "verify_carries_payment_request_id"),
                          ("a2m_release_resource", "valid_proof_returns_full_detail"),
                          ("a2m_confirm_fulfillment", "confirm_called_after_release"),
                          ("a2m_payment_challenge_shape", "challenge_has_all_fields"),
                          ("a2m_multi_resource_basic", "second_recipe_protected_and_specific"),
                          ("a2m_multi_resource_release", "second_recipe_valid_proof_releases"),
                          ("a2m_verify_failure_rejects", "failed_verify_no_content"),
                          ("a2m_ambiguous_verify_rejects", "ambiguous_verify_no_content")]:
            add(rid, scen, False, "service unreachable, cannot test: %s" % err)
        json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=2)
        return

    # ---- I2: public list stays open ----
    status, headers, body, err = http_get("/api/recipes")
    list_ok = status == 200
    try:
        payload = json.loads(body)
        items = payload.get("data") if isinstance(payload, dict) else payload
        list_ok = list_ok and isinstance(items, list) and len(items) > 0
    except ValueError:
        list_ok = False
    add("a2m_public_list_unchanged", "list_returns_200", list_ok,
        "" if list_ok else "GET /api/recipes returned status=%s, body[:200]=%r" % (status, body[:200]))

    # ---- I3: no proof -> 402, no full content ----
    status, h402, body402, err = http_get("/api/recipes/1")
    challenge_status_ok = status == 402
    no_leak = not has_full_content(body402, 1)
    add("a2m_402_challenge", "no_proof_returns_402",
        challenge_status_ok and no_leak,
        "" if (challenge_status_ok and no_leak) else
        "status=%s (expect 402), full-content leaked=%s, body[:200]=%r" % (status, not no_leak, body402[:200]))

    # ---- I4: Payment-Needed header usable ----
    pn = header_get(h402, "Payment-Needed")
    decoded = decode_payment_needed(pn)
    text = flat_text(decoded) if decoded is not None else ""
    all_checks = challenge_checks(text)
    # I4 only checks that Payment-Needed is usable by a client at the basic
    # access layer: it must be present, parseable, and identify the paid
    # resource plus price. More detailed shape checks are scored in U1.
    checks_i4 = {k: all_checks[k] for k in ("resource", "amount")}
    i4_ok = pn is not None and all(checks_i4.values())
    add("a2m_payment_needed_header", "contains_resource_and_amount", i4_ok,
        "" if i4_ok else "Payment-Needed header=%r decoded missing fields: %s" %
        ((pn[:120] if pn else None), [k for k, v in checks_i4.items() if not v]))

    # ---- U1: challenge shape complete (currency + challenge id + seller/service) ----
    checks_u1 = structured_challenge_checks(decoded)
    u1_ok = pn is not None and is_structured(decoded) and all(checks_u1.values())
    add("a2m_payment_challenge_shape", "challenge_has_all_fields", u1_ok,
        "" if u1_ok else "challenge must be JSON/base64(JSON) and include all fields; missing: %s" %
        ([k for k, v in checks_u1.items() if not v] + ([] if is_structured(decoded) else ["structured_json"])))

    # ---- I8: a second paid resource is protected and has resource-specific challenge ----
    status2, h402_2, body402_2, err2 = http_get("/api/recipes/2")
    pn2 = header_get(h402_2, "Payment-Needed")
    decoded2 = decode_payment_needed(pn2)
    text2 = flat_text(decoded2) if decoded2 is not None else ""
    second_protected = status2 == 402 and not has_full_content(body402_2, 2)
    second_specific = (
        pn2 is not None and text2 != text and
        challenge_targets_recipe(decoded2, 2, "南瓜泥")
    )
    add("a2m_multi_resource_basic", "second_recipe_protected_and_specific",
        second_protected and second_specific,
        "" if (second_protected and second_specific) else
        "GET /api/recipes/2 status=%s, full-content leaked=%s, challenge specific=%s, header=%r" %
        (status2, has_full_content(body402_2, 2), second_specific, pn2[:120] if pn2 else None))

    # ---- I5 + I6: valid proof -> gateway verify called, full content returned ----
    request_ids = challenge_request_ids(decoded)
    proof_valid_1 = "MOCK-PROOF-VALID-001"
    if request_ids:
        proof_valid_1 = "%s::%s" % (proof_valid_1, request_ids[0])
    set_mock_mode("success")
    entries0 = gateway_entries()
    v0, c0 = gateway_counts()
    status_ok, h_ok, body_ok, err = http_get(
        "/api/recipes/1", headers={"Payment-Proof": proof_valid_1}, timeout=60)
    time.sleep(2)  # allow async verify/confirm to land in the log
    entries1 = gateway_entries()
    v1, c1 = gateway_counts()
    verify_called = v1 > v0
    add("a2m_dep_sdk", "server_uses_gateway_client", verify_called,
        "" if verify_called else
        "no payment gateway validation request reached the mock gateway; "
        "the service did not demonstrate a runtime payment client integration. "
        "status=%s" % status_ok)
    add("a2m_verify_proof", "server_calls_gateway_verify", verify_called,
        "" if verify_called else
        "no verify-like request reached the mock gateway (A2M_GATEWAY_URL); "
        "the service either skipped server-side verification or called elsewhere. "
        "status=%s" % status_ok)
    new_verify_entries = [entry for entry in entries1[len(entries0):] if is_verify_request(entry)]
    challenge_bound = entries_carry_any_value(new_verify_entries, request_ids, 1, "高铁米粉糊")
    add("a2m_verify_challenge_binding", "verify_carries_payment_request_id", challenge_bound,
        "" if challenge_bound else
        "verify request for /api/recipes/1 did not carry a stable payment request id from Payment-Needed; "
        "challenge ids found=%s, verify requests=%d" %
        ([str(v)[:80] for v in request_ids], len(new_verify_entries)))

    # Release only counts as part of the paid-access loop: the server must have
    # actually verified the proof (otherwise an unprotected baseline would pass).
    release_ok = status_ok == 200 and has_full_content(body_ok, 1) and verify_called
    add("a2m_release_resource", "valid_proof_returns_full_detail", release_ok,
        "" if release_ok else
        "with valid proof and gateway success: status=%s, full content present=%s, "
        "server-side verify happened=%s, body[:200]=%r"
        % (status_ok, has_full_content(body_ok, 1), verify_called, body_ok[:200]))

    # ---- I7: fulfillment confirm after successful release ----
    deadline = time.time() + 10
    confirm_called = False
    verify_token = latest_verify_token(entries1[len(entries0):])
    while time.time() < deadline:
        entries_now = gateway_entries()
        new_entries = entries_now[len(entries0):]
        verify_token = verify_token or latest_verify_token(new_entries)
        if fulfillment_ack_observed(new_entries, verify_token, "/api/recipes/1"):
            confirm_called = True
            break
        time.sleep(1)
    i7_ok = release_ok and confirm_called
    if i7_ok:
        i7_msg = ""
    elif not release_ok:
        i7_msg = "valid proof did not release paid content, so fulfillment confirmation was not observed; inspect a2m_release_resource first"
    elif not verify_token:
        i7_msg = "payment verify happened, but the mock gateway did not expose a fulfillment token; inspect gateway log"
    else:
        i7_msg = "paid resource was released, but no post-release gateway request carried the verify response fulfillment token for /api/recipes/1 within 10s"
    add("a2m_confirm_fulfillment", "confirm_called_after_release", i7_ok, i7_msg)

    # ---- I9: another resource can complete the same paid-access loop ----
    v2, _ = gateway_counts()
    status2_ok, _, body2_ok, err2_ok = http_get(
        "/api/recipes/2", headers={"Payment-Proof": "MOCK-PROOF-VALID-002"}, timeout=60)
    time.sleep(2)
    v3, _ = gateway_counts()
    verify2_called = v3 > v2
    release2_ok = status2_ok == 200 and has_full_content(body2_ok, 2) and verify2_called
    add("a2m_multi_resource_release", "second_recipe_valid_proof_releases", release2_ok,
        "" if release2_ok else
        "with valid proof for /api/recipes/2: status=%s, full content present=%s, server-side verify happened=%s, body[:200]=%r" %
        (status2_ok, has_full_content(body2_ok, 2), verify2_called, body2_ok[:200]))

    # ---- U2: verify failure / malformed proof -> fail closed ----
    set_mock_mode("fail")
    failures = []
    for proof, scen in [("MOCK-PROOF-INVALID-002", "gateway_rejects"),
                        ("%%%not-a-proof%%%", "malformed_proof")]:
        status, _, body, err = http_get("/api/recipes/1", headers={"Payment-Proof": proof}, timeout=60)
        if status == 200 and has_full_content(body, 1):
            failures.append("proof=%r got full content with status 200" % proof)
        elif status is None:
            failures.append("proof=%r request error: %s" % (proof, err))
        elif has_full_content(body, 1):
            failures.append("proof=%r leaked full content with status=%s" % (proof, status))
        elif status not in (402, 403, 401, 400):
            failures.append("proof=%r unexpected status=%s (expect 402/403)" % (proof, status))
    add("a2m_verify_failure_rejects", "failed_verify_no_content", not failures,
        "" if not failures else "; ".join(failures))

    # ---- U3: API-level success without explicit payment success is not enough ----
    proof_ambiguous = "MOCK-PROOF-AMBIGUOUS-003"
    if request_ids:
        proof_ambiguous = "%s::%s" % (proof_ambiguous, request_ids[0])
    set_mock_mode("ambiguous")
    status_amb, _, body_amb, err_amb = http_get(
        "/api/recipes/1", headers={"Payment-Proof": proof_ambiguous}, timeout=60)
    ambiguous_failures = []
    if status_amb is None:
        ambiguous_failures.append("request error: %s" % err_amb)
    elif status_amb == 200 and has_full_content(body_amb, 1):
        ambiguous_failures.append("gateway returned code=10000 but UNKNOWN payment_status; service still returned full content")
    elif has_full_content(body_amb, 1):
        ambiguous_failures.append("full content leaked with status=%s" % status_amb)
    elif status_amb not in (400, 401, 402, 403, 409, 500, 502, 503, 504):
        ambiguous_failures.append("unexpected status=%s for ambiguous gateway verification" % status_amb)
    set_mock_mode("success")
    add("a2m_ambiguous_verify_rejects", "ambiguous_verify_no_content", not ambiguous_failures,
        "" if not ambiguous_failures else "; ".join(ambiguous_failures))

    with open(out_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
