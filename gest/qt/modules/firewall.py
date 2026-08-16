"""Firewall module: show the nftables status and enable it at boot."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from gest.core.firewall.reader import current_policy, is_managed, nft_available
from gest.qt.firewall import enable_at_boot, policy_summary
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="firewall", title="Firewall", category="Users & Security", icon="security-high"
)


class FirewallModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = QLabel()
        self._enable = QPushButton("Enable firewall at boot")
        self._result = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(self._status)
        layout.addWidget(self._enable)
        layout.addWidget(self._result)
        layout.addStretch(1)

        self._enable.clicked.connect(self._on_enable)
        self._refresh()

    def _refresh(self) -> None:
        self._status.setText(
            policy_summary(current_policy(), is_managed(), nft_available())
        )

    def _on_enable(self) -> None:
        ok, msg = enable_at_boot()
        self._result.setText("Enabled at boot." if ok else f"Failed: {msg}")


def factory() -> QWidget:
    return FirewallModule()
