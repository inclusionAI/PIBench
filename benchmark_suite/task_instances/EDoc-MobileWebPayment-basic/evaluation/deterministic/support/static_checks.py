#!/usr/bin/env python3
"""Static code checks (S1-S4) over the agent's modified eDoc app.

These are deliberately heuristic. They reward the *presence* of a real payment
integration shape and penalize committed secrets. They are NOT a substitute for
the integration tests; see known_limits in case_review.json.

Returns a dict keyed by rubric id: {id: {"passed": bool, "message": str, "evidence": [...]}}.
"""
import os
import re

# Files that ship with the upstream eDoc repo. We exclude them when judging
# whether the *agent* wrote a payment client, so legacy code can't pass S1.
BASELINE_HINT_DIRS = {"css", "img", "Screenshots"}


def _iter_php_files(app_dir):
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in {".git"} | BASELINE_HINT_DIRS]
        for fn in files:
            if fn.endswith(".php"):
                yield os.path.join(root, fn)


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def check_s1_dep_sdk(app_dir):
    """Alipay SDK / OpenAPI client / RSA2 signing / HTTP gateway call present."""
    sdk_patterns = [
        r"alipay", r"AlipayClient", r"openapi", r"aop\b",
        r"RSA2", r"openssl_sign", r"openssl_verify",
        r"gateway\.do", r"alipaydev", r"intl-?openapi",
        r"curl_exec", r"file_get_contents\s*\(\s*['\"]https?://",
        r"GuzzleHttp", r"composer", r"alipay-sdk",
    ]
    rx = re.compile("|".join(sdk_patterns), re.IGNORECASE)
    hits = []
    for path in _iter_php_files(app_dir):
        text = _read(path)
        if rx.search(text):
            hits.append(os.path.relpath(path, app_dir))
    # Require a signing/HTTP-ish capability, not just the word "alipay".
    strong = re.compile(r"RSA2|openssl_sign|openssl_verify|curl_exec|gateway\.do|AlipayClient|alipay-sdk|GuzzleHttp|file_get_contents\s*\(\s*['\"]https?://", re.IGNORECASE)
    strong_hits = [h for h in hits if strong.search(_read(os.path.join(app_dir, h)))]
    passed = bool(strong_hits)
    msg = ("found payment-client capability in: " + ", ".join(sorted(strong_hits)[:6])) if passed \
        else "no Alipay SDK / RSA2 / openssl signing / HTTP gateway call found (a pure local fake does not count)"
    return {"passed": passed, "message": msg, "evidence": sorted(hits)[:8]}


def check_s2_config_env(app_dir):
    """App id / gateway / keys / urls come from env or config, not hardcoded."""
    env_rx = re.compile(r"getenv\s*\(|\$_ENV\b|\$_SERVER\s*\[\s*['\"][A-Z_]+|parse_ini_file|require.*config", re.IGNORECASE)
    config_terms = re.compile(r"app_?id|gateway|notify_url|return_url|quit_url|private_key|public_key", re.IGNORECASE)
    env_files = []
    for path in _iter_php_files(app_dir):
        text = _read(path)
        if env_rx.search(text) and config_terms.search(text):
            env_files.append(os.path.relpath(path, app_dir))
    passed = bool(env_files)
    msg = ("config read from env in: " + ", ".join(sorted(env_files)[:6])) if passed \
        else "payment config (app_id/gateway/keys/urls) does not appear to be read from env/config"
    return {"passed": passed, "message": msg, "evidence": sorted(env_files)[:8]}


def check_s3_secret_safe(app_dir):
    """No real private keys / certs / suspicious secret .env committed."""
    findings = []
    # Only flag complete PEM material. Header/footer string builders around
    # env-provided bare keys are acceptable; committed key bodies are not.
    secret_rx = re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |)?PRIVATE KEY-----\s+"
        r"[A-Za-z0-9+/=\r\n]{80,}\s+"
        r"-----END (?:RSA |EC |OPENSSH |)?PRIVATE KEY-----"
        r"|-----BEGIN CERTIFICATE-----\s+"
        r"[A-Za-z0-9+/=\r\n]{80,}\s+"
        r"-----END CERTIFICATE-----",
        re.MULTILINE,
    )
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d != ".git"]
        for fn in files:
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, app_dir)
            lower = fn.lower()
            # Flag obvious secret material by extension/name.
            if lower.endswith((".pem", ".key", ".p12", ".pfx", ".crt", ".cer")):
                findings.append(f"{rel} (key/cert file)")
                continue
            if lower == ".env" or lower.startswith(".env."):
                findings.append(f"{rel} (.env file)")
                continue
            # Scan text-ish files for embedded private keys.
            if fn.endswith((".php", ".txt", ".md", ".ini", ".conf", ".json", ".yml", ".yaml")):
                text = _read(path)
                if secret_rx.search(text):
                    findings.append(f"{rel} (embedded private key/cert)")
    passed = not findings
    msg = "no committed secrets detected" if passed else "potential committed secrets: " + "; ".join(findings[:6])
    return {"passed": passed, "message": msg, "evidence": findings[:8]}


def check_s4_stable_endpoint(app_dir):
    """Required endpoint files exist at the fixed paths."""
    required = [
        "patient/alipay-h5/payment.php",
        "patient/alipay-h5/pay.php",
        "alipay/h5/notify.php",
    ]
    missing = [r for r in required if not os.path.isfile(os.path.join(app_dir, r))]
    present = [r for r in required if r not in missing]
    passed = not missing
    msg = ("all required endpoints present: " + ", ".join(present)) if passed \
        else "missing required endpoint files: " + ", ".join(missing)
    return {"passed": passed, "message": msg, "evidence": present}


def run_static_checks(app_dir):
    return {
        "wap_dep_sdk": check_s1_dep_sdk(app_dir),
        "wap_config_env": check_s2_config_env(app_dir),
        "wap_secret_safe": check_s3_secret_safe(app_dir),
        "wap_stable_endpoint": check_s4_stable_endpoint(app_dir),
    }


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(run_static_checks(sys.argv[1] if len(sys.argv) > 1 else "/workspace/app"), indent=2, ensure_ascii=False))
