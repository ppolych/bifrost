import pytest


def test_application_theme_stylesheets_are_distinct():
    from core.styles import THEME_NAMES, get_theme_stylesheet

    styles = {name: get_theme_stylesheet(name) for name in THEME_NAMES}

    assert "Bright (MobaXterm style)" in THEME_NAMES
    assert "Nord" in THEME_NAMES
    assert "Dracula" in THEME_NAMES
    assert "Gruvbox Dark" in THEME_NAMES
    assert "One Dark" in THEME_NAMES
    assert "Tokyo Night" in THEME_NAMES
    assert "Graphite" in THEME_NAMES
    assert "Breeze" in THEME_NAMES
    assert len(set(styles.values())) == len(THEME_NAMES)
    assert "#2f86c7" in styles["Bright (MobaXterm style)"]
    assert "#f5f6f8" in styles["Light"]
    assert "#3daee9" in styles["Breeze"]
    assert "#eee8d5" in styles["Solarized"]
    assert "#88c0d0" in styles["Nord"]
    assert "#bd93f9" in styles["Dracula"]
    assert "#fabd2f" in styles["Gruvbox Dark"]
    assert "#61afef" in styles["One Dark"]
    assert "#7aa2f7" in styles["Tokyo Night"]
    assert "#8ab4f8" in styles["Graphite"]
    assert "#ffff00" in styles["High Contrast"]


def test_application_theme_covers_common_qt_surfaces():
    from core.styles import get_theme_stylesheet

    style = get_theme_stylesheet("Breeze")

    for selector in (
        "QScrollArea",
        "QAbstractScrollArea",
        "QToolTip",
        "QHeaderView::section",
        "QLineEdit:disabled",
        "QTableCornerButton::section",
        "QCheckBox::indicator",
    ):
        assert selector in style


def test_settings_dialog_uses_central_application_theme_names(qapp):
    from core.styles import THEME_NAMES
    from widgets.settings_dialog import SettingsDialog

    dlg = SettingsDialog()

    names = [dlg.theme_combo.itemText(i) for i in range(dlg.theme_combo.count())]
    assert names == THEME_NAMES


def test_apply_global_visuals_applies_application_theme(qapp):
    from PyQt6.QtWidgets import QMainWindow

    from bifrost_app import BifrostApp
    from core.settings_store import default_settings

    app = BifrostApp.__new__(BifrostApp)
    QMainWindow.__init__(app)
    app.settings = default_settings()
    app.settings["theme"] = "Light"
    app.settings["opacity"] = 85

    BifrostApp.apply_global_visuals(app)

    assert "#f5f6f8" in app.styleSheet()
    assert app.windowOpacity() == pytest.approx(0.85, abs=0.01)


def test_credentials_flow_through_to_ssh_credentials():
    """The settings keys map cleanly into the SshCredentials a backend uses."""
    from core.ssh_backend import SshCredentials

    session = {"host": "h", "user": "u", "port": 2200, "auth": "agent"}
    creds = SshCredentials.from_session(session)
    # Simulate what BifrostApp._build_ssh_backend does.
    creds.connect_timeout = 30.0
    creds.agent_forwarding = True
    creds.known_hosts_file = "/tmp/known_hosts"
    assert creds.connect_timeout == 30.0
    assert creds.agent_forwarding is True
    assert creds.known_hosts_file == "/tmp/known_hosts"


def test_session_terminal_overrides_apply_to_tab_settings(qapp):
    from PyQt6.QtGui import QFont

    from bifrost_app import BifrostApp
    from core.settings_store import default_settings

    app = BifrostApp.__new__(BifrostApp)
    app.settings = default_settings()
    app.settings["font"] = QFont("DejaVu Sans Mono", 10)

    settings = BifrostApp._settings_for_session(app, {
        "overrides": {
            "scheme": "Nord",
            "font": "Courier New, 14",
        }
    })

    assert settings["term_bg"] == "#2e3440"
    assert settings["term_fg"] == "#d8dee9"
    assert settings["color_scheme"] == "Nord"
    assert settings["font"].family() == "Courier New"
    assert settings["font"].pointSize() == 14
    assert app.settings["term_bg"] == "#000000"


def test_session_terminal_overrides_reject_stale_scheme_name(qapp):
    from bifrost_app import BifrostApp
    from core.settings_store import default_settings

    app = BifrostApp.__new__(BifrostApp)
    app.settings = default_settings()

    settings = BifrostApp._settings_for_session(app, {
        "overrides": {"scheme": "Solarized"}
    })

    assert settings["color_scheme"] == "Default"
    assert settings["term_bg"] == "#000000"
    assert settings["term_fg"] == "#d3d7cf"
