"""urwid application runtime: screen stack, async/thread plumbing, chrome.

The one place that knows about urwid's event loop. Screens are ``WidgetWrap``
subclasses; the App keeps a stack and swaps the MainLoop's top widget. The loop
is an asyncio loop (via ``urwid.AsyncioEventLoop``) so the async dbus-next
backend client and threaded Portage/`ip` reads integrate cleanly.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import subprocess
from collections.abc import Awaitable, Callable

import urwid

# GeST normally runs unprivileged (privileged actions go through the polkit-gated
# backend). Show a "User Mode" banner in the top bar so it's obvious you're not
# root; it never changes during a run, so compute it once.
_IS_ROOT = os.geteuid() == 0

# A Gentoo-purple palette (the brand's violet, cf. the neofetch logo). Entries
# are 5-tuples — (name, fg16, bg16, mono, fg256, bg256) — so 256-colour terminals
# get the exact Gentoo lavenders while 16-colour ones fall back to magenta.
_BAR = "#546"      # deep Gentoo purple — bottom bar, menus, progress track
_BLUE = "#25a"     # Gentoo blue — top bar and the selection highlight
_ACCENT = "#a8f"   # lavender — titles, filled progress
_OUTLINE = "#639"  # dark Gentoo purple — box outlines (Filter/Packages/Detail…)
_KEYS = "#aad"     # light lavender — footer / menu-bar key chips
_TEXT = "#ccf"     # soft lavender text on the purple bars

PALETTE = [
    ("header", "white", "dark blue", "", "white", _BLUE),
    ("header_mode", "yellow,bold", "dark blue", "", "yellow,bold", _BLUE),
    ("footer", "light gray", "dark magenta", "", _TEXT, _BAR),
    ("footer_key", "black", "light gray", "", "black", _KEYS),
    ("title", "light magenta,bold", "default", "", f"{_ACCENT},bold", "default"),
    ("hint", "dark gray", "default", "", "#88a", "default"),
    # selected row: blue text (no background bar)
    ("focus", "light blue,bold", "default", "", "#5af,bold", "default"),
    ("boxline", "dark magenta", "default", "", _OUTLINE, "default"),  # box outline
    ("boxline_focus", "light blue", "default", "", "#5af", "default"),  # focused pane
    ("box_title", "light blue,bold", "default", "", "#5af,bold", "default"),  # box title

    ("body", "default", "default", "", "default", "default"),     # shields box content
    ("reversed", "standout", "default", "", "standout", "default"),
    ("ok", "light magenta", "default", "", _ACCENT, "default"),
    ("error", "light red", "default", "", "#f66", "default"),
    ("pane_title", "light magenta,bold", "default", "", f"{_ACCENT},bold", "default"),
    ("field", "white,bold", "default", "", "white,bold", "default"),
    ("cc_title", "light magenta,bold", "default", "", f"{_ACCENT},bold", "default"),
    ("menubar", "black", "light gray", "", "black", _KEYS),
    ("menu_title", "black", "light gray", "", "black", _KEYS),
    ("menu_focus", "white", "dark blue", "", "white", _BLUE),
    ("menu_drop", "black", "light gray", "", "black", _KEYS),
    ("dim", "dark gray", "default", "", "g50", "default"),
    ("update", "light green,bold", "default", "", "#8f8,bold", "default"),  # ↑ flag
    ("pb_normal", "white", "dark magenta", "", "white", _BAR),   # progress: unfilled
    ("pb_complete", "black", "light magenta", "", "black", _ACCENT),  # filled
]

# ANSI SGR foreground colours (normal and bold/bright) mapped to urwid names.
_FG = {30: "black", 31: "dark red", 32: "dark green", 33: "brown",
       34: "dark blue", 35: "dark magenta", 36: "dark cyan", 37: "light gray"}
_FG_BOLD = {30: "dark gray", 31: "light red", 32: "light green", 33: "yellow",
            34: "light blue", 35: "light magenta", 36: "light cyan", 37: "white"}
ANSI_PALETTE = (
    [(f"ansi{c}", col, "") for c, col in _FG.items()]
    + [(f"ansib{c}", col, "") for c, col in _FG_BOLD.items()]
    + [("ansib", "white", "")]
)
PALETTE.extend(ANSI_PALETTE)


# Terminal escape sequences (colour/cursor/OSC) that appear in subprocess
# output; strip them so they don't render as literal junk in the TUI.
_ANSI_RE = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"   # OSC (title, …) — match before 2-char
    r"|\x1b\[[0-9;?]*[ -/]*[@-~]"          # CSI (colour, cursor, …)
    r"|\x1b[@-Z\\-_]"                       # other two-char escapes
)


def strip_ansi(text: str) -> str:
    """Remove terminal escape sequences from a line of command output."""
    return _ANSI_RE.sub("", text)


_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def _ansi_attr(bold: bool, fg: int | None) -> str | None:
    if fg is not None:
        return f"ansib{fg}" if bold else f"ansi{fg}"
    return "ansib" if bold else None


def ansi_markup(text: str):
    """Convert a line with ANSI SGR codes into urwid markup (colour segments).

    Returns a plain ``str`` when the line has no colour, else a list of
    ``(attr, str)`` / ``str`` segments suitable for a Text/SelectableIcon.
    Non-SGR escapes (cursor, OSC) are stripped from the text.
    """
    markup: list = []
    pos = 0
    bold = False
    fg: int | None = None

    def emit(chunk: str) -> None:
        chunk = strip_ansi(chunk)
        if not chunk:
            return
        attr = _ansi_attr(bold, fg)
        markup.append((attr, chunk) if attr else chunk)

    for m in _SGR_RE.finditer(text):
        if m.start() > pos:
            emit(text[pos:m.start()])
        for part in (m.group(1).split(";") if m.group(1) else ["0"]):
            n = int(part or "0")
            if n == 0:
                bold, fg = False, None
            elif n == 1:
                bold = True
            elif n == 22:
                bold = False
            elif 30 <= n <= 37:
                fg = n
            elif n == 39:
                fg = None
            elif 90 <= n <= 97:
                fg, bold = n - 60, True
        pos = m.end()
    if pos < len(text):
        emit(text[pos:])

    if not markup:
        return ""
    if len(markup) == 1 and isinstance(markup[0], str):
        return markup[0]
    return markup


def function_bar(keys: list[tuple[str, str]]) -> urwid.Widget:
    """A YaST-style function-key footer: reversed key chips + labels."""
    markup: list = []
    for key, label in keys:
        markup.append(("footer_key", f" {key} "))
        markup.append(("footer", f" {label}   "))
    return urwid.AttrMap(urwid.Text(markup or ""), "footer")


def boxed(widget: urwid.Widget, title: str = "", **kw) -> urwid.Widget:
    """A LineBox with a Gentoo-purple outline and a lavender title.

    The content is shielded (its unattributed cells map to ``body`` = default)
    so the outer purple attr colours only the frame, never the inner text. When
    the pane holds focus the outline turns blue (``boxline_focus``).
    """
    kw.setdefault("title_attr", "box_title")
    shielded = urwid.AttrMap(widget, {None: "body"})
    # focus_map lights the outline blue when this pane holds focus.
    return urwid.AttrMap(
        urwid.LineBox(shielded, title=title, **kw),
        {None: "boxline"}, {None: "boxline_focus"})


def _header_row(title: str) -> urwid.Widget:
    """Top-bar contents: the title on the left, and a centered 'User Mode' banner
    when GeST runs unprivileged (not root). The banner sits between two
    equal-weight spacers so it stays centered regardless of the title's length.
    """
    title_w = urwid.Text(f" {title}")
    if _IS_ROOT:
        return title_w
    return urwid.Columns([
        ("weight", 1, title_w),
        ("pack", urwid.AttrMap(urwid.Text("User Mode"), "header_mode")),
        ("weight", 1, urwid.Text("")),
    ])


class NavPile(urwid.Pile):
    """A Pile whose arrow keys never move focus between its items — pane
    switching is Tab-only (see ``Screen.configure_pane_cycle``), so up/down
    can't wander from one pane into another (a list, a menu bar, an action row).

    ``porous_from`` names widget types that a *downward* move is allowed to
    leave (e.g. a filter ``Edit`` above a list): pressing Down in one of those
    drops into the next pane as usual, but Up/Down inside the list won't jump
    back out.
    """

    def __init__(self, widget_list, *, porous_from: tuple[type, ...] = ()):
        super().__init__(widget_list)
        self._porous_from = porous_from

    def keypress(self, size, key):
        before = self.focus_position
        result = super().keypress(size, key)
        if result is None and key in ("up", "down") and self.focus_position != before:
            leaving = self.contents[before][0].base_widget
            if key == "down" and isinstance(leaving, self._porous_from):
                return None                       # allow Down to leave (e.g. Edit)
            self.focus_position = before          # otherwise undo the arrow move
            return key
        return result


class ActionRow(urwid.Columns):
    """A right-aligned row of focusable ``[Label]`` buttons that own their
    callbacks. Tab lands on each; Enter/Space on the focused one fires it. Used
    for Cancel/Accept-style action bars (replaces the visual-only action_bar)."""

    def __init__(self, actions: list[tuple[str, Callable[[], None]]]):
        self.buttons: list[urwid.Widget] = []
        self._cb: dict[int, Callable[[], None]] = {}
        cols: list = [urwid.Text("")]                 # spacer → right-align
        for label, cb in actions:
            markup = ["[", ("cc_title", label[:1]), f"{label[1:]}]"]
            btn = urwid.AttrMap(urwid.SelectableIcon(markup, 0), None,
                                focus_map="focus")
            self.buttons.append(btn)
            self._cb[id(btn)] = cb
            cols += [("pack", btn), ("pack", urwid.Text("  "))]
        super().__init__(cols)

    def button_position(self, index: int) -> int:
        """The Columns focus_position of the ``index``-th button (after the
        leading spacer, buttons sit at odd positions 1, 3, …)."""
        return 1 + index * 2

    def activate_focused(self) -> bool:
        cb = self._cb.get(id(self.focus))
        if cb is not None:
            cb()
            return True
        return False


def focusable_actions(actions: list[tuple[str, Callable[[], None]]]) -> ActionRow:
    """A Tab-reachable Cancel/Accept-style action row (see :class:`ActionRow`)."""
    return ActionRow(actions)


class Screen(urwid.WidgetWrap):
    """Base screen: a framed widget with a title header and a footer holding a
    transient status line above the function-key bar.

    Subclasses build ``body`` and may override ``handle_key`` for screen-level
    keys (nav keys reach the focused body widget first).

    Chrome conventions (keep these consistent across screens):
    - **F1** opens a help overlay on every screen — pass ``help_text`` for
      bespoke help, else one is synthesised from ``footer_keys``. F1 is added to
      the footer automatically.
    - **Esc** steps back (``app.pop``) — every module screen handles it and lists
      ``("Esc", "Back")`` last in its ``footer_keys``.
    - **F10** applies/accepts a pending change where a screen has one.
    - **Quit is top-level only**: the Control Center menu handles q/Q/F9;
      sub-screens never exit the app (use Esc to back out).
    """

    def __init__(self, app: App, body: urwid.Widget, *, title: str = "",
                 footer_keys: list[tuple[str, str]] | None = None,
                 help_text: str = ""):
        self.app = app
        self._title = title
        self._status = urwid.Text("")
        keys = list(footer_keys or [])
        # context-sensitive footer + Tab pane-cycle state (opt-in; the defaults
        # below leave simple single-pane screens behaving exactly as before).
        self._base_footer_keys = list(footer_keys or [])   # the default context
        self._shown_footer_keys: list | None = None        # cache: skip rebuilds
        self._cycle_container = None                        # set via configure_pane_cycle
        self._cycle_positions: list = []
        self._cycle_action_row: ActionRow | None = None
        self._cycle_action_pos: int | None = None
        # Every screen gets an F1 help overlay. When a screen doesn't supply its
        # own help_text, synthesise one from its function-key list so help is
        # always available and consistent.
        if not help_text and keys:
            help_text = "Keys:\n" + "\n".join(f"  {k:<10} {d}" for k, d in keys)
        self._help_text = help_text
        if help_text and not any(label == "F1" for label, _desc in keys):
            keys = [("F1", "Help"), *keys]
        header = urwid.AttrMap(_header_row(title), "header")
        self._footer = urwid.Pile([self._status, function_bar(keys)])
        self._frame = urwid.Frame(body, header=header, footer=self._footer)
        super().__init__(self._frame)

    def set_body(self, body: urwid.Widget) -> None:
        self._frame.body = body

    def set_footer_keys(self, keys: list[tuple[str, str]]) -> None:
        """Replace the displayed function-key bar (F1 Help is always kept), so a
        screen can show only the keys relevant to the current focus."""
        keys = list(keys)
        if self._help_text and not any(k == "F1" for k, _ in keys):
            keys = [("F1", "Help"), *keys]
        self._footer.contents[1] = (function_bar(keys),
                                    self._footer.contents[1][1])

    def set_status(self, text: str, attr: str = "hint") -> None:
        self._status.set_text((attr, f" {text}") if text else "")

    def show_help(self) -> None:
        """Open a modal with this screen's help text (F1)."""
        if not self._help_text:
            return
        rows = [urwid.Text(line) for line in self._help_text.split("\n")]
        modal = Modal(self.app, f"Help — {self._title}", rows,
                      [("Close", self.app.pop)])
        self.app.push_modal(modal, width=("relative", 70))

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key is not None:
            key = self._nav_keypress(key)      # Tab / action-button Enter
        if key == "f1" and self._help_text:
            self.show_help()
            key = None
        elif key is not None:
            key = self.handle_key(key)
        self._refresh_footer()                 # focus may have moved
        return key

    def handle_key(self, key):  # override
        return key

    # -- Tab pane-cycle + context footer (opt-in) ---------------------------

    def configure_pane_cycle(self, container, positions, *,
                             action_row: ActionRow | None = None) -> None:
        """Declare the ordered focus stops for Tab. ``container`` is the top
        Pile/Columns; ``positions`` its focus_positions that are stops; each
        button of ``action_row`` (already a child of ``container``) becomes a
        trailing stop. Enables Tab/Shift-Tab cycling and button activation."""
        self._cycle_container = container
        self._cycle_positions = list(positions)
        self._cycle_action_row = action_row
        self._cycle_action_pos = None
        if action_row is not None:
            for i, (w, _opts) in enumerate(container.contents):
                if w is action_row:
                    self._cycle_action_pos = i
                    break

    def _nav_keypress(self, key):
        if self._cycle_container is None:
            return key                          # not configured → unchanged
        if key == "tab":
            self._cycle_pane(1)
            return None
        if key == "shift tab":
            self._cycle_pane(-1)
            return None
        if (key in ("enter", " ") and self._on_action_row()
                and self._cycle_action_row.activate_focused()):
            return None
        return key

    def _on_action_row(self) -> bool:
        return (self._cycle_action_pos is not None
                and self._cycle_container.focus_position == self._cycle_action_pos)

    def _cycle_stops(self):
        stops = [("pane", p) for p in self._cycle_positions]
        if self._cycle_action_row is not None:
            stops += [("btn", i) for i in range(len(self._cycle_action_row.buttons))]
        return stops

    def _current_stop(self, stops) -> int:
        pos = self._cycle_container.focus_position
        if self._on_action_row():
            btn = (self._cycle_action_row.focus_position - 1) // 2
            for i, (kind, val) in enumerate(stops):
                if kind == "btn" and val == btn:
                    return i
            return 0
        for i, (kind, val) in enumerate(stops):
            if kind == "pane" and val == pos:
                return i
        return 0

    def _cycle_pane(self, delta: int) -> None:
        stops = self._cycle_stops()
        if not stops:
            return
        kind, val = stops[(self._current_stop(stops) + delta) % len(stops)]
        if kind == "pane":
            self._cycle_container.focus_position = val
        else:
            self._cycle_container.focus_position = self._cycle_action_pos
            self._cycle_action_row.focus_position = \
                self._cycle_action_row.button_position(val)

    def _footer_context(self) -> list[tuple[str, str]]:
        """Keys applicable to the current focus. Default: the static footer_keys
        (so simple screens are unchanged). Override for multi-context screens."""
        return self._base_footer_keys

    def _refresh_footer(self) -> None:
        keys = self._footer_context()
        if keys != self._shown_footer_keys:     # no-op unless the context changed
            self._shown_footer_keys = keys
            self.set_footer_keys(keys)


class Modal(urwid.WidgetWrap):
    """A form modal: title, body rows, and a centered row of buttons.

    ``buttons`` is ``[(label, callback), …]``; Esc cancels (pops the overlay).
    """

    def __init__(self, app: App, title: str, rows: list, buttons: list,
                 *, button_width: int = 16):
        self.app = app
        # The first button is the primary action (Save/Accept); Enter on a field
        # fires it, so single-field dialogs (hostname, a size, a password) submit
        # without Tab-ing to the button (see keypress).
        self._primary = buttons[0][1] if buttons else None
        button_widgets = [
            urwid.AttrMap(urwid.Button(label, on_press=lambda _b, cb=cb: cb()),
                          None, focus_map="focus")
            for label, cb in buttons
        ]
        grid = urwid.GridFlow(button_widgets, cell_width=button_width, h_sep=2,
                              v_sep=1, align="center")
        self._pile = urwid.Pile(
            [urwid.Text(("title", title)), urwid.Divider(), *rows,
             urwid.Divider(), grid]
        )
        super().__init__(urwid.Filler(self._pile, valign="top"))

    def _cycle_focus(self, step: int) -> None:
        """Tab/Shift-Tab across the modal's focusable widgets — each selectable
        row (a field, a list) and the button row are separate stops, so a form
        with a search box + list + buttons cycles through all three."""
        positions = [i for i, (w, _o) in enumerate(self._pile.contents)
                     if w.selectable()]
        if not positions:
            return
        cur = self._pile.focus_position
        idx = positions.index(cur) if cur in positions else 0
        self._pile.focus_position = positions[(idx + step) % len(positions)]

    def focus_buttons(self) -> None:
        """Move focus to the button row (Accept/Cancel). List pickers wire this to
        Enter, so staging a choice advances to the Accept gate instead of firing."""
        self._pile.focus_position = len(self._pile.contents) - 1

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == "esc":
            self.app.pop()
            return None
        if key in ("tab", "shift tab"):
            self._cycle_focus(1 if key == "tab" else -1)
            return None
        # Enter on a field (a button/list would have consumed it above) submits via
        # the primary button — no need to Tab to Save.
        if key == "enter" and self._primary is not None:
            self._primary()
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
        urwid.set_encoding("utf-8")  # render UTF-8 regardless of locale detection
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
        # Ask for 256 colours so the Gentoo-purple high-colour values render;
        # terminals that can't fall back to the 16-colour magenta in each entry.
        with contextlib.suppress(Exception):
            self.main.screen.set_terminal_properties(colors=256)

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

    def replace(self, widget: urwid.Widget) -> None:
        """Swap the top screen for ``widget`` in a single redraw, so the screen
        beneath never flashes (used to hand a finished flow straight to the next
        one, e.g. an uninstall into Clean Up)."""
        if len(self._stack) > 1:
            self._stack.pop()
        self._stack.append(widget)
        self.main.widget = widget
        self.refresh()

    def pop_to(self, widget: urwid.Widget) -> None:
        """Pop screens until ``widget`` is on top (or only the root remains)."""
        while len(self._stack) > 1 and self._stack[-1] is not widget:
            self._stack.pop()
        self.main.widget = self._stack[-1]
        self.refresh()

    def pop_to_root(self) -> None:
        """Pop every screen back to the root (the Control Center main menu)."""
        del self._stack[1:]
        self.main.widget = self._stack[-1]
        self.refresh()

    def push_modal(self, modal: urwid.Widget, *, width=64, height=None) -> None:
        overlay = urwid.Overlay(
            boxed(modal),
            self._stack[-1],
            align="center", width=width, min_width=24,
            valign="middle", height=("pack" if height is None else height),
        )
        self.push(overlay)

    def push_overlay(self, widget: urwid.Widget, *, width, height,
                     align="center", valign="middle", left=0, top=0) -> None:
        """Push a positioned overlay (used for menu dropdowns)."""
        overlay = urwid.Overlay(
            widget, self._stack[-1],
            align=align, width=width, valign=valign, height=height,
            left=left, top=top, min_width=12,
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

    async def run_in_terminal(self, argv: list[str], *, cwd: str | None = None) -> int:
        """Suspend the TUI and run ``argv`` interactively on the real terminal.

        Stops the urwid *screen* only (not the event loop), so the subprocess
        inherits the real tty for an interactive session (e.g. a recovery shell),
        then restores the screen. Returns the subprocess exit code.
        """
        screen = self.main.screen
        screen.stop()                          # hand the terminal back to the child
        try:
            return await self.loop.run_in_executor(
                None, lambda: subprocess.call(argv, cwd=cwd))
        finally:
            screen.start()                     # reclaim the terminal for urwid
            self.refresh()

    def quit(self) -> None:
        raise urwid.ExitMainLoop()

    def run(self, root: urwid.Widget) -> None:
        from gest.tui.console import quiet_kernel_console

        self.push(root)
        # Keep kernel printk (warnings, udev noise) from painting over the TUI on
        # a text console; restored on exit. No-op off a VT / unprivileged.
        with quiet_kernel_console():
            self.main.run()

    def _unhandled(self, key):
        # Quitting is a top-level action: the Control Center menu handles q/Q/F9.
        # Sub-screens use Esc to step back rather than exiting the whole app.
        return


async def _guard(app: App, coro: Awaitable) -> None:
    try:
        await coro
    except Exception as exc:  # never let a worker crash the loop
        app.notify(str(exc), error=True)
