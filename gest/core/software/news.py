"""Read Gentoo news items via eselect.

Listing and reading item content work unprivileged; *marking* items read needs
root (the backend's MarkNewsRead), so the frontend reads here and persists reads
through the backend.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

Runner = Callable[[list[str]], str]
_LINE = re.compile(r"\[(\d+)\]\s+(.*?)\s*(\d{4}-\d{2}-\d{2})\s+(.*)")
# Accepted "mark read" selectors: every item, only-new items, or one number.
_SELECTOR = re.compile(r"^(all|new|[1-9][0-9]*)$")
# An indented "  Key    Value" header line in a read item's header block.
_HEADER = re.compile(r"^\s+([A-Z][A-Za-z-]*)\s{2,}(.+)$")


@dataclass(slots=True)
class NewsItem:
    number: int
    status: str
    date: str
    title: str

    @property
    def unread(self) -> bool:
        return self.status.upper() == "N"


@dataclass(slots=True)
class NewsContent:
    """A read news item split into its header block and body lines."""

    headers: list[tuple[str, str]] = field(default_factory=list)  # (label, value)
    body: list[str] = field(default_factory=list)                 # body lines


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


def parse_content(text: str) -> NewsContent:
    """Split a read item into its header block (Title/Author/Posted/…) and body.

    ``eselect news read`` prints a leading item-id slug, an indented aligned
    header block, a blank line, then the body (with ``[1] http…`` footnotes).
    Pure and CI-testable. Malformed input degrades to an all-body result.
    """
    lines = text.splitlines()
    idx = 0
    # A leading, non-indented slug line precedes the header block — skip it only
    # when the next line actually is a header (so we never eat real body text).
    if (len(lines) > 1 and not _HEADER.match(lines[0]) and lines[0].strip()
            and _HEADER.match(lines[1])):
        idx = 1
    headers: list[tuple[str, str]] = []
    while idx < len(lines) and (m := _HEADER.match(lines[idx])):
        headers.append((m.group(1), m.group(2).strip()))
        idx += 1
    while idx < len(lines) and not lines[idx].strip():   # blank(s) after headers
        idx += 1
    body = lines[idx:]
    while body and not body[-1].strip():                 # trim trailing blanks
        body.pop()
    return NewsContent(headers, body)


def mark_read_argv(selector: str, eselect: str = "eselect") -> list[str]:
    """Build the ``eselect news read`` argv, validating the selector.

    ``selector`` is ``"all"``, ``"new"``, or a positive item number (as a
    string). Kept here — pure and dependency-free — so the root backend and the
    tests share one validated command shape rather than trusting a bus caller.
    Raises :class:`ValueError` on anything else.
    """
    sel = selector.strip()
    if not _SELECTOR.match(sel):
        raise ValueError(f"invalid news selector: {selector!r}")
    return [eselect, "news", "read", sel]
