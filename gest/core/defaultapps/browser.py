"""Curated default-web-browser catalog + the pure ``xdg-settings`` argv/paths.

This is the *cockpit* answer to "which browser handles the web", not a store: a
short, hand-picked list — each entry an install atom plus the ``.desktop`` id
``xdg-settings`` uses to make it the default. Everything here is pure and
CI-testable; a thin caller (the Qt module) runs ``xdg-settings`` and installs
the atom through the Software backend.

The reference implementation for the whole *default-apps* family — a Default
Mail / Default Media control is this file with a different catalog and property.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# ``xdg-settings`` knows this property directly; setting it also wires the
# http/https scheme handlers, so we don't hand-roll ``xdg-mime`` here.
_PROP = "default-web-browser"


@dataclass(frozen=True)
class Browser:
    id: str  # stable short key (used in the UI's item data)
    name: str  # display name
    atom: str  # portage atom to install — prefer -bin: a 90s install, not a 4h compile
    desktop_id: str  # the ``.desktop`` basename xdg-settings sets as default
    summary: str  # one-line cockpit blurb
    recommended: bool = False


# Hand-picked, -bin-first so a casual pick is a quick install rather than a
# multi-hour source build. Presentation order = this order; the recommended one
# leads. (Atoms/desktop ids are the values to confirm against a real target.)
BROWSERS: tuple[Browser, ...] = (
    Browser(
        "firefox",
        "Firefox",
        "www-client/firefox-bin",
        "firefox",
        "Wayland-native, no compile — the safe default.",
        recommended=True,
    ),
    Browser(
        "chrome",
        "Google Chrome",
        "www-client/google-chrome",
        "google-chrome",
        "Google's browser, for people who already live in Chrome.",
    ),
    Browser(
        "brave",
        "Brave",
        "www-client/brave-bin",
        "brave-browser",
        "Chromium with privacy defaults and built-in blocking.",
    ),
    Browser(
        "ungoogled",
        "Ungoogled Chromium",
        "www-client/ungoogled-chromium-bin",
        "chromium-browser",
        "Chromium with Google integration stripped out.",
    ),
)


def by_id(browser_id: str) -> Browser | None:
    return next((b for b in BROWSERS if b.id == browser_id), None)


def by_desktop_id(desktop_id: str) -> Browser | None:
    """Map an ``xdg-settings`` answer (``firefox.desktop``) back to a catalog
    entry, tolerating a present-or-absent ``.desktop`` suffix."""
    key = desktop_id.strip()
    if key.endswith(".desktop"):
        key = key[: -len(".desktop")]
    return next((b for b in BROWSERS if b.desktop_id == key), None)


def get_default_argv() -> list[str]:
    """``xdg-settings get default-web-browser``."""
    return ["xdg-settings", "get", _PROP]


def set_default_argv(desktop_id: str) -> list[str]:
    """``xdg-settings set default-web-browser <id>.desktop`` (suffix ensured)."""
    if not desktop_id.endswith(".desktop"):
        desktop_id = f"{desktop_id}.desktop"
    return ["xdg-settings", "set", _PROP, desktop_id]


def parse_default(output: str) -> Browser | None:
    """Turn ``xdg-settings get`` stdout into a catalog entry (or ``None`` if the
    current default is unset or something we don't offer)."""
    return by_desktop_id(output) if output.strip() else None


# Standard locations a browser's launcher lands in — the ``.desktop`` existing
# there is our "installed enough to be the default" signal. Pure list; the thin
# caller checks the filesystem.
_APP_DIRS: tuple[str, ...] = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    "~/.local/share/applications",
)


def desktop_probe_paths(browser: Browser) -> list[Path]:
    """Where ``browser``'s ``.desktop`` would live if it were installed."""
    name = f"{browser.desktop_id}.desktop"
    return [Path(d).expanduser() / name for d in _APP_DIRS]


def is_installed(browser: Browser) -> bool:
    """True if the browser's ``.desktop`` exists in a standard app dir."""
    return any(p.exists() for p in desktop_probe_paths(browser))
