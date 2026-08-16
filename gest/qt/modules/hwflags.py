"""CPU & Video flags module: show the currently-set and hardware-detected
CPU_FLAGS_X86 / VIDEO_CARDS, and write either the detected set, a hand-edited
set, or clear the fragment — all through the polkit-gated Portage backend.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gest.core.hwflags.detect import detect_cpu_flags, detect_video_cards
from gest.core.hwflags.reader import current_cpu_flags, current_video_cards
from gest.qt.hwflags import apply_cpu_flags, apply_video_cards, format_flags, parse_flags
from gest.qt.registry import ModuleDescriptor

DESCRIPTOR = ModuleDescriptor(
    id="hwflags", title="CPU & Video Flags", category="Hardware", icon="cpu"
)


class _FlagSection(QGroupBox):
    """One USE_EXPAND variable: current + detected labels, an editable field,
    and Apply-detected / Apply-edited / Clear actions."""

    def __init__(
        self,
        *,
        title: str,
        current: list[str],
        detected: list[str],
        apply_fn: Callable[[list[str]], tuple[bool, str]],
        status: QLabel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)
        self._detected = detected
        self._apply_fn = apply_fn
        self._status = status

        self._current = QLabel()
        self._detected_label = QLabel(f"detected: {format_flags(detected) or '—'}")
        self._edit = QLineEdit(format_flags(current))
        apply_detected = QPushButton("Apply detected")
        apply_edited = QPushButton("Apply edited")
        clear = QPushButton("Clear")

        buttons = QHBoxLayout()
        buttons.addWidget(apply_detected)
        buttons.addWidget(apply_edited)
        buttons.addWidget(clear)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._current)
        layout.addWidget(self._detected_label)
        layout.addWidget(self._edit)
        layout.addLayout(buttons)

        apply_detected.clicked.connect(self._on_detected)
        apply_edited.clicked.connect(self._on_edited)
        clear.clicked.connect(self._on_clear)
        self._set_current(current)

    def _set_current(self, flags: list[str]) -> None:
        self._current.setText(f"now: {format_flags(flags) or '—'}")

    def _apply(self, flags: list[str]) -> None:
        ok, msg = self._apply_fn(flags)
        if ok:
            self._edit.setText(format_flags(flags))
            self._set_current(flags)
        self._status.setText("Applied." if ok else f"Failed: {msg}")

    def _on_detected(self) -> None:
        self._apply(self._detected)

    def _on_edited(self) -> None:
        self._apply(parse_flags(self._edit.text()))

    def _on_clear(self) -> None:
        self._apply([])


class HwFlagsModule(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = QLabel()

        cpu = _FlagSection(
            title="CPU_FLAGS_X86",
            current=current_cpu_flags(),
            detected=detect_cpu_flags(),
            apply_fn=apply_cpu_flags,
            status=self._status,
        )
        video = _FlagSection(
            title="VIDEO_CARDS",
            current=current_video_cards(),
            detected=detect_video_cards(),
            apply_fn=apply_video_cards,
            status=self._status,
        )

        layout = QVBoxLayout(self)
        layout.addWidget(cpu)
        layout.addWidget(video)
        layout.addWidget(self._status)
        layout.addStretch(1)


def factory() -> QWidget:
    return HwFlagsModule()
