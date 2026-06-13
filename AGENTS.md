# Repository Guidelines

## Project Structure & Module Organization

Bifrost is a single-process Python 3.10+ desktop app built with PyQt6. The
entry point is `bifrost_app.py`, which owns `BifrostApp(QMainWindow)` and the
`main()` function used by the `bifrost-cm` console script. Keep backend,
persistence, security, and OS integration logic in `core/`; keep PyQt widgets
and dialogs in `widgets/`. Tests live in `tests/`, with shared Qt setup in
`tests/conftest.py`. Static SVG icons are in `res/icons/material/`. Packaging
metadata is in `pyproject.toml`, and standalone bundle settings are in
`bifrost.spec`.

## Build, Test, and Development Commands

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
python bifrost_app.py
bifrost-cm
QT_QPA_PLATFORM=offscreen pytest -q
pytest tests/test_selection.py::test_word_extends_url -q
pyinstaller bifrost.spec
```

Use `pip install -r requirements.txt` for runtime dependencies, or
`pip install -e ".[dev]"` for editable development with pytest. Run the app
directly with `python bifrost_app.py`, or through `bifrost-cm` after install.
Use the offscreen Qt command for the full suite. PyInstaller output goes under
`dist/`.

## Coding Style & Naming Conventions

Use 4-space indentation, `snake_case` for functions, variables, modules, and
test files, and `PascalCase` for classes. There is no configured formatter or
linter, so match nearby code. Preserve the boundary between `core/` logic and
`widgets/` UI code. Keep files focused and at or below 300 lines when practical;
split new responsibilities into focused modules or tests instead of extending
large files further.

## Testing Guidelines

Tests use pytest. Name files `tests/test_*.py` and test functions `test_*`.
Tests that need Qt should request the `qapp` fixture. Add focused regression
tests for backend utilities, persistence changes, terminal behavior,
connection parsing, session-tree logic, and headless UI workflows.

## Commit & Pull Request Guidelines

Recent commits use short imperative subjects, for example `Add Serial session
backend via pyserial` and `Fix review findings across VNC, Telnet, cluster, and
search`. Keep commits scoped and describe user-visible behavior. Pull requests
should include a concise summary, test evidence such as `pytest -q`, linked
issues when applicable, and screenshots or recordings for visible UI changes.

## Architecture & Security Notes

Read `CLAUDE.md` before changing terminal routing, MultiExec, sidebar indexes,
SSH lifecycle, settings, or credential handling. Application state lives under
the platform-specific `bifrost` config directory via
`QStandardPaths.AppConfigLocation`; avoid hard-coded user paths. Persist JSON
through `core.platform_utils` atomic-write helpers. Do not store passwords or
key passphrases in JSON; route credential work through `core.credentials`. The
SFTP browser should reuse the terminal SSH client instead of triggering a
second authentication flow. Keep blocking work such as PTY reads, SSH connects,
SFTP transfers, and network scans off the GUI thread and report back through
Qt signals.
