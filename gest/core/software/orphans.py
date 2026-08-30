"""Repo-orphan detection — installed packages with no ebuild in any repo.

Distinct from the depclean orphans in :mod:`gest.core.software.cleanup`: those
are packages nothing in ``@world`` needs (``emerge --depclean`` would remove
them). A *repo-orphan* here is still wanted — it just has no ebuild anywhere to
reinstall or update it from, because an overlay renamed or dropped it, an overlay
was removed, or ::gentoo cleaned it out. Portage's safe depclean never removes
these while they are ``@world`` members (protected) or still depended on (kept),
so they linger invisibly. This module surfaces them with the two facts a user
needs before acting: whether each is a ``@world`` member and what still depends
on it.

Detection itself lives in :func:`gest.core.software.reader.list_unavailable`
(it needs the Portage API); everything here is thin assembly plus pure report
logic, so it is CI-testable by injecting a fake detector/size/deps.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from gest.core.software import reader
from gest.core.software.cleanup import human_size

Detector = Callable[[], "list[tuple[str, str, bool]]"]
SizeFn = Callable[[str], int]
DepsFn = Callable[[str], "list[str]"]


@dataclass(slots=True)
class RepoOrphan:
    """An installed package with no ebuild in any configured repo."""

    cp: str                                       # category/name
    version: str = ""
    world_member: bool = False                    # explicitly in @world
    size: int = 0                                 # installed size in bytes
    required_by: list[str] = field(default_factory=list)  # installed dependents

    @property
    def category(self) -> str:
        return self.cp.split("/", 1)[0]

    @property
    def package(self) -> str:
        return self.cp.split("/", 1)[1] if "/" in self.cp else self.cp

    @property
    def cpv(self) -> str:
        return f"{self.cp}-{self.version}" if self.version else self.cp

    @property
    def safe_to_unmerge(self) -> bool:
        """No installed package still depends on it — removing it strands nothing."""
        return not self.required_by


@dataclass(slots=True)
class OrphanReport:
    """The set of repo-orphans plus derived views the UIs need for guardrails."""

    orphans: list[RepoOrphan] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.orphans)

    @property
    def total_size(self) -> int:
        return sum(o.size for o in self.orphans)

    @property
    def world_members(self) -> list[RepoOrphan]:
        return [o for o in self.orphans if o.world_member]

    @property
    def depended_on(self) -> list[RepoOrphan]:
        """Orphans something still needs — unsafe to unmerge without care."""
        return [o for o in self.orphans if o.required_by]


def scan_orphans(
    *,
    detector: Detector | None = None,
    size_fn: SizeFn | None = None,
    deps_fn: DepsFn | None = None,
) -> OrphanReport:
    """Assemble the repo-orphan report (detection + size + reverse-deps).

    The three collaborators default to the live Portage-backed reader; tests
    inject fakes to exercise the pure assembly without a Gentoo host. Sorted by
    the detector (``list_unavailable`` returns rows sorted by cp).
    """
    detect = detector or reader.list_unavailable
    size_of = size_fn or reader.installed_size
    deps_of = deps_fn or reader.reverse_dependencies
    orphans = [
        RepoOrphan(
            cp=cp,
            version=version,
            world_member=world_member,
            size=size_of(cp),
            required_by=deps_of(cp),
        )
        for cp, version, world_member in detect()
    ]
    return OrphanReport(orphans=orphans)


def format_report(report: OrphanReport) -> str:
    """A compact text summary shared by the preview panes of both frontends."""
    if not report.orphans:
        return ("No unavailable packages — every installed package still has an "
                "ebuild in a configured repo.")
    lines = [
        f"{len(report.orphans)} unavailable package(s) — installed but no ebuild "
        f"in any repo ({human_size(report.total_size)}):",
        "",
    ]
    for o in report.orphans:
        tags = []
        if o.world_member:
            tags.append("@world")
        if o.required_by:
            tags.append(f"needed by {len(o.required_by)}")
        suffix = f"  [{', '.join(tags)}]" if tags else ""
        lines.append(f"  {o.cpv}  {human_size(o.size)}{suffix}")
    return "\n".join(lines)
