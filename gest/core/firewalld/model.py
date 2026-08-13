"""The value a firewalld zone's permanent config reduces to for this module."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class ZoneConfig:
    """A firewalld zone's permanent allowed services and ports.

    ``services`` are named service allowances (``ssh``, ``http``, …) and
    ``ports`` are explicit ``"port/proto"`` allowances (``"22/tcp"``). Both are
    frozen sets so the value is hashable and cheap to diff against a working copy.
    """

    zone: str
    services: frozenset[str] = field(default_factory=frozenset)
    ports: frozenset[str] = field(default_factory=frozenset)
