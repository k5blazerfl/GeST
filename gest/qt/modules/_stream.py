"""Shared machinery for the streamed package operations (Update / Clean Up /
Sync): a worker thread that drives one async backend op and emits its live
output + exit code, and a base widget that shows a preview, a Run button, the
streamed log, and honours the shared package-backend busy gate.

Generalises the ``InstallWorker`` in ``modules/software.py`` — instead of a
hardcoded ``backend.install(...)`` it takes an *op*: a callable
``(backend, on_progress, on_finished) -> Awaitable`` so each module supplies its
own backend method (``update_world`` / ``depclean`` / ``sync``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.qt.software import package_status

# op(backend, on_progress, on_finished) -> Awaitable ; callbacks match the backend:
#   on_progress: Callable[[list[str]], None]   (batched output lines)
#   on_finished: Callable[[int], None]         (exit code)
Op = Callable[..., Awaitable]


class StreamWorker(QThread):
    """Runs one streamed backend op off the GUI thread, emitting output + code."""

    output = Signal(str)
    done = Signal(int)

    def __init__(self, op: Op) -> None:
        super().__init__()
        self._op = op

    def run(self) -> None:
        async def drive() -> int:
            from gest.core.software.backend_client import SoftwareBackend

            loop = asyncio.get_running_loop()
            finished: asyncio.Future = loop.create_future()
            backend = await SoftwareBackend().connect()
            try:
                await self._op(
                    backend,
                    lambda lines: self.output.emit("\n".join(lines)),
                    lambda code: finished.done() or finished.set_result(code),
                )
                return await finished
            finally:
                await backend.close()

        try:
            code = asyncio.run(drive())
        except Exception as e:  # backend / D-Bus / polkit / busy
            self.output.emit(f"error: {e}")
            code = -1
        self.done.emit(code)


class OperationModule(QWidget):
    """Preview + streamed-Run widget shared by Update / Clean Up / Sync."""

    def __init__(
        self,
        *,
        run_label: str,
        preview_fn: Callable[[], str],
        op_factory: Callable[[], Op],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._preview_fn = preview_fn
        self._op_factory = op_factory
        self._worker: StreamWorker | None = None

        self._summary = QPlainTextEdit()
        self._summary.setReadOnly(True)
        self._reload = QPushButton("Reload")
        self._run = QPushButton(run_label)
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._status = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Preview:"))
        layout.addWidget(self._summary, 1)
        layout.addWidget(self._reload)
        layout.addWidget(self._run)
        layout.addWidget(QLabel("Output:"))
        layout.addWidget(self._output, 2)
        layout.addWidget(self._status)

        self._reload.clicked.connect(self._load_preview)
        self._run.clicked.connect(self._on_run)
        self._load_preview()

    def _load_preview(self) -> None:
        self._summary.setPlainText(self._preview_fn())

    def _on_run(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        busy, label = package_status()
        if busy:
            self._status.setText(f"Package management is busy: {label}")
            return
        self._output.setPlainText("")
        self._run.setEnabled(False)
        self._worker = StreamWorker(self._op_factory())
        self._worker.output.connect(self._output.appendPlainText)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, code: int) -> None:
        self._run.setEnabled(True)
        self._status.setText("Done." if code == 0 else f"Finished with exit code {code}.")
        self._load_preview()
