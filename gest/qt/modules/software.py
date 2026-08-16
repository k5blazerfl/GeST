"""Software module: search, preview (emerge --pretend), and streamed install.

The first module with *streamed* output: the install runs in a worker thread
that drives the async Software backend and emits emerge output live, so the UI
never freezes. Preview + search are read-only (no polkit).
"""

from __future__ import annotations

import asyncio

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.software.preview import preview_install
from gest.core.software.reader import search
from gest.qt.registry import ModuleDescriptor
from gest.qt.software import search_result_label
from gest.qt.theme import fixed_font

DESCRIPTOR = ModuleDescriptor(
    id="software", title="Software", category="Software", icon="applications-system"
)


class InstallWorker(QThread):
    """Runs a streamed merge on the async backend, emitting output + exit code."""

    output = Signal(str)
    done = Signal(int)

    def __init__(self, atom: str) -> None:
        super().__init__()
        self._atom = atom

    def run(self) -> None:
        async def op() -> int:
            from gest.core.software.backend_client import SoftwareBackend

            loop = asyncio.get_running_loop()
            finished: asyncio.Future = loop.create_future()
            backend = await SoftwareBackend().connect()
            try:
                await backend.install(
                    self._atom,
                    on_progress=lambda lines: self.output.emit("\n".join(lines)),
                    on_finished=lambda code: finished.done() or finished.set_result(code),
                )
                return await finished
            finally:
                await backend.close()

        try:
            code = asyncio.run(op())
        except Exception as e:  # backend/D-Bus/polkit/busy error
            self.output.emit(f"error: {e}")
            code = -1
        self.done.emit(code)


class SoftwareModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: InstallWorker | None = None

        self._query = QLineEdit()
        self._query.setPlaceholderText("Search packages…")
        search_btn = QPushButton("Search")
        self._results = QListWidget()

        left = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(self._query, 1)
        top.addWidget(search_btn)
        left.addLayout(top)
        left.addWidget(self._results, 1)

        self._preview = QPushButton("Preview")
        self._install = QPushButton("Install")
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(fixed_font())
        self._status = QLabel()

        actions = QHBoxLayout()
        actions.addWidget(self._preview)
        actions.addWidget(self._install)
        actions.addStretch(1)
        right = QVBoxLayout()
        right.addLayout(actions)
        right.addWidget(self._output, 1)
        right.addWidget(self._status)

        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addLayout(right, 2)

        self._query.returnPressed.connect(self._search)
        search_btn.clicked.connect(self._search)
        self._preview.clicked.connect(self._on_preview)
        self._install.clicked.connect(self._on_install)

    def _current_atom(self) -> str:
        item = self._results.currentItem()
        return item.data(Qt.UserRole) if item else ""

    def _search(self) -> None:
        term = self._query.text().strip()
        self._results.clear()
        if not term:
            return
        for result in search(term, limit=100):
            item = QListWidgetItem(search_result_label(result), self._results)
            item.setData(Qt.UserRole, result.cp)
        self._status.setText(f"{self._results.count()} result(s)")

    def _on_preview(self) -> None:
        atom = self._current_atom()
        if not atom:
            return
        self._output.setPlainText("Previewing…")
        result = preview_install(atom)
        self._output.setPlainText(result.output or result.summary)
        self._status.setText(result.summary)

    def _on_install(self) -> None:
        atom = self._current_atom()
        if not atom or (self._worker and self._worker.isRunning()):
            return
        self._output.setPlainText(f"Installing {atom}…\n")
        self._install.setEnabled(False)
        self._worker = InstallWorker(atom)
        self._worker.output.connect(self._append)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _append(self, text: str) -> None:
        self._output.appendPlainText(text)

    def _on_done(self, code: int) -> None:
        self._install.setEnabled(True)
        self._status.setText("Done." if code == 0 else f"Finished with exit code {code}.")


def factory() -> QWidget:
    return SoftwareModule()
