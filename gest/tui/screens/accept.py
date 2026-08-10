"""Software Management Accept (urwid): organized install + remove progress.

Replaces the raw streaming ApplyScreen dump for the Accept flow. Accept can both
install/update packages and remove others (a depclean pass), so this seeds a row
per marked package and advances each from emerge's markers — installs via
``>>> Emerging/Installing (N of M) …`` (pending → building → installed), removals
via ``>>> Unmerging (N of M) …`` (pending → removing → removed) — with a progress
bar and a combined result. The plans run sequentially (installs, then removals);
the full raw log is kept on demand (l / View log).
"""

from __future__ import annotations

import asyncio
import contextlib

import urwid

from gest.core.software.backend_client import SoftwareBackend
from gest.core.software.cleanup import parse_unmerge
from gest.core.software.update import parse_merge_progress, split_cpv
from gest.tui.runtime import App, Modal, Screen
from gest.tui.screens.apply import (
    RawLogScreen,
    StreamLog,
    install_binary_plan,
    install_plan,
    remove_plan,
)

_STATUS_W = 2
_CAT_W = 16
_PKG_W = 26

# active = building (install) or removing (remove); done = installed / removed.
_GLYPH = {"pending": "·", "active": "▸", "done": "✓", "failed": "✗"}
_ATTR = {"pending": "dim", "active": None, "done": "dim", "failed": "error"}


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width - 1 else text[: width - 2] + "…"


def _fmt(glyph: str, cat: str, pkg: str, op: str) -> str:
    return (f"{glyph:<{_STATUS_W}}{_clip(cat, _CAT_W):<{_CAT_W}}"
            f"{_clip(pkg, _PKG_W):<{_PKG_W}}{op}")


def _row(text: str, attr: str | None = None) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")
    return urwid.AttrMap(icon, attr, focus_map="focus")


class _Item:
    __slots__ = ("category", "cp", "detail", "kind", "package", "status")

    def __init__(self, cp: str, kind: str):
        self.cp, self.kind = cp, kind          # kind: "install" | "remove"
        self.category, _, self.package = cp.partition("/")
        if not self.package:
            self.package = cp
        self.detail = ""                       # version, filled from the markers
        self.status = "pending"

    def op_text(self) -> str:
        label = "install" if self.kind == "install" else "remove"
        return f"{label} {self.detail}" if self.detail else label


class AcceptRunScreen(StreamLog, Screen):
    def __init__(self, app: App, *, installs=(), binpkgs=(), binprefs=(),
                 removes=(), verb: str = "Accept", on_done=None):
        self._on_done = on_done
        self._plans = []
        if installs:
            self._plans.append(install_plan(list(installs)))
        if binpkgs:
            self._plans.append(install_binary_plan(list(binpkgs), only=True))
        if binprefs:
            self._plans.append(install_binary_plan(list(binprefs), only=False))
        if removes:
            self._plans.append(remove_plan(list(removes)))

        self._items = [_Item(cp, "install")
                       for cp in (*installs, *binpkgs, *binprefs)]
        self._items += [_Item(cp, "remove") for cp in removes]
        self._install = {it.cp: it for it in self._items if it.kind == "install"}
        self._remove = {it.cp: it for it in self._items if it.kind == "remove"}
        self._total = len(self._items)
        self._done = False
        self._logfile = None
        self._logpath: str | None = None
        self._refresh_pending = False

        self._walker = urwid.SimpleFocusListWalker([])
        self._list = urwid.ListBox(self._walker)
        self._phase = urwid.Text(("dim", " Preparing …"))
        self._bar = urwid.ProgressBar("pb_normal", "pb_complete", 0, max(self._total, 1))

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Category", "Package", "Operation"), wrap="clip"),
            "pane_title")
        table = urwid.LineBox(
            urwid.Pile([("pack", header), ("pack", urwid.Divider("─")),
                        ("weight", 1, self._list)]),
            title="Applying changes")
        body = urwid.Pile([
            ("pack", urwid.AttrMap(self._phase, "field")),
            ("pack", self._bar),
            ("pack", urwid.Divider("─")),
            ("weight", 1, table),
        ])
        super().__init__(
            app, body, title="Software Management",
            footer_keys=[("l", "View log"), ("Esc", "Back")],
            help_text=(
                "Applying the marked changes with emerge (installs first, then a\n"
                "depclean removal pass).\n\n"
                "Each row shows its status:  · pending   ▸ in progress   ✓ done"
                "   ✗ failed\n"
                "Packages pulled in as dependencies appear as they are built.\n"
                "The full raw emerge log is kept on disk — press l (or View log on\n"
                "failure) to read it. Esc returns when it finishes."
            ),
        )
        self._render()
        app.run_async(self._run())

    def _render(self) -> None:
        rows = [_row(_fmt(_GLYPH[it.status], it.category, it.package, it.op_text()),
                     _ATTR[it.status])
                for it in self._items] or [urwid.Text(" (nothing to apply)")]
        self._walker[:] = rows
        self._schedule_refresh()

    def _set_phase(self, text: str, attr: str = "field") -> None:
        self._phase.set_text((attr, f" {text}"))

    def _advance(self) -> None:
        done = sum(1 for it in self._items if it.status == "done")
        self._bar.set_completion(min(done, self._total))
        self._render()

    # -- run (plans sequentially) -------------------------------------------

    async def _run(self) -> None:
        self._set_phase("Applying changes …")
        overall = 0
        aborted = False
        for plan in self._plans:
            code = await self._run_one(plan)
            if code is None:
                aborted = True
                break
            overall = overall or code
        self._close_log()
        self._finish(None if aborted else overall)

    async def _run_one(self, plan) -> int | None:
        finished = asyncio.Event()
        result: dict[str, int | None] = {"code": None}

        def on_progress(lines: list[str]) -> None:
            self._write_log(lines)
            for ln in lines:
                self._consume(ln)

        def on_finished(code: int) -> None:
            result["code"] = code
            finished.set()

        backend = SoftwareBackend()
        try:
            await backend.connect()
            started = await plan.run(backend, on_progress, on_finished)
        except Exception:
            with contextlib.suppress(Exception):
                await backend.close()
            return None
        if not started:
            await backend.close()
            return None
        await finished.wait()
        await backend.close()
        return result["code"]

    def _consume(self, line: str) -> None:
        p = parse_merge_progress(line)
        if p is not None:
            cp, ver = split_cpv(p.atom)
            row = self._install.get(cp) or self._add(cp, "install")
            row.detail = ver
            row.status = "active" if p.phase == "Emerging" else "done"
            self._set_phase(f"{p.phase} {p.n} of {p.total} — {p.atom}")
            self._advance()
            return
        u = parse_unmerge(line)
        if u is not None:
            cp, ver = split_cpv(u.atom)
            for it in self._items:             # unmerge has one marker per package
                if it.kind == "remove" and it.status == "active":
                    it.status = "done"
            row = self._remove.get(cp) or self._add(cp, "remove")
            row.detail = ver
            row.status = "active"
            self._set_phase(f"Removing {u.atom}")
            self._advance()

    def _add(self, cp: str, kind: str) -> _Item:
        item = _Item(cp, kind)
        self._items.append(item)
        (self._install if kind == "install" else self._remove)[cp] = item
        self._total = len(self._items)
        self._bar.done = max(self._total, 1)
        return item

    def _finish(self, code: int | None) -> None:
        self._done = True
        ok = code == 0
        if ok:
            for it in self._items:
                if it.status in ("pending", "active"):
                    it.status = "done"
        elif code is not None:
            for it in self._items:
                if it.status == "active":
                    it.status = "failed"
        self._bar.set_completion(self._total if ok else self._bar.current)
        self._render()
        if self._on_done is not None and code is not None:
            with contextlib.suppress(Exception):
                self._on_done()
        installed = sum(1 for it in self._items
                        if it.kind == "install" and it.status == "done")
        removed = sum(1 for it in self._items
                      if it.kind == "remove" and it.status == "done")
        if code is None:
            title, ok, msg = "Not started", False, (
                "The operation did not start — administrator authentication was "
                "declined, or the backend was unavailable. Nothing was changed.")
        elif ok:
            parts = []
            if installed:
                parts.append(f"installed {installed}")
            if removed:
                parts.append(f"removed {removed}")
            title, msg = "Completed", (
                f"Done — {', '.join(parts) or 'no changes'} package(s).")
        else:
            title, msg = "Failed", (
                f"emerge exited {code}. The changes may be incomplete; see the log.")
        self._set_phase(f"{title.lower()}", "ok" if ok else "error")
        self._result_modal(title, ok, msg)

    def _result_modal(self, title: str, ok: bool, message: str) -> None:
        self.app.notify(title.lower(), error=not ok)
        if self._logpath:
            message = f"{message}\n\nFull log: {self._logpath}"

        def back():
            self.app.pop()   # the result modal
            self.app.pop()   # the run screen → back to Software Management

        def view():
            self.app.pop()
            self._view_log()

        modal = Modal(self.app, title,
                      [urwid.Text(("ok" if ok else "error", message))],
                      [("Back", back), ("View log", view)])
        self.app.push_modal(modal, width=("relative", 62), height=("relative", 40))

    def _view_log(self) -> None:
        self.app.push(RawLogScreen(self.app, self._logpath))

    def handle_key(self, key):
        if key == "esc" and self._done:
            self.app.pop()
        elif key in ("l", "L"):
            self._view_log()
        else:
            return key
        return None
