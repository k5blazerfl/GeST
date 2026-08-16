"""World & Package Sets module: browse @world and the package sets, and drop a
package from @world (deselect — does not unmerge), via the polkit-gated backend.

Custom-set creation/editing is not built here yet (the urwid screen has it); this
covers the common case — viewing the sets and pruning @world.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.software.reader import list_installed
from gest.core.software.sets import list_sets
from gest.qt.registry import ModuleDescriptor
from gest.qt.software import deselect, package_status

DESCRIPTOR = ModuleDescriptor(
    id="world", title="World & Package Sets", category="Software",
    icon="package-x-generic",
)

_WORLD = "@world"


class WorldModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sets = QListWidget()
        self._sets.setMaximumWidth(220)
        self._members = QListWidget()
        self._members.setSelectionMode(QListWidget.ExtendedSelection)
        self._deselect = QPushButton("Deselect from @world")
        self._status = QLabel()

        right = QVBoxLayout()
        right.addWidget(self._members, 1)
        right.addWidget(self._deselect)
        right.addWidget(self._status)

        layout = QHBoxLayout(self)
        layout.addWidget(self._sets)
        layout.addLayout(right, 1)

        self._set_atoms: dict[str, list[str]] = {}
        self._populate_sets()
        self._sets.currentTextChanged.connect(self._show_set)
        self._deselect.clicked.connect(self._on_deselect)
        if self._sets.count():
            self._sets.setCurrentRow(0)

    def _world_members(self) -> list[str]:
        return sorted(p.cp for p in list_installed() if p.world_member)

    def _populate_sets(self) -> None:
        self._sets.clear()
        self._set_atoms = {s.name: list(s.atoms) for s in list_sets()}
        self._sets.addItem(_WORLD)
        for name in self._set_atoms:
            self._sets.addItem(name)

    def _show_set(self, name: str) -> None:
        self._members.clear()
        if name == _WORLD:
            self._members.addItems(self._world_members())
            self._deselect.setEnabled(True)
        else:
            self._members.addItems(self._set_atoms.get(name, []))
            self._deselect.setEnabled(False)

    def _on_deselect(self) -> None:
        atoms = [i.text() for i in self._members.selectedItems()]
        if not atoms:
            self._status.setText("Select one or more @world members first.")
            return
        busy, label = package_status()
        if busy:
            self._status.setText(f"Package management is busy: {label}")
            return
        ok, msg = deselect(atoms)
        self._status.setText(f"Deselected {len(atoms)}." if ok else f"Failed: {msg}")
        if ok:
            self._show_set(_WORLD)


def factory() -> QWidget:
    return WorldModule()
