"""Portage tree sync — parse ``emerge --sync``'s per-repository progress.

``emerge --sync`` streams verbose rsync/git transfer output; the useful signal is
two per-repo markers: a start line ``>>> Syncing repository 'X' …`` and a result
line ``Action: sync for repo: X, returned code = N``. Parsing them lets the UI
show a compact per-repository status list instead of the raw stream. Pure and
CI-testable. (Which repos actually sync comes from ``repos.conf`` — see
:func:`gest.core.repos.reader.enabled_repos`.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_START_RE = re.compile(r">>> Syncing repository '(?P<repo>[^']+)'")
_RESULT_RE = re.compile(
    r"sync for repo:\s+(?P<repo>[\w][\w.+-]*),\s+returned code\s*=\s*(?P<code>-?\d+)")


@dataclass(slots=True)
class SyncEvent:
    kind: str                 # "start" (repo began) | "result" (repo finished)
    repo: str
    code: int | None = None   # exit code on a "result" event (0 = ok)


def parse_sync_event(line: str) -> SyncEvent | None:
    """Parse an ``emerge --sync`` start/result marker line, else None."""
    m = _START_RE.search(line)
    if m:
        return SyncEvent("start", m.group("repo"))
    m = _RESULT_RE.search(line)
    if m:
        return SyncEvent("result", m.group("repo"), int(m.group("code")))
    return None
