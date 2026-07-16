#!/usr/bin/env python3
"""Advanced static code checks for BookCars Alipay Preauthorization (13 items, 100pts).

Replaces static_checks.sh with unified Python.
"""
import json
import os
import re
import sys

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"
BACKEND_SRC = os.path.join(WORKSPACE, "backend", "src")

RESULTS = []


def record(rid, name, passed, evidence, score):
    RESULTS.append({
        "id": rid, "name": name, "passed": bool(passed),
        "evidence": str(evidence)[:600], "score": score,
    })
    tag = "PASS" if passed else "FAIL"
    print(f"  {tag}: [{rid}] {name} ({'+'if passed else ''}{score}pts)")


def find_ts_files(directory):
    files = []
    if not os.path.isdir(directory):
        return files
    for root, _, fnames in os.walk(directory):
        for f in fnames:
            if f.endswith((".ts", ".js")):
                files.append(os.path.join(root, f))
    return files


def strip_comments(content):
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return re.sub(r"//.*", "", content)


def grep_files(file_list, pattern, case_insensitive=False, strip=False):
    """Return list of (filepath, matching_lines) tuples."""
    results = []
    flags = re.IGNORECASE if case_insensitive else 0
    compiled = re.compile(pattern, flags)
    for fp in file_list:
        try:
            content = open(fp, "r", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if strip:
            content = strip_comments(content)
        lines = [l.strip() for l in content.splitlines() if compiled.search(l)]
        if lines:
            results.append((fp, lines))
    return results


def files_containing(file_list, pattern, case_insensitive=False):
    return [fp for fp, _ in grep_files(file_list, pattern, case_insensitive)]


def line_hits(file_list, pattern, case_insensitive=False, strip=False):
    results = []
    flags = re.IGNORECASE if case_insensitive else 0
    compiled = re.compile(pattern, flags)
    for fp in file_list:
        try:
            content = open(fp, "r", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if strip:
            content = strip_comments(content)
        for idx, line in enumerate(content.splitlines(), start=1):
            if compiled.search(line):
                results.append((fp, idx, line.strip()))
    return results


def main():
    all_ts = find_ts_files(BACKEND_SRC)
    alipay_files = files_containing(all_ts, r"alipay|fund\.auth|freeze.*order|unfreeze", case_insensitive=True)
    notify_files = files_containing(alipay_files, r"notify|Notify|callback", case_insensitive=True)

    # 1. integ_notify_reject (10pts): validateSign: true or checkNotifySign
    hits = grep_files(alipay_files, r"validateSign\s*[:=]\s*true")
    hits += grep_files(alipay_files, r"checkNotifySign|checkSign|verifySign|verify_sign")
    hits += grep_files(alipay_files, r"verify.*[Ss]ign|[Ss]ign.*verif")
    if hits:
        ev = "; ".join(f"{os.path.relpath(fp, WORKSPACE)}: {ls[0][:80]}" for fp, ls in hits[:3])
        record("integ_notify_reject", "通知验签", True, ev, 10)
    else:
        has_false = grep_files(alipay_files, r"validateSign\s*[:=]\s*false")
        ev = "validateSign still false" if has_false else "no verify found"
        record("integ_notify_reject", "通知验签", False, ev, 10)

    # 2. notify_verify_fields (5pts)
    field_count = 0
    field_ev = ""
    for pattern, name in [(r"app_id|appId", "app_id"), (r"auth_no|authNo", "auth_no"),
                           (r"out_order_no|outOrderNo", "out_order_no"),
                           (r"total_freeze_amount|totalFreezeAmount|freeze_amount", "amount")]:
        if files_containing(notify_files or alipay_files, pattern):
            field_count += 1
            field_ev += name + " "
    record("notify_verify_fields", "通知字段校验", field_count >= 3,
           f"Found {field_count}/4: {field_ev}", 5)

    # 3. unique_id_check (10pts): idempotency
    # A plain status comparison is not an idempotency check. Look for durable
    # processed-notification markers or explicit duplicate/idempotent handling.
    scan_files = notify_files or alipay_files
    source_hits = grep_files(
        scan_files,
        r"\bnotify_id\b|\bnotifyId\b|\boperation_id\b|\boperationId\b|\bout_request_no\b|\boutRequestNo\b",
        strip=True,
    )
    check_hits = grep_files(
        scan_files,
        r"already.*processed|processed.*includes|processed.*some|duplicate|idempoten|findOne|exists|countDocuments|E11000|unique\s*:\s*true",
        case_insensitive=True,
        strip=True,
    )
    mark_hits = grep_files(
        scan_files,
        r"processed.*push|processed.*add|\$addToSet|notifyProcessed|create\s*\(|insertOne|save\s*\(|upsert",
        case_insensitive=True,
        strip=True,
    )
    unique_ok = bool(source_hits and check_hits and mark_hits)
    if unique_ok:
        ev = "source/check/mark found: "
        ev += "; ".join(
            f"{os.path.relpath(fp, WORKSPACE)}: {ls[0][:80]}"
            for fp, ls in (source_hits[:1] + check_hits[:1] + mark_hits[:1])
        )
    else:
        missing = []
        if not source_hits:
            missing.append("unique source")
        if not check_hits:
            missing.append("duplicate check")
        if not mark_hits:
            missing.append("durable mark")
        ev = "missing " + ", ".join(missing)
    record("unique_id_check", "幂等性检查", unique_ok, ev, 10)

    # 4. close_cancel_boundary (5pts)
    has_cancel = files_containing(alipay_files, r"fund\.auth.*cancel|voucher\.cancel|authCancel|cancelAuth", True)
    has_unfreeze = files_containing(alipay_files, r"fund\.auth\.order\.unfreeze|[Uu]nfreeze")
    record("close_cancel_boundary", "cancel/unfreeze 区分", bool(has_cancel) and bool(has_unfreeze),
           f"cancel={'found' if has_cancel else 'none'}, unfreeze={'found' if has_unfreeze else 'none'}", 5)

    # 5. secret_storage (5pts)
    hardcoded = files_containing(all_ts, r"MII[A-Za-z0-9+/]{50,}")
    record("secret_storage", "无硬编码私钥", not bool(hardcoded),
           f"hardcoded in {os.path.relpath(hardcoded[0], WORKSPACE)}" if hardcoded else "clean", 5)

    # 6. secret_gitignore (5pts)
    has_gi = False
    for gi in [os.path.join(WORKSPACE, ".gitignore"), os.path.join(WORKSPACE, "backend", ".gitignore")]:
        if os.path.exists(gi):
            content = open(gi).read()
            if ".env" in content:
                has_gi = True
                break
    record("secret_gitignore", ".gitignore 含 .env", has_gi,
           ".env in .gitignore" if has_gi else "not found", 5)

    # 7. preauth_pay_auth_no (15pts): auth_no in trade.pay
    pay_files = files_containing(alipay_files, r"alipay\.trade\.pay|trade_pay|tradePay", True)
    if pay_files:
        auth_in_pay = grep_files(pay_files, r"auth_no|authNo")
        record("preauth_pay_auth_no", "冻结转支付用授权号", bool(auth_in_pay),
               "; ".join(f"{os.path.relpath(fp, WORKSPACE)}: {ls[0][:80]}" for fp, ls in auth_in_pay[:2]) if auth_in_pay else "trade.pay exists but no auth_no", 15)
    else:
        record("preauth_pay_auth_no", "冻结转支付用授权号", False, "no trade.pay found", 15)

    # 8. preauth_freeze_amount (5pts): lightweight static guard; LLM judges semantics.
    amount_guard = []
    if pay_files:
        amount_guard = grep_files(
            pay_files,
            r"freezeAmount|freeze_amount|total_freeze_amount|restAmount|rest_amount|remaining|alipayFreezeAmount",
        )
        amount_guard += grep_files(pay_files, r"payAmount\s*(<=|<|>|>=)|amount\s*(<=|<|>|>=)|remaining\s*(<=|<|>|>=)")
    record("preauth_freeze_amount", "转支付金额校验 (静态信号)", bool(amount_guard),
           "; ".join(f"{os.path.relpath(fp, WORKSPACE)}: {ls[0][:80]}" for fp, ls in amount_guard[:3]) if amount_guard else "no amount guard near trade.pay", 5)

    # 9. gateway_business_success_check (5pts): do not treat HTTP success as Alipay business success.
    code_hits = line_hits(
        alipay_files,
        r"(code|resultCode|sub_code|subCode).*(===|==|!==|!=).*['\"]10000['\"]|['\"]10000['\"].*(===|==|!==|!=).*(code|resultCode|sub_code|subCode)",
        case_insensitive=True,
        strip=True,
    )
    state_hits = line_hits(
        alipay_files,
        r"Booking\.(update|findOneAndUpdate|findByIdAndUpdate)|\.save\s*\(|status\s*[:=]|paymentStatus|alipayAuthStatus",
        case_insensitive=True,
        strip=True,
    )
    guarded_before_state = False
    state_files = {fp for fp, _, _ in state_hits}
    for cfp, cline, _ in code_hits:
        for sfp, sline, _ in state_hits:
            if cfp == sfp and cline <= sline and (sline - cline) <= 160:
                guarded_before_state = True
                break
        if guarded_before_state:
            break
    service_layer_guard = any(cfp not in state_files for cfp, _, _ in code_hits)
    guard_only = bool(code_hits) and not state_hits
    ok = guarded_before_state or service_layer_guard or guard_only
    if ok:
        first = code_hits[0]
        ev = f"{os.path.relpath(first[0], WORKSPACE)}:{first[1]} {first[2][:100]}"
    else:
        ev = "no Alipay business code guard before state update" if state_hits else "no Alipay business code guard"
    record("gateway_business_success_check", "网关业务成功码校验", ok, ev, 5)

    # 10. preauth_unfreeze_required (15pts)
    hits = grep_files(all_ts, r"fund\.auth\.order\.unfreeze|[Uu]nfreeze")
    record("preauth_unfreeze_required", "解冻接口实现", bool(hits),
           "; ".join(f"{os.path.relpath(fp, WORKSPACE)}: {ls[0][:80]}" for fp, ls in hits[:3]) if hits else "not found", 15)

    # 11. preauth_confirm_mode (5pts)
    hits = grep_files(alipay_files, r"auth_confirm_mode|authConfirmMode|NOT_COMPLETE|\bCOMPLETE\b")
    # Filter out PayPal COMPLETED
    filtered = [(fp, [l for l in ls if "COMPLETED" not in l and "paypal" not in l.lower()])
                for fp, ls in hits]
    filtered = [(fp, ls) for fp, ls in filtered if ls]
    record("preauth_confirm_mode", "确认模式 (COMPLETE/NOT_COMPLETE)", bool(filtered),
           "; ".join(f"{os.path.relpath(fp, WORKSPACE)}: {ls[0][:80]}" for fp, ls in filtered[:2]) if filtered else "not found", 5)

    # 12. preauth_init_poll_cancel (10pts): polling or INIT status
    hits = (grep_files(alipay_files, r"setTimeout|setInterval|poll|Poll|retry|Retry") +
            grep_files(alipay_files, r"status\s*(===|!==).*INIT|INIT.*===") +
            grep_files(alipay_files, r"fund\.auth\.operation\.detail\.query") +
            grep_files(alipay_files, r"await.*delay|sleep|new Promise.*setTimeout"))
    record("preauth_init_poll_cancel", "轮询/INIT状态处理", bool(hits),
           "; ".join(f"{os.path.relpath(fp, WORKSPACE)}: {ls[0][:80]}" for fp, ls in hits[:3]) if hits else "not found", 10)

    # 13. preauth_cancel_vs_unfreeze (5pts)
    hits = (grep_files(alipay_files, r"fund\.auth\.order\.voucher\.cancel|voucherCancel") +
            grep_files(alipay_files, r"auth.*[Cc]ancel|[Cc]ancel.*auth"))
    record("preauth_cancel_vs_unfreeze", "超时撤销 (cancel)", bool(hits),
           "; ".join(f"{os.path.relpath(fp, WORKSPACE)}: {ls[0][:80]}" for fp, ls in hits[:2]) if hits else "not found", 5)

    # Write results
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "static_results.json"), "w") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)

    total_pts = sum(r["score"] for r in RESULTS if r["passed"])
    max_pts = sum(r["score"] for r in RESULTS)
    print(f"\nAdvanced static checks: {total_pts}/{max_pts} pts, {sum(1 for r in RESULTS if r['passed'])}/{len(RESULTS)} passed")


if __name__ == "__main__":
    main()
