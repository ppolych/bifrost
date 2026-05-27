"""Named terminal color schemes.

Each preset declares only `bg` and `fg` — the 16-color ANSI palette stays as
the xterm defaults in `widgets/terminal.py`. Future work could expose
per-scheme palettes if needed.

`apply_scheme(settings, name)` mutates `settings["term_bg"]` and
`settings["term_fg"]` in place; returns the mutated dict for chaining.
"""

from __future__ import annotations

# (bg, fg)
SCHEMES: dict[str, tuple[str, str]] = {
    "Default":         ("#000000", "#d3d7cf"),
    "Solarized Dark":  ("#002b36", "#839496"),
    "Solarized Light": ("#fdf6e3", "#657b83"),
    "Dracula":         ("#282a36", "#f8f8f2"),
    "Nord":            ("#2e3440", "#d8dee9"),
    "Monokai":         ("#272822", "#f8f8f2"),
    "Gruvbox Dark":    ("#282828", "#ebdbb2"),
    "Tomorrow Night":  ("#1d1f21", "#c5c8c6"),
    "Black on White":  ("#ffffff", "#000000"),
}

DEFAULT_NAME = "Default"


def scheme_names() -> list[str]:
    return list(SCHEMES.keys())


def apply_scheme(settings: dict, name: str) -> dict:
    bg, fg = SCHEMES.get(name, SCHEMES[DEFAULT_NAME])
    settings["term_bg"] = bg
    settings["term_fg"] = fg
    return settings


def scheme_for(bg: str, fg: str) -> str | None:
    """Reverse lookup — name matching a (bg, fg) pair, else None."""
    bg = (bg or "").lower()
    fg = (fg or "").lower()
    for name, (b, f) in SCHEMES.items():
        if b.lower() == bg and f.lower() == fg:
            return name
    return None
