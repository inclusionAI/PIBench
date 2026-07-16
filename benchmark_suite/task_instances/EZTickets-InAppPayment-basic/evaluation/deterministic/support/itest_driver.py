#!/usr/bin/env python3
"""Integration driver for EZ Tickets App Pay.

Default mode runs I1-I4 against the real Alipay sandbox. The mock-success mode
is run after the backend is restarted against a local signed mock gateway and
appends I5-I7 to the same integration result file.
"""
import argparse
import json
import string
import subprocess
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus

BASE = "http://127.0.0.1:3331/api/v1"
CREATE_ENDPOINTS = (
    "/payments/alipay/create",
    "/payments/alipay/app",
    "/payments/alipay/app-pay",
    "/payments/alipay/order",
)
SUCCESS_HTTP = (200, 201)
ORDER_STR_KEYS = ("order_str", "orderStr", "order_string", "orderString", "order_info", "orderInfo")
ALIPAY_BUSINESS_CODES = {"10000", "40001", "40002", "40004", "40006", "20000"}


def mysql(sql, db_port, db="ez_tickets"):
    cmd = ["mysql", "--no-defaults", "-h", "127.0.0.1", "-P", str(db_port),
           "-u", "root", "-N", "-B", "-e", sql, db]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"mysql query failed: {out.stderr.strip()}")
    return [line.split("\t") for line in out.stdout.strip().splitlines() if line]


def http_post(path, payload, token):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode() or "{}")
        except Exception:
            body = {"raw": "unparsable body"}
        return exc.code, body
    except Exception as exc:  # noqa: BLE001
        return 0, {"transport_error": str(exc)}


def find_key(obj, key):
    """Recursively find the first value for `key` at any nesting level."""
    if isinstance(obj, dict):
        if key in obj and obj[key] is not None:
            return obj[key]
        for v in obj.values():
            found = find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_key(v, key)
            if found is not None:
                return found
    return None


def find_any_key(obj, keys):
    for key in keys:
        found = find_key(obj, key)
        if found is not None:
            return found
    return None


def extract_order_str(body):
    value = find_any_key(body, ORDER_STR_KEYS)
    return str(value) if value is not None else ""


def create_payload_variants(booking_id, show_id, extra=None):
    extra = dict(extra or {})
    variants = [
        {"booking_id": booking_id, "show_id": show_id},
        {"booking_id": booking_id},
        {"bookingId": booking_id, "show_id": show_id},
        {"bookingId": booking_id},
        {"bookings": [booking_id], "show_id": show_id},
        {"bookings": [booking_id]},
    ]
    return [{**payload, **extra} for payload in variants]


def create_alipay_order(args, booking_id, show_id, extra=None):
    attempts = []
    best = None
    for path in CREATE_ENDPOINTS:
        for payload in create_payload_variants(booking_id, show_id, extra):
            status, body = http_post(path, payload, args.token)
            out_trade_no = find_key(body, "out_trade_no")
            order_str = extract_order_str(body)
            attempt = {
                "path": path,
                "payload": payload,
                "status": status,
                "has_out_trade_no": bool(out_trade_no),
                "has_order_str": bool(order_str),
            }
            attempts.append(attempt)
            current = {
                "path": path,
                "payload": payload,
                "status": status,
                "body": body,
                "out_trade_no": out_trade_no,
                "order_str": order_str,
            }
            if status in SUCCESS_HTTP and out_trade_no and order_str:
                current["attempts"] = attempts
                return current
            if best is None or (status in SUCCESS_HTTP and best["status"] not in SUCCESS_HTTP):
                best = current
    if best is None:
        best = {"path": None, "payload": None, "status": 0, "body": {},
                "out_trade_no": None, "order_str": ""}
    best["attempts"] = attempts
    return best


def confirm_payload_variants(out_trade_no, booking_ids=None):
    variants = [{"out_trade_no": out_trade_no}]
    if booking_ids:
        booking_id = booking_ids[0] if isinstance(booking_ids, list) else booking_ids
        variants.extend([
            {"out_trade_no": out_trade_no, "booking_id": booking_id},
            {"out_trade_no": out_trade_no, "bookingId": booking_id},
            {"out_trade_no": out_trade_no, "bookings": [booking_id]},
        ])
    return variants


def alipay_result_fields(body):
    code = str(find_key(body, "code") or "")
    trade_status = str(find_any_key(body, ("trade_status", "tradeStatus")) or "")
    sub_code = str(find_key(body, "sub_code") or "")
    sub_msg = str(find_key(body, "sub_msg") or "")
    return {
        "code": code,
        "trade_status": trade_status,
        "sub_code": sub_code,
        "sub_msg": sub_msg,
        "has_result": bool(trade_status or sub_code or sub_msg or code in ALIPAY_BUSINESS_CODES),
    }


def confirm_alipay_payment(args, out_trade_no, booking_ids=None):
    attempts = []
    best = None
    for payload in confirm_payload_variants(out_trade_no, booking_ids):
        status, body = http_post("/payments/alipay/confirm", payload, args.token)
        fields = alipay_result_fields(body)
        attempt = {
            "payload": payload,
            "status": status,
            "has_alipay_result": fields["has_result"],
            "trade_status": fields["trade_status"],
            "code": fields["code"],
            "sub_code": fields["sub_code"],
        }
        attempts.append(attempt)
        current = {"status": status, "body": body, "payload": payload, "fields": fields}
        if status in SUCCESS_HTTP and fields["has_result"]:
            current["attempts"] = attempts
            return current
        if best is None or (status in SUCCESS_HTTP and best["status"] not in SUCCESS_HTTP):
            best = current
    if best is None:
        best = {"status": 0, "body": {}, "payload": None, "fields": alipay_result_fields({})}
    best["attempts"] = attempts
    return best


def parse_order_str(order_str):
    parsed = {k: v[-1] for k, v in parse_qs(order_str, keep_blank_values=True).items()}
    biz_raw = parsed.get("biz_content") or parsed.get("bizContent") or ""
    try:
        biz = json.loads(unquote_plus(biz_raw))
    except Exception:
        try:
            biz = json.loads(biz_raw)
        except Exception:
            biz = {}
    return parsed, biz


def to_decimal(value):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def amount_equal(left, right):
    left_d = to_decimal(left)
    right_d = to_decimal(right)
    return left_d is not None and right_d is not None and left_d == right_d


def pick_show_and_seat(db_port):
    shows = mysql(
        "SELECT s.show_id, t.theater_id, t.num_of_rows, t.seats_per_row "
        "FROM shows s JOIN theaters t ON s.theater_id = t.theater_id "
        "ORDER BY s.show_id LIMIT 10", db_port)
    for show_id, theater_id, num_rows, seats_per_row in shows:
        booked = {(r[0], r[1]) for r in mysql(
            f"SELECT seat_row, seat_number FROM bookings WHERE show_id={int(show_id)}", db_port)}
        bad = {(r[0], r[1]) for r in mysql(
            "SELECT seat_row, seat_number FROM theater_seats "
            f"WHERE theater_id={int(theater_id)} AND seat_type IN ('missing','blocked')", db_port)}
        for ri in range(int(num_rows)):
            row = string.ascii_uppercase[ri]
            for num in range(1, int(seats_per_row) + 1):
                if (row, str(num)) not in booked and (row, str(num)) not in bad:
                    return int(show_id), f"{row}-{num}"
    raise RuntimeError("no free seat found in seeded shows")


def make_out(rid, r):
    return {"id": rid, "name": r["name"], "dimension": "functionality",
            "type": "hard", "passed": bool(r["passed"]),
            "score": 1 if r["passed"] else 0, "max_score": 1,
            "message": r.get("message", ""), "evidence": r.get("evidence", [])}


def write_rubrics(checks_file, rubrics, merge=False):
    path = Path(checks_file)
    existing = []
    if merge and path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8")).get("rubrics", [])
        except Exception:
            existing = []
    by_id = {r.get("id"): r for r in existing if r.get("id")}
    for rid, r in rubrics.items():
        by_id[rid] = make_out(rid, r)
    ordered_ids = ["I1", "I2", "I3", "I4", "I5", "I6", "I7"]
    out = [by_id[rid] for rid in ordered_ids if rid in by_id]
    path.write_text(json.dumps({"rubrics": out, "infra_failure": False}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[itest] {sum(r['passed'] for r in out)}/{len(out)} passed")


def save(output_dir, name, data):
    path = Path(output_dir) / name
    with path.open("w", encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)


def create_reserved_booking(args, label, price=800):
    show_id, seat = pick_show_and_seat(args.db_port)
    status, body = http_post("/bookings", {
        "user_id": 2, "show_id": show_id, "seat": seat, "price": price,
        "booking_status": "reserved",
        "booking_datetime": "2026-06-12 10:00:00"}, args.token)
    save(args.output_dir, f"{label}_booking_create_response.json", {"status": status, "body": body})
    booking_id = find_key(body, "booking_id")
    if (status not in (200, 201)) or booking_id is None:
        raise RuntimeError(f"{label}: create booking failed HTTP {status}")
    return int(booking_id), int(show_id), seat


def run_real_sandbox(args):
    rubrics = {
        "I1": {"name": "后端基础测试（npm test）",
               "passed": args.i1_pass == "1",
               "message": "" if args.i1_pass == "1" else "npm test 未通过，见 npm_test.log",
               "evidence": ["npm_test.log"]},
        "I2": {"name": "创建合法 App 支付请求", "passed": False, "message": "",
               "evidence": ["alipay_create_response.json", "backend.log"]},
        "I3": {"name": "真实沙箱查询响应", "passed": False, "message": "",
               "evidence": ["alipay_confirm_response.json", "backend.log"]},
        "I4": {"name": "支付宝未成功时不确认订单", "passed": False, "message": "",
               "evidence": ["db_state_after_confirm.txt", "backend.log"]},
    }

    out_trade_no = None
    trade_status = ""
    alipay_code = sub_code = sub_msg = ""
    has_alipay_result = False
    try:
        max_payment_before = int((mysql(
            "SELECT COALESCE(MAX(payment_id),0) FROM payments", args.db_port))[0][0])
        booking_id, show_id, seat = create_reserved_booking(args, "real", price=800)
        print(f"[itest] real sandbox booking_id={booking_id} show_id={show_id} seat={seat}")

        create_result = create_alipay_order(args, booking_id, show_id)
        status, body = create_result["status"], create_result["body"]
        save(args.output_dir, "alipay_create_response.json", create_result)
        out_trade_no = create_result.get("out_trade_no")
        order_str = create_result.get("order_str") or ""
        order_params, order_biz = parse_order_str(order_str or "")
        biz_out_trade_no = order_biz.get("out_trade_no") or order_biz.get("outTradeNo")
        product_code = order_biz.get("product_code") or order_biz.get("productCode")
        order_checks = {
            "method_app_pay": order_params.get("method") == "alipay.trade.app.pay",
            "rsa2": str(order_params.get("sign_type") or "").upper() == "RSA2",
            "has_sign": bool(order_params.get("sign")),
            "out_trade_no_matches": bool(out_trade_no) and biz_out_trade_no == out_trade_no,
            "product_code": product_code == "QUICK_MSECURITY_PAY",
        }
        save(args.output_dir, "alipay_order_str_check.json", {
            "order_params": {k: order_params.get(k) for k in
                             ("app_id", "method", "charset", "sign_type", "timestamp", "version")},
            "biz_content": order_biz,
            "checks": order_checks,
            "selected_create_path": create_result.get("path"),
            "selected_create_payload": create_result.get("payload"),
        })
        if status in SUCCESS_HTTP and out_trade_no and order_str and all(order_checks.values()):
            rubrics["I2"]["passed"] = True
            print(f"[itest] I2 PASS path={create_result.get('path')} out_trade_no={out_trade_no}")
        else:
            failed = [k for k, ok in order_checks.items() if not ok]
            rubrics["I2"]["message"] = (
                f"创建支付宝 App 支付参数接口探测返回 HTTP {status}；"
                f"selected_path={create_result.get('path') or '缺失'}；"
                f"out_trade_no={'有' if out_trade_no else '缺失'}，"
                f"order_str={'有' if order_str else '缺失'}，"
                f"App 支付参数检查失败项={failed or '无'}。"
                "见 alipay_create_response.json 和 alipay_order_str_check.json")
            print(f"[itest] I2 FAIL: {rubrics['I2']['message']}")

        if out_trade_no:
            confirm_result = confirm_alipay_payment(args, out_trade_no, [booking_id])
            status, body = confirm_result["status"], confirm_result["body"]
            save(args.output_dir, "alipay_confirm_response.json", confirm_result)
            fields = confirm_result["fields"]
            trade_status = fields["trade_status"]
            alipay_code = fields["code"]
            sub_code = fields["sub_code"]
            sub_msg = fields["sub_msg"]
            has_alipay_result = fields["has_result"]
            if status in SUCCESS_HTTP and has_alipay_result:
                rubrics["I3"]["passed"] = True
                print(f"[itest] I3 PASS sandbox result trade_status={trade_status} code={alipay_code} sub_code={sub_code}")
            else:
                rubrics["I3"]["message"] = (
                    f"POST /payments/alipay/confirm 返回 HTTP {status}，"
                    f"trade_status={trade_status or '缺失'}，"
                    f"code={alipay_code or '缺失'}，sub_code={sub_code or '缺失'}。"
                    "见 alipay_confirm_response.json（是否真实请求沙箱并透出支付宝业务响应？）")
                print(f"[itest] I3 FAIL: {rubrics['I3']['message']}")
        else:
            rubrics["I3"]["message"] = "I2 未返回 out_trade_no，无法测试确认接口"

        rows = mysql(f"SELECT booking_status FROM bookings WHERE booking_id={booking_id}", args.db_port)
        booking_status = rows[0][0] if rows else "MISSING"
        pay_rows = mysql(
            "SELECT payment_id, amount, payment_method, user_id, show_id FROM payments "
            f"WHERE payment_id > {max_payment_before} AND user_id=2 AND show_id={show_id}",
            args.db_port)
        alipay_rows = [row for row in pay_rows if len(row) >= 3 and str(row[2]).lower() == "alipay"]
        save(args.output_dir, "db_state_after_confirm.txt",
             f"booking_id={booking_id} booking_status={booking_status}\n"
             f"new payments rows: {pay_rows}\n"
             f"matching alipay rows: {alipay_rows}\n"
             f"sandbox trade_status={trade_status or 'MISSING'} code={alipay_code or 'MISSING'} "
             f"sub_code={sub_code or 'MISSING'} sub_msg={sub_msg or 'MISSING'}\n")
        non_success_observed = has_alipay_result and (
            (trade_status and trade_status != "TRADE_SUCCESS")
            or bool(sub_code or sub_msg)
            or (alipay_code and alipay_code != "10000")
        )
        if trade_status == "TRADE_SUCCESS" and booking_status == "confirmed" and alipay_rows:
            rubrics["I4"]["passed"] = True
            print(f"[itest] I4 PASS booking=confirmed, alipay payment rows={alipay_rows}")
        elif has_alipay_result and non_success_observed and booking_status != "confirmed" and not alipay_rows:
            rubrics["I4"]["passed"] = True
            rubrics["I4"]["message"] = (
                f"沙箱返回非成功状态（trade_status={trade_status or '缺失'}, "
                f"sub_code={sub_code or '缺失'}），本地未确认订单或新增成功支付")
            print(f"[itest] I4 PASS non-success sandbox status preserved booking={booking_status}")
        elif not has_alipay_result:
            rubrics["I4"]["message"] = (
                "未拿到可解释的支付宝查询/确认结果，无法证明应用正确处理未成功支付；"
                "不能仅因为本地 booking 未变化就通过。见 alipay_confirm_response.json 与 db_state_after_confirm.txt")
            print(f"[itest] I4 FAIL: {rubrics['I4']['message']}")
        else:
            rubrics["I4"]["message"] = (
                f"确认后 trade_status={trade_status or '缺失'}，sub_code={sub_code or '缺失'}，"
                f"booking_status={booking_status}，alipay 新增 payment 行数={len(alipay_rows)}。"
                "TRADE_SUCCESS 时应 confirmed 且新增 alipay payment；"
                "支付宝未成功时不应 confirmed 或新增成功 payment。"
                "见 db_state_after_confirm.txt 与 backend.log")
            print(f"[itest] I4 FAIL: {rubrics['I4']['message']}")
    except Exception as exc:  # noqa: BLE001
        print(f"[itest] real sandbox driver aborted: {exc}")
        for rid in ("I2", "I3", "I4"):
            if not rubrics[rid]["passed"] and not rubrics[rid]["message"]:
                rubrics[rid]["message"] = f"集成测试驱动中断：{exc}"

    write_rubrics(args.checks_file, rubrics, merge=False)


def run_mock_success(args):
    rubrics = {
        "I5": {"name": "支付成功后确认绑定 booking", "passed": False, "message": "",
               "evidence": ["mock_success_flow.json", "backend_mock.log", "alipay-mock-requests.log"]},
        "I6": {"name": "支付确认不误确认其他 booking", "passed": False, "message": "",
               "evidence": ["mock_success_flow.json", "backend_mock.log", "alipay-mock-requests.log"]},
        "I7": {"name": "App 支付金额来自服务端 booking", "passed": False, "message": "",
               "evidence": ["mock_success_flow.json", "alipay_mock_order_str_check.json"]},
    }
    flow = {}
    try:
        max_payment_before = int((mysql(
            "SELECT COALESCE(MAX(payment_id),0) FROM payments", args.db_port))[0][0])
        primary_id, show_id, primary_seat = create_reserved_booking(args, "mock_primary", price=800)
        secondary_id, secondary_show_id, secondary_seat = create_reserved_booking(args, "mock_secondary", price=800)
        flow.update({
            "primary_booking_id": primary_id,
            "secondary_booking_id": secondary_id,
            "primary_show_id": show_id,
            "secondary_show_id": secondary_show_id,
            "primary_seat": primary_seat,
            "secondary_seat": secondary_seat,
        })

        forged_amount = "0.01"
        create_result = create_alipay_order(args, primary_id, show_id, {
            "amount": forged_amount,
            "total_amount": forged_amount,
            "price": forged_amount,
        })
        status, body = create_result["status"], create_result["body"]
        out_trade_no = create_result.get("out_trade_no")
        order_str = create_result.get("order_str") or ""
        order_params, order_biz = parse_order_str(order_str or "")
        server_price = mysql(f"SELECT price FROM bookings WHERE booking_id={primary_id}", args.db_port)[0][0]
        total_amount = order_biz.get("total_amount") or order_biz.get("totalAmount")
        amount_from_server = amount_equal(total_amount, server_price) and not amount_equal(total_amount, forged_amount)
        flow["create"] = {"status": status, "body": body, "path": create_result.get("path"),
                            "payload": create_result.get("payload"), "attempts": create_result.get("attempts", []),
                            "out_trade_no": out_trade_no, "biz_content": order_biz,
                            "server_price": server_price, "forged_amount": forged_amount,
                            "amount_from_server": amount_from_server}
        save(args.output_dir, "alipay_mock_order_str_check.json", {
            "order_params": {k: order_params.get(k) for k in ("method", "sign_type", "app_id")},
            "biz_content": order_biz,
            "server_price": server_price,
            "forged_amount": forged_amount,
            "amount_from_server": amount_from_server,
            "selected_create_path": create_result.get("path"),
            "selected_create_payload": create_result.get("payload"),
        })
        if amount_from_server:
            rubrics["I7"]["passed"] = True
        else:
            rubrics["I7"]["message"] = (
                f"order_str.biz_content.total_amount={total_amount or '缺失'}，"
                f"服务端 booking price={server_price}，伪造客户端金额={forged_amount}；"
                "应以服务端 booking 金额为准")

        if not out_trade_no:
            raise RuntimeError("mock success create did not return out_trade_no")
        confirm_result = confirm_alipay_payment(args, out_trade_no, [primary_id])
        status, body = confirm_result["status"], confirm_result["body"]
        flow["confirm"] = {"status": status, "body": body,
                            "payload": confirm_result.get("payload"),
                            "attempts": confirm_result.get("attempts", [])}

        primary_status = mysql(f"SELECT booking_status FROM bookings WHERE booking_id={primary_id}", args.db_port)[0][0]
        secondary_status = mysql(f"SELECT booking_status FROM bookings WHERE booking_id={secondary_id}", args.db_port)[0][0]
        pay_rows = mysql(
            "SELECT payment_id, amount, payment_method, user_id, show_id FROM payments "
            f"WHERE payment_id > {max_payment_before} AND user_id=2", args.db_port)
        alipay_rows = [row for row in pay_rows if len(row) >= 3 and str(row[2]).lower() == "alipay"]
        primary_show_alipay_rows = [row for row in alipay_rows if len(row) >= 5 and str(row[4]) == str(show_id)]
        flow["db_after_confirm"] = {
            "primary_status": primary_status,
            "secondary_status": secondary_status,
            "new_payment_rows": pay_rows,
            "alipay_rows": alipay_rows,
            "primary_show_alipay_rows": primary_show_alipay_rows,
        }

        if status in SUCCESS_HTTP and primary_status == "confirmed" and primary_show_alipay_rows:
            rubrics["I5"]["passed"] = True
        else:
            rubrics["I5"]["message"] = (
                f"mock TRADE_SUCCESS confirm HTTP {status}；primary booking={primary_status}；"
                f"primary show alipay payment rows={len(primary_show_alipay_rows)}")

        if secondary_status != "confirmed":
            rubrics["I6"]["passed"] = True
        else:
            rubrics["I6"]["message"] = (
                f"只确认 out_trade_no={out_trade_no} 对应 booking 时，"
                f"另一个 reserved booking({secondary_id}) 也被推进为 confirmed")

        save(args.output_dir, "mock_success_flow.json", flow)
    except Exception as exc:  # noqa: BLE001
        print(f"[itest] mock success driver aborted: {exc}")
        flow["error"] = str(exc)
        save(args.output_dir, "mock_success_flow.json", flow)
        for rid in ("I5", "I6", "I7"):
            if not rubrics[rid]["passed"] and not rubrics[rid]["message"]:
                rubrics[rid]["message"] = f"mock success 集成测试中断：{exc}"

    write_rubrics(args.checks_file, rubrics, merge=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--checks-file", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--i1-pass", default="0")
    ap.add_argument("--mock-success-only", action="store_true")
    args = ap.parse_args()

    if args.mock_success_only:
        run_mock_success(args)
    else:
        run_real_sandbox(args)


if __name__ == "__main__":
    main()
