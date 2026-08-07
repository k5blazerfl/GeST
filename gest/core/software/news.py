"""Read Gentoo news items via eselect (read-only, as the user).

Listing and reading item content work unprivileged; *marking* items read needs
root (a later backend step), so this module is a viewer only.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

Runner = Callable[[list[str]], str]
_LINE = re.compile(r"\[(\d+)\]\s+(.*?)\s*(\d{4}-\d{2}-\d{2})\s+(.*)")


@dataclass(slots=True)
class NewsItem:
    number: int
    status: str
    date: str
    title: str

    @property
    def unread(self) -> bool:
        return self.status.upper() == "N"


def _default_runner(argv: list[str]) -> str:
    try:
        # stdout only — reading prints content there; a mark-read permission
        # error may go to stderr when run as an unprivileged user.
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def list_news(runner: Runner | None = None) -> list[NewsItem]:
    run = runner or _default_runner
    items = []
    for line in run(["eselect", "news", "list"]).splitlines():
        m = _LINE.search(line)
        if m:
            num, status, date, title = m.groups()
            items.append(NewsItem(int(num), status.strip(), date, title.strip()))
    return items


def read_news(number: int, runner: Runner | None = None) -> str:
    run = runner or _default_runner
    return run(["eselect", "news", "read", str(number)]).strip()
