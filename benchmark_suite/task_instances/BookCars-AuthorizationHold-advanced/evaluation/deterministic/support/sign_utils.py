#!/usr/bin/env python3
"""RSA2 key generation and Alipay-compatible signing utilities.

Usage as CLI:
    python3 sign_utils.py genkeys <keys_dir>

Usage as module:
    from sign_utils import load_keys, sign_params, build_signed_notify
"""
import base64
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

_BACKEND = default_backend()


def generate_keypair():
    """Generate a 2048-bit RSA key pair, return (private_pem_bytes, public_pem_bytes)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=_BACKEND)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def pem_to_single_line(pem_bytes):
    """Strip PEM headers and join into a single base64 line (for config injection)."""
    text = pem_bytes.decode("utf-8") if isinstance(pem_bytes, bytes) else pem_bytes
    lines = [l.strip() for l in text.strip().splitlines()
             if l.strip() and not l.strip().startswith("-----")]
    return "".join(lines)


def genkeys(keys_dir):
    """Generate merchant + alipay key pairs and save to keys_dir."""
    os.makedirs(keys_dir, exist_ok=True)
    merchant_priv, merchant_pub = generate_keypair()
    alipay_priv, alipay_pub = generate_keypair()

    keys = {
        "merchant_private_pem": merchant_priv.decode(),
        "merchant_public_pem": merchant_pub.decode(),
        "merchant_private_b64": pem_to_single_line(merchant_priv),
        "merchant_public_b64": pem_to_single_line(merchant_pub),
        "alipay_private_pem": alipay_priv.decode(),
        "alipay_public_pem": alipay_pub.decode(),
        "alipay_private_b64": pem_to_single_line(alipay_priv),
        "alipay_public_b64": pem_to_single_line(alipay_pub),
    }
    with open(os.path.join(keys_dir, "keys.json"), "w") as f:
        json.dump(keys, f, indent=2)

    # Convenience files
    for name in ("merchant_private_pem", "merchant_public_pem",
                 "alipay_private_pem", "alipay_public_pem"):
        with open(os.path.join(keys_dir, name.replace("_pem", "") + ".pem"), "w") as f:
            f.write(keys[name])
    for name in ("merchant_private_b64", "alipay_public_b64"):
        with open(os.path.join(keys_dir, name + ".txt"), "w") as f:
            f.write(keys[name])

    return keys


def load_keys(keys_dir):
    """Load keys from keys_dir/keys.json."""
    with open(os.path.join(keys_dir, "keys.json")) as f:
        return json.load(f)


def sign_params(params, private_key_pem):
    """Sign parameters Alipay-style: sort keys, join k=v with &, RSA-SHA256, base64.

    Args:
        params: dict of string parameters (sign and sign_type are excluded)
        private_key_pem: PEM-encoded private key (str or bytes)
    Returns:
        base64-encoded signature string
    """
    if isinstance(private_key_pem, str):
        private_key_pem = private_key_pem.encode()
    private_key = serialization.load_pem_private_key(private_key_pem, password=None, backend=_BACKEND)

    filtered = {k: v for k, v in params.items()
                if k not in ("sign", "sign_type") and v is not None and v != ""}
    content = "&".join(f"{k}={v}" for k, v in sorted(filtered.items()))

    signature = private_key.sign(content.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("utf-8")


def build_signed_notify(fields, alipay_private_pem):
    """Build a complete signed notification parameter dict.

    Args:
        fields: dict with notification fields (out_trade_no, trade_status, etc.)
        alipay_private_pem: PEM private key to sign with (simulates Alipay signing)
    Returns:
        dict with all fields + sign + sign_type
    """
    import time
    defaults = {
        "notify_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "notify_type": "trade_status_sync",
        "notify_id": "mock_notify_%d" % int(time.time() * 1000),
        "charset": "utf-8",
        "version": "1.0",
        "sign_type": "RSA2",
    }
    params = {**defaults, **fields}
    params["sign"] = sign_params(params, alipay_private_pem)
    return params


def sign_gateway_response(method_response_key, response_body, alipay_private_pem):
    """Sign a gateway API response body (for mock gateway use).

    Alipay SDK verifies by extracting the JSON substring of the *_response node
    and checking the sign field. We sign the compact JSON of the response node.

    Returns:
        JSON string: {"method_response": {...}, "sign": "..."}
    """
    if isinstance(alipay_private_pem, str):
        alipay_private_pem = alipay_private_pem.encode()
    private_key = serialization.load_pem_private_key(alipay_private_pem, password=None, backend=_BACKEND)

    node_json = json.dumps(response_body, separators=(",", ":"), ensure_ascii=False)
    signature = private_key.sign(node_json.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    sign_b64 = base64.b64encode(signature).decode("utf-8")

    return json.dumps({
        method_response_key: response_body,
        "sign": sign_b64,
    }, ensure_ascii=False)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "genkeys":
        keys = genkeys(sys.argv[2])
        print("Keys generated in", sys.argv[2])
        print("  merchant_private_b64:", keys["merchant_private_b64"][:40] + "...")
        print("  alipay_public_b64:", keys["alipay_public_b64"][:40] + "...")
    else:
        print("Usage: python3 sign_utils.py genkeys <keys_dir>")
        sys.exit(1)
