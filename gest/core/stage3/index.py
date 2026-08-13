"""Pure parsers + URL builders for the Gentoo stage3 mirror index.

A mirror publishes, per arch/variant, a ``latest-stage3-<flavor>.txt`` pointer
whose single data line names the current tarball (a dated sub-directory + the
filename) and its byte size. Everything here is pure — building the pointer URL,
parsing it, and deriving the tarball / ``.DIGESTS`` / ``.asc`` URLs — except
``fetch_text``, a thin ``urllib`` wrapper (retries, like
``packaging/release-overlay.py``) for the *small* unprivileged index/DIGESTS
files. The large tarball is downloaded by the privileged backend, not here.
"""

from __future__ import annotations

import time
import urllib.request

# Default Gentoo distfiles mirror; overridable (a user may prefer a local mirror).
MIRROR = "https://distfiles.gentoo.org"

_FETCH_RETRIES = 5
_FETCH_TIMEOUT = 30
_RETRY_WAIT = 3


def latest_url(mirror: str, arch: str, flavor: str) -> str:
    """The ``latest-stage3-<flavor>.txt`` pointer URL for ``arch``/``flavor``."""
    base = mirror.rstrip("/")
    return f"{base}/releases/{arch}/autobuilds/latest-stage3-{flavor}.txt"


def parse_latest(text: str) -> tuple[str, int]:
    """Parse a ``latest-stage3-*.txt`` pointer into ``(relpath, size_bytes)``.

    Comment lines (``#``) and blanks are skipped; the data line is
    ``<subdir>/<filename> <size_bytes>`` (e.g.
    ``20240728T170331Z/stage3-amd64-openrc-20240728T170331Z.tar.xz 268435456``).
    Newer indexes may append extra whitespace-separated fields after the size;
    only the first two tokens are significant. Raises ``ValueError`` if no data
    line is found.
    """
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"malformed stage3 index line: {raw!r}")
        relpath, size = parts[0], parts[1]
        try:
            return relpath, int(size)
        except ValueError as exc:
            raise ValueError(f"malformed stage3 index size: {size!r}") from exc
    raise ValueError("no data line in stage3 index")


def tarball_url(mirror: str, arch: str, relpath: str) -> str:
    """The stage3 tarball URL for the ``relpath`` parsed from the index."""
    base = mirror.rstrip("/")
    return f"{base}/releases/{arch}/autobuilds/{relpath.lstrip('/')}"


def digests_url(tarball: str) -> str:
    """The co-located ``.DIGESTS`` URL for a tarball URL."""
    return tarball + ".DIGESTS"


def signature_url(tarball: str) -> str:
    """The co-located ``.asc`` (detached GPG signature) URL for a tarball URL."""
    return tarball + ".asc"


def fetch_text(url: str) -> str:
    """Fetch a small text resource (the index or a ``.DIGESTS``) over HTTPS.

    Unprivileged — the frontend can call it to resolve a selection before
    invoking the backend. Retries like ``release-overlay.py``'s ``load_tarball``;
    raises the last exception if every attempt fails.
    """
    last: Exception | None = None
    for attempt in range(_FETCH_RETRIES):
        try:
            with urllib.request.urlopen(url, timeout=_FETCH_TIMEOUT) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # pragma: no cover - network
            last = exc
            if attempt + 1 < _FETCH_RETRIES:
                time.sleep(_RETRY_WAIT)
    raise RuntimeError(f"failed to fetch {url}: {last}")
