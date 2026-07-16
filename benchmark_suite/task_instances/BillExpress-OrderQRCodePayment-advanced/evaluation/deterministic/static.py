#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from support.common import case_kind, rubric, write_phase, read_all_code, find_business_code


PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?:RSA )?PRIVATE KEY-----\s*(.*?)\s*-----END (?:RSA )?PRIVATE KEY-----",
    re.S,
)


def has_literal_private_key(text):
    for match in PRIVATE_KEY_BLOCK_RE.finditer(text):
        body = match.group(1)
        if "${" in body or "key.match" in body:
            continue
        compact = re.sub(r"\s+", "", body)
        if len(compact) >= 80 and re.match(r"^[A-Za-z0-9+/=]+$", compact):
            return True
    return False


def main():
    app = Path(sys.argv[1]); out = Path(sys.argv[2]); case_name = sys.argv[3]
    kind = case_kind()
    is_safety = kind.endswith("safety")
    is_barcode = kind.startswith("barcode")
    business = find_business_code(app)
    all_code = read_all_code(app)
    gitignore = (app / ".gitignore").read_text(encoding="utf-8", errors="ignore") if (app / ".gitignore").exists() else ""
    rubrics = []
    rubrics.append(rubric("static.project_structure", (app/"package.json").exists() and (app/"start.sh").exists() and (app/"server.ts").exists(), "package.json/start.sh/server.ts present", "static"))
    if is_safety:
        has_mock_keys = bool(list((Path(__file__).resolve().parent / "support/mock_keys").glob("mock_*_key.pem")))
        real_key_in_project = (app / "alipay-sandbox-keys.json").exists()
        rubrics.append(rubric("static.mock_key_separation", has_mock_keys and not real_key_in_project, "mock keys live under tests/mock_keys; no sandbox key json in safety fixture", "static"))
        rubrics.append(rubric("static.no_hardcoded_private_key", not has_literal_private_key(business), "business source has no literal private key material", "static"))
        bad_mock_markers = ["Mock Alipay Pay Success", "mock_result", "/api/mock-alipay", "mock-alipay://"]
        rubrics.append(rubric("static.no_app_internal_mock_shortcut", not any(m in business for m in bad_mock_markers), "no app-internal mock endpoint/button/dropdown markers", "static"))
        signature_marker = bool(re.search(r"checkNotifySign|checkNotifySignature|verifyNotifySign|createVerify|verifyString|RSA-SHA256|sign_type.*RSA2|parsed\.sign", business, re.I))
        signature_bypass = bool(re.search(r"if\s*\(\s*![^)]*(?:publicKey|public_key|alipayPublicKey)[^)]*\)\s*return\s+true", business, re.I))
        signature_bypass = signature_bypass or "ALIPAY_ALLOW_UNSIGNED_NOTIFY" in business
        rubrics.append(rubric(
            "static.signature_verification_capability",
            signature_marker and not signature_bypass,
            "signature_marker=%s signature_bypass=%s" % (signature_marker, signature_bypass),
            "static",
        ))
        field_hits = sum(1 for token in ["out_trade_no", "total_amount", "trade_status", "invoice_id", "grand_total"] if token in business)
        rubrics.append(rubric("static.field_binding_capability", field_hits >= 4, "business source references key binding fields: %s/5" % field_hits, "static"))
        if is_barcode:
            rubrics.append(rubric("static.auth_code_protection", "auth_code_hash" in business and "auth_code_last4" in business, "barcode source stores hash/last4 rather than full auth_code", "static"))
    else:
        rubrics.append(rubric("static.sdk_or_rsa2_capability", bool(re.search(r"alipay-sdk|openapi|gateway\.do|alipay\.trade|RSA2|sign_type|createSign|createVerify", all_code, re.I)), "source includes Alipay SDK/OpenAPI/RSA2 capability", "static"))
        rubrics.append(rubric("static.no_hardcoded_private_key", not has_literal_private_key(business), "business source has no literal private key material", "static"))
        missing_ignore = [token for token in ["node_modules", ".case-runtime"] if token not in gitignore]
        if not ("*.pem" in gitignore or "*.key" in gitignore or ".env" in gitignore):
            missing_ignore.append("*.pem or *.key or .env")
        rubrics.append(rubric("static.secret_gitignore", not missing_ignore, ".gitignore missing: %s" % (", ".join(missing_ignore) if missing_ignore else "none"), "static"))
        bad_mock_markers = ["Mock Alipay Pay Success", "mock_result", "/api/mock-alipay", "mock-alipay://"]
        rubrics.append(rubric("static.no_app_internal_mock_shortcut", not any(m in business for m in bad_mock_markers), "no app-internal mock success shortcut markers", "static"))
    write_phase(out, case_name, "static", rubrics, {"kind": kind})

if __name__ == "__main__":
    main()
