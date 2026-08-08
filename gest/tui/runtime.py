"""urwid application runtime: screen stack, async/thread plumbing, chrome.

The one place that knows about urwid's event loop. Screens are ``WidgetWrap``
subclasses; the App keeps a stack and swaps the MainLoop's top widget. The loop
is an asyncio loop (via ``urwid.AsyncioEventLoop``) so the async dbus-next
backend client and threaded Portage/`ip` reads integrate cleanly.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

import urwid

# A restrained, YaST-ish blue palette.
PALETTE = [
    ("header", "white", "dark blue"),
    ("footer", "light gray", "dark blue"),
    ("footer_key", "black", "light gray"),
    ("title", "light cyan,bold", "default"),
    ("hint", "dark gray", "default"),
    ("focus", "black", "light cyan"),
    ("reversed", "standout", "default"),
    ("ok", "light green", "default"),
    ("error", "light red", "default"),
    ("pane_title", "light cyan,bold", "default"),
]


def function_bar(keys: list[tuple[str, str]]) -> urwid.Widget:
    """A YaST-style function-key footer: reversed key chips + labels."""
    markup: list = []
    for key, label in keys:
        markup.append(("footer_key", f" {key} "))
        markup.append(("footer", f" {label}   "))
    return urwid.AttrMap(urwid.Text(markup or ""), "footer")


class BracketButton(urwid.Button):
    """A urwid Button rendered YaST-style as ``[Label]``."""

    button_left = urwid.Text("[")
    button_right = urwid.Text("]")


class Screen(urwid.WidgetWrap):
    """Base screen: a framed widget with a title header and a footer holding a
    transient status line above the function-key bar.

    Subclasses build ``body`` and may override ``handle_key`` for screen-level
    keys (nav keys reach the focused body widget first).
    """

    def __init__(self, app: App, body: urwid.Widget, *, title: str = "",
                 footer_keys: list[tuple[str, str]] | None = None):
        self.app = app
        self._status = urwid.Text("")
        header = urwid.AttrMap(urwid.Text(f" {title}"), "header")
        footer = urwid.Pile([self._status, function_bar(footer_keys or [])])
        self._frame = urwid.Frame(body, header=header, footer=footer)
        super().__init__(self._frame)

    def set_body(self, body: urwid.Widget) -> None:
        self._frame.body = body

    def set_status(self, text: str, attr: str = "hint") -> None:
        self._status.set_text((attr, f" {text}") if text else "")

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key is None:
            return None
        return self.handle_key(key)

    def handle_key(self, key):  # override
        return key


class Modal(urwid.WidgetWrap):
    """A form modal: title, body rows, and a centered row of buttons.

    ``buttons`` is ``[(label, callback), …]``; Esc cancels (pops the overlay).
    """

    def __init__(self, app: App, title: str, rows: list, buttons: list):
        self.app = app
        button_widgets = [
            urwid.AttrMap(urwid.Button(label, on_press=lambda _b, cb=cb: cb()),
                          None, focus_map="focus")
            for label, cb in buttons
        ]
        grid = urwid.GridFlow(button_widgets, cell_width=16, h_sep=2, v_sep=1,
                              align="center")
        pile = urwid.Pile(
            [urwid.Text(("title", title)), urwid.Divider(), *rows,
             urwid.Divider(), grid]
        )
        super().__init__(urwid.Filler(pile, valign="top"))

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == "esc":
            self.app.pop()
            return None
        return key

def _as_screen(widget) -> Screen | None:
    if isinstance(widget, Screen):
        return widget
    if isinstance(widget, urwid.Overlay):
        return _as_screen(widget.bottom_w)
    return None


class App:
    """Owns the urwid MainLoop, an asyncio loop, and a screen stack."""

    def __init__(self) -> None:
        self._stack: list[urwid.Widget] = []
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.main = urwid.MainLoop(
            urwid.SolidFill(" "),
            palette=PALETTE,
            event_loop=urwid.AsyncioEventLoop(loop=self.loop),
            unhandled_input=self._unhandled,
            pop_ups=True,
        )

    # -- screen stack -------------------------------------------------------

    def push(self, widget: urwid.Widget) -> None:
        self._stack.append(widget)
        self.main.widget = widget
        self.refresh()

    def pop(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop()
            self.main.widget = self._stack[-1]
            self.refresh()

    def push_modal(self, modal: urwid.Widget, *, width=64, height=None) -> None:
        overlay = urwid.Overlay(
            urwid.LineBox(modal),
            self._stack[-1],
            align="center", width=width, min_width=24,
            valign="middle", height=("pack" if height is None else height),
        )
        self.push(overlay)

    def refresh(self) -> None:
        with contextlib.suppress(Exception):
            self.main.draw_screen()

    def notify(self, text: str, *, error: bool = False) -> None:
        for widget in reversed(self._stack):
            screen = _as_screen(widget)
            if screen is not None:
                screen.set_status(text, "error" if error else "ok")
                self.refresh()
                return

    # -- async / threads ----------------------------------------------------

    def run_async(self, coro: Awaitable) -> None:
        """Schedule a coroutine on the app's asyncio loop."""
        self.loop.create_task(_guard(self, coro))

    async def run_blocking(self, fn: Callable, *args):
        """Run a blocking callable in a thread; return its result on the loop."""
        return await self.loop.run_in_executor(None, fn, *args)

    def quit(self) -> None:
        raise urwid.ExitMainLoop()

    def run(self, root: urwid.Widget) -> None:
        self.push(root)
        self.main.run()

    def _unhandled(self, key):
        if key in ("q", "Q"):
            self.quit()


async def _guard(app: App, coro: Awaitable) -> None:
    try:
        await coro
    except Exception as exc:  # never let a worker crash the loop
        app.notify(str(exc), error=True)
