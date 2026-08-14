"""Binhost module: manage binary-package hosts + FEATURES (via Portage backend)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
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

from gest.core.binhost.model import GETBINPKG, REQUIRE_SIGNATURE, Binhost
from gest.core.binhost.reader import features_state, read_all
from gest.qt.binhost import (
    delete_host,
    host_label,
    run_setup_trust,
    save_host,
    set_feature_token,
)
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="binhost", title="Binary Hosts", category="Software", icon="package-x-generic"
)


class BinhostModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._list = QListWidget()
        self._list.setMaximumWidth(280)
        self._name = QLineEdit()
        self._uri = QLineEdit()
        self._priority = QLineEdit()
        self._verify = QCheckBox("Verify signatures")
        self._verify.setChecked(True)
        self._save = QPushButton("Save host")
        self._delete = QPushButton("Delete host")

        self._getbinpkg = QCheckBox("Enable binary packages (getbinpkg)")
        self._require_sig = QCheckBox("Require package signatures")
        self._trust = QPushButton("Set up trust keyring (getuto)")
        self._status = QLabel()

        form = QFormLayout()
        form.addRow("Name:", self._name)
        form.addRow("Sync URI:", self._uri)
        form.addRow("Priority:", self._priority)
        form.addRow(self._verify)
        buttons = QHBoxLayout()
        buttons.addWidget(self._save)
        buttons.addWidget(self._delete)

        right = QVBoxLayout()
        right.addWidget(QLabel("Host (only GeST-managed hosts are editable):"))
        right.addLayout(form)
        right.addLayout(buttons)
        right.addWidget(QLabel("FEATURES:"))
        right.addWidget(self._getbinpkg)
        right.addWidget(self._require_sig)
        right.addWidget(self._trust)
        right.addWidget(self._status)
        right.addStretch(1)

        layout = QHBoxLayout(self)
        layout.addWidget(self._list)
        layout.addLayout(right, 1)

        self._list.currentItemChanged.connect(self._on_select)
        self._save.clicked.connect(self._on_save)
        self._delete.clicked.connect(self._on_delete)
        self._getbinpkg.clicked.connect(
            lambda: self._toggle(GETBINPKG, self._getbinpkg.isChecked())
        )
        self._require_sig.clicked.connect(
            lambda: self._toggle(REQUIRE_SIGNATURE, self._require_sig.isChecked())
        )
        self._trust.clicked.connect(self._on_trust)
        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for host in read_all():
            item = QListWidgetItem(host_label(host), self._list)
            item.setData(Qt.UserRole, host)
        state = features_state()
        self._getbinpkg.setChecked(state.getbinpkg)
        self._require_sig.setChecked(state.require_signature)

    def _on_select(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        host: Binhost = current.data(Qt.UserRole)
        self._name.setText(host.name)
        self._uri.setText(host.sync_uri)
        self._priority.setText(host.priority)
        self._verify.setChecked(host.verify_signature)
        editable = host.managed
        for w in (self._name, self._uri, self._priority, self._verify, self._delete):
            w.setEnabled(editable)

    def _on_save(self) -> None:
        name = self._name.text().strip()
        if not name:
            self._status.setText("A host name is required.")
            return
        host = Binhost(
            name=name,
            sync_uri=self._uri.text().strip(),
            priority=self._priority.text().strip(),
            verify_signature=self._verify.isChecked(),
            managed=True,
        )
        ok, msg = save_host(host)
        self._status.setText(f"Saved {name}." if ok else f"Failed: {msg}")
        if ok:
            self._enable_all()
            self._refresh()

    def _on_delete(self) -> None:
        name = self._name.text().strip()
        if not name:
            return
        ok, msg = delete_host(name)
        self._status.setText(f"Deleted {name}." if ok else f"Failed: {msg}")
        if ok:
            self._enable_all()
            self._refresh()

    def _toggle(self, token: str, enabled: bool) -> None:
        ok, msg = set_feature_token(token, enabled)
        self._status.setText("Applied." if ok else f"Failed: {msg}")
        self._refresh()

    def _on_trust(self) -> None:
        ok, msg = run_setup_trust()
        self._status.setText("Trust keyring ready." if ok else f"Failed: {msg}")

    def _enable_all(self) -> None:
        for w in (self._name, self._uri, self._priority, self._verify, self._delete):
            w.setEnabled(True)


def factory() -> QWidget:
    return BinhostModule()
