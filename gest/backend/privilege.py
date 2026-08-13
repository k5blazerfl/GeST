"""GeST root D-Bus interface for the privilege-escalation module (sudo / doas).

Registered on the shared bus name at /org/gentoo/gest/Privilege. Two methods:

* ``SetSudo`` writes (or removes) an isolated ``/etc/sudoers.d/10-gest-wheel``
  drop-in, validated with ``visudo -c`` before it is installed and given the
  0440 mode sudo requires.
* ``SetDoas`` upserts (or strips) a GeST-delimited block inside
  ``/etc/doas.conf``, preserving every other rule, validated with ``doas -C``.

Each candidate is written beside the live file, checked with the tool's own
validator, and only swapped in if it passes — so a bad policy can never leave the
host's admins unable to escalate. polkit-gated with
org.gentoo.gest.privilege.manage; audit-logged.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.privilege import commands, render
from gest.core.privilege.model import DOAS_CONF, SUDOERS_DROPIN, EscalationPolicy
from gest.ipc.interface import PRIVILEGE_IFACE, PRIVILEGE_PATH, PRIVILEGE_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{PRIVILEGE_IFACE}">
    <method name="SetSudo">
      <arg type="s" name="group" direction="in"/>
      <arg type="b" name="enabled" direction="in"/>
      <arg type="b" name="passwordless" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetDoas">
      <arg type="s" name="group" direction="in"/>
      <arg type="b" name="enabled" direction="in"/>
      <arg type="b" name="passwordless" direction="in"/>
      <arg type="b" name="persist" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_VISUDO = shutil.which("visudo") or "/usr/sbin/visudo"
_DOAS = shutil.which("doas") or "/usr/bin/doas"


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class PrivilegeService:
    """Implements the ``org.gentoo.gest.Privilege`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            PRIVILEGE_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method not in ("SetSudo", "SetDoas"):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, PRIVILEGE_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to change privilege escalation")
            return
        try:
            if method == "SetSudo":
                group, enabled, passwordless = params.unpack()
                ok, out = self._set_sudo(group, enabled, passwordless)
                detail = f"sudo {group} enabled={enabled}"
            else:  # SetDoas
                group, enabled, passwordless, persist = params.unpack()
                ok, out = self._set_doas(group, enabled, passwordless, persist)
                detail = f"doas {group} enabled={enabled}"
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        except OSError as exc:
            invocation.return_value(GLib.Variant("(bs)", (False, f"write failed: {exc}")))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=detail)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _write_checked(self, target, text, mode, check_argv):
        """Write ``text`` beside ``target``, run ``check_argv`` on the temp file,
        and only ``os.replace`` it into place if the check passes."""
        directory = os.path.dirname(target)
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gest.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(tmp, mode)
            ok, out = _run(check_argv(tmp))
            if not ok:
                return False, out
            os.replace(tmp, target)
            return True, ""
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def _set_sudo(self, group, enabled, passwordless):
        if not render.valid_group(group):
            raise ValueError("invalid group name")
        if not enabled:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(SUDOERS_DROPIN)
            return True, "sudo wheel escalation removed"
        policy = EscalationPolicy("sudo", group=group, passwordless=bool(passwordless))
        ok, out = self._write_checked(
            SUDOERS_DROPIN, render.render_sudoers(policy), 0o440,
            lambda p: commands.visudo_check_argv(p, visudo=_VISUDO))
        if not ok:
            return False, f"sudoers rejected by visudo, not installed:\n{out}"
        return True, f"sudo: %{group} may escalate" + (
            " without a password" if passwordless else "")

    def _set_doas(self, group, enabled, passwordless, persist):
        if not render.valid_group(group):
            raise ValueError("invalid group name")
        try:
            with open(DOAS_CONF, encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            current = ""
        if enabled:
            policy = EscalationPolicy(
                "doas", group=group, passwordless=bool(passwordless), persist=bool(persist))
            candidate = render.apply_doas_block(current, policy)
        else:
            candidate = render.strip_doas_block(current)
        ok, out = self._write_checked(
            DOAS_CONF, candidate, 0o644,
            lambda p: commands.doas_check_argv(p, doas=_DOAS))
        if not ok:
            return False, f"doas.conf rejected by doas -C, not applied:\n{out}"
        if not enabled:
            return True, "doas wheel escalation removed"
        return True, f"doas: :{group} may escalate" + (
            " without a password" if passwordless else "")
