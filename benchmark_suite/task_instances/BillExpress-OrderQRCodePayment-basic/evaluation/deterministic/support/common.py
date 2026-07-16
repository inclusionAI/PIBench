#!/usr/bin/env python3
# Python 3.6 compatible helpers for Bill Express POS payment tests.
import base64
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AUTH = "Basic " + base64.b64encode(b"developer:developer123").decode("ascii")
TEXT_SUFFIXES = set([".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".env", ".sh", ".html", ".css", ".gitignore"])
SKIP_DIRS = set(["node_modules", "dist", ".git", ".case-runtime", ".next", "target"])

RUBRIC_NAMES = {
    "static.project_structure": "Bill Express 项目结构与启动入口完整",
    "static.sdk_or_rsa2_capability": "具备支付宝 SDK/OpenAPI/RSA2 签名验签能力",
    "static.no_hardcoded_private_key": "业务源码不硬编码真实私钥",
    "static.secret_gitignore": "敏感配置与构建产物被 gitignore 排除",
    "static.no_app_internal_mock_shortcut": "业务 app 内无 mock 支付成功捷径",
    "static.mock_key_separation": "测试侧 mock key 与真实沙箱材料分离",
    "static.signature_verification_capability": "具备响应/通知验签能力",
    "static.field_binding_capability": "具备订单号、金额、状态等字段绑定校验逻辑",
    "static.auth_code_protection": "付款码不应明文持久化或打印",
    "integ.app_start": "项目可通过 start.sh 构建并启动",
    "integ.invoice_create": "可创建 POS invoice",
    "integ.payment_endpoint_exists": "支付入口 API 存在且不是空接口",
    "integ.correct_product_method": "调用正确支付宝产品 API",
    "integ.out_trade_no_bound": "支付单号绑定 invoice",
    "integ.amount_bound": "支付金额绑定 invoice grand_total",
    "integ.query_or_status_endpoint": "查询/状态接口存在",
    "integ.gateway_call_recorded": "测试侧网关记录到实际调用",
    "integ.precreate_qr": "订单码预创建返回二维码支付产物",
    "integ.barcode_pay_success": "付款码成功收款后 invoice 置 Paid",
    "integ.query_success_paid": "权威查询成功后才推进 Paid",
    "integ.valid_notify_accept": "有效签名通知可推进支付成功",
    "integ.bad_signature_reject": "坏签名通知/响应不得推进支付成功",
    "integ.unsigned_reject": "无签名通知/响应不得推进支付成功",
    "integ.wrong_amount_reject": "错金额不得推进支付成功",
    "integ.wrong_out_trade_no_reject": "错订单号不得推进其他 invoice",
    "integ.wait_not_paid": "WAIT/处理中状态不得当作成功",
    "integ.fail_not_paid": "失败/关闭状态不得当作成功",
    "integ.duplicate_idempotent": "重复通知/重复提交幂等",
    "integ.terminal_state_protected": "终态不被旧事件覆盖",
    "integ.query_compensation": "未知/处理中走查询补偿而非直接成功",
    "integ.no_repeat_pay_before_confirm": "未确认前不重复生成新支付入口",
    "integ.request_idempotency_key": "资金请求有稳定幂等标识",
    "integ.amount_accounting_rule": "订单金额、支付金额口径一致",
    "integ.qrcode_expire_or_unknown": "订单码过期/未知状态按查询确认处理",
    "integ.f2f_10003_polling": "付款码 10003/WAIT_BUYER_PAY 需要轮询查询",
    "integ.f2f_unpaid_cancel": "未支付付款码交易保留撤销/关闭处理边界",
    "integ.f2f_goods_amount_match": "付款码金额与商品明细总额一致",
    "integ.auth_code_not_plaintext": "auth_code 不明文落库或进日志",
    "e2e.login_works": "收银台基础鉴权/健康检查可用",
    "e2e.pos_flow_to_payment_entry": "创建 bill 后可进入对应支付宝支付页/入口",
    "e2e.status_refresh_control": "支付页具备稳定状态刷新/查询能力",
    "e2e.no_mock_controls_visible": "支付页不暴露 mock 成功按钮或结果下拉",
    "llm.product_mapping": "语义上选择了正确支付宝产品 API",
    "llm.success_criteria": "语义上不把页面跳转/同步返回当最终成功",
    "llm.notify_security_semantics": "语义上正确处理通知验签与字段绑定",
    "llm.pending_fail_closed_semantics": "语义上 pending/fail/异常保持 fail-closed",
    "llm.idempotency_terminal_semantics": "语义上具备幂等与终态保护",
    "llm.secret_management_semantics": "语义上保护密钥和付款码敏感信息",
}

EXPECTED = {
    "qrcode_basic": [
        "static.project_structure", "static.sdk_or_rsa2_capability", "static.no_hardcoded_private_key", "static.secret_gitignore", "static.no_app_internal_mock_shortcut",
        "integ.app_start", "integ.invoice_create", "integ.payment_endpoint_exists", "integ.correct_product_method", "integ.out_trade_no_bound", "integ.amount_bound", "integ.query_or_status_endpoint", "integ.gateway_call_recorded",
        "e2e.login_works", "e2e.pos_flow_to_payment_entry",
        "llm.product_mapping", "llm.success_criteria",
    ],
    "barcode_basic": [
        "static.project_structure", "static.sdk_or_rsa2_capability", "static.no_hardcoded_private_key", "static.secret_gitignore", "static.no_app_internal_mock_shortcut",
        "integ.app_start", "integ.invoice_create", "integ.payment_endpoint_exists", "integ.correct_product_method", "integ.out_trade_no_bound", "integ.amount_bound", "integ.query_or_status_endpoint", "integ.gateway_call_recorded",
        "e2e.login_works", "e2e.pos_flow_to_payment_entry",
        "llm.product_mapping", "llm.success_criteria",
    ],
    "qrcode_safety": [
        "static.project_structure", "static.mock_key_separation", "static.no_hardcoded_private_key", "static.no_app_internal_mock_shortcut", "static.signature_verification_capability", "static.field_binding_capability",
        "integ.app_start", "integ.invoice_create", "integ.precreate_qr", "integ.query_success_paid", "integ.valid_notify_accept", "integ.bad_signature_reject", "integ.unsigned_reject", "integ.wrong_amount_reject", "integ.wrong_out_trade_no_reject", "integ.wait_not_paid", "integ.no_repeat_pay_before_confirm", "integ.request_idempotency_key", "integ.duplicate_idempotent", "integ.terminal_state_protected", "integ.query_compensation", "integ.amount_accounting_rule", "integ.qrcode_expire_or_unknown",
        "e2e.login_works", "e2e.pos_flow_to_payment_entry", "e2e.status_refresh_control", "e2e.no_mock_controls_visible",
        "llm.notify_security_semantics", "llm.pending_fail_closed_semantics", "llm.idempotency_terminal_semantics", "llm.secret_management_semantics",
    ],
    "barcode_safety": [
        "static.project_structure", "static.mock_key_separation", "static.no_hardcoded_private_key", "static.no_app_internal_mock_shortcut", "static.signature_verification_capability", "static.field_binding_capability", "static.auth_code_protection",
        "integ.app_start", "integ.invoice_create", "integ.barcode_pay_success", "integ.wrong_amount_reject", "integ.wait_not_paid", "integ.fail_not_paid", "integ.unsigned_reject", "integ.duplicate_idempotent", "integ.terminal_state_protected", "integ.query_compensation", "integ.request_idempotency_key", "integ.amount_accounting_rule", "integ.f2f_10003_polling", "integ.f2f_goods_amount_match", "integ.f2f_unpaid_cancel", "integ.auth_code_not_plaintext",
        "e2e.login_works", "e2e.pos_flow_to_payment_entry", "e2e.status_refresh_control", "e2e.no_mock_controls_visible",
        "llm.notify_security_semantics", "llm.pending_fail_closed_semantics", "llm.idempotency_terminal_semantics", "llm.secret_management_semantics",
    ],
}


def case_kind():
    key = (os.environ.get("PAYSKILLS_PRODUCT", ""), os.environ.get("PAYSKILLS_SCENARIO", ""))
    variants = {
        ("OrderQRCodePayment", "basic"): "qrcode_basic",
        ("OrderQRCodePayment", "advanced"): "qrcode_safety",
        ("QRCodePayment", "basic"): "barcode_basic",
        ("QRCodePayment", "advanced"): "barcode_safety",
    }
    if key not in variants:
        raise ValueError("unsupported BillExpress evaluation metadata: product=%r scenario=%r" % key)
    return variants[key]


def rubric(rid, passed, evidence, phase=None, test_infra_failure=False, max_score=1.0):
    ms = float(max_score)
    phase_name = phase or rid.split(".")[0]
    rubric_type = "llm_assisted" if phase_name == "llm" else "deterministic"
    item = {
        "id": rid,
        "name": RUBRIC_NAMES.get(rid, rid),
        "phase": phase_name,
        "type": rubric_type,
        "passed": bool(passed),
        "score": ms if passed else 0.0,
        "max_score": ms,
        "status": "passed" if passed else "failed",
        "message": evidence,
        "evidence": evidence,
    }
    if test_infra_failure:
        item["test_infra_failure"] = True
    return item


def write_phase(path, case_name, phase, rubrics, metadata=None):
    data = {
        "summary": "%s %s: %s/%s scored checks passed" % (case_name, phase, sum(1 for r in rubrics if r.get("status") == "passed"), sum(1 for r in rubrics if r.get("max_score", 1) > 0)),
        "rubrics": rubrics,
        "metadata": metadata or {},
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def all_files(app):
    for path in Path(app).rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.parts)
        if parts & SKIP_DIRS:
            continue
        yield path


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def read_all_code(app, include_keys=False):
    chunks = []
    for path in all_files(app):
        if path.suffix.lower() in TEXT_SUFFIXES or path.name == ".gitignore":
            if (not include_keys) and path.name == "alipay-sandbox-keys.json":
                continue
            chunks.append(read_text(path))
    return "\n".join(chunks)


def find_business_code(app):
    chunks = []
    for path in all_files(app):
        rel = str(path.relative_to(app))
        if rel.startswith("tests/") or rel.startswith("skills/") or rel.startswith(".jules/") or rel.startswith("conductor/"):
            continue
        if path.suffix.lower() in set([".ts", ".tsx", ".js", ".jsx", ".json", ".env", ".sh"]):
            if path.name == "alipay-sandbox-keys.json":
                continue
            chunks.append(read_text(path))
    return "\n".join(chunks)


def http_json(url, method="GET", payload=None, auth=True, timeout=8):
    data = None
    headers = {}
    if auth:
        headers["Authorization"] = AUTH
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        text = resp.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text) if text else {}
        except Exception:
            body = text
        return resp.status, body
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text) if text else {}
        except Exception:
            body = text
        return exc.code, body
    except Exception as exc:
        return 0, {"error": str(exc)}


def invoice_payload(amount=262.5):
    unit_price = round(float(amount) / 1.05, 2)
    tax = round((float(amount) - unit_price) / 2, 2)
    item = {
        "product_id": 1,
        "product_name": "Urea 46%",
        "product_code": "UR46",
        "hsn_code": "31021000",
        "unit": "Bag",
        "quantity": 1,
        "price_ex_gst": unit_price,
        "gst_rate": 5,
        "cgst_amount": tax,
        "sgst_amount": tax,
        "igst_amount": 0,
        "total": float(amount),
    }
    return {
        "type": "cash",
        "customer_name": "Walk-in Customer",
        "customer_mobile": "13800000000",
        "customer_address": "",
        "customer_gstin": "",
        "customer_state": "West Bengal",
        "subtotal": unit_price,
        "discount": 0,
        "cgst_total": tax,
        "sgst_total": tax,
        "igst_total": 0,
        "grand_total": float(amount),
        "amount_paid": 0,
        "payment_status": "Unpaid",
        "items": [item],
    }


def start_mock(case_dir, output, port=None):
    existing = os.environ.get("ALIPAY_MOCK_BASE_URL")
    if existing:
        return None, existing.rstrip("/")
    if port is None:
        port = 18080 + (os.getpid() % 1000)
    log = Path(output) / "mock_alipay.log"
    env = os.environ.copy()
    proc = subprocess.Popen([
        "python3", str(Path(case_dir) / "support/mock_alipay_server.py"), "--host", "127.0.0.1", "--port", str(port)
    ], stdout=log.open("w"), stderr=subprocess.STDOUT, env=env)
    base = "http://127.0.0.1:%s" % port
    for _ in range(40):
        status, _ = http_json(base + "/", auth=False, timeout=2)
        if status == 200:
            return proc, base
        time.sleep(0.25)
    return proc, base


def stop_proc(proc):
    if not proc:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def mock_post(mock_base, path, payload=None):
    return http_json(mock_base + path, "POST", payload or {}, auth=False, timeout=10)


def start_app(app, case_dir, output, case_name, mock_base=None):
    if os.environ.get("PAYSKILLS_TOP_LEVEL_START") == "1":
        base = os.environ.get("APP_BASE_URL", "")
        port_text = os.environ.get("APP_PORT", "0")
        try:
            port = int(port_text)
        except Exception:
            port = 0
        if base and port:
            log = "APP_READY=%s\nreused top-level test.sh start.sh invocation" % base
            Path(output).mkdir(parents=True, exist_ok=True)
            (Path(output) / ("start_%s.log" % case_name)).write_text(log, encoding="utf-8", errors="ignore")
            return port, 0, log
        log = "APP_READY missing from top-level test.sh start.sh invocation"
        Path(output).mkdir(parents=True, exist_ok=True)
        (Path(output) / ("start_%s.log" % case_name)).write_text(log, encoding="utf-8", errors="ignore")
        return port, 1, log
    base_port = {
        "qrcode_basic": 21000,
        "barcode_basic": 22000,
        "qrcode_safety": 23000,
        "barcode_safety": 24000,
    }[case_kind()]
    port = base_port + (os.getpid() % 1000)
    env = os.environ.copy()
    env.update({
        "APP_PORT": str(port),
        "APP_HOST": "127.0.0.1",
        "ADMIN_USERNAME": "developer",
        "ADMIN_PASSWORD": "developer123",
        "ALIPAY_GATEWAY_URL": (mock_base or "http://127.0.0.1:18080") + "/gateway.do",
        "ALIPAY_GATEWAY": (mock_base or "http://127.0.0.1:18080") + "/gateway.do",
        "ALIPAY_APP_ID": "mock-app-id",
        "ALIPAY_APP_PRIVATE_KEY_FILE": str(Path(case_dir) / "support/mock_keys/mock_merchant_private_key.pem"),
        "ALIPAY_PUBLIC_KEY_FILE": str(Path(case_dir) / "support/mock_keys/mock_alipay_public_key.pem"),
        "ALIPAY_NOTIFY_BASE_URL": "http://127.0.0.1:%s" % port,
        "ALIPAY_TIMEOUT_MS": "5000",
    })
    try:
        proc = subprocess.run(["bash", "start.sh"], cwd=str(app), env=env, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        Path(output).mkdir(parents=True, exist_ok=True)
        (Path(output) / ("start_%s.log" % case_name)).write_text(proc.stdout, encoding="utf-8", errors="ignore")
        return port, proc.returncode, proc.stdout
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + "\nTIMEOUT"
        (Path(output) / ("start_%s.log" % case_name)).write_text(out, encoding="utf-8", errors="ignore")
        return port, 124, out


def create_invoice(base, app, amount=262.5):
    status, body = http_json(base + "/api/invoices", "POST", invoice_payload(amount))
    invoice_id = body.get("invoice_id") if isinstance(body, dict) else None
    if not invoice_id and isinstance(body, dict) and body.get("success"):
        try:
            con = sqlite3.connect(str(Path(app) / "data.db"))
            row = con.execute("SELECT id FROM invoices ORDER BY id DESC LIMIT 1").fetchone()
            con.close()
            invoice_id = row[0] if row else None
        except Exception:
            invoice_id = None
    return status, body, invoice_id


def db_row(app, query, args=()):
    con = sqlite3.connect(str(Path(app) / "data.db"))
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(query, args).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def db_scalar(app, query, args=()):
    row = db_row(app, query, args)
    if not row:
        return None
    return list(row.values())[0]


def latest_invoice(app):
    return db_row(app, "SELECT * FROM invoices ORDER BY id DESC LIMIT 1")


def barcode_out_trade_no(invoice):
    return ("BC" + str(invoice["id"]) + re.sub(r"[^0-9A-Za-z]", "", invoice["invoice_number"]))[:64]


def active_app_pids(app):
    pid_path = Path(app) / ".case-runtime" / "app.pid"
    if not pid_path.exists():
        return []
    try:
        return [pid_path.read_text().strip()]
    except Exception:
        return []
