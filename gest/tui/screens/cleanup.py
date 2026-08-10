"""Clean Up Packages (urwid): an organized review of what depclean would remove.

Instead of dumping raw ``emerge --pretend --depclean --verbose`` (a safety lecture
plus a "pulled in by" block for every *kept* package), this parses the orphan
list into a table — Category · Package · Version · reclaimable Size — with the
summary counts in a Details panel. Space keeps/removes an individual package;
F10 hands off to the streaming ApplyScreen to actually run ``emerge --depclean``
(on the whole set, or just the selected atoms).
"""

from __future__ import annotations

import urwid

from gest.core.software import cleanup
from gest.core.software.cleanup import Orphan, human_size
from gest.tui.runtime import App, Screen, action_bar
from gest.tui.screens.apply import ApplyScreen, depclean_plan, remove_plan

_MARK_W = 2   # ✓ = will be removed
_CAT_W = 16
_PKG_W = 22
_VER_W = 22
_SIZE_W = 11


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width - 1 else text[: width - 2] + "…"


def _fmt(mark: str, cat: str, pkg: str, ver: str, size: str) -> str:
    return (f"{mark:<{_MARK_W}}{_clip(cat, _CAT_W):<{_CAT_W}}"
            f"{_clip(pkg, _PKG_W):<{_PKG_W}}{_clip(ver, _VER_W):<{_VER_W}}"
            f"{size:>{_SIZE_W}}")


def _orphan_line(o: Orphan, keep: bool) -> str:
    mark = "" if keep else "✓"
    return _fmt(mark, o.category, o.package, o.version, human_size(o.size))


def _row(text: str, attr: str | None = None) -> urwid.Widget:
    icon = urwid.SelectableIcon(text, 0)
    icon.set_wrap_mode("clip")
    return urwid.AttrMap(icon, attr, focus_map="focus")


class CleanupScreen(Screen):
    def __init__(self, app: App) -> None:
        self._plan: cleanup.CleanupPlan | None = None
        self._kept: set[str] = set()   # cp of packages the user chose to keep
        self._walker = urwid.SimpleFocusListWalker([urwid.Text(" scanning …")])
        self._list = urwid.ListBox(self._walker)

        header = urwid.AttrMap(
            urwid.Text(_fmt("", "Category", "Package", "Version", "Size"),
                       wrap="clip"),
            "pane_title")
        table = urwid.LineBox(
            urwid.Pile([
                ("pack", header),
                ("pack", urwid.Divider("─")),
                ("weight", 1, self._list),
            ]),
            title="Orphaned packages")

        self._details = urwid.Pile([urwid.Text("")])
        details_box = urwid.LineBox(self._details, title="Details")
        self._count = urwid.Text("")

        body = urwid.Pile([
            ("weight", 1, table),
            ("pack", details_box),
            ("pack", self._count),
            ("pack", action_bar(["Cancel", "Clean up"])),
        ])
        super().__init__(
            app, body, title="Clean Up Packages",
            footer_keys=[
                ("Space", "Keep/Remove"), ("a", "All"), ("n", "None"),
                ("F10", "Clean up"), ("Esc", "Back"),
            ],
            help_text=(
                "Orphaned packages — installed but no longer required by any other\n"
                "installed package or by your @world set. Removing them is safe:\n"
                "depclean never removes a package something still needs.\n\n"
                "Columns:  Category · Package · Version · Size (space reclaimed).\n"
                "A ✓ marks a package for removal (all are marked by default).\n\n"
                "Space  keep / remove the highlighted package\n"
                "a      mark all for removal      n  keep all\n"
                "F10    clean up the marked packages (runs emerge --depclean)\n"
                "Esc    back"
            ),
        )
        app.run_async(self._load())

    async def _load(self) -> None:
        self._kept.clear()
        self._plan = await self.app.run_blocking(cleanup.plan_cleanup)
        self._rebuild()

    # -- rendering ----------------------------------------------------------

    def _orphans(self) -> list[Orphan]:
        return self._plan.orphans if self._plan else []

    def _rebuild(self) -> None:
        focus = self._walker.focus or 0
        plan = self._plan
        if plan is not None and not plan.ok:
            self._walker[:] = [urwid.Text(("error", f" {plan.error}"))]
        elif not self._orphans():
            self._walker[:] = [
                urwid.Text(("ok", " Nothing to clean up — no orphaned packages."))]
        else:
            self._walker[:] = [_row(_orphan_line(o, o.cp in self._kept),
                                    "dim" if o.cp in self._kept else None)
                               for o in self._orphans()]
            self._walker.set_focus(min(focus, len(self._orphans()) - 1))
        self._render_details()
        self._refresh_count()
        self.app.refresh()

    def _render_details(self) -> None:
        rows: list[urwid.Widget]
        if self._plan is None or not self._plan.ok:
            rows = [urwid.Text(("hint", " emerge could not compute a clean-up plan."))]
        else:
            c = self._plan.counts

            def n(key: str) -> str:
                return str(c[key]) if key in c else "—"

            rows = [
                urwid.Text([("field", " "), "No longer required by any installed "
                            "package or your @world set — removal is safe."]),
                urwid.Text([("field", " Installed "), n("installed"),
                            ("field", "   World "), n("world"),
                            ("field", "   System "), n("system")]),
            ]
        self._details.contents = [(w, self._details.options("pack")) for w in rows]

    def _refresh_count(self) -> None:
        orphans = self._orphans()
        if not orphans:
            self._count.set_text(("dim", " No packages to clean up"))
            return
        selected = [o for o in orphans if o.cp not in self._kept]
        size = human_size(sum(o.size for o in selected))
        total = len(orphans)
        if not selected:
            self._count.set_text(("dim", f" Keeping all {total} — nothing marked"))
            return
        scope = (f"{len(selected)} package{'s' if len(selected) != 1 else ''}"
                 if len(selected) == total
                 else f"{len(selected)} of {total} packages")
        self._count.set_text([
            ("ok", f" Clean up {scope}"),
            ("dim", f"   ·   {size} reclaimable   ·   F10 Clean up"),
        ])

    # -- keys ---------------------------------------------------------------

    def _current(self) -> Orphan | None:
        orphans = self._orphans()
        if orphans and 0 <= self._walker.focus < len(orphans):
            return orphans[self._walker.focus]
        return None

    def handle_key(self, key):
        if key == "esc":
            self.app.pop()
        elif key == "r":
            self.app.run_async(self._load())
        elif key == " ":
            self._toggle()
        elif key == "a":
            self._kept.clear()
            self._rebuild()
        elif key == "n":
            self._kept = {o.cp for o in self._orphans()}
            self._rebuild()
        elif key == "f10":
            self._clean()
        else:
            return key
        return None

    def _toggle(self) -> None:
        orphan = self._current()
        if orphan is None:
            return
        self._kept.discard(orphan.cp) if orphan.cp in self._kept \
            else self._kept.add(orphan.cp)
        self._rebuild()

    def _clean(self) -> None:
        selected = [o for o in self._orphans() if o.cp not in self._kept]
        if not selected:
            self.app.notify("Nothing marked to clean up.", error=True)
            return
        reload_after = lambda: self.app.run_async(self._load())  # noqa: E731
        if len(selected) == len(self._orphans()):
            plan = depclean_plan()                       # all orphans (bare depclean)
        else:
            plan = remove_plan([o.cp for o in selected])  # just the marked atoms
        self.app.push(ApplyScreen(self.app, [plan], verb="Clean up",
                                  on_done=reload_after))
