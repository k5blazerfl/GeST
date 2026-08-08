"""GeST root D-Bus interface for the users & groups module.

Registered on the shared bus name at /org/gentoo/gest/Users. Operations are
quick (useradd/usermod/userdel/groupadd/groupdel), so methods run synchronously
and return (ok, output). polkit-gated with org.gentoo.gest.users.manage. The
validated argv shapes live in gest.core.users.commands so a bus caller can't
inject arguments.
"""

from __future__ import annotations

import shutil
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.polkit import check_authorization
from gest.core.users import commands
from gest.ipc.interface import USERS_IFACE, USERS_PATH, USERS_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{USERS_IFACE}">
    <method name="AddUser">
      <arg type="s" name="name" direction="in"/>
      <arg type="s" name="comment" direction="in"/>
      <arg type="s" name="shell" direction="in"/>
      <arg type="s" name="home" direction="in"/>
      <arg type="s" name="groups" direction="in"/>
      <arg type="b" name="system" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="ModifyUser">
      <arg type="s" name="name" direction="in"/>
      <arg type="s" name="comment" direction="in"/>
      <arg type="s" name="shell" direction="in"/>
      <arg type="s" name="groups" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="DeleteUser">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="remove_home" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="AddGroup">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="system" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="DeleteGroup">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_USERADD = shutil.which("useradd") or "/usr/sbin/useradd"
_USERMOD = shutil.which("usermod") or "/usr/sbin/usermod"
_USERDEL = shutil.which("userdel") or "/usr/sbin/userdel"
_GROUPADD = shutil.which("groupadd") or "/usr/sbin/groupadd"
_GROUPDEL = shutil.which("groupdel") or "/usr/sbin/groupdel"


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class UsersService:
    """Implements the ``org.gentoo.gest.Users`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            USERS_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        handlers = {
            "AddUser": self._add_user,
            "ModifyUser": self._modify_user,
            "DeleteUser": self._delete_user,
            "AddGroup": self._add_group,
            "DeleteGroup": self._delete_group,
        }
        handler = handlers.get(method)
        if handler is None:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        if not check_authorization(self._conn, sender, USERS_POLKIT):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to manage users and groups")
            return
        try:
            argv = handler(params.unpack())
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        ok, out = _run(argv)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    # each returns the validated argv (raising ValueError on bad input)
    @staticmethod
    def _add_user(args):
        name, comment, shell, home, groups, system = args
        return commands.useradd_argv(
            name, comment=comment, shell=shell, home=home, groups=groups,
            system=system, useradd=_USERADD)

    @staticmethod
    def _modify_user(args):
        name, comment, shell, groups = args
        return commands.usermod_argv(
            name, comment=comment, shell=shell, groups=groups, usermod=_USERMOD)

    @staticmethod
    def _delete_user(args):
        name, remove_home = args
        return commands.userdel_argv(name, remove_home=remove_home, userdel=_USERDEL)

    @staticmethod
    def _add_group(args):
        name, system = args
        return commands.groupadd_argv(name, system=system, groupadd=_GROUPADD)

    @staticmethod
    def _delete_group(args):
        (name,) = args
        return commands.groupdel_argv(name, groupdel=_GROUPDEL)
