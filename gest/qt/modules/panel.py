"""Panel Layout module: a doorway to HeDE's panel editor (helm-barnacle).

The "one engine, two doors" design (docs/design/barnacle.md): the panel editor
itself is ``helm-barnacle``, which writes hede.conf [panel] applets and the bar
picks up live. This Control Center page is the second door — it opens that same
editor rather than reimplementing the layout logic in Python.
"""

from __future__ import annotations

import subprocess

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from gest.qt.panel import panel_editor_command
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="panel",
    title="Panel Layout",
    category="Personalization",
    icon="preferences-desktop-panel",
)


class PanelModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        intro = QLabel(
            "Choose which applets appear on the panel and the order they sit in. "
            "Changes apply to the bar as you make them."
        )
        intro.setWordWrap(True)
        self._edit = QPushButton("Edit panel…")
        self._status = QLabel()
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self._edit)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._edit.clicked.connect(self._on_edit)

    def _on_edit(self) -> None:
        # helm-barnacle is a GUI window, so launch it detached — a blocking
        # subprocess.run would freeze the Control Center for the editor's whole
        # lifetime, and start_new_session keeps the editor alive if this closes.
        try:
            subprocess.Popen(panel_editor_command(), start_new_session=True)
        except (FileNotFoundError, OSError):
            self._status.setText("helm-barnacle not found — install HeDE.")
            return
        self._status.setText("Opening the panel editor…")


def factory() -> QWidget:
    return PanelModule()
