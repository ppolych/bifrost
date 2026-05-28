"""Password-based encryption for session export/import files."""

from __future__ import annotations

import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


FORMAT = "bifrost.sessions.v1"
KDF = "pbkdf2-sha256"
ROUNDS = 390_000


def _key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ROUNDS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_sessions(data: dict, password: str) -> dict:
    if not password:
        raise ValueError("Password is required")
    salt = os.urandom(16)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    token = Fernet(_key(password, salt)).encrypt(payload)
    return {
        "format": FORMAT,
        "kdf": KDF,
        "rounds": ROUNDS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "data": token.decode("ascii"),
    }


def decrypt_sessions(wrapper: dict, password: str) -> dict:
    if wrapper.get("format") != FORMAT:
        raise ValueError("Unsupported encrypted session file")
    if wrapper.get("kdf") != KDF:
        raise ValueError("Unsupported key derivation")
    try:
        salt = base64.b64decode(wrapper["salt"])
        token = wrapper["data"].encode("ascii")
        plaintext = Fernet(_key(password, salt)).decrypt(token)
    except (KeyError, TypeError, ValueError, InvalidToken) as e:
        raise ValueError("Could not decrypt session file") from e
    data = json.loads(plaintext.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Decrypted session data is invalid")
    return data


def is_encrypted_session_file(data) -> bool:
    return isinstance(data, dict) and data.get("format") == FORMAT and "data" in data
