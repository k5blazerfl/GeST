"""GeST root D-Bus interface for the services module (systemd or OpenRC).

Registered on the same connection/bus name as the software service, at
``/org/gentoo/gest/Services``. Operations are quick (``systemctl`` /
``rc-service`` / ``rc-update``), so methods run synchronously and return
(ok, output). polkit-gated with the ``org.gentoo.gest.services.manage`` action.

The D-Bus contract is init-agnostic and unchanged: ``Control`` /
``SetEnabled`` / ``SetMasked``. Which command line each maps to is decided at
call time from :func:`gest.core.init.detect`, so a single backend drives both a
systemd HeDE box and a plain-Gentoo OpenRC host. Masking has no OpenRC analog
and is reported as unsupported there rather than silently doing nothing.
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
from gest.core import init
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
_RC_SERVICE = shutil.which("rc-service") or "/usr/bin/rc-service"
_RC_UPDATE = shutil.which("rc-update") or "/usr/bin/rc-update"
# Unit names allow alnum plus @ : . _ - (template instances, escaped names). We
# invoke via argv (no shell), so this is a sanity guard, not an injection fence.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@:._-]*$")
_ACTIONS = ("start", "stop", "restart", "reload", "try-restart")
# OpenRC lacks try-restart; rc-service honors start/stop/restart/reload.
_ACTIONS_RC = ("start", "stop", "restart", "reload")
# The runlevel OpenRC "enable at boot" adds to; disable removes from all levels.
_RC_DEFAULT_RUNLEVEL = "default"


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

    # systemd argv builders (pure — unit-tested without a bus)
    @staticmethod
    def _control_argv(name: str, action: str) -> list[str]:
        return [_SYSTEMCTL, action, name]

    @staticmethod
    def _enabled_argv(name: str, enabled: bool) -> list[str]:
        return [_SYSTEMCTL, "enable" if enabled else "disable", name]

    @staticmethod
    def _masked_argv(name: str, masked: bool) -> list[str]:
        return [_SYSTEMCTL, "mask" if masked else "unmask", name]

    # OpenRC argv builders (pure — unit-tested without a bus)
    @staticmethod
    def _control_argv_rc(name: str, action: str) -> list[str]:
        return [_RC_SERVICE, name, action]

    @staticmethod
    def _enabled_argv_rc(name: str, enabled: bool) -> list[str]:
        # Enable adds to the default runlevel; disable removes from every level.
        if enabled:
            return [_RC_UPDATE, "add", name, _RC_DEFAULT_RUNLEVEL]
        return [_RC_UPDATE, "del", name]

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
        openrc = init.is_openrc()
        allowed = _ACTIONS_RC if openrc else _ACTIONS
        if not _NAME_RE.match(name) or action not in allowed:
            return self._bad(invocation, "invalid service name or action")
        argv = (self._control_argv_rc(name, action) if openrc
                else self._control_argv(name, action))
        ok, out = _run(argv)
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
        argv = (self._enabled_argv_rc(name, enabled) if init.is_openrc()
                else self._enabled_argv(name, enabled))
        ok, out = _run(argv)
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
        if init.is_openrc():
            # OpenRC has no mask concept; report rather than pretend it worked.
            audit(action, uid=uid, result="unsupported", detail=name)
            return invocation.return_value(GLib.Variant(
                "(bs)", (False, "Masking is not supported on OpenRC systems.")))
        ok, out = _run(self._masked_argv(name, masked))
        audit(action, uid=uid, result="ok" if ok else "failed", detail=name)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))
