#!/usr/bin/env python3
"""Static checks for litemall-pc-advanced (3 scored items plus diagnostics)."""
import ipaddress
import json
import os
import re
import sys
from pathlib import Path

WORKSPACE = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace")
OUTPUT_DIR = Path(sys.argv[2] if len(sys.argv) > 2 else "/output")
RESULTS = []
DIAGNOSTICS = {}

SCAN_SUFFIXES = {".java", ".yml", ".yaml", ".properties", ".xml", ".json", ".js", ".vue"}
PUBLIC_IP_SCAN_SUFFIXES = SCAN_SUFFIXES | {".env"}
SKIP_PARTS = {".git", "target", "node_modules", "dist", "build", "logs", "test", "tests"}
REFERENCE_FILES = {"alipay-sandbox-keys.json"}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"MII[A-Za-z0-9+/=]{100,}"),
]
SENSITIVE_HINTS = (
    "private-key", "private_key", "privatekey", "public-key", "public_key",
    "alipay-public", "app-private", "app_private", "alipay-private",
    "merchant-private", "secret", "pem",
)
LOCAL_SECRET_HINTS = (
    ".env", "secret", "private", "local", "pem", "sandbox-keys",
)


def record(rid, name, passed, message):
    RESULTS.append({
        "id": rid, "name": name, "dimension": "security",
        "type": "static", "passed": bool(passed),
        "score": 1 if passed else 0, "max_score": 1,
        "message": str(message)[:500],
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] {rid}: {name} — {message[:150]}")


def iter_source_files():
    for path in WORKSPACE.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(WORKSPACE)
        if path.name in REFERENCE_FILES:
            continue
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        if path.suffix.lower() in SCAN_SUFFIXES:
            yield path


def check_secret_no_hardcode():
    violations = []
    for fp in iter_source_files():
        try:
            content = fp.read_text(errors="replace")
        except OSError:
            continue
        lowered = content.lower()
        has_secret = any(p.search(content) for p in SECRET_PATTERNS)
        has_sensitive_assignment = any(h in lowered for h in SENSITIVE_HINTS) and any(
            p.search(content) for p in SECRET_PATTERNS
        )
        if has_secret or has_sensitive_assignment:
            violations.append(str(fp.relative_to(WORKSPACE)))
    record("static.secret_no_hardcode", "无硬编码密钥材料",
           not violations,
           f"违规文件: {violations[:5]}" if violations else "未发现业务源码硬编码完整密钥材料")


def changed_files():
    path = OUTPUT_DIR / "changed_files.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(errors="replace").splitlines() if line.strip()]


def changed_sensitive_config_files():
    result = []
    for rel in changed_files():
        p = WORKSPACE / rel
        if not p.is_file() or p.name in REFERENCE_FILES:
            continue
        if p.suffix.lower() not in {".yml", ".yaml", ".properties", ".json", ".env", ".pem"}:
            continue
        try:
            raw_content = p.read_text(errors="replace")
        except OSError:
            continue
        rel_l = rel.lower()
        name_l = p.name.lower()
        content = raw_content.lower()
        if name_l.endswith((".example", ".sample", ".template")):
            continue
        has_secret_material = any(pattern.search(raw_content) for pattern in SECRET_PATTERNS)
        looks_local_secret_file = any(h in rel_l or h in name_l for h in LOCAL_SECRET_HINTS)
        has_sensitive_hint = any(h in content or h in rel_l for h in SENSITIVE_HINTS)
        if has_secret_material or (looks_local_secret_file and has_sensitive_hint):
            result.append(rel)
    return result


def gitignore_covers(rel, patterns):
    rel_l = rel.lower()
    name_l = Path(rel_l).name
    for pat in patterns:
        p = pat.strip().lower()
        if not p or p.startswith("#"):
            continue
        if p == rel_l or p == name_l:
            return True
        if p.endswith("/") and rel_l.startswith(p.rstrip("/")):
            return True
        if "*" in p:
            regex = "^" + re.escape(p).replace(r"\*", ".*") + "$"
            if re.match(regex, rel_l) or re.match(regex, name_l):
                return True
        if p in rel_l and any(token in p for token in ("private", "secret", ".env", "alipay", "pem")):
            return True
    return False


def check_secret_gitignore():
    sensitive = changed_sensitive_config_files()
    gitignore_path = WORKSPACE / ".gitignore"
    if not sensitive:
        record("static.secret_gitignore", ".gitignore 排除敏感文件", True,
               "未新增敏感本地配置文件")
        return
    if not gitignore_path.exists():
        record("static.secret_gitignore", ".gitignore 排除敏感文件", False,
               f"新增敏感配置 {sensitive[:3]}，但 .gitignore 不存在")
        return
    patterns = gitignore_path.read_text(errors="replace").splitlines()
    uncovered = [rel for rel in sensitive if not gitignore_covers(rel, patterns)]
    record("static.secret_gitignore", ".gitignore 排除敏感文件",
           not uncovered,
           f"未覆盖: {uncovered[:3]}" if uncovered else f"敏感配置已被 .gitignore 覆盖: {sensitive[:3]}")


def check_refund_sdk_usage():
    found_files = []
    for fp in iter_source_files():
        if fp.suffix.lower() != ".java":
            continue
        try:
            content = fp.read_text(errors="replace")
        except OSError:
            continue
        if "AlipayTradeRefundRequest" in content or "trade.refund" in content:
            found_files.append(str(fp.relative_to(WORKSPACE)))
    record("static.refund_sdk_usage", "退款使用 SDK (AlipayTradeRefundRequest)",
           len(found_files) > 0,
           f"找到: {found_files[:3]}" if found_files else "未找到退款 SDK 调用")


PUBLIC_URL_RE = re.compile(r"https?://((?:\d{1,3}\.){3}\d{1,3})(?::\d+)?[^\s\"'`)]*")


def is_disallowed_public_ip(ip_text):
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def iter_public_ip_scan_files():
    for path in WORKSPACE.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(WORKSPACE)
        if path.name in REFERENCE_FILES:
            continue
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        if path.suffix.lower() in PUBLIC_IP_SCAN_SUFFIXES or ".env" in path.name:
            yield path


def check_no_public_ip_urls():
    violations = []
    for fp in iter_public_ip_scan_files():
        try:
            lines = fp.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for match in PUBLIC_URL_RE.finditer(line):
                if is_disallowed_public_ip(match.group(1)):
                    violations.append(f"{fp.relative_to(WORKSPACE)}:{lineno}:{match.group(0)}")
                    break
            if len(violations) >= 10:
                break
        if len(violations) >= 10:
            break
    passed = not violations
    DIAGNOSTICS["no_public_ip_urls"] = {
        "id": "diagnostic.no_public_ip_urls",
        "name": "无硬编码公网 IP URL",
        "passed": passed,
        "violations": violations[:20],
        "message": f"违规: {violations[:5]}" if violations else "未发现业务源码/配置中硬编码公网 IP URL",
    }
    print(f"  [{'PASS' if passed else 'WARN'}] diagnostic.no_public_ip_urls: 无硬编码公网 IP URL — {DIAGNOSTICS['no_public_ip_urls']['message'][:150]}")


def main():
    print("--- Advanced Static Checks (3 scored items + diagnostics) ---")
    check_secret_no_hardcode()
    check_secret_gitignore()
    check_refund_sdk_usage()
    check_no_public_ip_urls()

    passed = sum(1 for r in RESULTS if r["passed"])
    print(f"\nStatic checks: {passed}/{len(RESULTS)} passed")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "static_results.json").write_text(
        json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "public_ip_diagnostics.json").write_text(
        json.dumps(DIAGNOSTICS, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
