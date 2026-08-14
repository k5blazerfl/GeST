"""Software module: a read-only Portage summary, via core/software."""

from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from gest.core.software.reader import counts
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="software", title="Software", category="Software", icon="applications-system"
)


class SoftwareModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        form = QFormLayout(self)
        for key, value in counts().items():
            form.addRow(f"{key.capitalize()}:", QLabel(str(value)))


def factory() -> QWidget:
    return SoftwareModule()
