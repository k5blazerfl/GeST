"""Default Browser: pick which browser handles the web — the cockpit's curated
answer, *not* the Software search box.

Same install backend as the Software module, but a hand-picked list: choose a
browser and this installs it (if it isn't already) and makes it the system
default in one step. On a fresh HeDE install nothing is set, so this control is
how the *first* browser gets on the machine — no throwaway browser needed to
download one, because picking from the list is the install.

This is the reference module for the default-apps family; a Default Mail / Media
control is this file pointed at a different catalog.
"""

from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.defaultapps import browser as browsers
from gest.qt.modules.software import InstallWorker
from gest.qt.registry import ModuleDescriptor
from gest.qt.theme import fixed_font

DESCRIPTOR = ModuleDescriptor(
    id="default-browser",
    title="Default Browser",
    category="Software",
    icon="web-browser",
)


def _run(argv: list[str]) -> tuple[bool, str]:
    """Run a short, non-root command (``xdg-settings``); return (ok, text)."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return proc.returncode == 0, (proc.stdout or proc.stderr).strip()


def _is_installed(b: browsers.Browser) -> bool:
    try:
        return browsers.is_installed(b)
    except OSError:
        return False


class DefaultBrowserModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: InstallWorker | None = None
        self._pending: browsers.Browser | None = None

        self._current = QLabel()
        self._list = QListWidget()
        self._use = QPushButton()
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(fixed_font())
        self._output.hide()  # only appears while an install streams
        self._status = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(self._current)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._use)
        layout.addWidget(self._output, 1)
        layout.addWidget(self._status)

        self._list.itemSelectionChanged.connect(self._refresh_button)
        self._use.clicked.connect(self._on_use)

        self._populate()
        self._refresh_current()
        self._refresh_button()

    # ---- rendering ----------------------------------------------------------
    def _populate(self) -> None:
        for b in browsers.BROWSERS:
            tag = "  ·  Recommended" if b.recommended else ""
            item = QListWidgetItem(f"{b.name}{tag}\n    {b.summary}", self._list)
            item.setData(Qt.UserRole, b.id)
            if b.recommended:
                self._list.setCurrentItem(item)

    def _selected(self) -> browsers.Browser | None:
        item = self._list.currentItem()
        return browsers.by_id(item.data(Qt.UserRole)) if item else None

    def _refresh_current(self) -> None:
        ok, out = _run(browsers.get_default_argv())
        current = browsers.parse_default(out) if ok else None
        self._current.setText(
            f"Current browser: {current.name}"
            if current
            else "Current browser: — (none set)"
        )

    def _refresh_button(self) -> None:
        b = self._selected()
        busy = bool(self._worker and self._worker.isRunning())
        self._use.setEnabled(b is not None and not busy)
        if b is None:
            self._use.setText("Use this browser")
        else:
            self._use.setText(
                "Set as default" if _is_installed(b) else "Install & set default"
            )

    # ---- actions ------------------------------------------------------------
    def _on_use(self) -> None:
        b = self._selected()
        if b is None or (self._worker and self._worker.isRunning()):
            return
        if _is_installed(b):
            self._apply_default(b)
            return
        # Not installed: merge it first, then set the default when it succeeds.
        self._pending = b
        self._output.show()
        self._output.setPlainText(f"Installing {b.atom}…\n")
        self._status.setText(f"Installing {b.name}…")
        self._worker = InstallWorker(b.atom)
        self._worker.output.connect(self._output.appendPlainText)
        self._worker.done.connect(self._on_installed)
        self._worker.start()
        self._refresh_button()

    def _on_installed(self, code: int) -> None:
        b, self._pending = self._pending, None
        if code == 0 and b is not None:
            self._apply_default(b)
        else:
            self._status.setText(f"Install failed (exit {code}).")
        self._refresh_button()

    def _apply_default(self, b: browsers.Browser) -> None:
        ok, msg = _run(browsers.set_default_argv(b.desktop_id))
        if ok:
            self._refresh_current()
            self._status.setText(f"{b.name} is now your default browser.")
        else:
            self._status.setText(f"Could not set default: {msg}")


def factory() -> QWidget:
    return DefaultBrowserModule()
