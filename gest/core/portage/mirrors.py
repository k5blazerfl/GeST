"""Gentoo mirror + main-repo configuration — the Handbook's "Repo Mirror
Selection", done GeSI-native.

A fresh GeSI install left two Portage things unmanaged: a first-class main-repo
config (``repos.conf/gentoo.conf`` with a chosen sync mirror — it leaned on the
stage3's built-in default), and ``GENTOO_MIRRORS`` (distfile download mirrors) in
make.conf. This module owns:

- the mirror **catalog** — a bundled offline snapshot, so selection works with no
  live mirror list (offline-first, like the timezone list);
- a light latency **probe** to auto-pick the fastest mirrors at install time;
- the pure **renderers** for ``GENTOO_MIRRORS`` and ``repos.conf/gentoo.conf``.

It stays firmly on Gentoo's own mechanisms — ``GENTOO_MIRRORS``, ``repos.conf``
``sync-uri``, standard https/rsync mirrors — no fork of Gentoo's infrastructure.
See ``docs/design/gesi-repos-mirrors.md``.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

#: Where the main ebuild repo lives on the target (matches the stage3 default, so an
#: explicit gentoo.conf overrides the built-in one without moving the tree).
GENTOO_REPO_LOCATION = "/var/db/repos/gentoo"
#: The rsync rotation Gentoo uses when no specific mirror is chosen.
DEFAULT_SYNC_URI = "rsync://rsync.gentoo.org/gentoo-portage"
#: Coarse default region for the offline fallback — the project's audience is
#: US-Eastern (Tallahassee, FL), matching the timezone/locale defaults.
DEFAULT_REGION = "us-east"


@dataclass(frozen=True, slots=True)
class Mirror:
    """One Gentoo mirror: an https distfiles URL (a ``GENTOO_MIRRORS`` entry) and a
    matching rsync ``sync-uri`` for the main repo, tagged with a coarse region."""

    name: str
    region: str          # "us-east" | "us-west" | "eu" | "asia" | "oceania" | "global"
    distfiles: str       # https distfiles URL (GENTOO_MIRRORS entry)
    rsync: str           # rsync sync-uri for repos.conf/gentoo.conf


#: A curated offline snapshot of well-known official Gentoo mirrors. Not exhaustive —
#: enough to auto-pick a fast one from anywhere, and to fall back sensibly offline.
#: Refreshable against https://api.gentoo.org/mirrors/distfiles.xml (design phase 2).
CATALOG: tuple[Mirror, ...] = (
    Mirror("Gentoo official (distfiles.gentoo.org)", "global",
           "https://distfiles.gentoo.org/", DEFAULT_SYNC_URI),
    Mirror("MIT (US-East)", "us-east",
           "https://mirrors.mit.edu/gentoo-distfiles/", "rsync://rsync.us.gentoo.org/gentoo-portage"),
    Mirror("Rackspace (US)", "us-east",
           "https://mirror.rackspace.com/gentoo/", "rsync://rsync.us.gentoo.org/gentoo-portage"),
    Mirror("OSU OSL (US-West)", "us-west",
           "https://gentoo.osuosl.org/", "rsync://rsync.us.gentoo.org/gentoo-portage"),
    Mirror("RWTH Aachen (DE)", "eu",
           "https://ftp.halifax.rwth-aachen.de/gentoo/", "rsync://rsync.de.gentoo.org/gentoo-portage"),
    Mirror("Bytemark (UK)", "eu",
           "https://mirror.bytemark.co.uk/gentoo/", "rsync://rsync.uk.gentoo.org/gentoo-portage"),
    Mirror("TUNA Tsinghua (CN)", "asia",
           "https://mirrors.tuna.tsinghua.edu.cn/gentoo/", "rsync://rsync.cn.gentoo.org/gentoo-portage"),
    Mirror("AARNet (AU)", "oceania",
           "https://mirror.aarnet.edu.au/pub/gentoo/", "rsync://rsync.au.gentoo.org/gentoo-portage"),
)


@dataclass(frozen=True, slots=True)
class MirrorSelection:
    """The chosen distfile mirrors (``GENTOO_MIRRORS``, fastest-first) + the main-repo
    sync mirror. ``probed`` is True when latency-picked, False for the offline default."""

    distfiles: tuple[str, ...]
    sync_uri: str
    sync_type: str = "rsync"
    probed: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.distfiles and self.sync_uri)


# --- probe ------------------------------------------------------------------

def probe_latency(uri: str, *, timeout: float = 2.0) -> float | None:
    """TCP-connect latency (seconds) to a mirror's host, or ``None`` if unreachable
    within ``timeout``. A connect-time probe (no download) — fast, and enough to rank
    mirrors by proximity/responsiveness. I/O; injected in tests."""
    parts = urlsplit(uri)
    host = parts.hostname
    if not host:
        return None
    port = parts.port or {"https": 443, "http": 80, "rsync": 873}.get(parts.scheme, 443)
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return time.monotonic() - start
    except OSError:
        return None


Probe = Callable[..., "float | None"]


def rank_mirrors(catalog: Sequence[Mirror] = CATALOG, *, probe: Probe = probe_latency,
                 top: int = 3, timeout: float = 2.0) -> list[Mirror]:
    """The ``top`` fastest reachable mirrors by connect latency (unreachable ones
    dropped). Empty when none answer (offline) — the caller falls back to a default."""
    scored: list[tuple[float, int, Mirror]] = []
    for i, m in enumerate(catalog):
        lat = probe(m.distfiles, timeout=timeout)
        if lat is not None:
            scored.append((lat, i, m))       # i keeps the sort stable on ties
    scored.sort()
    return [m for _lat, _i, m in scored[:top]]


def default_selection(*, catalog: Sequence[Mirror] = CATALOG,
                      region: str = DEFAULT_REGION, top: int = 3) -> MirrorSelection:
    """The offline fallback: the region's mirrors (else the whole catalog), no probe."""
    regional = [m for m in catalog if m.region == region] or list(catalog)
    picks = regional[:top]
    return MirrorSelection(distfiles=tuple(m.distfiles for m in picks),
                           sync_uri=picks[0].rsync if picks else DEFAULT_SYNC_URI,
                           sync_type="rsync", probed=False)


def select_mirrors(*, catalog: Sequence[Mirror] = CATALOG, probe: Probe = probe_latency,
                   top: int = 3, timeout: float = 2.0,
                   region: str = DEFAULT_REGION) -> MirrorSelection:
    """Auto-pick the fastest mirrors at install time (latency probe), falling back to
    the offline regional default when nothing answers. This is the wizard's Get Online
    hook — run it off the UI thread; it does network I/O."""
    ranked = rank_mirrors(catalog, probe=probe, top=top, timeout=timeout)
    if ranked:
        return MirrorSelection(distfiles=tuple(m.distfiles for m in ranked),
                               sync_uri=ranked[0].rsync, sync_type="rsync", probed=True)
    return default_selection(catalog=catalog, region=region, top=top)


# --- renderers (pure) -------------------------------------------------------

def render_gentoo_mirrors(mirrors: MirrorSelection | Sequence[str]) -> str:
    """The ``GENTOO_MIRRORS`` value (space-joined distfile URLs)."""
    uris = mirrors.distfiles if isinstance(mirrors, MirrorSelection) else tuple(mirrors)
    return " ".join(uris)


def gentoo_repos_conf(sync_uri: str = DEFAULT_SYNC_URI, *, sync_type: str = "rsync",
                      location: str = GENTOO_REPO_LOCATION) -> str:
    """The target's ``repos.conf/gentoo.conf`` — a first-class main-repo entry with the
    chosen sync mirror and ``auto-sync = yes``. Makes the gentoo repo visible + updatable
    instead of relying on the stage3's built-in default."""
    return (
        "[gentoo]\n"
        f"location = {location}\n"
        f"sync-type = {sync_type}\n"
        f"sync-uri = {sync_uri}\n"
        "auto-sync = yes\n"
    )
