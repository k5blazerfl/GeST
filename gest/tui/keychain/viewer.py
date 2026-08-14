"""A read-only urwid viewer for the keychain vault.

Deliberately minimal and *read-only*: it lists collections and their items with
attributes, never revealing a secret (that stays an explicit ``keychainctl get``).
The row rendering is a pure function so it is unit-testable without a display; the
urwid loop is a thin shell around it.
"""

from __future__ import annotations

from collections.abc import Iterable

from gest.core.keychain.model import Collection


def build_rows(collections: Iterable[Collection]) -> list[str]:
    """Flatten collections + items into display lines (no secrets). Pure."""
    rows: list[str] = []
    cols = list(collections)
    if not cols:
        return ["(empty vault)"]
    for col in cols:
        alias = f" ({', '.join(col.aliases)})" if col.aliases else ""
        rows.append(f"▸ {col.label}{alias}  —  {len(col.items)} item(s)")
        for item in col.items.values():
            attrs = ", ".join(f"{k}={v}" for k, v in sorted(item.attributes.items()))
            detail = f"    {item.label}"
            if attrs:
                detail += f"   [{attrs}]"
            rows.append(detail)
    return rows


def run_viewer(vault) -> None:  # pragma: no cover - interactive urwid loop
    """Open the vault's collections in a scrollable read-only list. Requires an
    already-unlocked :class:`~gest.core.keychain.vault.Vault`."""
    import urwid

    rows = build_rows(vault.collections())
    body = urwid.SimpleFocusListWalker([urwid.Text(r) for r in rows])
    listbox = urwid.ListBox(body)
    header = urwid.AttrMap(urwid.Text("  Keychain — read-only  "), "header")
    footer = urwid.AttrMap(urwid.Text("  q: quit   (secrets are never shown here)  "), "footer")
    frame = urwid.Frame(listbox, header=header, footer=footer)

    def unhandled(key: str) -> None:
        if key in ("q", "Q", "esc"):
            raise urwid.ExitMainLoop()

    palette = [("header", "white", "dark blue"), ("footer", "white", "dark gray")]
    urwid.MainLoop(frame, palette=palette, unhandled_input=unhandled).run()
