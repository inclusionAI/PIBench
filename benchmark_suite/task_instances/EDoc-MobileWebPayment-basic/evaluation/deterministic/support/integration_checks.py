#!/usr/bin/env python3
"""Integration checks against the running eDoc app over HTTP.

Adapted from the upstream grader (grader/conftest.py + test_basic_checkout.py).
Each check is isolated and returns {"passed": bool, "message": str} so a failure
in one rubric never prevents the others from being scored. The fixed denominator
is owned by grade.py / rubrics.json — this module only reports per-rubric results.
"""
import html
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

import requests

PATIENT_EMAIL = "patient@edoc.com"
PATIENT_PASSWORD = "123"
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
DESKTOP_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36")
SANDBOX_GATEWAY = os.environ.get("ALIPAY_GATEWAY") or os.environ.get("ALIPAY_GATEWAY_URL") \
    or "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
VALID_NOTIFY_SIGN = os.environ.get("ALIPAY_NOTIFY_FIXTURE_VALID_SIGN") \
    or os.environ.get("ALIPAY_SANDBOX_VALID_SIGN") \
    or "mock-valid"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/output"))


class EdocClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def health(self):
        return requests.get(f"{self.base_url}/health.php", timeout=10)

    def login(self, email, password):
        session = requests.Session()
        resp = session.post(
            f"{self.base_url}/login.php",
            data={"useremail": email, "userpassword": password},
            allow_redirects=False,
            timeout=10,
        )
        if resp.status_code not in (302, 303):
            raise AssertionError(f"login did not redirect (status {resp.status_code}): {resp.text[:200]}")
        return session

    def create_appointment(self, session, apponum=701, promo_code=""):
        resp = session.post(
            f"{self.base_url}/patient/booking-complete.php",
            data={
                "scheduleid": "1",
                "apponum": str(apponum),
                "date": time.strftime("%Y-%m-%d"),
                "promo_code": promo_code,
                "booknow": "Book and pay",
            },
            allow_redirects=False,
            timeout=10,
        )
        if resp.status_code not in (302, 303):
            raise AssertionError(f"booking-complete did not redirect (status {resp.status_code}): {resp.text[:200]}")
        location = resp.headers.get("Location", "")
        if "out_trade_no=" not in location:
            raise AssertionError(f"redirect Location has no out_trade_no: {location!r}")
        return location.split("out_trade_no=", 1)[1].split("&", 1)[0]

    def payment_entry(self, session, out_trade_no):
        return session.post(
            f"{self.base_url}/patient/alipay-h5/payment.php",
            data={"out_trade_no": out_trade_no},
            timeout=10,
        )

    def notify(self, out_trade_no, **overrides):
        payload = {
            "app_id": os.environ.get("ALIPAY_APP_ID", "edoc-h5-sandbox-app"),
            "seller_id": os.environ.get("ALIPAY_SELLER_ID", "edoc-clinic"),
            "out_trade_no": out_trade_no,
            "trade_no": f"MOCK{out_trade_no}",
            "trade_status": "TRADE_SUCCESS",
            "total_amount": "99.00",
            "sign": VALID_NOTIFY_SIGN,
            "sign_type": "RSA2",
        }
        payload.update(overrides)
        return requests.post(f"{self.base_url}/alipay/h5/notify.php", data=payload, timeout=10)


def _ok(msg="", evidence=None):
    item = {"passed": True, "message": msg}
    if evidence:
        item["evidence"] = evidence
    return item


def _fail(msg, evidence=None):
    item = {"passed": False, "message": msg}
    if evidence:
        item["evidence"] = evidence
    return item


def _infra_fail(msg, evidence=None):
    item = _fail(msg, evidence)
    item["infra_failure"] = True
    return item


def save_evidence(name, content):
    try:
        p = OUTPUT_DIR / "integration_evidence"
        p.mkdir(parents=True, exist_ok=True)
        if not isinstance(content, str):
            content = json.dumps(content, indent=2, ensure_ascii=False, default=str)
        (p / name).write_text(content, encoding="utf-8")
        return f"integration_evidence/{name}"
    except OSError:
        return None


def _guard(fn):
    try:
        return fn()
    except AssertionError as exc:
        return _fail(str(exc))
    except requests.RequestException as exc:
        return _fail(f"HTTP error: {exc}")
    except Exception as exc:  # noqa: BLE001
        return _fail(f"unexpected error: {exc}")


def _parse_url_params(params, url):
    if not url:
        return None
    url = html.unescape(str(url))
    parsed = urllib.parse.urlparse(url)
    if parsed.query:
        params.update(dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)))
    return parsed


def _parse_form_inputs(params, body):
    for name, value in re.findall(r'name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']', body, re.I):
        params.setdefault(html.unescape(name), html.unescape(value))
    for value, name in re.findall(r'value=["\']([^"\']*)["\'][^>]*name=["\']([^"\']+)["\']', body, re.I):
        params.setdefault(html.unescape(name), html.unescape(value))


def _normalize_app_url(client, url, current_url=None):
    if not url:
        return None
    url = html.unescape(str(url)).strip()
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        base = current_url or (client.base_url + "/")
        return urllib.parse.urljoin(base, url)
    return url


def _is_alipay_url(url):
    parsed = urllib.parse.urlparse(html.unescape(str(url or "")))
    return "alipay" in parsed.netloc.lower()


def _is_external_alipay_gateway_url(url):
    parsed = urllib.parse.urlparse(html.unescape(str(url or "")).strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.lower()
    if parsed.scheme not in {"http", "https"}:
        return False
    if not netloc or "alipay" not in netloc:
        return False
    if "localhost" in netloc or netloc.startswith("127.") or netloc.startswith("[::1]"):
        return False
    return "gateway.do" in path


def _has_external_alipay_gateway(action, raw):
    if _is_external_alipay_gateway_url(action):
        return True
    for url in re.findall(r"https?://[^\s\"'<>]+", str(raw or "")):
        if _is_external_alipay_gateway_url(url):
            return True
    return False


def _is_local_app_url(client, url):
    parsed = urllib.parse.urlparse(html.unescape(str(url or "")))
    base = urllib.parse.urlparse(client.base_url)
    if not parsed.scheme or not parsed.netloc:
        return True
    return parsed.scheme in {"http", "https"} and parsed.netloc == base.netloc


def _extract_form_action(body):
    m = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', body, re.I)
    if not m:
        return None
    return html.unescape(m.group(1))


def _extract_handoff(client, session, out_trade_no, payment_url):
    """Collect Alipay request params by following the app-provided payment URL."""
    params = {}
    raw_blobs = []
    action = None
    evidence = None
    queue = []
    seen = set()
    payment_entry_url = f"{client.base_url}/patient/alipay-h5/payment.php"

    has_payment_url = bool(payment_url)
    if payment_url:
        raw_blobs.append(str(payment_url))
        parsed = _parse_url_params(params, payment_url)
        if parsed and "alipay" in parsed.netloc.lower():
            action = payment_url
        elif _is_local_app_url(client, payment_url):
            queue.append(_normalize_app_url(client, payment_url, payment_entry_url))
        else:
            raw_blobs.append(f"SKIP_NON_APP_PAYMENT_URL {payment_url}")

    # Backward-compatible fallback for the starter's default route. This is only
    # reached when payment.php did not return a payment_url at all.
    if not has_payment_url and not queue and not action:
        queue.append(f"{client.base_url}/patient/alipay-h5/pay.php?out_trade_no={out_trade_no}")

    while queue and len(seen) < 4:
        url = queue.pop(0)
        if not url or url in seen:
            continue
        seen.add(url)
        if _is_alipay_url(url):
            _parse_url_params(params, url)
            action = url
            raw_blobs.append(f"ALIPAY_URL {url}")
            continue
        if not _is_local_app_url(client, url):
            raw_blobs.append(f"SKIP_NON_APP_URL {url}")
            continue

        try:
            r = session.get(
                url,
                headers={"User-Agent": MOBILE_UA},
                allow_redirects=False,
                timeout=20,
            )
            loc = r.headers.get("Location", "")
            body = r.text or ""
            raw_blobs.extend([f"GET {url}", f"HTTP {r.status_code}", loc, body])
            if loc:
                next_url = _normalize_app_url(client, loc, url)
                parsed = _parse_url_params(params, next_url)
                if parsed and "alipay" in parsed.netloc.lower():
                    action = next_url
                elif _is_local_app_url(client, next_url):
                    queue.append(next_url)
            _parse_form_inputs(params, body)
            form_action = _extract_form_action(body)
            if form_action:
                action_url = _normalize_app_url(client, form_action, url)
                raw_blobs.append(f"FORM_ACTION {action_url}")
                if _is_alipay_url(action_url):
                    action = action_url
                elif _is_local_app_url(client, action_url):
                    queue.append(action_url)
        except requests.RequestException as exc:
            raw_blobs.append(f"pay handoff fetch error for {url}: {exc}")

    evidence = save_evidence(f"pay_mobile_{out_trade_no}.html", "\n".join(raw_blobs)[:200000])

    biz = {}
    if params.get("biz_content"):
        candidate = urllib.parse.unquote(html.unescape(params.get("biz_content", "")))
        try:
            biz = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            biz = {}
    return {
        "params": params,
        "biz": biz,
        "raw": "\n".join(raw_blobs),
        "action": action,
        "evidence": evidence,
    }


def _has_url_value(params, biz, raw_lower, key):
    return bool(params.get(key) or (isinstance(biz, dict) and biz.get(key)) or key in raw_lower)


def _amount_is_99(value):
    try:
        return f"{float(value):.2f}" == "99.00"
    except (TypeError, ValueError):
        return False


def _sandbox_gateway_accepts(handoff):
    params = handoff["params"]
    allowed = {
        "app_id", "method", "format", "charset", "sign_type", "sign",
        "timestamp", "version", "notify_url", "return_url", "app_auth_token",
        "biz_content", "terminal_type", "terminal_info", "prod_code", "auth_token",
    }
    request_params = {k: v for k, v in params.items()
                      if k in allowed and isinstance(v, str) and v != ""}
    required = ("app_id", "method", "biz_content", "sign", "sign_type")
    missing = [k for k in required if not request_params.get(k)]
    if missing:
        return False, f"缺少提交真实沙箱所需参数: {missing}", None, False

    action = handoff.get("action") or SANDBOX_GATEWAY
    if "alipay" not in action.lower():
        action = SANDBOX_GATEWAY
    parsed_action = urllib.parse.urlparse(action)
    if parsed_action.scheme and parsed_action.netloc:
        action = urllib.parse.urlunparse((parsed_action.scheme, parsed_action.netloc,
                                          parsed_action.path, "", "", ""))

    fail_markers = (
        "invalid-signature", "isv.invalid-signature", "illegal_sign",
        "sign check fail", "check sign fail", "验签失败", "签名验证失败",
        "isv.invalid-app-id", "invalid-app-id", "app_id无效", "缺少必选参数", "错误码"
    )

    def is_ascii(text):
        return all(ord(ch) < 128 for ch in text)

    transient_statuses = {502, 503, 504}
    attempts = []
    last_body = ""
    last_status = None
    last_has_alipay_page = False
    last_has_failure = False
    last_transient = False
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(action, data=request_params, headers={"User-Agent": MOBILE_UA},
                                 timeout=30, allow_redirects=True)
        except requests.RequestException as exc:
            attempts.append(f"ATTEMPT {attempt}: EXCEPTION {exc}")
            last_transient = True
            if attempt < max_attempts:
                time.sleep(attempt)
                continue
            evidence = save_evidence("sandbox_gateway_response.html", "\n".join(attempts))
            return False, f"提交真实支付宝沙箱连续异常: {exc}", evidence, True

        body = resp.text or ""
        loc = resp.headers.get("Location", "")
        final_url = getattr(resp, "url", "") or ""
        combined_lower = (body + "\n" + loc + "\n" + final_url).lower()
        combined = body + "\n" + loc + "\n" + final_url
        has_failure = any(marker in combined_lower for marker in fail_markers if is_ascii(marker)) \
            or any(marker in combined for marker in fail_markers if not is_ascii(marker))
        has_alipay_page = any(marker in combined_lower for marker in ("alipay", "cashier", "gateway", "login")) \
            or any(marker in combined for marker in ("支付宝", "收银台"))
        status_ok = resp.status_code in (200, 301, 302, 303, 307)

        attempts.append(
            f"ATTEMPT {attempt}: HTTP {resp.status_code}, Final-URL: {final_url}, "
            f"Location: {loc}, has_alipay_page={has_alipay_page}, has_failure_marker={has_failure}"
        )
        last_body = body
        last_status = resp.status_code
        last_has_alipay_page = has_alipay_page
        last_has_failure = has_failure
        last_transient = resp.status_code in transient_statuses and not has_failure

        if status_ok and has_alipay_page and not has_failure:
            evidence = save_evidence(
                "sandbox_gateway_response.html",
                "\n".join(attempts) + f"\n\nLAST_BODY:\n{body[:200000]}",
            )
            return True, f"真实支付宝沙箱接受支付请求: HTTP {resp.status_code}", evidence, False

        if last_transient and attempt < max_attempts:
            time.sleep(attempt)
            continue

        evidence = save_evidence(
            "sandbox_gateway_response.html",
            "\n".join(attempts) + f"\n\nLAST_BODY:\n{body[:200000]}",
        )
        return False, (f"真实支付宝沙箱未接受支付请求: HTTP {resp.status_code}, "
                       f"has_alipay_page={has_alipay_page}, has_failure_marker={has_failure}"), evidence, False

    evidence = save_evidence(
        "sandbox_gateway_response.html",
        "\n".join(attempts) + f"\n\nLAST_BODY:\n{last_body[:200000]}",
    )
    if last_transient:
        return False, (f"真实支付宝沙箱连续 {max_attempts} 次临时不可用: HTTP {last_status}, "
                       f"has_alipay_page={last_has_alipay_page}, "
                       f"has_failure_marker={last_has_failure}"), evidence, True
    return False, (f"真实支付宝沙箱未接受支付请求: HTTP {last_status}, "
                   f"has_alipay_page={last_has_alipay_page}, "
                   f"has_failure_marker={last_has_failure}"), evidence, False


def _sql_quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _db_query_rows(sql):
    client = shutil.which("mariadb") or shutil.which("mysql")
    if not client:
        raise AssertionError("mariadb/mysql client not available for DB verification")
    env = os.environ.copy()
    env["MYSQL_PWD"] = os.environ.get("DB_PASSWORD", "edoc")
    cmd = [
        client, "--no-defaults",
        "-h", os.environ.get("DB_HOST", "127.0.0.1"),
        "-P", os.environ.get("DB_PORT", "3306"),
        "-u", os.environ.get("DB_USER", "edoc"),
        "--batch", "--skip-column-names",
        os.environ.get("DB_NAME", "edoc"),
        "-e", sql,
    ]
    proc = subprocess.run(cmd, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=10, check=False)
    if proc.returncode != 0:
        raise AssertionError(f"DB query failed: {proc.stderr.strip()[:300]}")
    rows = []
    for line in proc.stdout.splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows


def _load_payment_state(out_trade_no):
    sql = (
        "SELECT "
        "COALESCE(a.payment_status,''), "
        "COALESCE(a.appointment_status,''), "
        "COALESCE(a.alipay_trade_no,''), "
        "COALESCE(DATE_FORMAT(a.paid_at, '%Y-%m-%d %H:%i:%s'),''), "
        "COALESCE(ap.status,''), "
        "COALESCE(ap.trade_no,'') "
        "FROM appointment a "
        "LEFT JOIN appointment_payment ap ON ap.out_trade_no = a.out_trade_no "
        f"WHERE a.out_trade_no = {_sql_quote(out_trade_no)} "
        "LIMIT 1"
    )
    rows = _db_query_rows(sql)
    if not rows:
        return None
    row = (rows[0] + [""] * 6)[:6]
    return {
        "appointment_payment_status": row[0],
        "appointment_status": row[1],
        "appointment_trade_no": row[2],
        "paid_at": row[3],
        "payment_row_status": row[4],
        "payment_row_trade_no": row[5],
    }


def _read_payment_state(out_trade_no):
    return _load_payment_state(out_trade_no)


def _payment_state_is_confirmed(state):
    if not state:
        return False
    paid_values = {
        "paid", "success", "succeeded", "completed", "confirmed",
        "payment_received", "trade_success", "trade_finished",
    }
    payment_status = str(state.get("appointment_payment_status", "")).strip().lower()
    payment_row_status = str(state.get("payment_row_status", "")).strip().lower()
    appointment_status = str(state.get("appointment_status", "")).strip().lower()
    has_trade_or_paid_at = bool(state.get("appointment_trade_no") or state.get("payment_row_trade_no")
                                or state.get("paid_at"))
    payment_advanced = payment_status in paid_values or payment_row_status in paid_values or has_trade_or_paid_at
    appointment_not_pending = appointment_status not in {"", "pending", "failed", "cancelled", "canceled"}
    return payment_advanced and appointment_not_pending


def _payment_state_values(state):
    if not state:
        return []
    return [
        str(state.get("appointment_payment_status", "")).strip().lower(),
        str(state.get("payment_row_status", "")).strip().lower(),
        str(state.get("appointment_status", "")).strip().lower(),
    ]


def _payment_state_has_success(state):
    paid_values = {
        "paid", "success", "succeeded", "completed", "confirmed",
        "payment_received", "trade_success", "trade_finished",
    }
    if any(value in paid_values for value in _payment_state_values(state)):
        return True
    return bool(state and (state.get("appointment_trade_no") or state.get("payment_row_trade_no")
                           or state.get("paid_at")))


def _payment_state_has_failure_or_cancel(state):
    terminal_values = {"failed", "failure", "cancelled", "canceled", "closed", "close"}
    for value in _payment_state_values(state):
        if value in terminal_values or "cancel" in value or "fail" in value:
            return True
    return False


class _HandoffHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.candidates = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if not value:
                continue
            key = key.lower()
            if key in {"href", "action", "src", "value"} or key.startswith("data-"):
                self.candidates.append(value)

    def handle_data(self, data):
        if data:
            self.candidates.append(data)


_URL_LIKE_RE = re.compile(r"(?:https?://|alipays://|/[^\s\"'<>]+)[^\s\"'<>]*", re.I)


def _decode_handoff_candidate(value):
    value = html.unescape(str(value or ""))
    return urllib.parse.unquote_plus(value)


def _is_payment_handoff_endpoint(value):
    lower = _decode_handoff_candidate(value).lower()
    return (
        lower.startswith("alipays://")
        or ("gateway.do" in lower and "alipay" in lower)
        or "alipay-h5/pay.php" in lower
        or "alipay-h5/payment.php" in lower
    )


def _candidate_binds_current_order(value, out_trade_no):
    decoded = _decode_handoff_candidate(value)
    if out_trade_no not in decoded:
        return False
    return _is_payment_handoff_endpoint(decoded)


def _html_has_desktop_handoff(text, out_trade_no):
    decoded_text = _decode_handoff_candidate(text)
    if out_trade_no not in decoded_text:
        return False

    parser = _HandoffHtmlParser()
    try:
        parser.feed(text or "")
    except Exception:
        parser.candidates = []

    candidates = list(parser.candidates)
    candidates.extend(_URL_LIKE_RE.findall(decoded_text))

    if any(_candidate_binds_current_order(candidate, out_trade_no) for candidate in candidates):
        return True

    has_payment_endpoint = any(_is_payment_handoff_endpoint(candidate) for candidate in candidates)
    has_order_field = "out_trade_no" in decoded_text.lower() and out_trade_no in decoded_text
    return has_payment_endpoint and has_order_field


def check_i1(client):
    def f():
        r = client.health()
        assert r.status_code == 200, f"health status {r.status_code}"
        assert r.json().get("ok") is True, f"health ok!=true: {r.text[:200]}"
        return _ok("health 200 ok=true")
    return _guard(f)


def check_i2(client):
    def f():
        sess = client.login(PATIENT_EMAIL, PATIENT_PASSWORD)
        otn = client.create_appointment(sess, apponum=711)
        r = client.payment_entry(sess, otn)
        assert r.status_code == 200, f"payment.php status {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data.get("out_trade_no") == otn, f"out_trade_no mismatch: {data.get('out_trade_no')} != {otn}"
        assert data.get("payment_status") == "pending", f"payment_status != pending: {data.get('payment_status')}"
        assert str(data.get("amount")) == "99.00", f"amount != 99.00: {data.get('amount')}"
        assert data.get("currency") == "CNY", f"currency != CNY: {data.get('currency')}"
        payment_url = str(data.get("payment_url", ""))
        assert payment_url, "payment_url missing"
        assert otn in payment_url, f"payment_url is not bound to current out_trade_no: {payment_url}"
        return _ok("pending payment entry created with bound handoff url")
    return _guard(f)


def check_i3(client):
    def f():
        sess = client.login(PATIENT_EMAIL, PATIENT_PASSWORD)
        otn = client.create_appointment(sess, apponum=712)
        r = sess.get(
            f"{client.base_url}/patient/alipay-h5/pay.php",
            params={"out_trade_no": otn, "desktop": "1"},
            timeout=10,
        )
        assert r.status_code == 200, f"pay.php status {r.status_code}"
        assert _html_has_desktop_handoff(r.text, otn), (
            "desktop handoff page does not expose a copyable/mobile payment entry "
            "bound to the current out_trade_no"
        )
        return _ok("desktop handoff shows copyable link")
    return _guard(f)


def check_i4(client):
    def f():
        sess = client.login(PATIENT_EMAIL, PATIENT_PASSWORD)
        otn = client.create_appointment(sess, apponum=713)
        r = sess.get(
            f"{client.base_url}/patient/alipay-h5/return.php",
            params={"out_trade_no": otn},
            timeout=10,
        )
        assert r.status_code == 200, f"return.php status {r.status_code}"
        state = _read_payment_state(otn)
        assert state, f"payment state missing for {otn}"
        assert not _payment_state_has_success(state), f"return page advanced payment state: {state}"
        assert not _payment_state_has_failure_or_cancel(state), f"return page moved order to terminal failure: {state}"
        return _ok("return page does not trust frontend redirect", evidence=state)
    return _guard(f)


def check_i5(client):
    def f():
        sess = client.login(PATIENT_EMAIL, PATIENT_PASSWORD)
        otn = client.create_appointment(sess, apponum=714)
        r = sess.get(
            f"{client.base_url}/patient/alipay-h5/quit.php",
            params={"out_trade_no": otn},
            timeout=10,
        )
        assert r.status_code == 200, f"quit.php status {r.status_code}"
        state = _read_payment_state(otn)
        assert state, f"payment state missing for {otn}"
        assert not _payment_state_has_success(state), f"quit page advanced payment state: {state}"
        assert not _payment_state_has_failure_or_cancel(state), f"quit page moved order to failed/cancelled: {state}"
        return _ok("quit page leaves payment unresolved", evidence=state)
    return _guard(f)


def check_i6(client):
    def f():
        sess = client.login(PATIENT_EMAIL, PATIENT_PASSWORD)
        otn = client.create_appointment(sess, apponum=715)
        bad_sig = client.notify(otn, sign="invalid")
        assert bad_sig.status_code == 400, f"invalid-sign notify status {bad_sig.status_code} (want 400)"
        assert bad_sig.text.strip() == "fail", f"invalid-sign body {bad_sig.text[:80]!r} (want 'fail')"
        bad_amt = client.notify(otn, total_amount="98.99")
        assert bad_amt.status_code == 400, f"amount-mismatch notify status {bad_amt.status_code} (want 400)"
        assert bad_amt.text.strip() == "fail", f"amount-mismatch body {bad_amt.text[:80]!r} (want 'fail')"
        return _ok("invalid signature & amount rejected with 400/fail")
    return _guard(f)


def check_i7(client):
    def f():
        sess = client.login(PATIENT_EMAIL, PATIENT_PASSWORD)
        otn = client.create_appointment(sess, apponum=716)
        r = client.notify(otn)
        assert r.status_code == 200, f"valid notify status {r.status_code} (want 200)"
        assert r.text.strip() == "success", f"valid notify body {r.text[:80]!r} (want 'success')"
        dup = client.notify(otn)
        assert dup.status_code == 200, f"duplicate notify status {dup.status_code} (want 200)"
        assert dup.text.strip() == "success", f"duplicate notify body {dup.text[:80]!r} (want 'success')"
        last_state = None
        for _ in range(5):
            last_state = _load_payment_state(otn)
            if _payment_state_is_confirmed(last_state):
                break
            time.sleep(1)
        assert last_state is not None, f"order not found in DB after notify: {otn}"
        assert _payment_state_is_confirmed(last_state), \
            f"notify returned success but DB state is not paid/confirmed: {last_state}"
        evidence = save_evidence(f"notify_db_state_{otn}.json", last_state)
        return _ok("valid + idempotent duplicate notify confirmed and persisted", [evidence] if evidence else None)
    return _guard(f)


def check_i8(client):
    def f():
        sess = client.login(PATIENT_EMAIL, PATIENT_PASSWORD)
        otn = client.create_appointment(sess, apponum=717)
        r = client.payment_entry(sess, otn)
        assert r.status_code == 200, f"payment.php status {r.status_code}: {r.text[:200]}"
        data = r.json()
        handoff = _extract_handoff(client, sess, otn, data.get("payment_url"))
        params = handoff["params"]
        biz = handoff["biz"]
        raw_lower = handoff["raw"].lower()
        action = handoff.get("action") or ""

        checks = {
            "gateway": _has_external_alipay_gateway(action, handoff["raw"]),
            "method": params.get("method") == "alipay.trade.wap.pay"
                      or "alipay.trade.wap.pay" in raw_lower,
            "product": (isinstance(biz, dict) and biz.get("product_code") == "QUICK_WAP_WAY")
                       or "quick_wap_way" in raw_lower,
            "order": (isinstance(biz, dict) and str(biz.get("out_trade_no")) == otn)
                     or otn in handoff["raw"],
            "amount": (isinstance(biz, dict) and _amount_is_99(biz.get("total_amount")))
                      or "99.00" in handoff["raw"],
            "sign": bool(params.get("sign")),
            "sign_type": str(params.get("sign_type", "")).upper() == "RSA2" or "rsa2" in raw_lower,
            "return_url": _has_url_value(params, biz, raw_lower, "return_url"),
            "notify_url": _has_url_value(params, biz, raw_lower, "notify_url"),
            "quit_url": _has_url_value(params, biz, raw_lower, "quit_url"),
        }
        assert all(checks.values()), f"WAP request incomplete: {checks}"
        return _ok("mobile handoff builds signed alipay.trade.wap.pay request",
                   [e for e in [handoff["evidence"]] if e])
    return _guard(f)


def check_i9(client):
    def f():
        sess = client.login(PATIENT_EMAIL, PATIENT_PASSWORD)
        otn = client.create_appointment(sess, apponum=718)
        r = client.payment_entry(sess, otn)
        assert r.status_code == 200, f"payment.php status {r.status_code}: {r.text[:200]}"
        data = r.json()
        handoff = _extract_handoff(client, sess, otn, data.get("payment_url"))
        ok, msg, evidence, infra_failure = _sandbox_gateway_accepts(handoff)
        ev = [e for e in [handoff["evidence"], evidence] if e]
        if ok:
            return _ok(msg, ev)
        if infra_failure:
            return _infra_fail(msg, ev)
        return _fail(msg, ev)
    return _guard(f)


def wait_ready(base_url, attempts=30):
    client = EdocClient(base_url)
    for _ in range(attempts):
        try:
            if client.health().status_code == 200:
                return client, True
        except requests.RequestException:
            pass
        time.sleep(1)
    return client, False


def run_integration_checks(base_url):
    client, ready = wait_ready(base_url)
    if not ready:
        reason = f"service not ready at {base_url} (health.php never returned 200)"
        return {rid: {"passed": False, "message": reason, "infra_failure": True}
                for rid in ["wap_build_runtime", "wap_create_payment_entry", "wap_payment_handoff",
                            "wap_return_not_final", "wap_quit_url_flow", "wap_notify_endpoint",
                            "wap_notify_or_query_confirm", "wap_wap_request_shape",
                            "wap_sandbox_gateway_accepts"]}
    return {
        "wap_build_runtime": check_i1(client),
        "wap_create_payment_entry": check_i2(client),
        "wap_payment_handoff": check_i3(client),
        "wap_return_not_final": check_i4(client),
        "wap_quit_url_flow": check_i5(client),
        "wap_notify_endpoint": check_i6(client),
        "wap_notify_or_query_confirm": check_i7(client),
        "wap_wap_request_shape": check_i8(client),
        "wap_sandbox_gateway_accepts": check_i9(client),
    }


if __name__ == "__main__":
    import json
    import os
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("EDOC_BASE_URL", "http://localhost:8136")
    print(json.dumps(run_integration_checks(url), indent=2, ensure_ascii=False))
