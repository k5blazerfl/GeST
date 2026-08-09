"""Parse, validate and render /etc/fstab entries — pure and CI-testable.

The backend does the privileged write; everything about *what* a valid line is,
which mount points are off-limits, and how to splice one entry into the file
without disturbing the rest lives here. A malformed fstab can make a system
unbootable, so validation is strict (no whitespace, no comment/newline
injection) and the essential mounts are protected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Mount points that must never be edited or removed from the TUI.
PROTECTED_MOUNTS = frozenset({"/", "/boot", "/efi", "/boot/efi"})

# Path-like fields: no whitespace and no shell metacharacters (these end up in
# /etc/fstab and are passed to `mount`).
_MOUNTPOINT_RE = re.compile(r"\A/[A-Za-z0-9/._@+-]*\Z")
_SPEC_RE = re.compile(r"\A[A-Za-z0-9/][A-Za-z0-9/._=:@+-]*\Z")
_FSTYPE_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")
# Options: comma-separated tokens of safe characters (defaults, rw, noatime,
# nofail, uid=1000, x-systemd.automount, subvol=/@home, …).
_OPTIONS_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._=:,+@/-]*\Z")
_SPEC_PREFIXES = ("UUID=", "LABEL=", "PARTUUID=", "PARTLABEL=", "ID=")


@dataclass(slots=True)
class FstabEntry:
    spec: str                 # device / UUID= / LABEL=
    mountpoint: str           # absolute path, or "none"/"swap" for swap
    fstype: str
    options: str = "defaults"
    dump: int = 0
    passno: int = 0
    protected: bool = False


def is_protected(entry: FstabEntry) -> bool:
    """True for the essential mounts and any swap entry (read-only in GeST)."""
    return entry.mountpoint in PROTECTED_MOUNTS or entry.fstype == "swap"


def valid_spec(spec: str) -> bool:
    if not _SPEC_RE.match(spec) or len(spec) > 255:
        return False
    return spec.startswith("/") or spec.startswith(_SPEC_PREFIXES)


def valid_mountpoint(mp: str) -> bool:
    if mp in ("none", "swap"):
        return True
    return bool(_MOUNTPOINT_RE.match(mp)) and len(mp) <= 255


def valid_mount_target(mp: str) -> bool:
    """A mountpoint we can actually `mount`/`umount` — a real absolute path."""
    return mp.startswith("/") and valid_mountpoint(mp)


def valid_fstype(fstype: str) -> bool:
    return bool(_FSTYPE_RE.match(fstype)) and len(fstype) <= 64


def valid_options(options: str) -> bool:
    return bool(_OPTIONS_RE.match(options)) and ",," not in options and len(options) <= 512


def valid_entry(entry: FstabEntry) -> bool:
    return (
        valid_spec(entry.spec)
        and valid_mountpoint(entry.mountpoint)
        and valid_fstype(entry.fstype)
        and valid_options(entry.options)
        and entry.dump in (0, 1)
        and 0 <= entry.passno <= 2
    )


def _mountpoint_of(line: str) -> str | None:
    """The mountpoint field of a data line, or None for blank/comment lines."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    parts = stripped.split()
    return parts[1] if len(parts) >= 2 else None


def parse_fstab(text: str) -> list[FstabEntry]:
    """Parse /etc/fstab text into entries (blank/comment lines skipped)."""
    entries: list[FstabEntry] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 4:
            continue
        spec, mountpoint, fstype, options = parts[:4]
        dump = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
        passno = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0
        entry = FstabEntry(spec, mountpoint, fstype, options, dump, passno)
        entry.protected = is_protected(entry)
        entries.append(entry)
    return entries


def render_entry(entry: FstabEntry) -> str:
    """Render one entry as a tab-separated fstab line (no trailing newline)."""
    return "\t".join([
        entry.spec, entry.mountpoint, entry.fstype, entry.options,
        f"{entry.dump} {entry.passno}",
    ])


def _rejoin(lines: list[str]) -> str:
    text = "\n".join(lines)
    return text + "\n" if text else text


def upsert_entry(text: str, entry: FstabEntry) -> str:
    """Add `entry`, or replace the existing line with the same mountpoint.

    All other lines (comments, blanks, unrelated entries) are preserved.
    """
    new_line = render_entry(entry)
    lines = text.splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if _mountpoint_of(line) == entry.mountpoint:
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)
    return _rejoin(lines)


def remove_entry(text: str, mountpoint: str) -> str:
    """Drop the data line whose mountpoint matches; keep everything else."""
    lines = [line for line in text.splitlines() if _mountpoint_of(line) != mountpoint]
    return _rejoin(lines)
