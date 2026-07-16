#!/usr/bin/env python3
"""run_static.py — 静态检查（SPEC 2.1） + 一个低权重的「确实新增了安全逻辑」信号。

  S1 a2m_no_fake_bypass         无 fake verify/confirm 绕过、保留真实 verify 调用
  S2 a2m_secret_safe_security   仓库不含真实私钥/证书
  S3 a2m_stable_endpoint_security 安全逻辑仍挂在 GET /api/recipes/:id
  H  a2m_added_security_logic   （启发式，低权重）patch 中确实加入了绑定/持久化/幂等相关代码

用法: run_static.py <app_dir> <patch_diff> <out_json>
"""
import os
import re
import sys
import json

CODE_EXT = (".ts", ".tsx", ".js", ".mjs", ".cjs", ".json")
SKIP_DIRS = {"node_modules", ".next", ".git", "dist", ".turbo"}


def iter_code_files(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn.endswith(CODE_EXT) or fn.startswith(".env"):
                yield os.path.join(dp, fn)


def read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return ""


def check_secret_safe(root):
    """只在出现「真正的多行 PEM 私钥块」或非空 .env 私钥时判失败；
    a2m.ts 里 detectKeyType 的 PEM 头字符串字面量不算。"""
    findings = []
    pem_begin = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
    b64line = re.compile(r"^[A-Za-z0-9+/=]{40,}$")
    for path in iter_code_files(root):
        content = read(path)
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if pem_begin.search(line):
                # 真实 PEM：紧随其后存在 base64 材料行（排除被引号包住的单行字面量）。
                stripped = line.strip().strip("'").strip('"').strip("`")
                if stripped.endswith("PRIVATE KEY-----") and i + 1 < len(lines):
                    nxt = lines[i + 1].strip().strip("'").strip('"').strip("`").strip("\\n")
                    if b64line.match(nxt):
                        findings.append("%s:%d 出现真实私钥块" % (os.path.relpath(path, root), i + 1))
        # .env*（非 example）含非空私钥
        base = os.path.basename(path)
        if base.startswith(".env") and base != ".env.example":
            for m in re.finditer(r"A2M_PRIVATE_KEY\s*=\s*(\S+)", content):
                if m.group(1).strip():
                    findings.append("%s 含非空 A2M_PRIVATE_KEY" % os.path.relpath(path, root))
    return (len(findings) == 0), findings


def main():
    app_dir = sys.argv[1]
    patch_path = sys.argv[2]
    out = sys.argv[3]
    checks = []

    def add(rid, name, passed, message, evidence=None):
        checks.append({"id": rid, "name": name, "passed": bool(passed),
                       "message": message, "evidence": evidence or []})

    route_path = os.path.join(app_dir, "src/app/api/recipes/[id]/route.ts")
    a2m_path = os.path.join(app_dir, "src/lib/a2m.ts")
    route_src = read(route_path)
    a2m_src = read(a2m_path)
    combined = route_src + "\n" + a2m_src
    patch = read(patch_path)

    # ---- S1: no fake bypass ----
    verify_call_present = "alipay.aipay.agent.payment.verify" in a2m_src or "payment.verify" in combined
    bypass_smells = []
    smell_patterns = [
        r"//\s*(bypass|skip|hack|todo:?\s*remove)",
        r"BYPASS_(VERIFY|PROOF|PAYMENT)",
        r"FAKE_(VERIFY|PROOF)",
        r"return\s*{\s*verified:\s*true[^}]*}\s*;?\s*//",   # 带注释的硬编码成功
        r"if\s*\(\s*true\s*\)",
        r"===\s*['\"]TEST_PROOF['\"]",
        r"DEV_FALLBACK|DEV_PRIVATE_KEY|降级放行",
    ]
    for pat in smell_patterns:
        if re.search(pat, combined, re.IGNORECASE):
            bypass_smells.append(pat)
    s1_pass = verify_call_present and not bypass_smells
    add("a2m_no_fake_bypass", "无 fake verify/confirm 绕过",
        s1_pass,
        "verify_call_present=%s, bypass_smells=%s" % (verify_call_present, bypass_smells or "none"),
        ["code_files/src/lib/a2m.ts", "patch.diff"])

    # ---- S2: secret safe ----
    safe, findings = check_secret_safe(app_dir)
    add("a2m_secret_safe_security", "安全题仍不泄漏密钥",
        safe, "findings=%s" % (findings or "none"), ["patch.diff"])

    # ---- S3: stable endpoint ----
    route_exists = os.path.isfile(route_path)
    has_get = bool(re.search(r"export\s+async\s+function\s+GET", route_src)) or "export const GET" in route_src
    payment_needed_kept = "Payment-Needed" in combined
    s3_pass = route_exists and has_get and payment_needed_kept
    add("a2m_stable_endpoint_security", "保留固定 API 入口",
        s3_pass,
        "route_exists=%s, GET_handler=%s, Payment-Needed_kept=%s" % (route_exists, has_get, payment_needed_kept),
        ["code_files/src/app/api/recipes/[id]/route.ts"])

    # ---- H: 确实新增了安全逻辑（启发式，低权重，仅作确定性下限）----
    binding_kw = [
        "resource_id", "resourceId", "out_trade_no", "tradeNo", "trade_no",
        "amount", "currency", "seller_id", "service_id",
        "fulfilled", "idempot", "replay", "persist", "order",
    ]
    # 统计 patch 新增行（+ 开头）里命中的关键字种类数。
    added_lines = [l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
    added_blob = "\n".join(added_lines)
    hits = sorted({kw for kw in binding_kw if kw.lower() in added_blob.lower()})
    touched_core = ("a2m.ts" in patch or "[id]/route.ts" in patch or "route.ts" in patch)
    h_pass = touched_core and len(hits) >= 3
    add("a2m_added_security_logic", "确实新增了绑定/防重放/幂等相关逻辑（启发式）",
        h_pass,
        "touched_core=%s, keyword_hits=%s" % (touched_core, hits),
        ["patch.diff"])

    passed = sum(1 for c in checks if c["passed"])
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"checks": checks, "passed": passed, "total": len(checks)},
                  f, ensure_ascii=False, indent=2)
    for c in checks:
        print("[static] %-30s %s  %s" % (c["id"], "PASS" if c["passed"] else "FAIL", c["message"]))
    print("[static] %d/%d passed" % (passed, len(checks)))


if __name__ == "__main__":
    main()
