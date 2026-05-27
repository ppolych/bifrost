"""Generate SSH keypairs.

paramiko 5.x removed `Ed25519Key.generate`, so we use `cryptography` directly
(it's a transitive paramiko dependency, so no new requirement). Produces
OpenSSH-format private keys and `ssh-ed25519 …` / `ssh-rsa …` public lines.
"""

from __future__ import annotations

import os
from typing import Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

KeyAlgo = Literal["ed25519", "rsa"]


def _private_bytes(priv, passphrase: str | None) -> bytes:
    encryption = (
        serialization.BestAvailableEncryption(passphrase.encode())
        if passphrase
        else serialization.NoEncryption()
    )
    return priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=encryption,
    )


def _public_bytes(priv) -> bytes:
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )


def generate_keypair(
    out_path: str,
    algorithm: KeyAlgo = "ed25519",
    rsa_bits: int = 4096,
    passphrase: str | None = None,
    comment: str = "bifrost-generated",
) -> tuple[str, str]:
    """Generate a keypair and write {out_path, out_path.pub}.

    Refuses to overwrite existing files. Tightens private-key perms to 0600.
    """
    out_path = os.path.expanduser(out_path)
    pub_path = out_path + ".pub"

    if os.path.exists(out_path) or os.path.exists(pub_path):
        raise FileExistsError(f"Refusing to overwrite {out_path} or {pub_path}")

    parent = os.path.dirname(out_path) or "."
    os.makedirs(parent, exist_ok=True)

    if algorithm == "ed25519":
        priv = ed25519.Ed25519PrivateKey.generate()
    elif algorithm == "rsa":
        priv = rsa.generate_private_key(public_exponent=65537, key_size=rsa_bits)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm!r}")

    with open(out_path, "wb") as f:
        f.write(_private_bytes(priv, passphrase))
    try:
        os.chmod(out_path, 0o600)
    except OSError:
        pass

    pub_line = _public_bytes(priv).rstrip() + f" {comment}".encode() + b"\n"
    with open(pub_path, "wb") as f:
        f.write(pub_line)
    try:
        os.chmod(pub_path, 0o644)
    except OSError:
        pass

    return out_path, pub_path
