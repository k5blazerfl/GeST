"""Unavailable Packages module: find repo-orphans (installed packages with no
ebuild in any configured repo) and clear them — Deselect from @world, or Unmerge
outright — via the polkit-gated backend.

These are distinct from depclean orphans: an overlay renamed or dropped the
package, or was removed, so nothing can reinstall or update it and (when it's a
@world member or still depended on) ``emerge --depclean`` won't touch it. This
module is where they surface. Unmerge bypasses depclean's dependency safety net,
so it is always behind a confirmation that spells out what still needs each one.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.software.cleanup import human_size
from gest.core.software.orphans import RepoOrphan, scan_orphans
from gest.qt.registry import ModuleDescriptor
from gest.qt.software import deselect, package_status, unmerge

DESCRIPTOR = ModuleDescriptor(
    id="orphans", title="Unavailable Packages", category="Software",
    icon="package-x-generic",
)


class OrphansModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._intro = QLabel(
            "Installed packages with no ebuild in any configured repo — an overlay "
            "renamed or dropped them, or was removed. They still run, but can't be "
            "updated or reinstalled, and Clean Up (depclean) won't surface them. "
            "Review and clear them here."
        )
        self._intro.setWordWrap(True)
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.ExtendedSelection)
        self._rescan_btn = QPushButton("Rescan")
        self._deselect_btn = QPushButton("Deselect from @world")
        self._unmerge_btn = QPushButton("Unmerge…")
        self._status = QLabel()
        self._status.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self._rescan_btn)
        buttons.addStretch(1)
        buttons.addWidget(self._deselect_btn)
        buttons.addWidget(self._unmerge_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._intro)
        layout.addWidget(self._list, 1)
        layout.addLayout(buttons)
        layout.addWidget(self._status)

        self._orphans: dict[str, RepoOrphan] = {}
        self._rescan_btn.clicked.connect(self._rescan)
        self._deselect_btn.clicked.connect(self._on_deselect)
        self._unmerge_btn.clicked.connect(self._on_unmerge)
        self._rescan()

    # -- data ---------------------------------------------------------------

    def _rescan(self) -> None:
        self._list.clear()
        report = scan_orphans()
        self._orphans = {o.cp: o for o in report.orphans}
        have = bool(report.orphans)
        self._deselect_btn.setEnabled(have)
        self._unmerge_btn.setEnabled(have)
        if not have:
            self._status.setText(
                "No unavailable packages — every installed package still has an "
                "ebuild in a configured repo.")
            return
        for orphan in report.orphans:
            item = QListWidgetItem(self._row_label(orphan))
            item.setData(Qt.UserRole, orphan.cp)
            self._list.addItem(item)
        self._status.setText(
            f"{len(report.orphans)} unavailable package(s), "
            f"{human_size(report.total_size)} installed.")

    @staticmethod
    def _row_label(orphan: RepoOrphan) -> str:
        tags = []
        if orphan.world_member:
            tags.append("@world")
        if orphan.required_by:
            tags.append(f"needed by {len(orphan.required_by)}")
        suffix = f"   [{', '.join(tags)}]" if tags else ""
        return f"{orphan.cpv}   {human_size(orphan.size)}{suffix}"

    def _selected(self) -> list[RepoOrphan]:
        cps = [i.data(Qt.UserRole) for i in self._list.selectedItems()]
        return [self._orphans[cp] for cp in cps if cp in self._orphans]

    def _busy(self) -> bool:
        busy, label = package_status()
        if busy:
            self._status.setText(f"Package management is busy: {label}")
        return busy

    # -- actions ------------------------------------------------------------

    def _on_deselect(self) -> None:
        chosen = self._selected()
        if not chosen:
            self._status.setText("Select one or more packages first.")
            return
        members = [o for o in chosen if o.world_member]
        if not members:
            self._status.setText("None of the selected packages are @world members.")
            return
        if self._busy():
            return
        ok, msg = deselect([o.cp for o in members])
        self._status.setText(
            f"Deselected {len(members)} from @world." if ok else f"Failed: {msg}")
        if ok:
            self._rescan()

    def _on_unmerge(self) -> None:
        chosen = self._selected()
        if not chosen:
            self._status.setText("Select one or more packages first.")
            return
        if self._busy():
            return
        if not self._confirm_unmerge(chosen):
            return
        ok, msg = unmerge([o.cp for o in chosen])
        self._status.setText(
            f"Unmerged {len(chosen)} package(s)." if ok else f"Failed: {msg}")
        if ok:
            self._rescan()

    def _confirm_unmerge(self, chosen: list[RepoOrphan]) -> bool:
        depended = [o for o in chosen if o.required_by]
        body = [f"Permanently remove {len(chosen)} package(s):", ""]
        body += [f"  • {o.cpv}" for o in chosen]
        if depended:
            body += ["", "⚠ Some are still required by other installed packages — "
                     "removing them may break those packages:"]
            for o in depended:
                more = " …" if len(o.required_by) > 5 else ""
                body.append(f"  • {o.cpv} ← needed by "
                            f"{', '.join(o.required_by[:5])}{more}")
        body += ["", "This uses 'emerge --unmerge' (no dependency safety check) "
                 "and cannot be undone. Continue?"]
        box = QMessageBox(self)
        box.setWindowTitle("Unmerge unavailable packages")
        box.setIcon(QMessageBox.Warning if depended else QMessageBox.Question)
        box.setText("\n".join(body))
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        box.setDefaultButton(QMessageBox.Cancel)
        return box.exec() == QMessageBox.Yes


def factory() -> QWidget:
    return OrphansModule()
