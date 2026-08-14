"""Synthesize freedesktop ``.desktop`` launcher entries for foreign apps.

The GeST/core *write* side (HeDE's C++ ``DesktopEntry`` is the read/launch side):
build an entry with an ``Exec`` pointing at a Gangway/Drydock launcher stub, an
icon, and optional jump-list ``Actions``, then write it into the user's XDG
applications dir so it appears in ``helm-menu``.

Pure and CI-testable: rendering/parsing and ``Exec`` quoting are string work; only
:func:`write_entry`/:func:`remove_entry` touch the filesystem (atomically).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

APPLICATIONS_DIR = "~/.local/share/applications"

# Exec field codes (%f %u %U …) — stripped when we reuse an existing Exec line.
_FIELD_CODE = re.compile(r"%[fFuUdDnNickvm%]")
# Chars that force an Exec argument to be quoted, per the Exec spec.
_NEEDS_QUOTING = re.compile(r"""[\s"'\\<>~|&;$*?#()`]""")


def strip_field_codes(exec_line: str) -> str:
    """Drop ``%f``/``%U``/… field codes and collapse the leftover spacing."""
    return re.sub(r"\s+", " ", _FIELD_CODE.sub("", exec_line)).strip()


def _quote_arg(arg: str) -> str:
    if not arg:
        return '""'
    if not _NEEDS_QUOTING.search(arg):
        return arg
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def build_exec(argv: list[str]) -> str:
    """Render an argv list into an ``Exec=`` value with correct quoting."""
    return " ".join(_quote_arg(a) for a in argv)


def _escape_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")


def _unescape_value(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")


@dataclass(slots=True)
class DesktopAction:
    """A jump-list action (right-click entry) on a launcher."""

    id: str
    name: str
    exec: str


@dataclass(slots=True)
class DesktopEntry:
    name: str
    exec: str
    icon: str = ""
    comment: str = ""
    categories: list[str] = field(default_factory=list)
    mime_types: list[str] = field(default_factory=list)
    startup_wm_class: str = ""
    terminal: bool = False
    no_display: bool = False
    actions: list[DesktopAction] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)  # e.g. X-GeST-Origin=gangway

    def render(self) -> str:
        lines = ["[Desktop Entry]", "Type=Application", f"Name={_escape_value(self.name)}",
                 f"Exec={self.exec}"]
        if self.icon:
            lines.append(f"Icon={self.icon}")
        if self.comment:
            lines.append(f"Comment={_escape_value(self.comment)}")
        if self.categories:
            lines.append("Categories=" + "".join(f"{c};" for c in self.categories))
        if self.mime_types:
            lines.append("MimeType=" + "".join(f"{m};" for m in self.mime_types))
        if self.startup_wm_class:
            lines.append(f"StartupWMClass={self.startup_wm_class}")
        if self.terminal:
            lines.append("Terminal=true")
        if self.no_display:
            lines.append("NoDisplay=true")
        for key, value in self.extra.items():
            lines.append(f"{key}={_escape_value(value)}")
        if self.actions:
            lines.append("Actions=" + "".join(f"{a.id};" for a in self.actions))
        for action in self.actions:
            lines += ["", f"[Desktop Action {action.id}]",
                      f"Name={_escape_value(action.name)}", f"Exec={action.exec}"]
        return "\n".join(lines) + "\n"

    @classmethod
    def parse(cls, text: str) -> DesktopEntry:
        groups = _parse_groups(text)
        entry = groups.get("Desktop Entry", {})
        actions = []
        for aid in _split_list(entry.get("Actions", "")):
            grp = groups.get(f"Desktop Action {aid}", {})
            actions.append(DesktopAction(id=aid, name=_unescape_value(grp.get("Name", "")),
                                         exec=grp.get("Exec", "")))
        known = {"Type", "Name", "Exec", "Icon", "Comment", "Categories", "MimeType",
                 "StartupWMClass", "Terminal", "NoDisplay", "Actions"}
        return cls(
            name=_unescape_value(entry.get("Name", "")),
            exec=entry.get("Exec", ""),
            icon=entry.get("Icon", ""),
            comment=_unescape_value(entry.get("Comment", "")),
            categories=_split_list(entry.get("Categories", "")),
            mime_types=_split_list(entry.get("MimeType", "")),
            startup_wm_class=entry.get("StartupWMClass", ""),
            terminal=entry.get("Terminal", "").lower() == "true",
            no_display=entry.get("NoDisplay", "").lower() == "true",
            actions=actions,
            extra={k: _unescape_value(v) for k, v in entry.items() if k not in known},
        )


def _split_list(value: str) -> list[str]:
    return [part for part in value.split(";") if part]


def _parse_groups(text: str) -> dict[str, dict[str, str]]:
    groups: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = {}
            groups[line[1:-1]] = current
        elif current is not None and "=" in line:
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
    return groups


def entry_path(desktop_id: str, applications_dir: str = APPLICATIONS_DIR) -> Path:
    return Path(applications_dir).expanduser() / f"{desktop_id}.desktop"


def write_entry(entry: DesktopEntry, desktop_id: str,
                applications_dir: str = APPLICATIONS_DIR) -> Path:
    """Write ``entry`` to ``<applications_dir>/<desktop_id>.desktop`` atomically
    (0644, dir created 0755). Returns the path."""
    path = entry_path(desktop_id, applications_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(entry.render())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def remove_entry(desktop_id: str, applications_dir: str = APPLICATIONS_DIR) -> bool:
    path = entry_path(desktop_id, applications_dir)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
