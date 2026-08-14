"""Boot & Kernel module: show boot/kernel info; regenerate the GRUB config."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from gest.core.bootloader.reader import boot_info
from gest.core.kernel.reader import build_info
from gest.qt.boot import boot_summary, regenerate_grub
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="bootloader", title="Boot & Kernel", category="System", icon="computer"
)


class BootloaderModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._info = QLabel()
        self._regen = QPushButton("Regenerate GRUB config")
        self._status = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(self._info)
        layout.addWidget(self._regen)
        layout.addWidget(self._status)
        layout.addStretch(1)

        self._regen.clicked.connect(self._on_regen)
        self._refresh()

    def _refresh(self) -> None:
        rows = boot_summary(boot_info(), build_info())
        self._info.setText("\n".join(f"{k}: {v}" for k, v in rows))

    def _on_regen(self) -> None:
        ok, msg = regenerate_grub()
        self._status.setText("GRUB config regenerated." if ok else f"Failed: {msg}")


def factory() -> QWidget:
    return BootloaderModule()
