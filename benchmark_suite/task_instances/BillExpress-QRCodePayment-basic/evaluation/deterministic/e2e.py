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


def response_out_trade_no(body):
    if not isinstance(body, dict):
        return None
    nested = body.get("payment")
    for source in (nested, body):
        if not isinstance(source, dict):
            continue
        for key in ("out_trade_no", "outTradeNo"):
            value = source.get(key)
            if value:
                return value
    return None


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
                payment=pbody.get("payment") if isinstance(pbody,dict) else {}; out_no=response_out_trade_no(pbody)
                page_status,_=http_json(base+"/api/alipay/payments/%s"%out_no) if out_no else (0,{})
                refresh_status,_=http_json(base+"/api/alipay/payments/%s/query"%out_no,"POST",{}) if out_no and is_safety else (page_status,{})
            else:
                pst,pbody=http_json(base+"/api/invoices/%s/alipay/barcode/pay"%inv,"POST",{"auth_code":"286123456789012345"}) if inv else (0,{})
                out_no=response_out_trade_no(pbody)
                page_status,_=http_json(base+"/api/invoices/%s/alipay/barcode/payment"%inv) if inv else (0,{})
                refresh_status,_=http_json(base+"/api/invoices/%s/alipay/barcode/query"%inv,"POST",{}) if inv and is_safety else (page_status,{})
            _, mock = http_json(mock_base + "/__mock/state", auth=False)
            mock_trade = mock.get("trades", {}).get(out_no, {}) if isinstance(mock, dict) and out_no else {}
            mock_status = str(mock_trade.get("trade_status", "")) if isinstance(mock_trade, dict) else ""
            mock_ok = bool(mock_trade) and (is_qrcode or mock_status in ("TRADE_SUCCESS", "TRADE_FINISHED"))
            rubrics.append(rubric("e2e.pos_flow_to_payment_entry", http_success(pst) and http_success(page_status) and bool(out_no) and mock_ok, "invoice=%s payment_status=%s page/status=%s out_trade_no=%s mock_trade=%s"%(inv,pst,page_status,out_no,mock_trade), "e2e"))
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
