"""Shared polkit authorization check for backend interfaces."""

from __future__ import annotations

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


def authorization_variant(sender: str, action_id: str) -> GLib.Variant:
    """Build the polkit CheckAuthorization argument.

    The subject struct must be an inline tuple — embedding a pre-built
    GLib.Variant here raises TypeError on newer PyGObject (Python 3.14+).
    """
    return GLib.Variant(
        "((sa{sv})sa{ss}us)",
        (("system-bus-name", {"name": GLib.Variant("s", sender)}), action_id, {}, 1, ""),
    )


def authorization_is_granted(result: GLib.Variant) -> bool:
    """Extract is_authorized from a polkit CheckAuthorization reply.

    Newer PyGObject returns the out-args tuple wrapped — ``((bool, bool,
    a{ss}),)`` — while older versions returned the struct flat. Handle both.
    """
    data = result.unpack()
    inner = data[0] if len(data) == 1 and isinstance(data[0], tuple) else data
    return bool(inner[0])


def check_authorization(conn, sender: str, action_id: str) -> bool:
    """Ask polkit whether ``sender`` (a system-bus name) may do ``action_id``."""
    try:
        authority = Gio.DBusProxy.new_sync(
            conn,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.PolicyKit1",
            "/org/freedesktop/PolicyKit1/Authority",
            "org.freedesktop.PolicyKit1.Authority",
            None,
        )
        result = authority.call_sync(
            "CheckAuthorization",
            authorization_variant(sender, action_id),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        return authorization_is_granted(result)
    except GLib.Error:
        return False


def caller_uid(conn, sender: str) -> int | None:
    """Resolve the uid behind a system-bus sender name (for audit logging)."""
    try:
        proxy = Gio.DBusProxy.new_sync(
            conn,
            Gio.DBusProxyFlags.NONE,
            None,
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            None,
        )
        result = proxy.call_sync(
            "GetConnectionUnixUser",
            GLib.Variant("(s)", (sender,)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        (uid,) = result.unpack()
        return int(uid)
    except Exception:
        return None
