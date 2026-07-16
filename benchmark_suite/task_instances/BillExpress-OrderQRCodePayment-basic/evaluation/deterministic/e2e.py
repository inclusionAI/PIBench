#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from support.common import *


def http_success(status):
    try:
        return 200 <= int(status) < 400
    except Exception:
        return False


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
            value = direct_value(payment, *keys)
            if value is None:
                value = direct_value(body, *keys)
            if value is not None:
                payment[canonical] = value
    return payment


def main():
    app=Path(sys.argv[1]); out=Path(sys.argv[2]); case_name=sys.argv[3]; output=Path(os.environ.get("OUTPUT_DIR","/output")); case_dir=Path(os.environ["CASE_DIR"])
    kind=case_kind(); is_qrcode=kind.startswith("qrcode_"); is_safety=kind.endswith("_safety")
    rubrics=[]; mock_proc, mock_base=start_mock(case_dir, output)
    try:
        port,rc,log=start_app(app,case_dir,output,case_name,mock_base); base="http://127.0.0.1:%s"%port
        st,health=http_json(base+"/api/health") if rc==0 and "APP_READY" in log else (0,{})
        rubrics.append(rubric("e2e.login_works", st==200 and isinstance(health,dict) and health.get("status")=="ok", "health status=%s body=%s"%(st,health), "e2e"))
        if st==200:
            _,_,inv=create_invoice(base,app)
            if is_qrcode:
                pst,pbody=http_json(base+"/api/invoices/%s/alipay/precreate"%inv,"POST",{}) if inv else (0,{})
                payment=normalize_payment_response(pbody); out_no=payment.get("out_trade_no")
                page_status,_=http_json(base+"/api/alipay/payments/%s"%out_no) if out_no else (0,{})
                refresh_status,_=http_json(base+"/api/alipay/payments/%s/query"%out_no,"POST",{}) if out_no and is_safety else (page_status,{})
            else:
                pst,pbody=http_json(base+"/api/invoices/%s/alipay/barcode/pay"%inv,"POST",{"auth_code":"286123456789012345"}) if inv else (0,{})
                page_status,_=http_json(base+"/api/invoices/%s/alipay/barcode/payment"%inv) if inv else (0,{})
                refresh_status,_=http_json(base+"/api/invoices/%s/alipay/barcode/query"%inv,"POST",{}) if inv and is_safety else (page_status,{})
            rubrics.append(rubric("e2e.pos_flow_to_payment_entry", http_success(pst) and http_success(page_status), "invoice=%s payment_status=%s page/status=%s"%(inv,pst,page_status), "e2e"))
            if is_safety:
                rubrics.append(rubric("e2e.status_refresh_control", http_success(refresh_status), "refresh/query status=%s"%refresh_status, "e2e"))
                page_code=read_all_code(app)
                bad=any(m in page_code for m in ["Mock Alipay Pay Success", "mock_result", "mock-alipay://", "/api/mock-alipay"])
                rubrics.append(rubric("e2e.no_mock_controls_visible", not bad, "no visible mock control markers in app source", "e2e"))
        else:
            rubrics.append(rubric("e2e.pos_flow_to_payment_entry", False, "app health failed", "e2e"))
            if is_safety:
                rubrics.append(rubric("e2e.status_refresh_control", False, "app health failed", "e2e"))
                rubrics.append(rubric("e2e.no_mock_controls_visible", False, "app health failed", "e2e"))
    finally:
        stop_proc(mock_proc)
    write_phase(out, case_name, "e2e", rubrics, {"kind": kind})

if __name__ == "__main__": main()
