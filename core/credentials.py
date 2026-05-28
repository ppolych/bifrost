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
import shutil
import subprocess
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

PROVIDER_SYSTEM = "system"
PROVIDER_1PASSWORD = "1password"
PROVIDER_KEEPASSXC = "keepassxc"
PROVIDER_LABELS = {
    PROVIDER_SYSTEM: "system keyring",
    PROVIDER_1PASSWORD: "1Password",
    PROVIDER_KEEPASSXC: "KeePassXC",
}
_provider = PROVIDER_SYSTEM


def set_provider(provider: str | None) -> None:
    global _provider
    _provider = provider if provider in PROVIDER_LABELS else PROVIDER_SYSTEM


def provider() -> str:
    return _provider


def provider_label(provider_name: str | None = None) -> str:
    return PROVIDER_LABELS.get(provider_name or _provider, PROVIDER_LABELS[PROVIDER_SYSTEM])


def is_available(provider_name: str | None = None) -> bool:
    """True if a working keyring backend is configured and can persist secrets.

    A `fail.Keyring` chain element is the sentinel keyring uses when nothing
    real is reachable — treat that as unavailable so we don't pretend to save.
    """
    active = provider_name or _provider
    if active == PROVIDER_1PASSWORD:
        return shutil.which("op") is not None
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


def _op_title(service: str, account: str) -> str:
    return f"Bifrost {service} {account}".strip()


def _op_read(service: str, account: str) -> Optional[str]:
    if not is_available(PROVIDER_1PASSWORD):
        return None
    try:
        proc = subprocess.run(
            ["op", "item", "get", _op_title(service, account), "--fields", "password", "--reveal"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        log.debug("1Password read failed", exc_info=True)
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.rstrip("\r\n") or None


def _op_write(service: str, account: str, secret: str) -> bool:
    if not is_available(PROVIDER_1PASSWORD) or not secret:
        return False
    title = _op_title(service, account)
    assignment = f"password={secret}"
    try:
        edit = subprocess.run(
            ["op", "item", "edit", title, assignment],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if edit.returncode == 0:
            return True
        create = subprocess.run(
            [
                "op", "item", "create",
                "--category", "password",
                "--title", title,
                "--tags", "bifrost",
                assignment,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return create.returncode == 0
    except (OSError, subprocess.SubprocessError):
        log.warning("1Password write failed for %s", account, exc_info=True)
        return False


def _op_delete(service: str, account: str) -> bool:
    if not is_available(PROVIDER_1PASSWORD):
        return False
    try:
        proc = subprocess.run(
            ["op", "item", "delete", _op_title(service, account), "--archive"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        log.debug("1Password delete failed", exc_info=True)
        return False


# ---- password helpers ------------------------------------------------------

def get_password(user: str, host: str, port: int | str = 22) -> Optional[str]:
    account = password_account(user, host, port)
    if _provider == PROVIDER_1PASSWORD:
        return _op_read(SERVICE_PASSWORD, account)
    if not _HAS_KEYRING:
        return None
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
    account = password_account(user, host, port)
    if _provider == PROVIDER_1PASSWORD:
        return _op_write(SERVICE_PASSWORD, account, password)
    if not is_available() or not password:
        return False
    try:
        keyring.set_password(SERVICE_PASSWORD, account, password)
        return True
    except keyring.errors.KeyringError:
        log.warning("Could not save password for %s", account, exc_info=True)
        return False


def forget_password(user: str, host: str, port: int | str = 22) -> bool:
    account = password_account(user, host, port)
    if _provider == PROVIDER_1PASSWORD:
        return _op_delete(SERVICE_PASSWORD, account)
    if not _HAS_KEYRING:
        return False
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
    account = passphrase_account(key_path)
    if _provider == PROVIDER_1PASSWORD:
        return _op_read(SERVICE_PASSPHRASE, account)
    if not _HAS_KEYRING or not key_path:
        return None
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
    account = passphrase_account(key_path)
    if _provider == PROVIDER_1PASSWORD:
        return _op_write(SERVICE_PASSPHRASE, account, passphrase)
    if not is_available() or not key_path or not passphrase:
        return False
    try:
        keyring.set_password(SERVICE_PASSPHRASE, account, passphrase)
        return True
    except keyring.errors.KeyringError:
        log.warning("Could not save passphrase for %s", key_path, exc_info=True)
        return False


def forget_passphrase(key_path: str) -> bool:
    account = passphrase_account(key_path)
    if _provider == PROVIDER_1PASSWORD:
        return _op_delete(SERVICE_PASSPHRASE, account)
    if not _HAS_KEYRING or not key_path:
        return False
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
