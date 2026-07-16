#!/usr/bin/env python3
"""Static checks for litemall-pc basic (3 scored items plus diagnostics)."""
import ipaddress
import json
import os
import re
import sys

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"
RESULTS = []
DIAGNOSTICS = {}


def record(rid, name, passed, message):
    RESULTS.append({
        "id": rid, "name": name, "dimension": "functionality",
        "type": "static", "passed": bool(passed),
        "score": 1 if passed else 0, "max_score": 1,
        "message": str(message)[:500],
    })
    print(f"  [{'PASS' if passed else 'FAIL'}] {rid}: {name} — {message[:150]}")


def check_sdk_dependency():
    found = []
    searched = 0
    for root, dirs, files in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if d not in {".git", "target", "node_modules", "dist", "build"}]
        if "pom.xml" not in files:
            continue
        searched += 1
        pom = os.path.join(root, "pom.xml")
        try:
            content = open(pom, errors="replace").read().lower()
        except OSError:
            continue
        if "alipay-sdk-java" in content:
            found.append(os.path.relpath(pom, WORKSPACE))
    record("static.sdk_dependency", "SDK 依赖 (alipay-sdk-java)", bool(found),
           f"找到 in {found[:5]}" if found else f"扫描 {searched} 个 pom.xml，未找到 alipay-sdk-java")


SECRET_EXTS = (".java", ".yml", ".yaml", ".properties", ".xml", ".json", ".js", ".vue")
SECRET_EXCLUDED_DIRS = {".git", "target", "node_modules", "dist", "build", "logs", "test", "tests"}
KNOWN_REFERENCE_FILES = {"alipay-sandbox-keys.json"}


def iter_secret_scan_files():
    for root, dirs, files in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if d not in SECRET_EXCLUDED_DIRS and not d.startswith(".")]
        for f in files:
            if f in KNOWN_REFERENCE_FILES:
                continue
            if not f.endswith(SECRET_EXTS):
                continue
            yield os.path.join(root, f)


def looks_like_private_key(content):
    return (
        "-----BEGIN PRIVATE KEY-----" in content
        or "-----BEGIN RSA PRIVATE KEY-----" in content
        or re.search(r'MII[A-Za-z0-9+/]{180,}', content)
    )


def check_secret_no_hardcode():
    violations = []
    for fp in iter_secret_scan_files():
        try:
            content = open(fp, errors="replace").read()
        except OSError:
            continue
        if looks_like_private_key(content):
            violations.append(os.path.relpath(fp, WORKSPACE))
            if len(violations) >= 5:
                break
    record("static.secret_no_hardcode", "无硬编码私钥", not violations,
           f"违规: {violations[:5]}" if violations else "未在业务源码/配置中发现完整私钥")


def changed_sensitive_paths():
    changed_path = os.path.join(OUTPUT_DIR, "changed_files.txt")
    patch_path = os.path.join(OUTPUT_DIR, "patch.diff")
    changed = []
    if os.path.exists(changed_path):
        for line in open(changed_path, errors="replace"):
            rel = line.strip()
            lower = rel.lower()
            if not rel:
                continue
            if any(token in lower for token in ["alipay", "private", "secret", ".pem", ".key", ".env"]):
                if lower.endswith((".yml", ".yaml", ".properties", ".json", ".pem", ".key", ".env")):
                    changed.append(rel)
    if os.path.exists(patch_path):
        patch = open(patch_path, errors="replace").read()
        if looks_like_private_key(patch):
            changed.append("patch.diff:private-key-content")
    return sorted(set(changed))


def check_secret_gitignore():
    sensitive = changed_sensitive_paths()
    if not sensitive:
        record("static.secret_gitignore", ".gitignore 排除敏感文件", True,
               "未发现新增敏感配置/密钥文件，跳过强制 gitignore 要求")
        return
    gi = os.path.join(WORKSPACE, ".gitignore")
    if not os.path.exists(gi):
        record("static.secret_gitignore", ".gitignore 排除敏感文件", False,
               f"存在敏感改动 {sensitive[:3]}，但 .gitignore 不存在")
        return
    content = open(gi, errors="replace").read().lower()
    patterns = ["*.pem", "*.key", ".env", "application*.yml", "application*.yaml", "private_key", "alipay-sandbox-keys.json"]
    found = [pat for pat in patterns if pat.replace("*", "") in content or pat in content]
    record("static.secret_gitignore", ".gitignore 排除敏感文件", len(found) >= 1,
           f"敏感改动: {sensitive[:3]}, gitignore匹配: {found}" if found else f"敏感改动: {sensitive[:3]}，未找到排除规则")


PUBLIC_URL_RE = re.compile(r"https?://((?:\d{1,3}\.){3}\d{1,3})(?::\d+)?[^\s\"'`)]*")
PUBLIC_IP_SCAN_EXTS = SECRET_EXTS + (".env",)


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
    for root, dirs, files in os.walk(WORKSPACE):
        dirs[:] = [d for d in dirs if d not in SECRET_EXCLUDED_DIRS and not d.startswith(".")]
        for f in files:
            if f in KNOWN_REFERENCE_FILES:
                continue
            if not (f.endswith(PUBLIC_IP_SCAN_EXTS) or ".env" in f):
                continue
            yield os.path.join(root, f)


def check_no_public_ip_urls():
    violations = []
    for fp in iter_public_ip_scan_files():
        try:
            lines = open(fp, errors="replace").read().splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for match in PUBLIC_URL_RE.finditer(line):
                if is_disallowed_public_ip(match.group(1)):
                    rel = os.path.relpath(fp, WORKSPACE)
                    violations.append(f"{rel}:{lineno}:{match.group(0)}")
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
    print("--- Basic Static Checks (3 scored items + diagnostics) ---")
    check_sdk_dependency()
    check_secret_no_hardcode()
    check_secret_gitignore()
    check_no_public_ip_urls()
    passed = sum(1 for r in RESULTS if r["passed"])
    print(f"\nStatic checks: {passed}/{len(RESULTS)} passed")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "static_results.json"), "w") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUTPUT_DIR, "public_ip_diagnostics.json"), "w") as f:
        json.dump(DIAGNOSTICS, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
