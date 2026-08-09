"""CPU & Video flags editor (urwid): detect and set CPU_FLAGS_X86 / VIDEO_CARDS.

Detection (cpuid2cpuflags / lspci) is unprivileged; the package.use fragments
GeST owns (50gest-cpuflags / 50gest-videocards) are written through the
polkit-gated Portage backend (WriteConfig → portage.configure).
"""

from __future__ import annotations

import urwid

from gest.core.hwflags import detect, reader, writer
from gest.core.portage.backend_client import PortageBackend
from gest.tui.runtime import App, Modal, Screen

# (row key, display name) for the two USE_EXPAND vars this screen manages.
_VARS = [("cpu", "CPU_FLAGS_X86"), ("video", "VIDEO_CARDS")]


def _row(text: str) -> urwid.Widget:
    return urwid.AttrMap(urwid.SelectableIcon(text, 0), None, focus_map="focus")


def _fmt(values: list[str]) -> str:
    return " ".join(values) if values else "(none)"


class HwFlagsScreen(Screen):
    def __init__(self, app: App) -> None:
        self._current: dict[str, list[str]] = {"cpu": [], "video": []}
        self._detected: dict[str, list[str]] = {"cpu": [], "video": []}
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" detecting …")])
        self._list = urwid.ListBox(self._walker)
        super().__init__(
            app, urwid.LineBox(self._list, title="CPU & Video flags"),
            title="CPU/Video flags",
            footer_keys=[
                ("a/Enter", "Apply detected"), ("e", "Edit"),
                ("x", "Clear"), ("Esc", "Back"),
            ],
            help_text=(
                "Set the hardware USE_EXPAND flags Portage compiles against.\n\n"
                "CPU_FLAGS_X86  — CPU instruction sets (via cpuid2cpuflags)\n"
                "VIDEO_CARDS    — GPU drivers (detected from lspci)\n\n"
                "a/Enter   apply the detected values to the highlighted row\n"
                "e     edit the highlighted row's values by hand\n"
                "x     clear the highlighted row (remove GeST's fragment)\n\n"
                "GeST writes package.use/50gest-cpuflags and …/50gest-videocards; "
                "the Handbook's 00* files are left untouched."
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        self._current["cpu"] = await self.app.run_blocking(reader.current_cpu_flags)
        self._current["video"] = await self.app.run_blocking(reader.current_video_cards)
        self._detected["cpu"] = await self.app.run_blocking(detect.detect_cpu_flags)
        self._detected["video"] = await self.app.run_blocking(detect.detect_video_cards)
        self._render()
        self.app.refresh()

    def _render(self) -> None:
        rows = []
        for key, name in _VARS:
            rows.append(_row(f" {name:<14}  now: {_fmt(self._current[key])}"))
            rows.append(urwid.Text(f"                detected: {_fmt(self._detected[key])}"))
            rows.append(urwid.Divider())
        focus = self._walker.focus if self._walker else 0
        self._walker[:] = rows
        self._walker.set_focus(min(focus, len(rows) - 1))

    def _focused_key(self) -> str | None:
        # rows come in groups of three (selectable name row + detected + divider)
        idx = self._walker.focus // 3
        return _VARS[idx][0] if 0 <= idx < len(_VARS) else None

    def handle_key(self, key):
        which = self._focused_key()
        if key == "esc":
            self.app.pop()
        elif which is None:
            return key
        elif key in ("a", "enter"):
            self._apply(which, self._detected[which])
        elif key == "e":
            self._edit_modal(which)
        elif key == "x":
            self._apply(which, [])
        else:
            return key
        return None

    # -- backend plumbing ---------------------------------------------------

    def _build(self, which: str, values: list[str]):
        if which == "cpu":
            return writer.write_cpu_flags(values)
        return writer.write_video_cards(values)

    def _apply(self, which: str, values: list[str]) -> None:
        self.app.run_async(self._write(which, values))

    async def _write(self, which: str, values: list[str]) -> None:
        backend = PortageBackend()
        try:
            await backend.connect()
            ok = await backend.write_config([self._build(which, values)])
        except Exception as exc:
            self.app.notify(str(exc), error=True)
            await backend.close()
            return
        await backend.close()
        if not ok:
            self.app.notify("change was not applied", error=True)
        await self._load()

    def _edit_modal(self, which: str) -> None:
        name = dict(_VARS)[which]
        seed = self._detected[which] or self._current[which]
        value = urwid.Edit(f"{name}: ", " ".join(seed))

        def save():
            self.app.pop()
            self._apply(which, value.edit_text.split())

        modal = Modal(self.app, f"Edit {name}",
                      [urwid.Text("Space-separated values; empty clears it."),
                       urwid.Divider(), value],
                      [("Save", save), ("Cancel", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 80), height=("relative", 55))
