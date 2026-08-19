"""Appearance module: pick a world (biome) + light/dark + accent; drives
helm-theme (Phase 2e).

A desktop module in the GeST frontend that writes theme config through HeDE's
``helm-theme`` tool (the single source of truth), so GTK apps and the HeDE shell
both follow the choice. The world picker is the primary control — choosing a
world sets its wallpaper + accent for the whole shell; the fields below are the
fine-grained overrides.
"""

from __future__ import annotations

import subprocess

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.qt.appearance import (
    default_config_path,
    list_worlds,
    read_appearance,
    read_world,
    theme_args,
    world_args,
)
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="appearance", title="Appearance", category="Personalization",
    icon="preferences-desktop-theme",
)

_THUMB = QSize(160, 90)  # 16:9 world thumbnail


class AppearanceModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        # --- world picker (the primary control) ---
        root.addWidget(QLabel("Desktop theme"))
        self._worlds = QListWidget()
        self._worlds.setViewMode(QListWidget.IconMode)
        self._worlds.setIconSize(_THUMB)
        self._worlds.setGridSize(QSize(_THUMB.width() + 20, _THUMB.height() + 34))
        self._worlds.setResizeMode(QListWidget.Adjust)
        self._worlds.setMovement(QListWidget.Static)
        self._worlds.setSelectionMode(QListWidget.SingleSelection)
        self._worlds.setSpacing(6)
        self._worlds.setUniformItemSizes(True)
        self._worlds.setMinimumHeight(_THUMB.height() + 54)
        self._worlds.itemClicked.connect(self._apply_world)
        root.addWidget(self._worlds)

        # --- fine-grained overrides ---
        form_host = QWidget()
        form = QFormLayout(form_host)

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
        root.addWidget(form_host)

        dark, accent = read_appearance(default_config_path())
        self._dark.setChecked(dark)
        self._accent.setText(accent)
        self._populate_worlds()

    def _populate_worlds(self) -> None:
        """Fill the picker from helm-theme; hide it if no worlds/HeDE."""
        self._worlds.clear()
        active = read_world(default_config_path())
        worlds = list_worlds()
        self._worlds.setVisible(bool(worlds))
        for w in worlds:
            item = QListWidgetItem(w.name)
            item.setData(Qt.UserRole, w.id)
            item.setData(Qt.UserRole + 1, w.accent)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            if w.wallpaper:
                pm = QPixmap(w.wallpaper)
                if not pm.isNull():
                    item.setIcon(
                        QIcon(
                            pm.scaled(
                                _THUMB,
                                Qt.KeepAspectRatioByExpanding,
                                Qt.SmoothTransformation,
                            )
                        )
                    )
            self._worlds.addItem(item)
            if w.id == active:
                item.setSelected(True)
                self._worlds.setCurrentItem(item)

    def _apply_world(self, item: QListWidgetItem) -> None:
        world_id = item.data(Qt.UserRole)
        try:
            result = subprocess.run(
                ["helm-theme", *world_args(world_id)],
                capture_output=True, text=True, check=False,
            )
        except FileNotFoundError:
            self._status.setText("helm-theme not found — install HeDE.")
            return
        if result.returncode != 0:
            self._status.setText(f"Failed: {result.stderr.strip()}")
            return
        self._status.setText(f"Switched to {item.text()}.")
        # A world switch adopts the world's accent and clears any explicit one:
        # reflect that in the field (empty = "use the world's accent").
        self._accent.clear()
        world_accent = item.data(Qt.UserRole + 1)
        if world_accent:
            self._accent.setPlaceholderText(world_accent)

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
