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
