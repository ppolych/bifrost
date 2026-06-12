# Repository Guidelines

## Project Structure & Module Organization

Bifrost is a single-process Python 3.10+ desktop app built with PyQt6. The entry point is `bifrost_app.py`, which owns the main window and wires together the UI, session manager, and macros. Keep backend and persistence logic in `core/`; this package should stay mostly UI-free except for minimal Qt platform types such as `QFont` or `QStandardPaths`. Put PyQt widgets and dialogs in `widgets/`. SVG assets live under `res/icons/material/`. Tests are in `tests/` and mirror user-facing behavior and core utilities.

## Build, Test, and Development Commands

```bash
pip install -r requirements.txt
```

Installs runtime dependencies declared in both `requirements.txt` and `pyproject.toml`.

```bash
python bifrost_app.py
bifrost-cm
```

Runs the app directly, or through the installed console script after `pip install .`.

```bash
pytest -q
pytest tests/test_selection.py::test_word_extends_url -q
```

Runs the full suite or a single test. Qt is configured for headless tests in `tests/conftest.py`.

## Coding Style & Naming Conventions

Use idiomatic Python with 4-space indentation and descriptive `snake_case` names for functions, variables, modules, and test files. Classes use `PascalCase`. Preserve the existing separation between `core` logic and `widgets` UI code. For JSON persistence, use the project helpers in `core.platform_utils` so writes remain atomic. Do not store passwords or key passphrases in JSON; route credential work through `core.credentials`.

Keep files short and focused: every source, test, and documentation file should stay at or below 300 lines. If a change would push a file over 300 lines, split the responsibility into a new focused module or test file instead of extending the oversized file.

## Testing Guidelines

The test suite uses `pytest`. Add focused tests for backend utilities, persistence changes, terminal behavior, session-tree logic, and UI workflows that can run headlessly. Tests that need a `QApplication` should request the `qapp` fixture. Prefer explicit behavioral names such as `test_quick_connect_parses_ssh_port`.

## Commit & Pull Request Guidelines

Recent commits use short imperative subjects, for example `Fix terminal thread shutdown` and `Add remote Docker and monitor details`. Keep commits scoped and describe the behavior change, not the implementation detail alone. Pull requests should include a concise summary, test evidence such as `pytest -q`, linked issues when applicable, and screenshots or recordings for visible UI changes.

## Security & Configuration Tips

Application state is stored under the platform-specific `bifrost` config directory via `QStandardPaths.AppConfigLocation`. Avoid hard-coded user paths. Keep SSH host-key, keyring, and SFTP changes conservative: the SFTP browser should reuse the terminal SSH client instead of triggering a second authentication flow.
