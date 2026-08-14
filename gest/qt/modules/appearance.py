"""Appearance module: pick light/dark + accent; drives helm-theme (Phase 2e).

A desktop module in the GeST frontend that writes theme config through HeDE's
``helm-theme`` tool (the single source of truth), so GTK apps and the HeDE shell
both follow the choice.
"""

from __future__ import annotations

import subprocess

from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from gest.qt.appearance import default_config_path, read_appearance, theme_args
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="appearance", title="Appearance", category="Desktop", icon="preferences-desktop-theme"
)


class AppearanceModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        form = QFormLayout(self)

        self._dark = QCheckBox("Use a dark theme")
        self._accent = QLineEdit()
        self._accent.setPlaceholderText("#33d6c8")
        self._gtk = QLineEdit()
        self._gtk.setPlaceholderText("(auto: Adwaita / Adwaita-dark)")
        self._icon = QLineEdit()
        self._status = QLabel()

        pick = QPushButton("Choose…")
        pick.clicked.connect(self._pick_accent)
        accent_row = QHBoxLayout()
        accent_row.setContentsMargins(0, 0, 0, 0)
        accent_row.addWidget(self._accent, 1)
        accent_row.addWidget(pick)
        accent_widget = QWidget()
        accent_widget.setLayout(accent_row)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)

        form.addRow(self._dark)
        form.addRow("Accent:", accent_widget)
        form.addRow("GTK theme:", self._gtk)
        form.addRow("Icon theme:", self._icon)
        form.addRow(apply_btn)
        form.addRow(self._status)

        dark, accent = read_appearance(default_config_path())
        self._dark.setChecked(dark)
        self._accent.setText(accent)

    def _pick_accent(self) -> None:
        color = QColorDialog.getColor()
        if color.isValid():
            self._accent.setText(color.name())

    def _apply(self) -> None:
        args = theme_args(
            self._dark.isChecked(),
            self._accent.text().strip(),
            self._gtk.text().strip(),
            self._icon.text().strip(),
        )
        try:
            result = subprocess.run(
                ["helm-theme", *args], capture_output=True, text=True, check=False
            )
        except FileNotFoundError:
            self._status.setText("helm-theme not found — install HeDE.")
            return
        self._status.setText(
            "Applied." if result.returncode == 0 else f"Failed: {result.stderr.strip()}"
        )


def factory() -> QWidget:
    return AppearanceModule()
