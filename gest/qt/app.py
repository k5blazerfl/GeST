"""gest-settings — the standalone GeST Control Center (PySide6)."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gest.qt.registry import Registry


class ControlCenter(QWidget):
    """A category tree + a stacked module pane (YaST / System-Settings shape)."""

    def __init__(self, registry: Registry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GeST — Control Center")
        self.resize(820, 560)
        self._registry = registry
        self._widgets: dict[str, QWidget] = {}  # id -> instantiated widget (cache)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMaximumWidth(240)
        self.stack = QStackedWidget()
        self.stack.addWidget(QLabel("Select a module.", alignment=Qt.AlignCenter))

        layout = QHBoxLayout(self)
        layout.addWidget(self.tree)
        layout.addWidget(self.stack, 1)

        for category, entries in registry.by_category().items():
            cat = QTreeWidgetItem(self.tree, [category])
            cat.setExpanded(True)
            cat.setFlags(cat.flags() & ~Qt.ItemIsSelectable)
            for entry in entries:
                item = QTreeWidgetItem(cat, [entry.descriptor.title])
                item.setData(0, Qt.UserRole, entry.descriptor.id)

        self.tree.currentItemChanged.connect(self._on_selected)

    def _on_selected(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        module_id = current.data(0, Qt.UserRole)
        if module_id:
            self.activate(module_id)

    def activate(self, module_id: str) -> QWidget:
        """Lazily build (once) and show a module; returns its widget."""
        if module_id not in self._widgets:
            entry = next(e for e in self._registry.entries() if e.descriptor.id == module_id)
            widget = entry.factory()
            self._widgets[module_id] = widget
            self.stack.addWidget(widget)
        self.stack.setCurrentWidget(self._widgets[module_id])
        return self._widgets[module_id]

    def select_first(self) -> None:
        for i in range(self.tree.topLevelItemCount()):
            cat = self.tree.topLevelItem(i)
            if cat.childCount() > 0:
                self.tree.setCurrentItem(cat.child(0))
                return


def parse_embed_arg(args: list[str]) -> str | None:
    """The module id from ``--embed <id>``, or None (full Control Center)."""
    for i, a in enumerate(args):
        if a == "--embed":
            return args[i + 1] if i + 1 < len(args) else None
    return None


def embed_window(registry: Registry, module_id: str) -> QWidget | None:
    """A top-level window hosting a single module (for HeDE popovers, 2d).

    Same module widget as the Control Center — just a different frame. Returns
    None if the id is unknown.
    """
    entry = next((e for e in registry.entries() if e.descriptor.id == module_id), None)
    if entry is None:
        return None
    host = QWidget()
    host.setWindowTitle(f"GeST — {entry.descriptor.title}")
    host.resize(480, 520)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(entry.factory())
    return host


def build_registry() -> Registry:
    from gest.qt.modules import (
        appearance,
        binhost,
        bootloader,
        cleanup,
        clock,
        consolefont,
        disk,
        dns,
        envd,
        eselect,
        firewall,
        hardware,
        hostname,
        hosts,
        hwflags,
        keymap,
        licenses,
        locale,
        logs,
        makeconf,
        network,
        news,
        preferences,
        privilege,
        repos,
        services,
        software,
        sshd,
        sync,
        sysctl,
        update,
        users,
        wifi,
        world,
    )

    registry = Registry()
    for mod in (hardware, hwflags, disk, software, world, repos, update, cleanup,
                sync, news, makeconf, binhost, licenses, preferences, services,
                clock, hostname, locale, keymap, consolefont, bootloader, users,
                sysctl, eselect, envd, privilege, logs, firewall, network, wifi,
                sshd, dns, hosts, appearance):
        registry.register(mod.DESCRIPTOR, mod.factory)
    return registry


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("gest-settings")
    # Match HeDE: consume the shared Helm appearance (palette + Fusion) before any
    # window is built, exactly like the shell's Start menu (menu/main.cpp). A
    # no-op until the user has themed the desktop, so a bare gest-settings keeps
    # its native look. Covers both the full Control Center and --embed windows.
    from gest.qt.theme import apply_appearance

    apply_appearance(app)
    registry = build_registry()

    embed = parse_embed_arg(app.arguments()[1:])
    if embed is not None:
        window = embed_window(registry, embed)
        if window is None:
            print(f"gest-settings: no such module '{embed}'", file=sys.stderr)
            sys.exit(2)
    else:
        window = ControlCenter(registry)
        window.select_first()

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
