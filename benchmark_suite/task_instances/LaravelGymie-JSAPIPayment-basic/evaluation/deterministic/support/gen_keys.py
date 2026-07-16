"""Generate the sandbox RSA keypairs (merchant app pair + mock-Alipay pair)."""
import os
import sys

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def write_pair(directory, prefix):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(os.path.join(directory, prefix + "_private_key.pem"), "wb") as f:
        f.write(priv)
    with open(os.path.join(directory, prefix + "_public_key.pem"), "wb") as f:
        f.write(pub)


def main():
    directory = sys.argv[1] if len(sys.argv) > 1 else "/opt/alipay-keys"
    os.makedirs(directory, exist_ok=True)
    for prefix in ("app", "alipay"):
        if not os.path.exists(os.path.join(directory, prefix + "_private_key.pem")):
            write_pair(directory, prefix)
    print("keys ready in %s" % directory)


if __name__ == "__main__":
    main()
