"""The MIME types and URI schemes Customs associates with foreign-app launchers.

Registration is two parts: the launcher's ``.desktop`` declares ``MimeType=`` (so
double-clicking a file offers it), and ``xdg-mime default`` makes it the default
handler. Both the type lists and the argv are pure/testable here; a thin caller
runs ``xdg-mime`` / ``update-desktop-database``.
"""

from __future__ import annotations

# Gangway (remote Windows): .rdp files and the rdp:// URI scheme.
RDP_FILE = "application/x-rdp"
RDP_SCHEME = "x-scheme-handler/rdp"
GANGWAY_TYPES = [RDP_FILE, RDP_SCHEME]

# Drydock (local Windows apps).
EXE = "application/x-ms-dos-executable"
MSI = "application/x-msi"
LNK = "application/x-ms-shortcut"
BAT = "application/x-bat"
DRYDOCK_TYPES = [EXE, MSI, LNK, BAT]

APPLICATIONS_DIR = "~/.local/share/applications"


def register_default_argv(desktop_id: str, mime_types: list[str]) -> list[str]:
    """``xdg-mime default <id>.desktop <type>…`` — makes the launcher the default
    handler for the given types."""
    return ["xdg-mime", "default", f"{desktop_id}.desktop", *mime_types]


def query_default_argv(mime_type: str) -> list[str]:
    return ["xdg-mime", "query", "default", mime_type]


def update_database_argv(applications_dir: str = APPLICATIONS_DIR) -> list[str]:
    """Refresh the MIME cache after writing/removing a launcher."""
    from pathlib import Path

    return ["update-desktop-database", str(Path(applications_dir).expanduser())]
