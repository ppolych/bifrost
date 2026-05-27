"""Tests for the one-shot asbru → bifrost config dir migration."""

from __future__ import annotations

import os


def test_migration_copies_when_new_dir_is_empty(qapp, tmp_path, monkeypatch):
    """A legacy ~/.config/asbru-style dir is copied into the new bifrost dir
    on first run."""
    import core.platform_utils as pu

    legacy = tmp_path / "old"
    legacy.mkdir()
    (legacy / "sessions.json").write_text('{"User sessions": []}')
    (legacy / "macros.json").write_text("{}")
    nested = legacy / "logs"
    nested.mkdir()
    (nested / "x.log").write_text("hi")

    new = tmp_path / "new"
    new.mkdir()

    monkeypatch.setattr(pu, "config_dir", lambda: str(new))
    monkeypatch.setattr(pu, "_legacy_asbru_dirs", lambda: [str(legacy)])

    result = pu.migrate_legacy_config()
    assert result is not None
    count, source = result
    assert count == 3
    assert source == str(legacy)
    assert (new / "sessions.json").read_text() == '{"User sessions": []}'
    assert (new / "logs" / "x.log").read_text() == "hi"


def test_migration_is_skipped_when_new_dir_already_populated(qapp, tmp_path, monkeypatch):
    """Idempotency: if anything already lives in the new dir, don't migrate."""
    import core.platform_utils as pu

    legacy = tmp_path / "old"
    legacy.mkdir()
    (legacy / "sessions.json").write_text("{}")

    new = tmp_path / "new"
    new.mkdir()
    (new / "settings.json").write_text("{}")  # makes new dir non-empty

    monkeypatch.setattr(pu, "config_dir", lambda: str(new))
    monkeypatch.setattr(pu, "_legacy_asbru_dirs", lambda: [str(legacy)])

    assert pu.migrate_legacy_config() is None
    # New file still untouched; legacy file NOT copied over.
    assert not (new / "sessions.json").exists()


def test_migration_noop_when_no_legacy_dir(qapp, tmp_path, monkeypatch):
    import core.platform_utils as pu

    new = tmp_path / "new"
    new.mkdir()
    monkeypatch.setattr(pu, "config_dir", lambda: str(new))
    monkeypatch.setattr(pu, "_legacy_asbru_dirs", lambda: [
        str(tmp_path / "does-not-exist"),
    ])

    assert pu.migrate_legacy_config() is None


def test_credentials_legacy_fallback(qapp, monkeypatch):
    """Passwords saved under the legacy 'asbru-ssh' service must still be
    readable through the new 'bifrost-ssh' service name."""
    import keyring
    import keyring.backend

    class _Mem(keyring.backend.KeyringBackend):
        priority = 999
        def __init__(self):
            super().__init__()
            self.store: dict[tuple[str, str], str] = {}
        def get_password(self, service, username):
            return self.store.get((service, username))
        def set_password(self, service, username, password):
            self.store[(service, username)] = password
        def delete_password(self, service, username):
            self.store.pop((service, username), None)

    backend = _Mem()
    prev = keyring.get_keyring()
    keyring.set_keyring(backend)
    try:
        from core import credentials

        # Pre-rename world: password stored under the old service name.
        backend.store[("asbru-ssh", "alice@host:22")] = "legacy-pw"

        # New-service lookup must transparently fall back to the legacy slot.
        assert credentials.get_password("alice", "host", 22) == "legacy-pw"

        # Forget must clean both new and legacy slots.
        assert credentials.forget_password("alice", "host", 22) is True
        assert backend.store == {}
    finally:
        keyring.set_keyring(prev)
