# Bifrost Connection Manager

A cross-platform desktop terminal and connection manager, MobaXterm-style,
built with PyQt6. Single-process desktop app — no server component.

Bifrost groups local shells, SSH sessions, WSL distros, and (stub) RDP entries
into a tree of saved sessions, with a built-in SFTP browser that attaches to
the same authenticated SSH channel as the terminal so file transfers don't
require a second login.

> **Status:** early. The terminal stack, SSH, SFTP, credential storage, and
> session/macro persistence work today. RDP, VNC, Serial, and Telnet beyond
> shelling out to the system `telnet` binary are not implemented yet — see
> *Not done yet* below.

## Features

- **Real VT100/xterm emulator** — `pyte`-backed, with 16-color + truecolor
  attributes, bold/italic/underline, configurable cursor shape (block /
  underline / bar), visible bell, scrollback via the mouse wheel.
- **Local PTY on every platform.** POSIX uses `pty.fork()`; Windows uses
  ConPTY via `pywinpty`. Same reader-thread model end-to-end.
- **SSH** via `paramiko` with an interactive host-key prompt that writes to
  `~/.ssh/known_hosts` on accept, optional agent forwarding, configurable
  keepalive, and a connect thread so the GUI never blocks.
- **System-keyring credential storage** (`python-keyring`) for SSH passwords
  and key passphrases — never persisted to `sessions.json`. Save-on-success
  flow: only stores after the connection comes up clean.
- **SFTP browser** sharing the terminal's `SSHClient` (no second auth
  roundtrip). Drag-and-drop uploads, theme-aware file icons, optional
  external editor for remote files.
- **MultiExec** — broadcast input to every open terminal tab; viewport tints
  red while broadcasting.
- **Quick-connect toolbar** with a method picker (SSH / Telnet / Local / WSL)
  and per-method input parsing.
- **Wake-on-LAN** — both per-session (right-click an SSH session with a `mac`
  field set) and one-off from the toolbar.
- **Macros** — record a sequence of keystrokes and replay them into the
  active terminal.
- **Network/utility tools** in the sidebar — port scanner, network scanner,
  IP calculator, SSH keypair generator (Ed25519, OpenSSH-format).
- **Session tree with favorites**, two-column rows, folder icons that swap
  on expand/collapse. Double-click a leaf to connect.
- **Detach a tab** into a standalone window without losing state.

## Install

```bash
pip install -r requirements.txt
```

Runtime dependencies: PyQt6, psutil, pyte, paramiko, keyring; `pywinpty` on
Windows. Same set is declared in `pyproject.toml` so `pip install .` also
works.

Requires Python 3.10+.

## Run

```bash
python bifrost_app.py
# or, after `pip install .`
bifrost-cm
```

## Configuration

All state is written under `QStandardPaths.AppConfigLocation` for the
application name `bifrost`:

| Platform | Path |
| --- | --- |
| Linux   | `~/.config/bifrost/` |
| macOS   | `~/Library/Application Support/bifrost/` |
| Windows | `%APPDATA%\bifrost\` |

Contents: `sessions.json`, `macros.json`, `settings.json`, `bifrost.log`.

Per-session shell transcripts (when `auto_log` is on) go to
`./logs/<name>_<timestamp>.log` in the current working directory.

JSON writes are atomic (tempfile + `os.replace`).


## Tests

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

`tests/conftest.py` already sets `QT_QPA_PLATFORM=offscreen` as a default and
exposes a `qapp` session fixture for tests that need a live `QApplication`.

Run a single test:

```bash
pytest tests/test_selection.py -q
pytest tests/test_selection.py::test_word_extends_url -q
```

## Project layout

- `core/` — backend, persistence, OS integration. No Qt UI code beyond
  `QFont` / `QStandardPaths`.
- `widgets/` — PyQt6 UI components.
- `bifrost_app.py` — `BifrostApp(QMainWindow)`, the single orchestrator and
  CLI entry point (`main()`).

See `CLAUDE.md` for the load-bearing architectural details (terminal stack
layering, key-routing/MultiExec contract, sidebar tab indexes, settings
plumbing).

## Not done yet

- RDP / VNC / Serial session backends (some UI tabs exist).
- Cross-scrollback selection — today selections live in the visible buffer.
- In-process Telnet — quick-connect shells out to the system `telnet`.
- PyInstaller spec files for `.app` / `.exe` bundles.
- Cluster / auto-cluster mode (the broader version of MultiExec).

## License

Bifrost is licensed under the **GNU General Public License v3.0 or later**.
See [`LICENSE`](LICENSE) for the full text.

PyQt6 itself is GPL v3 (or commercial), which makes GPL v3 a natural fit
for this project.

## Third-party notices

Bundled SVG icons under `res/icons/material/` are from Google's
[Material Symbols](https://github.com/google/material-design-icons) project,
distributed under the Apache License 2.0. See
[`NOTICE-THIRD-PARTY.md`](NOTICE-THIRD-PARTY.md) for the full list and the
modification note.
