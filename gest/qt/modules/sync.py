"""Sync Portage Tree module: show the syncable repos, then run ``emerge --sync``
live.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from gest.core.repos.reader import enabled_repos
from gest.qt.modules._stream import OperationModule
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="sync", title="Sync Portage Tree", category="Software", icon="view-refresh"
)


def _syncable_preview() -> str:
    repos = [r for r in enabled_repos() if getattr(r, "sync_uri", "")]
    if not repos:
        return "No repositories have a sync URI configured."
    lines = [f"{r.name}\t{getattr(r, 'sync_type', '') or '—'}\t"
             f"{getattr(r, 'sync_uri', '')}" for r in repos]
    return "Repositories that will sync:\n\n" + "\n".join(lines)


def factory() -> QWidget:
    return OperationModule(
        run_label="Sync",
        preview_fn=_syncable_preview,
        op_factory=lambda: (
            lambda backend, on_progress, on_finished:
            backend.sync(on_progress=on_progress, on_finished=on_finished)
        ),
    )
