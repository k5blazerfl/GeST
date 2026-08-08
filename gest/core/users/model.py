"""Data types for the Users & Groups module."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class User:
    name: str
    uid: int
    gid: int
    gecos: str = ""       # full name / comment field
    home: str = ""
    shell: str = ""

    @property
    def full_name(self) -> str:
        # GECOS is comma-separated; the first field is the display name.
        return self.gecos.split(",", 1)[0]

    @property
    def system(self) -> bool:
        # By Gentoo/shadow convention normal accounts start at UID 1000.
        return self.uid < 1000


@dataclass(slots=True)
class Group:
    name: str
    gid: int
    members: list[str] = field(default_factory=list)

    @property
    def system(self) -> bool:
        return self.gid < 1000
