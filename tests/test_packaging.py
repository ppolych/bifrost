import tomllib
from pathlib import Path


def test_pyproject_installs_all_app_modules():
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    configured = set(data["tool"]["setuptools"]["py-modules"])
    actual = {path.stem for path in root.glob("bifrost_app*.py")}

    assert actual <= configured


def test_pyproject_installs_material_icons():
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    data_files = data["tool"]["setuptools"]["data-files"]

    assert "res/icons/material" in data_files
    assert "res/icons/material/*.svg" in data_files["res/icons/material"]


def test_icon_lookup_checks_installed_data_paths(monkeypatch):
    import core.icons as icons

    checked = []

    icons._icon.cache_clear()
    monkeypatch.setattr(icons, "_icon_dirs", lambda: ["/installed/res/icons/material"])
    monkeypatch.setattr(icons.os.path, "exists", lambda path: checked.append(path) or False)

    icon = icons.named_icon("terminal.svg")

    assert icon.isNull()
    assert checked == ["/installed/res/icons/material/terminal.svg"]
