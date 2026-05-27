"""Keyring-backed credential storage.

Wraps python-keyring with two narrow concerns:
- Detect whether the active backend actually persists (some systems return a
  no-op `fail.Keyring` when no real secret service is reachable — saving to
  that would silently drop credentials).
- Provide stable service/account naming so passwords for `user@host:port` and
  passphrases for a key file path go to predictable slots.

All functions are safe to call even when keyring isn't installed.
"""

from __future__ import annotations

import logging
from typing import Optional

try:
    import keyring
    import keyring.errors
    from keyring.backends import fail as _fail_backend
    _HAS_KEYRING = True
except ImportError:  # pragma: no cover - exercised only when dep is missing
    keyring = None  # type: ignore[assignment]
    _fail_backend = None  # type: ignore[assignment]
    _HAS_KEYRING = False

log = logging.getLogger(__name__)


SERVICE_PASSWORD = "bifrost-ssh"
SERVICE_PASSPHRASE = "bifrost-ssh-passphrase"
# Old service names from before the rename; checked as a read-only fallback in
# get_* so users don't lose access to credentials they saved under the old name.
# Writes always go to the new service slots.
_LEGACY_SERVICE_PASSWORD = "asbru-ssh"
_LEGACY_SERVICE_PASSPHRASE = "asbru-ssh-passphrase"


def is_available() -> bool:
    """True if a working keyring backend is configured and can persist secrets.

    A `fail.Keyring` chain element is the sentinel keyring uses when nothing
    real is reachable — treat that as unavailable so we don't pretend to save.
    """
    if not _HAS_KEYRING:
        return False
    try:
        backend = keyring.get_keyring()
    except Exception:
        log.debug("get_keyring failed", exc_info=True)
        return False
    # ChainerBackend may still wrap a fail backend; detect by class name to
    # avoid coupling to a specific keyring version's internals.
    name = type(backend).__name__.lower()
    if "fail" in name:
        return False
    if _fail_backend is not None and isinstance(backend, _fail_backend.Keyring):
        return False
    return True


def password_account(user: str, host: str, port: int | str = 22) -> str:
    user = (user or "").strip()
    host = (host or "").strip()
    return f"{user}@{host}:{port}"


def passphrase_account(key_path: str) -> str:
    return (key_path or "").strip()


# ---- password helpers ------------------------------------------------------

def get_password(user: str, host: str, port: int | str = 22) -> Optional[str]:
    if not _HAS_KEYRING:
        return None
    account = password_account(user, host, port)
    try:
        pw = keyring.get_password(SERVICE_PASSWORD, account)
        if pw is not None:
            return pw
        # Legacy fallback for entries saved before the asbru → bifrost rename.
        return keyring.get_password(_LEGACY_SERVICE_PASSWORD, account)
    except keyring.errors.KeyringError:
        log.debug("keyring read failed", exc_info=True)
        return None


def set_password(user: str, host: str, port: int | str, password: str) -> bool:
    if not is_available() or not password:
        return False
    account = password_account(user, host, port)
    try:
        keyring.set_password(SERVICE_PASSWORD, account, password)
        return True
    except keyring.errors.KeyringError:
        log.warning("Could not save password for %s", account, exc_info=True)
        return False


def forget_password(user: str, host: str, port: int | str = 22) -> bool:
    if not _HAS_KEYRING:
        return False
    account = password_account(user, host, port)
    removed = False
    for service in (SERVICE_PASSWORD, _LEGACY_SERVICE_PASSWORD):
        try:
            keyring.delete_password(service, account)
            removed = True
        except keyring.errors.PasswordDeleteError:
            pass
        except keyring.errors.KeyringError:
            log.warning("Could not delete password for %s in %s", account, service,
                        exc_info=True)
    return removed


# ---- passphrase helpers ----------------------------------------------------

def get_passphrase(key_path: str) -> Optional[str]:
    if not _HAS_KEYRING or not key_path:
        return None
    account = passphrase_account(key_path)
    try:
        pp = keyring.get_password(SERVICE_PASSPHRASE, account)
        if pp is not None:
            return pp
        # Legacy fallback for entries saved before the asbru → bifrost rename.
        return keyring.get_password(_LEGACY_SERVICE_PASSPHRASE, account)
    except keyring.errors.KeyringError:
        log.debug("keyring read failed", exc_info=True)
        return None


def set_passphrase(key_path: str, passphrase: str) -> bool:
    if not is_available() or not key_path or not passphrase:
        return False
    try:
        keyring.set_password(SERVICE_PASSPHRASE, passphrase_account(key_path), passphrase)
        return True
    except keyring.errors.KeyringError:
        log.warning("Could not save passphrase for %s", key_path, exc_info=True)
        return False


def forget_passphrase(key_path: str) -> bool:
    if not _HAS_KEYRING or not key_path:
        return False
    account = passphrase_account(key_path)
    removed = False
    for service in (SERVICE_PASSPHRASE, _LEGACY_SERVICE_PASSPHRASE):
        try:
            keyring.delete_password(service, account)
            removed = True
        except keyring.errors.PasswordDeleteError:
            pass
        except keyring.errors.KeyringError:
            pass
    return removed
