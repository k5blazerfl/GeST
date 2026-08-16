"""DNS resolvers module: edit /etc/resolv.conf nameservers + search domains
(via the polkit-gated Network backend).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.network.resolv import current_resolvers, valid_resolv
from gest.qt.net import parse_tokens, set_resolvers
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="dns", title="DNS Resolvers", category="Network", icon="network-server"
)


class DnsModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        nameservers, search = current_resolvers()
        self._nameservers = QLineEdit(" ".join(nameservers))
        self._nameservers.setPlaceholderText("1.1.1.1 9.9.9.9")
        self._search = QLineEdit(" ".join(search))
        self._search.setPlaceholderText("example.com")
        self._apply = QPushButton("Apply")
        self._status = QLabel()
        hint = QLabel(
            "Space-separated. Note: dhcpcd or NetworkManager may overwrite "
            "/etc/resolv.conf on the next lease."
        )
        hint.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Nameservers:", self._nameservers)
        form.addRow("Search domains:", self._search)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._apply)
        layout.addWidget(self._status)
        layout.addWidget(hint)
        layout.addStretch(1)

        self._apply.clicked.connect(self._on_apply)

    def _on_apply(self) -> None:
        nameservers = parse_tokens(self._nameservers.text())
        search = parse_tokens(self._search.text())
        if not valid_resolv(nameservers, search):
            self._status.setText(
                "Need at least one valid nameserver; check the addresses/domains."
            )
            return
        ok, msg = set_resolvers(nameservers, search)
        self._status.setText("Applied." if ok else f"Failed: {msg}")


def factory() -> QWidget:
    return DnsModule()
