"""GeST root D-Bus interface for the services (systemd) module.

Registered on the same connection/bus name as the software service, at
``/org/gentoo/gest/Services``. Operations are quick (``systemctl``), so methods
run synchronously and return (ok, output). polkit-gated with the
``org.gentoo.gest.services.manage`` action.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.ipc.interface import SERVICES_IFACE, SERVICES_PATH, SERVICES_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{SERVICES_IFACE}">
    <method name="Control">
      <arg type="s" name="name" direction="in"/>
      <arg type="s" name="action" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetEnabled">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="enabled" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetMasked">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="masked" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_SYSTEMCTL = shutil.which("systemctl") or "/usr/bin/systemctl"
# Unit names allow alnum plus @ : . _ - (template instances, escaped names). We
# invoke via argv (no shell), so this is a sanity guard, not an injection fence.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@:._-]*$")
_ACTIONS = ("start", "stop", "restart", "reload", "try-restart")


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class ServicesService:
    """Implements the ``org.gentoo.gest.Services`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            SERVICES_PATH, node.interfaces[0], self._on_call, None, None
        )

    # argv builders (pure — unit-tested without a bus)
    @staticmethod
    def _control_argv(name: str, action: str) -> list[str]:
        return [_SYSTEMCTL, action, name]

    @staticmethod
    def _enabled_argv(name: str, enabled: bool) -> list[str]:
        return [_SYSTEMCTL, "enable" if enabled else "disable", name]

    @staticmethod
    def _masked_argv(name: str, masked: bool) -> list[str]:
        return [_SYSTEMCTL, "mask" if masked else "unmask", name]

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method == "Control":
            name, action = params.unpack()
            self._control(name, action, sender, invocation)
        elif method == "SetEnabled":
            name, enabled = params.unpack()
            self._set_enabled(name, enabled, sender, invocation)
        elif method == "SetMasked":
            name, masked = params.unpack()
            self._set_masked(name, masked, sender, invocation)
        else:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")

    def _deny(self, invocation, msg):
        invocation.return_error_literal(
            Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED, msg)

    def _bad(self, invocation, msg):
        invocation.return_error_literal(
            Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, msg)

    def _authorized(self, sender: str) -> bool:
        return check_authorization(self._conn, sender, SERVICES_POLKIT)

    def _control(self, name, action, sender, invocation):
        uid = caller_uid(self._conn, sender)
        if not self._authorized(sender):
            audit(f"service.{action}", uid=uid, result="denied", detail=name)
            return self._deny(invocation, "Not authorized to manage services")
        if not _NAME_RE.match(name) or action not in _ACTIONS:
            return self._bad(invocation, "invalid service name or action")
        ok, out = _run(self._control_argv(name, action))
        audit(f"service.{action}", uid=uid, result="ok" if ok else "failed", detail=name)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _set_enabled(self, name, enabled, sender, invocation):
        uid = caller_uid(self._conn, sender)
        action = "service.enable" if enabled else "service.disable"
        if not self._authorized(sender):
            audit(action, uid=uid, result="denied", detail=name)
            return self._deny(invocation, "Not authorized to manage services")
        if not _NAME_RE.match(name):
            return self._bad(invocation, "invalid service name")
        ok, out = _run(self._enabled_argv(name, enabled))
        audit(action, uid=uid, result="ok" if ok else "failed", detail=name)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _set_masked(self, name, masked, sender, invocation):
        uid = caller_uid(self._conn, sender)
        action = "service.mask" if masked else "service.unmask"
        if not self._authorized(sender):
            audit(action, uid=uid, result="denied", detail=name)
            return self._deny(invocation, "Not authorized to manage services")
        if not _NAME_RE.match(name):
            return self._bad(invocation, "invalid service name")
        ok, out = _run(self._masked_argv(name, masked))
        audit(action, uid=uid, result="ok" if ok else "failed", detail=name)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))
