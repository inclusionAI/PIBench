#!/usr/bin/env python3
"""Static code checks for BookCars Alipay Preauthorization basic (S1-S5)."""

import json
import os
import re
import sys
from pathlib import Path


RESULTS = []


def record(rid, name, passed, message):
    RESULTS.append({
        "id": rid, "name": name,
        "type": "static",
        "passed": bool(passed),
        "score": 1 if passed else 0, "max_score": 1,
        "message": str(message)[:1000],
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] {rid}: {name} -- {message[:200]}")


def grep_files(directory, pattern, extensions=None):
    results = []
    if not os.path.isdir(directory):
        return results
    for root, _, files in os.walk(directory):
        for f in files:
            if extensions and not any(f.endswith(ext) for ext in extensions):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                    if pattern in content:
                        results.append(filepath)
            except (IOError, OSError):
                continue
    return results


def check_s1_sdk_or_openapi_client(workspace):
    """S1: Official SDK or equivalent signed OpenAPI client."""
    pkg_path = os.path.join(workspace, "backend", "package.json")
    if not os.path.exists(pkg_path):
        return False, "backend/package.json not found"
    with open(pkg_path, "r") as f:
        pkg = json.load(f)
    deps = pkg.get("dependencies", {})
    dev_deps = pkg.get("devDependencies", {})
    if "alipay-sdk" in deps or "alipay-sdk" in dev_deps:
        return True, "alipay-sdk found in package.json"

    backend_src = os.path.join(workspace, "backend", "src")
    signals = []
    for root, _, files in os.walk(backend_src):
        for filename in files:
            if not filename.endswith((".ts", ".js")):
                continue
            filepath = os.path.join(root, filename)
            try:
                content = open(filepath, "r", encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            lower = content.lower()
            has_alipay_gateway = "openapi.alipay.com" in lower or "gateway.do" in lower
            has_signing = (
                "rsa-sha256" in lower
                or "rsa2" in lower
                or re.search(r"createSign\s*\(", content)
            )
            has_api_params = "app_id" in content and "method" in content and "sign" in content
            if has_alipay_gateway and has_signing and has_api_params:
                signals.append(os.path.relpath(filepath, workspace))
    if signals:
        return True, "Equivalent signed OpenAPI client found in: " + ", ".join(signals[:3])

    return False, "No alipay-sdk dependency or equivalent signed Alipay OpenAPI client found"


def check_s2_preauth_scheme_entry(workspace):
    """S2: Code creates a real Alipay preauth entry and exposes an authorization entry."""
    backend_src = os.path.join(workspace, "backend", "src")
    api_results = []
    for pattern in (
        "alipay.fund.auth.order.app.freeze",
        "alipay.fund.auth.order.voucher.create",
    ):
        api_results.extend(grep_files(backend_src, pattern, [".ts", ".js"]))

    entry_results = []
    for pattern in (
        "schemeUrl",
        "scheme_url",
        "schemeURL",
        "alipays://",
        "qr.alipay.com",
        "codeValue",
        "codeUrl",
        "qrCode",
    ):
        entry_results.extend(grep_files(backend_src, pattern, [".ts", ".js"]))

    if api_results and entry_results:
        rel_api = [os.path.relpath(r, workspace) for r in api_results[:2]]
        rel_entry = [os.path.relpath(r, workspace) for r in entry_results[:2]]
        return True, f"Found Alipay preauth API in {', '.join(rel_api)} and entry handling in {', '.join(rel_entry)}"
    missing = []
    if not api_results:
        missing.append("alipay.fund.auth.order.app.freeze or alipay.fund.auth.order.voucher.create")
    if not entry_results:
        missing.append("Alipay authorization entry handling")
    return False, "Missing: " + ", ".join(missing)


def check_s3_product_code(workspace):
    """S3: Code contains PRE_AUTH or PREAUTH_PAY."""
    backend_src = os.path.join(workspace, "backend", "src")
    for pattern in ["PRE_AUTH", "PREAUTH_PAY", "preauth", "FUND_AUTH"]:
        results = grep_files(backend_src, pattern, [".ts", ".js"])
        if results:
            rel = [os.path.relpath(r, workspace) for r in results[:3]]
            return True, f"Found '{pattern}' in: {', '.join(rel)}"
    return False, "PRE_AUTH/PREAUTH_PAY not found in backend/src"


def check_s4_route_registered(workspace):
    """S4: Code has /api/alipay route."""
    backend_src = os.path.join(workspace, "backend", "src")
    for pattern in ["/api/alipay", "alipay", "alipayRouter"]:
        results = grep_files(backend_src, pattern, [".ts", ".js"])
        if results:
            rel = [os.path.relpath(r, workspace) for r in results[:3]]
            return True, f"Found '{pattern}' in: {', '.join(rel)}"
    return False, "/api/alipay route not found in backend/src"


def check_s5_frontend_qr(workspace):
    """S5: Frontend code has QR code component for Alipay."""
    frontend_src = os.path.join(workspace, "frontend", "src")
    qr_patterns = [
        "qrcode",
        "QRCode",
        "qr-code",
        "react-qr",
        "QRCodeSVG",
        "QRCodeCanvas",
        "qrCodeDataUrl",
        "qrCodeUrl",
        "qrDataUrl",
        "QR code",
        "data:image/png",
    ]
    for pattern in qr_patterns:
        results = grep_files(frontend_src, pattern, [".ts", ".tsx", ".js", ".jsx"])
        if results:
            rel = [os.path.relpath(r, workspace) for r in results[:3]]
            return True, f"Found '{pattern}' in: {', '.join(rel)}"
    # Also check package.json
    pkg_path = os.path.join(workspace, "frontend", "package.json")
    if os.path.exists(pkg_path):
        content = open(pkg_path).read()
        for p in ["qrcode", "react-qr"]:
            if p in content:
                return True, f"Found '{p}' in frontend/package.json"
    return False, "No QR code component found in frontend/src"


def main():
    workspace = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "/output"

    checks = [
        ("S1", "SDK/签名客户端 (alipay-sdk 或等价 OpenAPI 调用)", check_s1_sdk_or_openapi_client),
        ("S2", "支付宝预授权入口 (App 唤起或扫码)", check_s2_preauth_scheme_entry),
        ("S3", "产品码 (PRE_AUTH/PREAUTH_PAY)", check_s3_product_code),
        ("S4", "路由注册 (/api/alipay/)", check_s4_route_registered),
        ("S5", "前端二维码组件", check_s5_frontend_qr),
    ]

    for check_id, name, check_fn in checks:
        passed, message = check_fn(workspace)
        record(check_id, name, passed, message)

    output_path = os.path.join(output_dir, "static_results.json")
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(RESULTS, f, indent=2, ensure_ascii=False)

    passed_count = sum(1 for r in RESULTS if r["passed"])
    print(f"\nStatic checks: {passed_count}/{len(RESULTS)} passed")


if __name__ == "__main__":
    main()
