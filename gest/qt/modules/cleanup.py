"""Clean Up Packages module: preview the depclean orphans, then unmerge live."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from gest.core.software.cleanup import plan_cleanup
from gest.qt.modules._stream import OperationModule
from gest.qt.registry import ModuleDescriptor
from gest.qt.software import format_cleanup_plan

DESCRIPTOR = ModuleDescriptor(
    id="depclean", title="Clean Up Packages", category="Software",
    icon="edit-clear",
)


def factory() -> QWidget:
    return OperationModule(
        run_label="Clean up",
        preview_fn=lambda: format_cleanup_plan(plan_cleanup()),
        op_factory=lambda: (
            lambda backend, on_progress, on_finished:
            backend.depclean(on_progress=on_progress, on_finished=on_finished)
        ),
    )
