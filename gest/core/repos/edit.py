"""Edit an existing repository's fields in its repos.conf fragment.

Changing a repo's ``sync-type`` / ``sync-uri`` / ``priority`` means rewriting
its section in whichever ``/etc/portage/repos.conf/*.conf`` defines it, touching
only the named keys and leaving everything else (other keys, other sections)
verbatim. :func:`locate` finds that file; :func:`set_fields` does the rewrite.
Both are pure/IO-light and CI-testable. The main-repo mirror picker
(:mod:`gest.core.repos.mirrors`) is the single-key special case of this.
"""

from __future__ import annotations

import glob
import os

from gest.core.portage import paths
from gest.core.portage.codec import ini


def _keyname(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("[") or "=" not in stripped:
        return ""
    return stripped.split("=", 1)[0].strip().lower()


def set_fields(text: str, repo: str, fields: dict[str, str]) -> str:
    """Return ``text`` with ``[repo]``'s keys set from ``fields``.

    Each ``key: value`` in ``fields`` (keys lower-case, e.g. ``sync-uri``) is
    replaced in place, or inserted at the end of the section if missing; an
    empty value deletes that key. Every other line is preserved. If the section
    (or the whole file) is absent, a minimal ``[repo]`` override fragment is
    appended — Portage merges it over its built-in default.
    """
    header = f"[{repo}]"
    remaining = dict(fields)
    out: list[str] = []
    in_section = False

    def flush() -> None:
        for key, value in remaining.items():
            if value:
                out.append(f"{key} = {value}")
        remaining.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section:
                flush()
            in_section = stripped == header
            out.append(line)
            continue
        if in_section and _keyname(line) in remaining:
            value = remaining.pop(_keyname(line))
            if value:
                out.append(f"{_keyname(line)} = {value}")
            continue                      # empty value → drop the key
        out.append(line)

    if in_section:
        flush()

    if any(remaining.values()):           # section not present → append fragment
        if out and out[-1].strip():
            out.append("")
        out.append(header)
        for key, value in remaining.items():
            if value:
                out.append(f"{key} = {value}")

    return "\n".join(out).rstrip("\n") + "\n"


def locate(conf_dir: str | None, name: str) -> tuple[str, str]:
    """``(path, text)`` for the fragment defining ``[name]``.

    Returns the first ``*.conf`` whose sections include ``name`` with its current
    text; if none defines it (e.g. it comes from Portage's built-in default), a
    fresh ``<conf_dir>/<name>.conf`` path with empty text — an override to write.
    """
    conf_dir = conf_dir or paths.repos_conf_dir()
    for path in sorted(glob.glob(os.path.join(conf_dir, "*.conf"))):
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        _defaults, sections = ini.parse(text)
        if any(sect.name == name for sect in sections):
            return path, text
    return os.path.join(conf_dir, f"{name}.conf"), ""
