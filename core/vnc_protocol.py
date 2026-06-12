"""Protocol constants and auth helpers for RFB/VNC."""

SEC_INVALID = 0
SEC_NONE = 1
SEC_VNC_AUTH = 2

ENC_RAW = 0
ENC_COPY_RECT = 1
ENC_DESKTOP_SIZE = -223

BPP = 4


def _reverse_bits(byte: int) -> int:
    out = 0
    for i in range(8):
        out = (out << 1) | ((byte >> i) & 1)
    return out


def vnc_auth_response(password: str, challenge: bytes) -> bytes:
    """DES-encrypt the 16-byte challenge with VNC's bit-reversed password key."""
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    try:  # cryptography >= 48 moved 3DES to the decrepit module
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    except ImportError:  # pragma: no cover - older cryptography
        from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES

    key = password.encode("latin-1", "replace")[:8].ljust(8, b"\0")
    key = bytes(_reverse_bits(b) for b in key)
    encryptor = Cipher(TripleDES(key * 3), modes.ECB()).encryptor()
    return encryptor.update(challenge) + encryptor.finalize()
