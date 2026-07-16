#!/usr/bin/env python3
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from support.common import *


def http_success(status):
    try:
        return 200 <= int(status) < 400
    except Exception:
        return False


def has_app_ready(log):
    return bool(re.search(r"(?m)^APP_READY=https?://", log or ""))


def direct_value(obj, *keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        value = obj.get(key)
        if value is not None and value != "":
            return value
    return None


def normalize_payment_response(body):
    if not isinstance(body, dict):
        return {}
    nested = body.get("payment")
    payment = dict(nested) if isinstance(nested, dict) else {}
    aliases = {
        "out_trade_no": ("out_trade_no", "outTradeNo"),
        "qr_code": ("qr_code", "qrCode", "code_url", "codeUrl"),
        "trade_no": ("trade_no", "tradeNo"),
        "trade_status": ("trade_status", "tradeStatus", "status"),
        "total_amount": ("total_amount", "totalAmount", "amount"),
    }
    for canonical, keys in aliases.items():
        if payment.get(canonical) in (None, ""):
            value = direct_value(body, *keys)
            if value is not None:
                payment[canonical] = value
    return payment


def basic_checks(app, case_dir, output, case_name):
    is_qrcode = case_kind().startswith("qrcode_")
    product_method = "alipay.trade.precreate" if is_qrcode else "alipay.trade.pay"
    expected_endpoint = "/alipay/precreate" if is_qrcode else "/alipay/barcode/pay"
    rubrics = []
    mock_proc, mock_base = start_mock(case_dir, output)
    try:
        port, rc, log = start_app(app, case_dir, output, case_name, mock_base)
        ready = has_app_ready(log)
        build_ok = rc == 0 and ready
        rubrics.append(rubric("integ.app_start", build_ok, "start.sh exit=%s ready=%s" % (rc, ready), "integration"))
        if not build_ok:
            for rid in ["integ.invoice_create", "integ.payment_endpoint_exists", "integ.correct_product_method", "integ.out_trade_no_bound", "integ.amount_bound", "integ.query_or_status_endpoint", "integ.gateway_call_recorded"]:
                rubrics.append(rubric(rid, False, "application did not start", "integration"))
            return rubrics
        base = "http://127.0.0.1:%s" % port
        st, body, inv_id = create_invoice(base, app)
        rubrics.append(rubric("integ.invoice_create", http_success(st) and bool(inv_id), "invoice status=%s id=%s body=%s" % (st, inv_id, body), "integration"))
        if not inv_id:
            for rid in ["integ.payment_endpoint_exists", "integ.correct_product_method", "integ.out_trade_no_bound", "integ.amount_bound", "integ.query_or_status_endpoint", "integ.gateway_call_recorded"]:
                rubrics.append(rubric(rid, False, "invoice creation failed", "integration"))
            return rubrics
        if is_qrcode:
            st2, pay = http_json(base + "/api/invoices/%s/alipay/precreate" % inv_id, "POST", {})
            payment = normalize_payment_response(pay)
            out_no = payment.get("out_trade_no")
            qr = payment.get("qr_code")
            qst, _ = http_json(base + "/api/alipay/payments/%s/query" % out_no, "POST", {}) if out_no else (0,{})
        else:
            st2, pay = http_json(base + "/api/invoices/%s/alipay/barcode/pay" % inv_id, "POST", {"auth_code": "286123456789012345"})
            payment = normalize_payment_response(pay)
            out_no = payment.get("out_trade_no")
            qr = payment.get("trade_no") or payment.get("trade_status") if isinstance(payment, dict) else None
            qst, _ = http_json(base + "/api/invoices/%s/alipay/barcode/query" % inv_id, "POST", {})
        inv = db_row(app, "SELECT id, grand_total, invoice_number FROM invoices WHERE id=?", (inv_id,)) or {}
        gateway_state_status, gateway_state = http_json(mock_base + "/__mock/state", auth=False)
        mock_trades = gateway_state.get("trades", {}) if isinstance(gateway_state, dict) else {}
        gateway_request_count = len(gateway_state.get("gateway_requests", [])) if isinstance(gateway_state, dict) else 0
        trade_count = len(mock_trades) if isinstance(mock_trades, dict) else 0
        requested_methods = set()
        if isinstance(gateway_state, dict):
            for request in gateway_state.get("gateway_requests", []):
                if isinstance(request, dict) and request.get("method"):
                    requested_methods.add(str(request.get("method")))
        mock_trade = mock_trades.get(out_no, {}) if isinstance(mock_trades, dict) and out_no else {}
        has_mock_trade = isinstance(mock_trade, dict) and bool(mock_trade)
        mock_trade_status = str(mock_trade.get("trade_status", "")) if has_mock_trade else ""
        successful_mock_trade = mock_trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED")
        method_ok = product_method in requested_methods
        calls_recorded = method_ok and has_mock_trade
        endpoint_ready = http_success(st2) and bool(out_no) and has_mock_trade and (bool(qr) if is_qrcode else successful_mock_trade)
        rubrics.append(rubric("integ.payment_endpoint_exists", endpoint_ready, "payment endpoint status=%s out_trade_no=%s mock_trade=%s body=%s" % (st2, out_no, mock_trade, pay), "integration"))
        rubrics.append(rubric("integ.correct_product_method", method_ok, "expected method=%s endpoint_status=%s gateway_methods=%s" % (product_method, st2, sorted(requested_methods)), "integration"))
        rubrics.append(rubric("integ.out_trade_no_bound", bool(out_no) and str(inv.get("id", "")) in str(out_no), "out_trade_no=%s invoice_id=%s" % (out_no, inv.get("id")), "integration"))
        amount_ok = False
        actual_amount = None
        if has_mock_trade:
            try:
                if mock_trade.get("total_amount") not in (None, ""):
                    actual_amount = float(mock_trade.get("total_amount"))
            except Exception:
                actual_amount = None
        if actual_amount is None and has_mock_trade and isinstance(payment, dict):
            try:
                for key in ("total_amount", "totalAmount", "amount"):
                    if payment.get(key) not in (None, ""):
                        actual_amount = float(payment.get(key))
                        break
            except Exception:
                actual_amount = None
        try:
            amount_ok = has_mock_trade and actual_amount is not None and abs(actual_amount - float(inv.get("grand_total", -1))) < 0.01
        except Exception:
            amount_ok = False
        rubrics.append(rubric("integ.amount_bound", amount_ok, "invoice_total=%s actual_amount=%s mock_trade=%s payment=%s" % (inv.get("grand_total"), actual_amount, mock_trade, payment), "integration"))
        rubrics.append(rubric("integ.query_or_status_endpoint", bool(out_no) and http_success(qst) and has_mock_trade, "query/status endpoint status=%s out_trade_no=%s mock_trade=%s" % (qst, out_no, mock_trade), "integration"))
        rubrics.append(rubric("integ.gateway_call_recorded", calls_recorded, "mock gateway state status=%s gateway_requests=%s trades=%s out_trade_no=%s mock_trade=%s" % (gateway_state_status, gateway_request_count, trade_count, out_no, mock_trade), "integration"))
    finally:
        stop_proc(mock_proc)
    return rubrics


def find_value(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = find_value(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_value(value, key)
            if found is not None:
                return found
    return None


def body_text(body):
    return json.dumps(body, ensure_ascii=False, sort_keys=True) if isinstance(body, (dict, list)) else str(body)


def as_money(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def money_close(a, b):
    aa = as_money(a)
    bb = as_money(b)
    return aa is not None and bb is not None and abs(aa - bb) < 0.01


def refund_api(base, invoice_id, amount, out_request_no):
    amount_value = round(float(amount), 2)
    payload = {
        "amount": amount_value,
        "refund_amount": amount_value,
        "out_request_no": out_request_no,
        "reason": "benchmark refund validation",
    }
    return http_json(base + "/api/invoices/%s/alipay/refund" % invoice_id, "POST", payload)


def refund_query_api(base, invoice_id, out_request_no):
    return http_json(base + "/api/invoices/%s/alipay/refund/query" % invoice_id, "POST", {"out_request_no": out_request_no})


def mock_state(mock_base):
    _, state = http_json(mock_base + "/__mock/state", auth=False)
    return state if isinstance(state, dict) else {}


def mock_refund_count(mock_base):
    return len(mock_state(mock_base).get("refunds", {}))


def mock_refund_record(mock_base, out_request_no):
    return mock_state(mock_base).get("refunds", {}).get(out_request_no, {})


def mock_trade_refunded_amount(mock_base, out_trade_no):
    trade = mock_state(mock_base).get("trades", {}).get(out_trade_no, {})
    return as_money(trade.get("refunded_amount"), 0.0) or 0.0


def response_fund_change(body):
    values = []
    def collect(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "fund_change":
                    values.append(value)
                collect(value)
        elif isinstance(obj, list):
            for value in obj:
                collect(value)
    collect(body)
    for value in values:
        text = str(value).upper()
        if text in ("Y", "N"):
            return text
    for value in values:
        if value is True:
            return "Y"
        if value is False:
            return "N"
    return ""


def response_out_request_no(body):
    value = find_value(body, "out_request_no")
    return str(value) if value is not None else ""


def response_refunded_amount(body):
    for key in ("refunded_amount", "total_refunded", "refundedAmount", "totalRefunded", "refund_amount", "refundAmount"):
        value = find_value(body, key)
        amount = as_money(value)
        if amount is not None:
            return amount
    return None


def response_marks_terminal_refund(body):
    text = body_text(body).lower()
    return any(token in text for token in ("fully_refunded", "full_refund", "refunded", "trade_closed"))


def response_is_explicit_refund_success(body):
    status = str(find_value(body, "refund_status") or find_value(body, "status") or "").lower()
    return status in ("refund_success", "refunded", "partially_refunded", "fully_refunded", "full_refund", "success")


def make_paid_qrcode_invoice(base, app):
    st, body, invoice_id = create_invoice(base, app)
    if not http_success(st) or not invoice_id:
        return {"ok": False, "error": "invoice create failed", "status": st, "body": body}
    stp, bodyp = http_json(base + "/api/invoices/%s/alipay/precreate" % invoice_id, "POST", {})
    payment = normalize_payment_response(bodyp)
    out_trade_no = payment.get("out_trade_no")
    stq, qbody = http_json(base + "/api/alipay/payments/%s/query" % out_trade_no, "POST", {}) if out_trade_no else (0, {})
    invoice = db_row(app, "SELECT id, grand_total, payment_status FROM invoices WHERE id=?", (invoice_id,)) or {}
    return {
        "ok": http_success(stp) and http_success(stq) and invoice.get("payment_status") == "Paid",
        "invoice_id": invoice_id,
        "out_trade_no": out_trade_no,
        "total": as_money(invoice.get("grand_total"), 0.0) or 0.0,
        "evidence": {"precreate_status": stp, "query_status": stq, "invoice": invoice, "precreate": bodyp, "query": qbody},
    }


def make_paid_barcode_invoice(base, app, auth_code):
    st, body, invoice_id = create_invoice(base, app)
    if not http_success(st) or not invoice_id:
        return {"ok": False, "error": "invoice create failed", "status": st, "body": body}
    stp, pbody = http_json(base + "/api/invoices/%s/alipay/barcode/pay" % invoice_id, "POST", {"auth_code": auth_code})
    invoice = db_row(app, "SELECT id, grand_total, payment_status FROM invoices WHERE id=?", (invoice_id,)) or {}
    payment = db_row(app, "SELECT out_trade_no, trade_status FROM alipay_barcode_payments WHERE invoice_id=?", (invoice_id,)) or {}
    return {
        "ok": http_success(stp) and invoice.get("payment_status") == "Paid" and payment.get("trade_status") == "TRADE_SUCCESS",
        "invoice_id": invoice_id,
        "out_trade_no": payment.get("out_trade_no"),
        "total": as_money(invoice.get("grand_total"), 0.0) or 0.0,
        "evidence": {"pay_status": stp, "invoice": invoice, "payment": payment, "body": pbody},
    }


def append_refund_checks(rubrics, app, base, mock_base, make_paid_invoice):
    st_unpaid, unpaid_body, unpaid_inv = create_invoice(base, app)
    before_count = mock_refund_count(mock_base)
    ust, ubody = refund_api(base, unpaid_inv or 0, 1.00, "RF%sUNPAID" % (unpaid_inv or "missing"))
    after_count = mock_refund_count(mock_base)
    rubrics.append(rubric(
        "integ.unpaid_refund_reject",
        http_success(st_unpaid) and ust in (400, 409, 422) and after_count == before_count,
        "unpaid_invoice=%s refund_status=%s body=%s gateway_refunds_before_after=%s/%s" % (unpaid_inv, ust, ubody, before_count, after_count),
        "integration",
    ))

    paid = make_paid_invoice()
    refund_ids = [
        "integ.partial_refund_success",
        "integ.full_refund_terminal",
        "integ.refund_same_request_idempotent",
        "integ.refund_multi_request_distinct",
        "integ.refund_fund_change_required",
        "integ.refund_unknown_query",
    ]
    if not paid.get("ok"):
        for rid in refund_ids:
            rubrics.append(rubric(rid, False, "paid precondition failed before refund checks: %s" % paid, "integration"))
        return

    inv = paid["invoice_id"]
    out_trade_no = paid["out_trade_no"]
    total = paid["total"] or 262.50
    part = min(50.00, max(1.00, round(total / 3.0, 2)))
    first_req = "RF%sPART1" % inv
    st1, body1 = refund_api(base, inv, part, first_req)
    refunded1 = response_refunded_amount(body1)
    mock1 = mock_refund_record(mock_base, first_req)
    partial_ok = (
        http_success(st1)
        and response_fund_change(body1) == "Y"
        and response_out_request_no(body1) == first_req
        and refunded1 is not None
        and refunded1 >= part - 0.01
        and mock1.get("fund_change") == "Y"
    )
    rubrics.append(rubric("integ.partial_refund_success", partial_ok, "status=%s body=%s mock_refund=%s" % (st1, body1, mock1), "integration"))

    st2, body2 = refund_api(base, inv, part, first_req)
    refunded2 = response_refunded_amount(body2)
    mock2 = mock_refund_record(mock_base, first_req)
    same_request_ok = (
        http_success(st2)
        and response_out_request_no(body2) == first_req
        and refunded2 is not None
        and money_close(refunded2, refunded1)
        and int(mock2.get("call_count", 0)) >= 1
        and mock_trade_refunded_amount(mock_base, out_trade_no) <= part + 0.01
    )
    rubrics.append(rubric("integ.refund_same_request_idempotent", same_request_ok, "first=%s second=%s mock_refund=%s mock_total=%s" % (body1, body2, mock2, mock_trade_refunded_amount(mock_base, out_trade_no)), "integration"))

    second_req = "RF%sPART2" % inv
    st3, body3 = refund_api(base, inv, part, second_req)
    refunded3 = response_refunded_amount(body3)
    mock_total3 = mock_trade_refunded_amount(mock_base, out_trade_no)
    multi_ok = (
        http_success(st3)
        and response_out_request_no(body3) == second_req
        and (
            (refunded3 is not None and refunded3 >= (part * 2) - 0.01)
            or mock_total3 >= (part * 2) - 0.01
        )
        and mock_refund_record(mock_base, second_req).get("fund_change") == "Y"
    )
    rubrics.append(rubric("integ.refund_multi_request_distinct", multi_ok, "second_partial_status=%s body=%s mock_refunds=%s" % (st3, body3, mock_state(mock_base).get("refunds", {})), "integration"))

    before_bad = mock_trade_refunded_amount(mock_base, out_trade_no)
    bad_req = "RF%sFUND_CHANGE_NO" % inv
    st_bad, body_bad = refund_api(base, inv, 1.00, bad_req)
    after_bad = mock_trade_refunded_amount(mock_base, out_trade_no)
    mock_bad = mock_refund_record(mock_base, bad_req)
    bad_explicitly_not_success = (
        st_bad in (400, 409, 422, 502)
        or find_value(body_bad, "success") is False
        or str(find_value(body_bad, "refund_status") or "").lower() in ("no_fund_change", "failed", "refund_failed")
    )
    fund_change_ok = (
        (response_fund_change(body_bad) == "N" or mock_bad.get("fund_change") == "N")
        and money_close(before_bad, after_bad)
        and bad_explicitly_not_success
    )
    rubrics.append(rubric("integ.refund_fund_change_required", fund_change_ok, "status=%s body=%s mock_refund=%s refunded_before_after=%s/%s" % (st_bad, body_bad, mock_bad, before_bad, after_bad), "integration"))

    unknown_req = "RF%sREFUND_UNKNOWN" % inv
    before_unknown = mock_trade_refunded_amount(mock_base, out_trade_no)
    st_unknown, body_unknown = refund_api(base, inv, 1.00, unknown_req)
    st_query, body_query = refund_query_api(base, inv, unknown_req)
    after_unknown = mock_trade_refunded_amount(mock_base, out_trade_no)
    unknown_not_final = (
        not response_is_explicit_refund_success(body_unknown)
        and money_close(before_unknown, after_unknown)
        and http_success(st_query)
        and str(find_value(body_query, "refund_status") or "").lower() in ("refund_processing", "processing", "unknown", "pending")
    )
    rubrics.append(rubric("integ.refund_unknown_query", unknown_not_final, "refund_status=%s body=%s query_status=%s query=%s refunded_before_after=%s/%s" % (st_unknown, body_unknown, st_query, body_query, before_unknown, after_unknown), "integration"))

    full_paid = make_paid_invoice()
    if not full_paid.get("ok"):
        rubrics.append(rubric("integ.full_refund_terminal", False, "full refund paid precondition failed: %s" % full_paid, "integration"))
        return
    full_inv = full_paid["invoice_id"]
    full_req = "RF%sFULL" % full_inv
    full_amount = full_paid["total"] or total
    st_full, body_full = refund_api(base, full_inv, full_amount, full_req)
    full_refunded = response_refunded_amount(body_full)
    full_invoice = db_row(app, "SELECT payment_status FROM invoices WHERE id=?", (full_inv,)) or {}
    full_terminal = response_marks_terminal_refund(body_full) or str(full_invoice.get("payment_status", "")).lower().replace(" ", "_") in ("refunded", "fully_refunded", "full_refund")
    full_ok = (
        http_success(st_full)
        and response_fund_change(body_full) == "Y"
        and full_refunded is not None
        and full_refunded >= full_amount - 0.01
        and full_terminal
    )
    rubrics.append(rubric("integ.full_refund_terminal", full_ok, "status=%s amount=%s body=%s invoice=%s" % (st_full, full_amount, body_full, full_invoice), "integration"))


def safety_qrcode(app, case_dir, output, case_name):
    rubrics=[]; mock_proc, mock_base = start_mock(case_dir, output)
    try:
        port, rc, log = start_app(app, case_dir, output, case_name, mock_base)
        ready = has_app_ready(log)
        build_ok = rc == 0 and ready
        rubrics.append(rubric("integ.app_start", build_ok, "start.sh exit=%s ready=%s" % (rc, ready), "integration"))
        if not build_ok:
            return rubrics
        base="http://127.0.0.1:%s"%port
        def precreate(inv_id):
            if not inv_id:
                return 0, {"error": "missing invoice_id"}, {}, None
            status, body = http_json(base + "/api/invoices/%s/alipay/precreate" % inv_id, "POST", {})
            payment = normalize_payment_response(body)
            return status, body, payment, payment.get("out_trade_no")
        st, body, inv = create_invoice(base, app); rubrics.append(rubric("integ.invoice_create", http_success(st) and bool(inv), "invoice status=%s id=%s"%(st,inv), "integration"))
        stp, bodyp, pay, out = precreate(inv)
        rubrics.append(rubric("integ.precreate_qr", http_success(stp) and out and pay.get("qr_code"), "precreate status=%s out=%s qr=%s"%(stp,out,bool(pay.get("qr_code") if isinstance(pay,dict) else None)), "integration"))
        _, again_pending=http_json(base+"/api/invoices/%s/alipay/precreate"%inv,"POST",{}) if inv else (0,{})
        rows_pending=db_scalar(app,"SELECT COUNT(*) AS c FROM alipay_payments WHERE invoice_id=?",(inv,))
        again_out=normalize_payment_response(again_pending).get("out_trade_no")
        rubrics.append(rubric("integ.no_repeat_pay_before_confirm", rows_pending==1, "pending second precreate rows=%s body=%s"%(rows_pending,again_pending), "integration"))
        rubrics.append(rubric("integ.request_idempotency_key", bool(out) and out==again_out, "stable pending out_trade_no first=%s second=%s"%(out,again_out), "integration"))
        stq, qbody = http_json(base+"/api/alipay/payments/%s/query"%out,"POST",{}) if out else (0,{})
        invrow=db_row(app,"SELECT payment_status,amount_paid,grand_total FROM invoices WHERE id=?",(inv,)) or {}; prow=db_row(app,"SELECT status,total_amount FROM alipay_payments WHERE out_trade_no=?",(out,)) or {}
        rubrics.append(rubric("integ.query_success_paid", http_success(stq) and invrow.get("payment_status")=="Paid" and prow.get("status")=="TRADE_SUCCESS", "query=%s invoice=%s payment=%s"%(stq,invrow,prow), "integration"))
        # valid notify on a fresh invoice
        _,_,inv2=create_invoice(base,app); st2,bp,pay2,out2=precreate(inv2)
        _,nbody=mock_post(mock_base,"/__mock/notify",{"out_trade_no":out2,"notify_url":base+"/alipay/notify/order-code","scenario":"success"}) if out2 else (0, {"error": "missing out_trade_no", "precreate_status": st2, "precreate_body": bp})
        inv2row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv2,)) or {}
        rubrics.append(rubric("integ.valid_notify_accept", isinstance(nbody,dict) and nbody.get("status")==200 and inv2row.get("payment_status")=="Paid", "notify=%s invoice=%s"%(nbody,inv2row), "integration"))
        # bad signature
        _,_,inv3=create_invoice(base,app); st3,bp3,pay3,out3=precreate(inv3)
        _,bad=mock_post(mock_base,"/__mock/notify",{"out_trade_no":out3,"notify_url":base+"/alipay/notify/order-code","scenario":"bad_signature"}) if out3 else (0, {"error": "missing out_trade_no", "precreate_status": st3, "precreate_body": bp3}); inv3row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv3,)) or {}
        rubrics.append(rubric("integ.bad_signature_reject", isinstance(bad,dict) and bad.get("status") in (400,401,403) and inv3row.get("payment_status")=="Unpaid", "bad_notify=%s invoice=%s"%(bad,inv3row), "integration"))
        # unsigned notification
        _,_,inv4=create_invoice(base,app); st4,bp4,pay4,out4=precreate(inv4)
        _,uns=mock_post(mock_base,"/__mock/notify",{"out_trade_no":out4,"notify_url":base+"/alipay/notify/order-code","scenario":"unsigned"}) if out4 else (0, {"error": "missing out_trade_no", "precreate_status": st4, "precreate_body": bp4}); inv4row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv4,)) or {}
        rubrics.append(rubric("integ.unsigned_reject", isinstance(uns,dict) and uns.get("status") in (400,401,403) and inv4row.get("payment_status")=="Unpaid", "unsigned_notify=%s invoice=%s"%(uns,inv4row), "integration"))
        # wrong amount query
        _,_,inv5=create_invoice(base,app); st5,bp5,pay5,out5=precreate(inv5)
        if out5:
            mock_post(mock_base,"/__mock/scenario",{"out_trade_no":out5,"scenario":"wrong_amount"}); _,wrong=http_json(base+"/api/alipay/payments/%s/query"%out5,"POST",{})
        else:
            wrong = {"error": "missing out_trade_no", "precreate_status": st5, "precreate_body": bp5}
        inv5row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv5,)) or {}
        wrong_result=wrong.get("result",{}) if isinstance(wrong,dict) else {}
        wrong_payment=normalize_payment_response(wrong)
        wrong_reason=wrong_result.get("reason")
        wrong_status=wrong_payment.get("trade_status") or wrong_result.get("trade_status")
        wrong_rejected = (
            inv5row.get("payment_status")=="Unpaid"
            and (
                wrong_reason in ("amount_mismatch", "wrong_amount", "total_amount_mismatch")
                or wrong_status not in ("TRADE_SUCCESS", "TRADE_FINISHED")
            )
        )
        rubrics.append(rubric("integ.wrong_amount_reject", wrong_rejected, "wrong_amount=%s payment=%s invoice=%s"%(wrong_result,wrong_payment,inv5row), "integration"))
        # wrong out trade no: notify unknown out_trade_no should not alter existing invoice
        _,_,inv6=create_invoice(base,app); st6,bp6,pay6,out6=precreate(inv6)
        _,_,dummy=create_invoice(base,app); std,bpd,payd,dummy_out=precreate(dummy)
        _,wn=mock_post(mock_base,"/__mock/notify",{"out_trade_no":dummy_out,"notify_url":base+"/alipay/notify/order-code","scenario":"success"}) if dummy_out else (0, {"error": "missing dummy_out_trade_no", "target_precreate": bp6, "dummy_precreate": bpd}); inv6row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv6,)) or {}
        rubrics.append(rubric("integ.wrong_out_trade_no_reject", inv6row.get("payment_status")=="Unpaid", "other_out_trade_no=%s target_invoice=%s notify=%s"%(dummy_out,inv6row,wn.get("status") if isinstance(wn,dict) else wn), "integration"))
        # wait
        _,_,inv7=create_invoice(base,app); st7,bp7,pay7,out7=precreate(inv7)
        if out7:
            mock_post(mock_base,"/__mock/scenario",{"out_trade_no":out7,"scenario":"wait"}); _,wait=http_json(base+"/api/alipay/payments/%s/query"%out7,"POST",{})
        else:
            wait = {"error": "missing out_trade_no", "precreate_status": st7, "precreate_body": bp7}
        inv7row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv7,)) or {}
        wait_result=wait.get("result",{}) if isinstance(wait,dict) else {}
        wait_payment=wait.get("payment",{}) if isinstance(wait,dict) else {}
        wait_reason=wait_result.get("reason")
        wait_status=wait_payment.get("status") or wait_payment.get("trade_status") or wait_result.get("trade_status")
        pending_wait = wait_reason in ("not_success","wait_buyer_pay","pending_buyer","query_not_success") or wait_status=="WAIT_BUYER_PAY"
        rubrics.append(rubric("integ.wait_not_paid", pending_wait and inv7row.get("payment_status")=="Unpaid", "wait=%s payment=%s invoice=%s"%(wait_result,wait_payment,inv7row), "integration"))
        rubrics.append(rubric("integ.query_compensation", isinstance(wait,dict) and wait.get("payment",{}).get("status") in ("WAIT_BUYER_PAY","TRADE_CLOSED") and inv7row.get("payment_status")=="Unpaid", "query result retained non-terminal paid state wait=%s invoice=%s"%(wait,inv7row), "integration"))
        # duplicate notify and terminal state
        _,_,inv8=create_invoice(base,app); st8,bp8,pay8,out8=precreate(inv8)
        if out8:
            _,n1=mock_post(mock_base,"/__mock/notify",{"out_trade_no":out8,"notify_url":base+"/alipay/notify/order-code","scenario":"success"}); _,n2=mock_post(mock_base,"/__mock/notify",{"out_trade_no":out8,"notify_url":base+"/alipay/notify/order-code","scenario":"success"})
        else:
            n1=n2={"error": "missing out_trade_no", "precreate_status": st8, "precreate_body": bp8}
        rows=db_scalar(app,"SELECT COUNT(*) AS c FROM alipay_payments WHERE invoice_id=?",(inv8,)); inv8row=db_row(app,"SELECT payment_status,amount_paid FROM invoices WHERE id=?",(inv8,)) or {}
        rubrics.append(rubric("integ.duplicate_idempotent", rows==1 and inv8row.get("payment_status")=="Paid", "notify_status=%s/%s rows=%s invoice=%s"%(n1.get("status") if isinstance(n1,dict) else None,n2.get("status") if isinstance(n2,dict) else None,rows,inv8row), "integration"))
        if out8:
            mock_post(mock_base,"/__mock/scenario",{"out_trade_no":out8,"scenario":"wait"}); http_json(base+"/api/alipay/payments/%s/query"%out8,"POST",{})
        inv8after=db_row(app,"SELECT payment_status,amount_paid FROM invoices WHERE id=?",(inv8,)) or {}
        rubrics.append(rubric("integ.terminal_state_protected", inv8after.get("payment_status")=="Paid" and float(inv8after.get("amount_paid",0))>0, "after old wait query invoice=%s"%inv8after, "integration"))
        grand_row = db_row(app,"SELECT grand_total FROM invoices WHERE id=?",(inv8,)) or {}
        rubrics.append(rubric("integ.amount_accounting_rule", abs(float(inv8after.get("amount_paid",0))-float(grand_row.get("grand_total", -1)))<0.01, "paid amount equals invoice total invoice=%s grand=%s"%(inv8after, grand_row), "integration"))
        rubrics.append(rubric("integ.qrcode_expire_or_unknown", pending_wait and inv7row.get("payment_status")=="Unpaid", "unknown/wait query path retained non-paid state: wait=%s invoice=%s" % (wait_result, inv7row), "integration"))
        append_refund_checks(rubrics, app, base, mock_base, lambda: make_paid_qrcode_invoice(base, app))
    finally:
        stop_proc(mock_proc)
    return rubrics


def safety_barcode(app, case_dir, output, case_name):
    rubrics=[]; mock_proc, mock_base=start_mock(case_dir, output)
    auth_code="286123456789012345"
    try:
        port,rc,log=start_app(app,case_dir,output,case_name,mock_base); ready=has_app_ready(log); build_ok=rc==0 and ready
        rubrics.append(rubric("integ.app_start", build_ok, "start.sh exit=%s ready=%s"%(rc,ready), "integration"))
        if not build_ok: return rubrics
        base="http://127.0.0.1:%s"%port
        st,body,inv=create_invoice(base,app); rubrics.append(rubric("integ.invoice_create", http_success(st) and bool(inv), "invoice status=%s id=%s"%(st,inv), "integration"))
        stp,pbody=http_json(base+"/api/invoices/%s/alipay/barcode/pay"%inv,"POST",{"auth_code":auth_code}); invrow=db_row(app,"SELECT payment_status,amount_paid,grand_total FROM invoices WHERE id=?",(inv,)) or {}; prow=db_row(app,"SELECT * FROM alipay_barcode_payments WHERE invoice_id=?",(inv,)) or {}
        rubrics.append(rubric("integ.barcode_pay_success", http_success(stp) and invrow.get("payment_status")=="Paid" and prow.get("trade_status")=="TRADE_SUCCESS", "pay=%s invoice=%s payment=%s"%(stp,invrow,{k:prow.get(k) for k in ["out_trade_no","trade_status","auth_code_last4"]}), "integration"))
        # duplicate
        before_dup_calls=len(mock_state(mock_base).get("trades",{})); std,dup=http_json(base+"/api/invoices/%s/alipay/barcode/pay"%inv,"POST",{"auth_code":"286999999999999999"}); rows=db_scalar(app,"SELECT COUNT(*) AS c FROM alipay_barcode_payments WHERE invoice_id=?",(inv,)); after_dup_calls=len(mock_state(mock_base).get("trades",{})); dup_invrow=db_row(app,"SELECT payment_status,amount_paid FROM invoices WHERE id=?",(inv,)) or {}
        duplicate_ok = rows==1 and dup_invrow.get("payment_status")=="Paid" and after_dup_calls==before_dup_calls and (isinstance(dup,dict) and dup.get("duplicate") is True or std in (400,409,422))
        rubrics.append(rubric("integ.duplicate_idempotent", duplicate_ok, "duplicate status=%s body=%s rows=%s gateway_trades_before_after=%s/%s invoice=%s"%(std,dup,rows,before_dup_calls,after_dup_calls,dup_invrow), "integration"))
        rubrics.append(rubric("integ.terminal_state_protected", invrow.get("payment_status")=="Paid" and rows==1, "paid invoice remained terminal after duplicate attempt", "integration"))
        # wrong amount
        st2,_,inv2=create_invoice(base,app); invoice2=db_row(app,"SELECT id,invoice_number,grand_total FROM invoices WHERE id=?",(inv2,)); out2=barcode_out_trade_no(invoice2); mock_post(mock_base,"/__mock/scenario",{"out_trade_no":out2,"scenario":"wrong_amount"}); _,wrong=http_json(base+"/api/invoices/%s/alipay/barcode/pay"%inv2,"POST",{"auth_code":auth_code}); inv2row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv2,)) or {}
        rubrics.append(rubric("integ.wrong_amount_reject", wrong.get("result",{}).get("reason")=="amount_mismatch" and inv2row.get("payment_status")=="Unpaid", "wrong_amount=%s invoice=%s"%(wrong.get("result"),inv2row), "integration"))
        # wait/f2f polling/query compensation
        _,_,inv3=create_invoice(base,app); invoice3=db_row(app,"SELECT id,invoice_number FROM invoices WHERE id=?",(inv3,)); out3=barcode_out_trade_no(invoice3); mock_post(mock_base,"/__mock/scenario",{"out_trade_no":out3,"scenario":"wait"}); _,wait=http_json(base+"/api/invoices/%s/alipay/barcode/pay"%inv3,"POST",{"auth_code":auth_code}); inv3row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv3,)) or {}
        wait_result=wait.get("result",{}) if isinstance(wait,dict) else {}
        wait_payment=wait.get("payment",{}) if isinstance(wait,dict) else {}
        wait_reason=wait_result.get("reason")
        wait_status = None
        if isinstance(wait, dict):
            wait_status = wait_payment.get("last_query_status") or wait_payment.get("trade_status") or wait.get("alipay",{}).get("trade_status")
        pending_wait = wait_reason in ("not_success","wait_buyer_pay","pending_buyer","query_not_success") or wait_status=="WAIT_BUYER_PAY" or (isinstance(wait,dict) and wait.get("alipay",{}).get("code")=="10003")
        rubrics.append(rubric("integ.wait_not_paid", pending_wait and inv3row.get("payment_status")=="Unpaid", "wait=%s payment=%s invoice=%s"%(wait_result,wait_payment,inv3row), "integration"))
        rubrics.append(rubric("integ.f2f_10003_polling", wait.get("payment",{}).get("last_query_status") in ("WAIT_BUYER_PAY","TRADE_CLOSED") or wait.get("alipay",{}).get("code")=="10003", "WAIT_BUYER_PAY captured for later query", "integration"))
        stq,qbody=http_json(base+"/api/invoices/%s/alipay/barcode/query"%inv3,"POST",{}); inv3after=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv3,)) or {}
        rubrics.append(rubric("integ.query_compensation", http_success(stq) and inv3after.get("payment_status")=="Unpaid", "query status=%s body=%s invoice=%s"%(stq,qbody,inv3after), "integration"))
        # fail
        _,_,inv4=create_invoice(base,app); invoice4=db_row(app,"SELECT id,invoice_number FROM invoices WHERE id=?",(inv4,)); out4=barcode_out_trade_no(invoice4); mock_post(mock_base,"/__mock/scenario",{"out_trade_no":out4,"scenario":"fail"}); stf,fail=http_json(base+"/api/invoices/%s/alipay/barcode/pay"%inv4,"POST",{"auth_code":auth_code}); inv4row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv4,)) or {}
        fail_reason = fail.get("result",{}).get("reason") if isinstance(fail,dict) else ""
        fail_closed = fail_reason in ("not_success","closed","trade_closed","failed","fail_closed") or stf in (400,409,422,502)
        rubrics.append(rubric("integ.fail_not_paid", fail_closed and inv4row.get("payment_status")=="Unpaid", "fail_status=%s fail=%s invoice=%s"%(stf,fail.get("result") if isinstance(fail,dict) else fail,inv4row), "integration"))
        # unsigned bad gateway response
        _,_,inv5=create_invoice(base,app); invoice5=db_row(app,"SELECT id,invoice_number FROM invoices WHERE id=?",(inv5,)); out5=barcode_out_trade_no(invoice5); mock_post(mock_base,"/__mock/scenario",{"out_trade_no":out5,"scenario":"unsigned"}); stu,uns=http_json(base+"/api/invoices/%s/alipay/barcode/pay"%inv5,"POST",{"auth_code":auth_code}); inv5row=db_row(app,"SELECT payment_status FROM invoices WHERE id=?",(inv5,)) or {}
        rubrics.append(rubric("integ.unsigned_reject", stu>=400 and inv5row.get("payment_status")=="Unpaid", "unsigned status=%s invoice=%s body=%s"%(stu,inv5row,uns), "integration"))
        # idempotency + amount/goods
        rubrics.append(rubric("integ.request_idempotency_key", bool(prow.get("out_trade_no")) and str(inv) in str(prow.get("out_trade_no")), "out_trade_no=%s invoice=%s"%(prow.get("out_trade_no"),inv), "integration"))
        amount_accounting_ok = (
            invrow.get("payment_status")=="Paid"
            and prow.get("trade_status")=="TRADE_SUCCESS"
            and abs(float(prow.get("total_amount",0))-float(invrow.get("grand_total",-1)))<0.01
            and abs(float(invrow.get("amount_paid",0))-float(invrow.get("grand_total",-1)))<0.01
        )
        rubrics.append(rubric("integ.amount_accounting_rule", amount_accounting_ok, "invoice=%s payment_status=%s payment_total=%s"%(invrow,prow.get("trade_status"),prow.get("total_amount")), "integration"))
        item_sum=db_scalar(app,"SELECT ROUND(SUM(total), 2) AS total FROM invoice_items WHERE invoice_id=?",(inv,)); rubrics.append(rubric("integ.f2f_goods_amount_match", abs(float(item_sum)-float(invrow.get("grand_total",0)))<0.01, "item_sum=%s grand_total=%s"%(item_sum,invrow.get("grand_total")), "integration"))
        rubrics.append(rubric("integ.f2f_unpaid_cancel", "alipay.trade.cancel" in read_all_code(app) or "alipay.trade.close" in read_all_code(app) or qbody.get("payment",{}).get("trade_status") in ("WAIT_BUYER_PAY","TRADE_CLOSED"), "unpaid/wait branch preserved; reverse action boundary inspectable", "integration"))
        # auth code plaintext scan
        db_strings=""
        for fname in ["data.db","data.db-wal"]:
            fp=Path(app)/fname
            if fp.exists():
                try: db_strings += subprocess.check_output(["strings", str(fp)], universal_newlines=True, stderr=subprocess.DEVNULL)
                except Exception: pass
        app_log=read_text(Path(app)/".case-runtime/app.log")
        rows=[]
        try:
            con=sqlite3.connect(str(Path(app)/"data.db")); rows=con.execute("SELECT auth_code_hash,auth_code_last4 FROM alipay_barcode_payments WHERE auth_code_last4=?",(auth_code[-4:],)).fetchall(); con.close()
        except Exception: rows=[]
        no_plain=bool(rows) and auth_code not in db_strings and auth_code not in app_log and all(r[0] != auth_code and r[1] == auth_code[-4:] for r in rows)
        rubrics.append(rubric("integ.auth_code_not_plaintext", no_plain, "rows=%s plaintext_hit=%s"%(len(rows), auth_code in db_strings or auth_code in app_log), "integration"))
        append_refund_checks(rubrics, app, base, mock_base, lambda: make_paid_barcode_invoice(base, app, auth_code))
    finally:
        stop_proc(mock_proc)
    return rubrics


def main():
    app=Path(sys.argv[1]); out=Path(sys.argv[2]); case_name=sys.argv[3]; output=Path(os.environ.get("OUTPUT_DIR","/output")); case_dir=Path(os.environ["CASE_DIR"])
    kind=case_kind()
    if kind.endswith("basic"):
        rubrics=basic_checks(app, case_dir, output, case_name)
    elif kind=="qrcode_safety":
        rubrics=safety_qrcode(app, case_dir, output, case_name)
    else:
        rubrics=safety_barcode(app, case_dir, output, case_name)
    write_phase(out, case_name, "integration", rubrics, {"kind": kind})

if __name__ == "__main__": main()
