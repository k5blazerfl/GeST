"""Official Gentoo rsync mirrors for the main repository.

The main ``::gentoo`` ebuild tree is synced over rsync from one of Gentoo's
mirrors; a geographically near mirror makes ``emerge --sync`` faster. This
module carries the curated list of Gentoo's rsync rotations (from
https://api.gentoo.org/mirrors/rsync.xml) and the pure rewrite that points the
main repo's ``sync-uri`` at a chosen mirror by editing
``/etc/portage/repos.conf/gentoo.conf`` — preserving every other setting
(location, verification keys, auto-sync), so nothing about repository security
changes. This is the ``sync-uri`` (rsync) side of what ``mirrorselect -r`` does;
distfiles mirrors (``GENTOO_MIRRORS``) are a make.conf concern handled elsewhere.
"""

from __future__ import annotations

import os

from gest.core.portage import paths

# The rsync module every Gentoo rotation exposes the tree under.
_MODULE = "/gentoo-portage"

# (region label, host). The rsync URI is ``rsync://<host>/gentoo-portage``. The
# first entry is the global rotation (Portage's default); the rest are Gentoo's
# per-country rotations. Kept short and human-picked rather than the full API
# dump — a user chooses their region, or enters a custom URI.
_HOSTS: list[tuple[str, str]] = [
    ("Default (global rotation)", "rsync.gentoo.org"),
    ("Australia", "rsync.au.gentoo.org"),
    ("Belgium", "rsync.be.gentoo.org"),
    ("Bulgaria", "rsync.bg.gentoo.org"),
    ("Canada", "rsync.ca.gentoo.org"),
    ("China", "rsync.cn.gentoo.org"),
    ("Czech Republic", "rsync.cz.gentoo.org"),
    ("Denmark", "rsync.dk.gentoo.org"),
    ("France", "rsync.fr.gentoo.org"),
    ("Germany", "rsync.de.gentoo.org"),
    ("Japan", "rsync.jp.gentoo.org"),
    ("Netherlands", "rsync.nl.gentoo.org"),
    ("Poland", "rsync.pl.gentoo.org"),
    ("Portugal", "rsync.pt.gentoo.org"),
    ("Romania", "rsync.ro.gentoo.org"),
    ("Russia", "rsync.ru.gentoo.org"),
    ("Serbia", "rsync.rs.gentoo.org"),
    ("Slovakia", "rsync.sk.gentoo.org"),
    ("South Africa", "rsync.za.gentoo.org"),
    ("South Korea", "rsync.kr.gentoo.org"),
    ("Sweden", "rsync.se.gentoo.org"),
    ("Switzerland", "rsync.ch.gentoo.org"),
    ("Taiwan", "rsync.tw.gentoo.org"),
    ("United Kingdom", "rsync.uk.gentoo.org"),
    ("United States", "rsync.us.gentoo.org"),
]


def mirrors() -> list[tuple[str, str]]:
    """The official rsync mirrors as ``(region, rsync-uri)`` pairs."""
    return [(label, f"rsync://{host}{_MODULE}") for label, host in _HOSTS]


def gentoo_conf_path(conf_dir: str | None = None) -> str:
    """Path of the main repo's config fragment (``repos.conf/gentoo.conf``)."""
    return os.path.join(conf_dir or paths.repos_conf_dir(), "gentoo.conf")


def _is_sync_uri(line: str) -> bool:
    stripped = line.strip()
    return "=" in stripped and stripped.split("=", 1)[0].strip().lower() == "sync-uri"


def set_sync_uri(text: str, repo: str, uri: str) -> str:
    """Return ``gentoo.conf`` content with ``[repo]``'s ``sync-uri`` set to ``uri``.

    Every other line is preserved verbatim — only the ``sync-uri`` value under
    the main repo's section changes (verification keys, location and auto-sync
    are untouched). If the section has no ``sync-uri`` line it is inserted; if
    the section (or the whole file) is absent, a minimal override fragment is
    appended, which Portage merges over its built-in default.
    """
    header = f"[{repo}]"
    out: list[str] = []
    in_section = False
    replaced = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not replaced:          # leaving target w/o a sync-uri
                out.append(f"sync-uri = {uri}")
                replaced = True
            in_section = stripped == header
            out.append(line)
            continue
        if in_section and _is_sync_uri(line):
            out.append(f"sync-uri = {uri}")
            replaced = True
            continue
        out.append(line)

    if in_section and not replaced:                   # target section ran to EOF
        out.append(f"sync-uri = {uri}")
        replaced = True

    if not replaced:                                  # no such section anywhere
        if out and out[-1].strip():
            out.append("")
        out += [header, f"sync-uri = {uri}"]

    return "\n".join(out).rstrip("\n") + "\n"
