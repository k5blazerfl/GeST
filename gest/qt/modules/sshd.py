"""sshd module: edit key SSH server settings (via the polkit backend)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from gest.core.sshd.model import ROOT_LOGIN_VALUES, SshdSettings
from gest.core.sshd.reader import current_settings
from gest.qt.registry import ModuleDescriptor
from gest.qt.sshd import apply_config, sshd_summary

DESCRIPTOR = ModuleDescriptor(
    id="sshd", title="SSH Server", category="Network", icon="network-server"
)


class SshdModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary = QLabel()
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._root = QComboBox()
        self._root.addItems(list(ROOT_LOGIN_VALUES))
        self._password = QCheckBox("Password authentication")
        self._pubkey = QCheckBox("Public-key authentication")
        self._x11 = QCheckBox("X11 forwarding")
        self._apply = QPushButton("Apply")
        self._status = QLabel()

        form = QFormLayout(self)
        form.addRow(self._summary)
        form.addRow("Port:", self._port)
        form.addRow("Permit root login:", self._root)
        form.addRow(self._password)
        form.addRow(self._pubkey)
        form.addRow(self._x11)
        form.addRow(self._apply)
        form.addRow(self._status)

        self._apply.clicked.connect(self._on_apply)
        self._load()

    def _load(self) -> None:
        s = current_settings()
        self._summary.setText(sshd_summary(s))
        self._port.setValue(s.port)
        self._root.setCurrentText(s.permit_root_login)
        self._password.setChecked(s.password_authentication)
        self._pubkey.setChecked(s.pubkey_authentication)
        self._x11.setChecked(s.x11_forwarding)

    def _on_apply(self) -> None:
        settings = SshdSettings(
            port=self._port.value(),
            permit_root_login=self._root.currentText(),
            password_authentication=self._password.isChecked(),
            pubkey_authentication=self._pubkey.isChecked(),
            x11_forwarding=self._x11.isChecked(),
        )
        ok, msg = apply_config(settings)
        self._status.setText("Applied." if ok else f"Failed: {msg}")
        self._load()


def factory() -> QWidget:
    return SshdModule()
