"""Integration tests I1-I14 for the eDoc H5 payment safety bench.

These run against the live PHP app serving the agent's modified workspace.
Each test maps 1:1 to a fixed integration rubric (see tests/rubrics.json and the
TEST_TO_RUBRIC map in tests/build_result.py). Do not delete or rename tests
without updating rubrics.json and build_result.py.
"""
import os
import re
import subprocess


def _appointment_card(client, patient, out_trade_no):
    response = patient.get(f"{client.base_url}/patient/appointment.php", timeout=10)
    assert response.status_code == 200
    marker = f"Trade: {out_trade_no}"
    idx = response.text.find(marker)
    assert idx >= 0, response.text[:1000]
    start = response.text.rfind('<td style="width: 25%;">', 0, idx)
    end = response.text.find("</td>", idx)
    if start < 0:
        start = max(0, idx - 1500)
    if end < 0:
        end = idx + 800
    return response.text[start:end]


def _status_from_appointment_page(client, patient, out_trade_no):
    card = _appointment_card(client, patient, out_trade_no)
    matches = re.findall(r"Payment: <b>([^<]+)</b>", card)
    assert matches, card
    return matches[-1]


def _refunded_amount_from_appointment_page(client, patient, out_trade_no):
    card = _appointment_card(client, patient, out_trade_no)
    match = re.search(r"Refunded:\s*CNY\s*([0-9]+(?:\.[0-9]+)?)", card)
    assert match, card
    return f"{float(match.group(1)):.2f}"


def _paid_appointment(client, patient, apponum):
    out_trade_no = client.create_appointment(patient, apponum=apponum)
    payment_response = client.payment_entry(patient, out_trade_no)
    assert payment_response.status_code == 200
    appoid = int(payment_response.json()["appoid"])
    response = client.notify(out_trade_no)
    assert response.status_code == 200
    assert response.text == "success"
    return out_trade_no, appoid


def test_wap_return_not_final(client, patient):
    out_trade_no = client.create_appointment(patient, apponum=811)
    client.payment_entry(patient, out_trade_no)

    response = patient.get(
        f"{client.base_url}/patient/alipay-h5/return.php",
        params={"out_trade_no": out_trade_no},
        timeout=10,
    )
    assert response.status_code == 200
    assert "pending" in response.text
    assert _status_from_appointment_page(client, patient, out_trade_no) == "pending"


def test_wap_quit_url_flow(client, patient):
    out_trade_no = client.create_appointment(patient, apponum=812)
    client.payment_entry(patient, out_trade_no)

    response = patient.get(
        f"{client.base_url}/patient/alipay-h5/quit.php",
        params={"out_trade_no": out_trade_no},
        timeout=10,
    )
    assert response.status_code == 200
    assert "pending" in response.text
    assert _status_from_appointment_page(client, patient, out_trade_no) == "pending"


def test_wap_notify_verify_fields(client, patient):
    out_trade_no = client.create_appointment(patient, apponum=813)
    client.payment_entry(patient, out_trade_no)

    cases = [
        {"sign": "invalid"},
        {"total_amount": "98.99"},
        {"seller_id": "wrong-seller"},
        {"app_id": "wrong-app"},
        {"out_trade_no": f"{out_trade_no}-other"},
    ]
    for payload in cases:
        response = client.notify(out_trade_no, **payload)
        assert response.status_code == 400
        assert response.text == "fail"

    assert _status_from_appointment_page(client, patient, out_trade_no) == "pending"


def test_wap_mock_signature_not_prod_bypass():
    """A mock fixture signature must not become a non-mock verification bypass."""
    workspace = os.environ.get("WORKSPACE_DIR", "/workspace/app")
    lib_path = os.path.join(workspace, "lib", "alipay_h5.php")
    assert os.path.isfile(lib_path), f"missing {lib_path}"

    php = f"""<?php
putenv("ALIPAY_MOCK_MODE=false");
putenv("ALIPAY_PUBLIC_KEY=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvNPr2a5fD4r0QjKp0WmnHvV89KJ1lf8s6Ot3LQy66kx54wt8vOvSRNGYmkb4Ypyf55RXVM4A5eIE9v8lWVMpjgz1p1fQpGoOWlbUkzb1xUErXyHm1mW+qgGvZGcttYwHNxHSDwT62d6VYJv8gIYiTNzfbqzbrEJgw8ZUnmRqAG89U6ZrwqHw1sS4bH3TGmxTMiBeGLiJ82w3JJ7d7oFIOFCThOxBbBY6QFHxHHbFhCDJlKuDKdpQk82T1ldnDPczcaIOQV14vzTcEkgoi11oGZ7ZcOswOFSASVMaQUiGcnPSv4dGgoGkpiJBrTBVnjS+hgmq5pB7jpDrpMBk6QIDAQAB");
require_once {lib_path!r};
if (!function_exists("alipay_verify")) {{
    echo "alipay_verify missing\\n";
    exit(3);
}}
$params = [
    "app_id" => "edoc-h5-sandbox-app",
    "seller_id" => "edoc-clinic",
    "out_trade_no" => "EDOC-MOCK-BYPASS",
    "trade_no" => "MOCK-TRADE-BYPASS",
    "trade_status" => "TRADE_SUCCESS",
    "total_amount" => "99.00",
    "sign" => "mock-valid",
    "sign_type" => "RSA2",
];
$publicKey = getenv("ALIPAY_PUBLIC_KEY");
try {{
    $accepted = alipay_verify($params, $publicKey);
}} catch (Throwable $e) {{
    fwrite(STDOUT, "mock-valid rejected by verifier exception\\n");
    exit(0);
}}
if ($accepted) {{
    echo "mock-valid accepted while ALIPAY_MOCK_MODE=false\\n";
    exit(2);
}}
fwrite(STDOUT, "mock-valid rejected outside mock mode\\n");
exit(0);
"""
    proc = subprocess.run(
        ["php"],
        input=php,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-1000:]


def test_wap_notify_accept_paid_and_idempotent(client, patient):
    out_trade_no = client.create_appointment(patient, apponum=814)
    client.payment_entry(patient, out_trade_no)

    response = client.notify(out_trade_no)
    assert response.status_code == 200
    assert response.text == "success"
    assert _status_from_appointment_page(client, patient, out_trade_no) == "paid"

    duplicate = client.notify(out_trade_no)
    assert duplicate.status_code == 200
    assert duplicate.text == "success"
    assert _status_from_appointment_page(client, patient, out_trade_no) == "paid"


def test_wap_notify_missing_query_compensation(client, patient):
    out_trade_no = client.create_appointment(patient, apponum=815)
    client.payment_entry(patient, out_trade_no)

    response = client.sync(patient, out_trade_no, status="TRADE_SUCCESS")
    assert response.status_code == 200
    assert response.json()["status"] == "paid"
    assert _status_from_appointment_page(client, patient, out_trade_no) == "paid"


def test_wap_processing_polling_keeps_pending(client, patient):
    out_trade_no = client.create_appointment(patient, apponum=816)
    client.payment_entry(patient, out_trade_no)

    response = client.sync(patient, out_trade_no, status="WAIT_BUYER_PAY")
    assert response.status_code in (200, 202)
    assert response.json()["status"] == "pending"
    assert _status_from_appointment_page(client, patient, out_trade_no) == "pending"


def test_wap_no_repeat_pay_before_confirm(client, patient):
    out_trade_no = client.create_appointment(patient, apponum=817)
    first = client.payment_entry(patient, out_trade_no)
    second = client.payment_entry(patient, out_trade_no)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["payment_url"] == second.json()["payment_url"]
    assert first.json()["out_trade_no"] == second.json()["out_trade_no"]


def test_wap_partial_refund_idempotency_and_over_refund(client, patient, admin):
    out_trade_no, appoid = _paid_appointment(client, patient, apponum=818)

    refund = client.refund(admin, appoid, "20.00", f"RF-PART-{appoid}")
    assert refund.status_code == 200
    data = refund.json()
    assert data["appointment"]["payment_status"] == "partially_refunded"
    assert data["appointment"]["refunded_amount"] == "20.00"
    assert data["refundable_amount"] == "79.00"

    duplicate = client.refund(admin, appoid, "20.00", f"RF-PART-{appoid}")
    assert duplicate.status_code == 200
    duplicate_data = duplicate.json()
    assert duplicate_data["appointment"]["refunded_amount"] == "20.00"

    over_refund = client.refund(admin, appoid, "999.00", f"RF-OVER-{appoid}")
    assert over_refund.status_code == 422

    assert _refunded_amount_from_appointment_page(client, patient, out_trade_no) == "20.00"


def test_wap_refund_response_verify_not_code_only(client, patient, admin):
    _, appoid = _paid_appointment(client, patient, apponum=819)

    response = client.refund(
        admin,
        appoid,
        "10.00",
        f"RF-NOFUND-{appoid}",
        mock_refund_status="unknown",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["refund"]["status"] in ("unknown", "pending", "failed")
    assert data["appointment"]["refunded_amount"] == "0.00"

    query = client.refund_query(admin, f"RF-NOFUND-{appoid}")
    assert query.status_code == 200
    assert "query" in query.json()


def test_wap_refund_success_code_with_unsafe_fields_not_accounted(client, patient, admin):
    out_trade_no, appoid = _paid_appointment(client, patient, apponum=820)

    cases = [
        ("no_fund_change", f"RF-NOFUNDY-{appoid}"),
        ("amount_mismatch", f"RF-BADAMT-{appoid}"),
        ("request_mismatch", f"RF-BADREQ-{appoid}"),
    ]
    for mock_status, request_no in cases:
        response = client.refund(
            admin,
            appoid,
            "10.00",
            request_no,
            mock_refund_status=mock_status,
        )
        assert response.status_code in (200, 400, 409, 422)
        if response.status_code == 200:
            data = response.json()
            assert data["refund"]["status"] != "succeeded"
            assert data["appointment"]["payment_status"] == "paid"
            assert data["appointment"]["refunded_amount"] == "0.00"

        assert _refunded_amount_from_appointment_page(client, patient, out_trade_no) == "0.00"
        assert _status_from_appointment_page(client, patient, out_trade_no) == "paid"


def test_wap_terminal_refund_state_not_downgraded_by_late_events(client, patient, admin):
    out_trade_no, appoid = _paid_appointment(client, patient, apponum=821)

    refund = client.refund(admin, appoid, "20.00", f"RF-TERM-{appoid}")
    assert refund.status_code == 200
    assert refund.json()["appointment"]["payment_status"] == "partially_refunded"
    assert _status_from_appointment_page(client, patient, out_trade_no) == "partially_refunded"

    stale_unpaid_notify = client.notify(out_trade_no, trade_status="WAIT_BUYER_PAY")
    assert stale_unpaid_notify.status_code in (200, 400, 409)
    assert _status_from_appointment_page(client, patient, out_trade_no) == "partially_refunded"

    stale_success_notify = client.notify(out_trade_no, trade_status="TRADE_SUCCESS")
    assert stale_success_notify.status_code in (200, 400, 409)
    assert _status_from_appointment_page(client, patient, out_trade_no) == "partially_refunded"

    sync = client.sync(patient, out_trade_no, status="WAIT_BUYER_PAY")
    assert sync.status_code in (200, 409)
    if sync.status_code == 200:
        assert sync.json()["status"] == "partially_refunded"
    assert _status_from_appointment_page(client, patient, out_trade_no) == "partially_refunded"

    quit_response = patient.get(
        f"{client.base_url}/patient/alipay-h5/quit.php",
        params={"out_trade_no": out_trade_no},
        timeout=10,
    )
    assert quit_response.status_code == 200
    assert _status_from_appointment_page(client, patient, out_trade_no) == "partially_refunded"


def test_wap_unpaid_appointment_refund_rejected(client, patient, admin):
    out_trade_no = client.create_appointment(patient, apponum=822)
    payment_response = client.payment_entry(patient, out_trade_no)
    assert payment_response.status_code == 200
    appoid = int(payment_response.json()["appoid"])

    refund = client.refund(admin, appoid, "10.00", f"RF-UNPAID-{appoid}")
    business_failed = False
    if refund.status_code == 200:
        try:
            body = refund.json()
            success = body.get("success")
            status = str(body.get("status", "")).lower()
            business_failed = (
                bool(body.get("error"))
                or success in (False, 0, "0")
                or status in ("failed", "failure", "rejected", "not_refundable")
            )
        except ValueError:
            business_failed = False
    assert refund.status_code in (400, 409, 422) or business_failed

    assert _refunded_amount_from_appointment_page(client, patient, out_trade_no) == "0.00"
    assert _status_from_appointment_page(client, patient, out_trade_no) == "pending"


def test_wap_refund_query_success_writeback_idempotent(client, patient, admin):
    out_trade_no, appoid = _paid_appointment(client, patient, apponum=823)
    request_no = f"RF-QUERY-{appoid}"

    refund = client.refund(
        admin,
        appoid,
        "99.00",
        request_no,
        mock_refund_status="unknown",
    )
    assert refund.status_code == 200
    data = refund.json()
    assert data["refund"]["status"] in ("unknown", "pending", "failed")
    assert data["appointment"]["payment_status"] == "paid"
    assert data["appointment"]["refunded_amount"] == "0.00"

    first_query = client.refund_query(admin, request_no)
    assert first_query.status_code == 200
    first_data = first_query.json()
    assert first_data["query"]["code"] == "10000"
    assert first_data["query"]["refund_status"] == "REFUND_SUCCESS"
    assert first_data["query"]["out_request_no"] == request_no
    assert _status_from_appointment_page(client, patient, out_trade_no) == "refunded"

    assert _refunded_amount_from_appointment_page(client, patient, out_trade_no) == "99.00"

    duplicate_query = client.refund_query(admin, request_no)
    assert duplicate_query.status_code == 200
    assert _status_from_appointment_page(client, patient, out_trade_no) == "refunded"
    assert _refunded_amount_from_appointment_page(client, patient, out_trade_no) == "99.00"
