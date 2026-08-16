"""System Update module: preview the ``@world`` update, then run it live."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from gest.core.software.update import plan_update
from gest.qt.modules._stream import OperationModule
from gest.qt.registry import ModuleDescriptor
from gest.qt.software import format_update_plan

DESCRIPTOR = ModuleDescriptor(
    id="update", title="System Update", category="Software",
    icon="system-software-update",
)


def factory() -> QWidget:
    return OperationModule(
        run_label="Update @world",
        preview_fn=lambda: format_update_plan(plan_update()),
        op_factory=lambda: (
            lambda backend, on_progress, on_finished:
            backend.update_world(on_progress=on_progress, on_finished=on_finished)
        ),
    )
