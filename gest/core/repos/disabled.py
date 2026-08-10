"""GeST's record of repositories it disabled, so they can be re-added easily.

When GeST disables a repository it drops its ``repos.conf`` entry (via ``eselect
repository disable``, which keeps the files on disk) but saves the repo's sync
info here — an INI file at ``/etc/portage/gest/disabled`` — so the user can
re-enable it straight from the list without retyping the URI. Re-enabling
``eselect repository add``\\ s it back from the saved info; the file record is
then dropped. Pure parse/render, CI-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from gest.core.portage import paths
from gest.core.portage.codec import ini

STATE_NAME = "disabled"


@dataclass(slots=True)
class DisabledRepo:
    name: str
    sync_type: str = ""
    sync_uri: str = ""
    priority: str = ""


def state_path(root: str | None = None) -> str:
    """The disabled-repos state file, ``/etc/portage/gest/disabled``."""
    return paths.gest_state(STATE_NAME, root)


def parse(text: str) -> list[DisabledRepo]:
    """Parse the INI state file into DisabledRepo rows (first-seen order)."""
    _defaults, sections = ini.parse(text)
    return [
        DisabledRepo(
            name=s.name,
            sync_type=s.entries.get("sync-type", ""),
            sync_uri=s.entries.get("sync-uri", ""),
            priority=s.entries.get("priority", ""),
        )
        for s in sections
    ]


def render(repos: list[DisabledRepo]) -> str:
    """Render rows to INI text (sorted by name). Empty list -> '' (deletes file)."""
    sections: list[ini.Section] = []
    for r in sorted(repos, key=lambda x: x.name):
        entries: dict[str, str] = {}
        if r.sync_type:
            entries["sync-type"] = r.sync_type
        if r.sync_uri:
            entries["sync-uri"] = r.sync_uri
        if r.priority:
            entries["priority"] = r.priority
        sections.append(ini.Section(r.name, entries))
    return ini.render(sections)


def upsert(repos: list[DisabledRepo], repo: DisabledRepo) -> list[DisabledRepo]:
    """Return ``repos`` with ``repo`` added or replaced (matched by name)."""
    return [r for r in repos if r.name != repo.name] + [repo]


def without(repos: list[DisabledRepo], name: str) -> list[DisabledRepo]:
    """Return ``repos`` without the entry named ``name``."""
    return [r for r in repos if r.name != name]
