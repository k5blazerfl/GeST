"""Pure hashing + ``.DIGESTS`` parsing and the mandatory integrity check.

Gentoo publishes each stage3's hashes in a co-located ``.DIGESTS`` file using
exactly two algorithms — BLAKE2B and SHA512 — the same pair
``packaging/release-overlay.py`` computes for a release tarball. This module
parses those expected hashes, recomputes them over the downloaded bytes, and
compares. ``verify_hashes`` is the **mandatory** integrity gate the backend runs
*before* any unpack: unpacking an unverified (or tampered) tarball over a target
root is exactly the destructive mistake the whole module guards against.
"""

from __future__ import annotations

import hashlib
import os
import re

# The two algorithms a Gentoo .DIGESTS carries (and that we verify against).
ALGORITHMS = ("BLAKE2B", "SHA512")

# A hex digest (BLAKE2B-512 / SHA512 are 128 hex chars; accept any long hex run
# so we tolerate other digest widths a mirror might list).
_HEX_RE = re.compile(r"\A[0-9a-fA-F]{16,}\Z")


def parse_digests(text: str, filename: str) -> dict[str, str]:
    """Expected hashes for ``filename`` from a Gentoo ``.DIGESTS`` ``text``.

    Returns ``{"BLAKE2B": hex, "SHA512": hex}`` for the entries whose associated
    file basename matches ``filename`` — empty if the file is not listed.

    Handles both shapes a ``.DIGESTS`` can take, keyed off whether the ``#``
    header carries the hash inline:

    * ``# <ALGO> <hexhash>`` followed by a ``<filename>`` line (the shape this
      module documents and tests against), and
    * ``# <ALGO> HASH`` followed by a ``<hexhash>  <filename>`` data line (the
      shape a live Gentoo mirror emits).

    Only BLAKE2B and SHA512 are kept; other algorithms in the file are ignored.
    """
    target = os.path.basename(filename)
    result: dict[str, str] = {}
    pending_algo: str | None = None
    pending_hash: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            parts = line[1:].split()
            if not parts:
                continue
            algo = parts[0].upper()
            inline = parts[1] if len(parts) >= 2 and _HEX_RE.match(parts[1]) else None
            pending_algo, pending_hash = algo, inline.lower() if inline else None
            continue
        if pending_algo is None:
            continue
        if pending_hash is not None:
            # Inline-hash shape: this line is the filename.
            if os.path.basename(line) == target:
                result[pending_algo] = pending_hash
        else:
            # Hash+filename data line: "<hex>  <filename>".
            bits = line.split()
            if (len(bits) >= 2 and _HEX_RE.match(bits[0])
                    and os.path.basename(bits[-1]) == target):
                result[pending_algo] = bits[0].lower()
        pending_algo = pending_hash = None
    return {k: v for k, v in result.items() if k in ALGORITHMS}


def hashes_of(data: bytes) -> dict[str, str]:
    """Compute BLAKE2B + SHA512 hex digests of ``data`` (as ``.DIGESTS`` names
    them), the same two algorithms ``release-overlay.py`` uses."""
    return {
        "BLAKE2B": hashlib.blake2b(data).hexdigest(),
        "SHA512": hashlib.sha512(data).hexdigest(),
    }


def verify_hashes(data: bytes, expected: dict[str, str]) -> bool:
    """True iff every algorithm in ``expected`` matches ``hashes_of(data)``.

    Requires at least one expected hash (an empty ``expected`` — e.g. a
    ``.DIGESTS`` that did not list the file — can never satisfy this, so an
    unverifiable download is refused). Case-insensitive on the hex. This is the
    mandatory integrity check; the backend aborts before unpacking if it is
    False.
    """
    if not expected:
        return False
    actual = hashes_of(data)
    for algo, want in expected.items():
        have = actual.get(algo)
        if have is None or have.lower() != want.lower():
            return False
    return True
