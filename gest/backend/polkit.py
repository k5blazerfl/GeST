"""Shared polkit authorization check for backend interfaces."""

from __future__ import annotations

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


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
        subject = GLib.Variant(
            "(sa{sv})", ("system-bus-name", {"name": GLib.Variant("s", sender)})
        )
        result = authority.call_sync(
            "CheckAuthorization",
            GLib.Variant("((sa{sv})sa{ss}us)", (subject, action_id, {}, 1, "")),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        is_authorized, _challenge, _details = result.unpack()
        return bool(is_authorized)
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
