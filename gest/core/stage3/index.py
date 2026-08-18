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
    """The ``latest-stage3-<arch>-<flavor>.txt`` pointer URL for ``arch``/``flavor``.

    The mirror filename includes the arch (e.g. ``latest-stage3-amd64-systemd.txt``);
    the arch-less form 404s.
    """
    base = mirror.rstrip("/")
    return f"{base}/releases/{arch}/autobuilds/latest-stage3-{arch}-{flavor}.txt"


_STAGE3_EXTS = (".tar.xz", ".tar.gz", ".tar.bz2")


def parse_latest(text: str) -> tuple[str, int]:
    """Parse a ``latest-stage3-*.txt`` pointer into ``(relpath, size_bytes)``.

    The pointer is **PGP-clearsigned**, so it is not "comments then one data line":
    it carries ``-----BEGIN/END PGP …-----`` armor and ``Hash:`` headers around the
    real line. So rather than trust line position, find the data line by shape —
    ``<subdir>/<tarball>.tar.<ext> <size_bytes> [extra…]`` (e.g.
    ``20240728T170331Z/stage3-amd64-systemd-20240728T170331Z.tar.xz 268435456``).
    Blank/comment/armor lines are skipped; raises ``ValueError`` if none is found.
    """
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-----")):
            continue  # blank, comment, or PGP armor delimiter
        parts = line.split()
        if (len(parts) >= 2 and parts[0].endswith(_STAGE3_EXTS)
                and parts[1].isdigit()):
            return parts[0], int(parts[1])
    raise ValueError("no stage3 data line in index")


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
