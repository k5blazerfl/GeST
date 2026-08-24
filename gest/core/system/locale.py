"""Read/list/validate the system locale (LANG)."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable

_LOCALE_RE = re.compile(r"\A[A-Za-z0-9._@-]+\Z")
_LANG_RE = re.compile(r'^\s*LANG\s*=\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', re.MULTILINE)

Runner = Callable[[list[str]], str]


def valid_locale(name: str) -> bool:
    return bool(name) and bool(_LOCALE_RE.match(name))


def parse_lang(text: str) -> str:
    """Pull LANG out of /etc/env.d/02locale or /etc/locale.conf."""
    match = _LANG_RE.search(text)
    return match.group(1).strip() if match else ""


def _default_runner(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def list_locales(runner: Runner | None = None) -> list[str]:
    run = runner or _default_runner
    seen = [ln.strip() for ln in run(["locale", "-a"]).splitlines() if ln.strip()]
    return sorted(set(seen))


def canonical_key(name: str) -> tuple[str, str]:
    """A comparison key that treats encoding notations as equal: ``C.UTF-8`` and
    glibc's ``locale -a`` form ``C.utf8`` map to the same key. The base name is
    kept verbatim; the charset after the first ``.`` is lowercased with ``-``/``_``
    stripped (so ``UTF-8`` == ``utf8``)."""
    base, _, enc = name.partition(".")
    return base, enc.lower().replace("-", "").replace("_", "")


def match_in(name: str, choices: list[str]) -> str:
    """The entry in ``choices`` denoting the same locale as ``name`` (notation-
    insensitive via :func:`canonical_key`), or ``name`` unchanged if none. Lets a
    picker highlight the current value even when it's stored ``C.UTF-8`` but listed
    ``C.utf8``."""
    key = canonical_key(name)
    for choice in choices:
        if canonical_key(choice) == key:
            return choice
    return name


def locale_gen_line(name: str) -> str | None:
    """The ``/etc/locale.gen`` entry (``"<locale> <charmap>"``) needed to generate
    ``name``, or ``None`` for glibc built-ins (C/POSIX and C.UTF-8) that are always
    present and need no generation. ``en_US.utf8`` and ``en_US.UTF-8`` both →
    ``"en_US.UTF-8 UTF-8"``."""
    base, _, enc = name.partition(".")
    if base in ("C", "POSIX") or not enc:
        return None
    charmap = "UTF-8" if enc.lower().replace("-", "") == "utf8" else enc.upper()
    return f"{base}.{charmap} {charmap}"


def current_locale(paths=("/etc/env.d/02locale", "/etc/locale.conf")) -> str:
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                lang = parse_lang(fh.read())
            if lang:
                return lang
        except OSError:
            continue
    return ""
