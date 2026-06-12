from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppTheme:
    window: str
    panel: str
    panel_alt: str
    surface: str
    surface_alt: str
    text: str
    muted: str
    border: str
    accent: str
    accent_text: str
    selection: str
    danger: str


THEMES: dict[str, AppTheme] = {
    "Dark (MobaXterm style)": AppTheme(
        window="#242629", panel="#2f3337", panel_alt="#3a3f44",
        surface="#1d1f22", surface_alt="#2a2d31", text="#e6e6e6",
        muted="#a8adb3", border="#4a4f55", accent="#4f8cc9",
        accent_text="#ffffff", selection="#315f8f", danger="#e05f5f",
    ),
    "Bright (MobaXterm style)": AppTheme(
        window="#eef3f8", panel="#f8fbff", panel_alt="#dce9f6",
        surface="#ffffff", surface_alt="#edf4fb", text="#1f2d3a",
        muted="#52697d", border="#b7c8d8", accent="#2f86c7",
        accent_text="#ffffff", selection="#b9dcf4", danger="#c94f4f",
    ),
    "Light": AppTheme(
        window="#f5f6f8", panel="#ffffff", panel_alt="#eef1f4",
        surface="#ffffff", surface_alt="#e7ebef", text="#20242a",
        muted="#5e6670", border="#c9d0d8", accent="#2468a8",
        accent_text="#ffffff", selection="#cfe3f7", danger="#b3261e",
    ),
    "Breeze": AppTheme(
        window="#eff0f1", panel="#fcfcfc", panel_alt="#e5e7e9",
        surface="#ffffff", surface_alt="#f2f3f4", text="#232629",
        muted="#5f6266", border="#bdc3c7", accent="#3daee9",
        accent_text="#ffffff", selection="#93cee9", danger="#da4453",
    ),
    "Solarized": AppTheme(
        window="#eee8d5", panel="#fdf6e3", panel_alt="#eee8d5",
        surface="#fdf6e3", surface_alt="#e7dfc8", text="#073642",
        muted="#586e75", border="#93a1a1", accent="#268bd2",
        accent_text="#fdf6e3", selection="#d7e8e8", danger="#dc322f",
    ),
    "Nord": AppTheme(
        window="#2e3440", panel="#3b4252", panel_alt="#434c5e",
        surface="#242933", surface_alt="#363d4c", text="#eceff4",
        muted="#d8dee9", border="#4c566a", accent="#88c0d0",
        accent_text="#1f252f", selection="#5e81ac", danger="#bf616a",
    ),
    "Dracula": AppTheme(
        window="#282a36", panel="#343746", panel_alt="#44475a",
        surface="#21222c", surface_alt="#383a4a", text="#f8f8f2",
        muted="#c4c8d4", border="#55596f", accent="#bd93f9",
        accent_text="#1f1f29", selection="#6272a4", danger="#ff5555",
    ),
    "Gruvbox Dark": AppTheme(
        window="#282828", panel="#3c3836", panel_alt="#504945",
        surface="#1d2021", surface_alt="#32302f", text="#ebdbb2",
        muted="#d5c4a1", border="#665c54", accent="#fabd2f",
        accent_text="#282828", selection="#7c6f64", danger="#fb4934",
    ),
    "One Dark": AppTheme(
        window="#282c34", panel="#323842", panel_alt="#3b4250",
        surface="#21252b", surface_alt="#2c313a", text="#abb2bf",
        muted="#8b94a5", border="#4b5263", accent="#61afef",
        accent_text="#1b2027", selection="#3e5c7f", danger="#e06c75",
    ),
    "Tokyo Night": AppTheme(
        window="#1a1b26", panel="#24283b", panel_alt="#2f3549",
        surface="#16161e", surface_alt="#202437", text="#c0caf5",
        muted="#9aa5ce", border="#414868", accent="#7aa2f7",
        accent_text="#10131d", selection="#364a82", danger="#f7768e",
    ),
    "Graphite": AppTheme(
        window="#202124", panel="#2b2d31", panel_alt="#36393f",
        surface="#18191c", surface_alt="#25272b", text="#f1f3f4",
        muted="#bdc1c6", border="#5f6368", accent="#8ab4f8",
        accent_text="#111418", selection="#3c5f8f", danger="#f28b82",
    ),
    "High Contrast": AppTheme(
        window="#000000", panel="#000000", panel_alt="#101010",
        surface="#000000", surface_alt="#181818", text="#ffffff",
        muted="#ffffff", border="#ffffff", accent="#ffff00",
        accent_text="#000000", selection="#ffff00", danger="#ff4d4d",
    ),
}

THEME_NAMES = list(THEMES.keys())
DEFAULT_THEME = "Dark (MobaXterm style)"
