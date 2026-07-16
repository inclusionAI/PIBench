"""RSA2 (SHA256withRSA) helpers implementing standard Alipay OpenAPI signing."""
import base64
import json

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


def load_private_key(path):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())


def load_public_key(path):
    with open(path, "rb") as f:
        return serialization.load_pem_public_key(f.read(), backend=default_backend())


def canonical_string(params, exclude_keys):
    items = []
    for key in sorted(params.keys()):
        if key in exclude_keys:
            continue
        value = params[key]
        if value is None or value == "":
            continue
        items.append("%s=%s" % (key, value))
    return "&".join(items)


def sign_text(text, private_key):
    sig = private_key.sign(text.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


def verify_text(text, signature_b64, public_key):
    try:
        public_key.verify(
            base64.b64decode(signature_b64),
            text.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


def sign_params(params, private_key, exclude_sign_type=False):
    exclude = {"sign"}
    if exclude_sign_type:
        exclude.add("sign_type")
    return sign_text(canonical_string(params, exclude), private_key)


def verify_params(params, public_key):
    """Verify a signed param set, tolerating both canonicalization conventions.

    Returns (valid, mode) where mode is 'sign_excluded' or 'sign_and_sign_type_excluded'.
    """
    signature = params.get("sign", "")
    if not signature:
        return False, None
    text_a = canonical_string(params, {"sign"})
    if verify_text(text_a, signature, public_key):
        return True, "sign_excluded"
    text_b = canonical_string(params, {"sign", "sign_type"})
    if verify_text(text_b, signature, public_key):
        return True, "sign_and_sign_type_excluded"
    return False, None


def signed_gateway_response(node_name, node, private_key):
    """Build an Alipay gateway response body whose sign covers the exact node JSON."""
    node_str = json.dumps(node, separators=(",", ":"), ensure_ascii=False)
    sign = sign_text(node_str, private_key)
    return '{"%s":%s,"sign":"%s"}' % (node_name, node_str, sign)
