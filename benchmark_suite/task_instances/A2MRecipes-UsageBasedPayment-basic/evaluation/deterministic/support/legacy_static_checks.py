#!/usr/bin/env python3
"""Static checks S1-S4 over the agent workspace. Writes static_results.json."""
import json
import os
import re
import sys

SKIP_DIRS = {"node_modules", ".next", "dist", ".git", "build", "out", "coverage", ".turbo"}
TEXT_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".env", ".yaml", ".yml",
            ".md", ".sh", ".txt", ".toml", ".example", ""}


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = os.path.join(dirpath, name)
            ext = os.path.splitext(name)[1].lower()
            if ext in TEXT_EXT:
                yield path


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def main():
    workspace = sys.argv[1]
    out_path = sys.argv[2]

    src_code = {}      # source files (ts/js) under workspace
    all_text = {}      # all text files
    for path in iter_files(workspace):
        rel = os.path.relpath(path, workspace)
        content = read(path)
        all_text[rel] = content
        if os.path.splitext(path)[1].lower() in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
            src_code[rel] = content

    results = []

    def add(rid, passed, message, evidence=None):
        results.append({"id": rid, "passed": bool(passed), "message": message,
                        "evidence": evidence or []})

    # ---- S2 a2m_config_env: payment config from runtime env ----
    env_readers = []
    for rel, content in src_code.items():
        direct_env = re.search(r"process\.env[.\[]['\"]?A2M_", content)
        helper_env = "process.env" in content and re.search(r"['\"]A2M_[A-Z0-9_]+['\"]", content)
        config_getter = re.search(r"getenv|env\(|readEnv|processEnv", content) and re.search(r"['\"]A2M_[A-Z0-9_]+['\"]", content)
        if direct_env or helper_env or config_getter:
            env_readers.append(rel)
    add("a2m_config_env", bool(env_readers),
        "A2M_* env vars read in: %s" % env_readers[:5] if env_readers else
        "no source file reads A2M_* payment configuration from runtime env",
        env_readers[:5])

    # ---- S3 a2m_secret_safe: no real-looking secrets committed ----
    leaks = []
    for rel, content in all_text.items():
        base = os.path.basename(rel)
        if base in (".env", ".env.local", ".env.production", ".env.development"):
            if re.search(r"(KEY|SECRET|TOKEN)\s*=\s*\S{20,}", content):
                leaks.append("%s: env file with non-placeholder secrets" % rel)
        if "BEGIN RSA PRIVATE KEY" in content or "BEGIN PRIVATE KEY" in content:
            leaks.append("%s: embedded private key material" % rel)
        if re.search(r"(PRIVATE_KEY|API_SECRET|APP_SECRET)\s*[:=]\s*['\"][A-Za-z0-9+/=]{60,}['\"]",
                     content):
            leaks.append("%s: hardcoded long secret literal" % rel)
    add("a2m_secret_safe", not leaks,
        "no committed secrets detected" if not leaks else "; ".join(leaks[:5]), leaks[:5])

    # ---- S4 a2m_stable_endpoint: original API entrypoints kept ----
    list_route = "src/app/api/recipes/route.ts"
    detail_route_dir_ok = any(
        re.match(r"src/app/api/recipes/\[id\]/route\.(ts|tsx|js)$", rel)
        for rel in src_code)
    proof_handled = [rel for rel, c in src_code.items() if "Payment-Proof" in c or "payment-proof" in c]
    s4_pass = (list_route in src_code) and detail_route_dir_ok
    add("a2m_stable_endpoint", s4_pass,
        ("list and detail routes kept; Payment-Proof handled in %s" % proof_handled[:3]) if s4_pass else
        "original /api/recipes or /api/recipes/[id] route file is missing — fixed entrypoints were not preserved",
        proof_handled[:3])

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    for r in results:
        print("[static] %-22s %s  %s" % (r["id"], "PASS" if r["passed"] else "FAIL", r["message"]))


if __name__ == "__main__":
    main()
