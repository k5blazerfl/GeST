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

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, Signal
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
    boot_sync_target,
    default_config_path,
    list_worlds,
    read_appearance,
    read_boot_sync,
    read_world,
    theme_args,
    world_args,
    write_boot_sync,
)
from gest.qt.registry import ModuleDescriptor

# How long to wait after the last theme change before rebuilding the boot splash,
# so browsing several biomes coalesces into a single (heavy) initramfs rebuild.
_BOOT_SYNC_DEBOUNCE_MS = 3000


class _BootSyncWorker(QObject):
    """Runs the blocking SyncBootTheme call off the UI thread; the ~30 s
    initramfs rebuild must not freeze the Control Center."""

    done = Signal(bool, str)

    def __init__(self, accent: str, world: str) -> None:
        super().__init__()
        self._accent = accent
        self._world = world

    def run(self) -> None:
        from gest.qt.boot import sync_boot_theme

        ok, msg = sync_boot_theme(self._accent, self._world)
        self.done.emit(ok, msg)

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

        # Keep the boot splash (Plymouth + GRUB) tracking the biome. Default on;
        # the desktop background is unaffected either way.
        self._boot_sync = QCheckBox("Match the boot splash to this theme")
        self._boot_sync.setChecked(read_boot_sync(default_config_path()))
        self._boot_sync.toggled.connect(self._on_boot_sync_toggled)

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
        form.addRow(self._boot_sync)
        form.addRow(apply_btn)
        form.addRow(self._status)
        root.addWidget(form_host)

        # Debounce boot-splash rebuilds: restart on each theme change so browsing
        # biomes coalesces into one rebuild once the user settles.
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(_BOOT_SYNC_DEBOUNCE_MS)
        self._sync_timer.timeout.connect(self._run_boot_sync)
        self._sync_thread: QThread | None = None
        self._sync_worker: _BootSyncWorker | None = None

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
        self._schedule_boot_sync()

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
        if result.returncode == 0:
            self._status.setText("Applied.")
            self._schedule_boot_sync()
        else:
            self._status.setText(f"Failed: {result.stderr.strip()}")

    # --- boot-splash sync (debounced, off-thread) ---

    def _on_boot_sync_toggled(self, on: bool) -> None:
        write_boot_sync(default_config_path(), on)
        if on:
            self._schedule_boot_sync()  # catch up to the current theme now
        else:
            self._sync_timer.stop()

    def _schedule_boot_sync(self) -> None:
        """(Re)arm the debounce so the boot splash rebuilds once the user settles."""
        if self._boot_sync.isChecked():
            self._sync_timer.start()

    def _run_boot_sync(self) -> None:
        # One rebuild at a time — if the last is still running, defer.
        if self._sync_thread is not None and self._sync_thread.isRunning():
            self._sync_timer.start()
            return
        accent, world = boot_sync_target(default_config_path())
        self._status.setText("Updating the boot splash…")
        self._sync_thread = QThread(self)
        self._sync_worker = _BootSyncWorker(accent, world)
        self._sync_worker.moveToThread(self._sync_thread)
        self._sync_thread.started.connect(self._sync_worker.run)
        self._sync_worker.done.connect(self._on_boot_sync_done)
        self._sync_worker.done.connect(self._sync_thread.quit)
        self._sync_thread.start()

    def _on_boot_sync_done(self, ok: bool, msg: str) -> None:
        self._status.setText(
            "Boot splash updated." if ok else f"Boot splash sync failed: {msg}"
        )
        self._sync_worker = None


def factory() -> QWidget:
    return AppearanceModule()
