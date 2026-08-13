"""GeST root D-Bus interface for the sshd server-config module.

Registered on the shared bus name at /org/gentoo/gest/Sshd. A single method,
``ApplyConfig``, takes the managed directives as primitives, upserts them into a
*candidate* copy of /etc/ssh/sshd_config, validates it with ``sshd -t -f`` and
only then replaces the live file — so a bad value can never leave sshd unable to
start. After a successful write it reloads the service (best-effort; a failed
reload, e.g. sshd not running, is reported but doesn't undo the saved config).
polkit-gated with org.gentoo.gest.sshd.manage; audit-logged.
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
from gest.core.sshd import commands, config
from gest.core.sshd.model import SshdSettings
from gest.core.sshd.reader import SSHD_CONFIG
from gest.ipc.interface import SSHD_IFACE, SSHD_PATH, SSHD_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{SSHD_IFACE}">
    <method name="ApplyConfig">
      <arg type="i" name="port" direction="in"/>
      <arg type="s" name="permit_root_login" direction="in"/>
      <arg type="b" name="password_authentication" direction="in"/>
      <arg type="b" name="pubkey_authentication" direction="in"/>
      <arg type="b" name="x11_forwarding" direction="in"/>
      <arg type="b" name="permit_empty_passwords" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_SSHD = shutil.which("sshd") or "/usr/sbin/sshd"
_RC_SERVICE = shutil.which("rc-service") or "/sbin/rc-service"


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


class SshdService:
    """Implements the ``org.gentoo.gest.Sshd`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            SSHD_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "ApplyConfig":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, SSHD_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to change the SSH server configuration")
            return
        try:
            values = params.unpack()
            ok, out = self._apply_config(*values)
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        except OSError as exc:
            invocation.return_value(GLib.Variant("(bs)", (False, f"write failed: {exc}")))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=f"port={values[0]}")
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _apply_config(self, port, permit_root_login, password_auth,
                      pubkey_auth, x11_forwarding, permit_empty_passwords):
        settings = SshdSettings(
            port=int(port),
            permit_root_login=permit_root_login,
            password_authentication=bool(password_auth),
            pubkey_authentication=bool(pubkey_auth),
            x11_forwarding=bool(x11_forwarding),
            permit_empty_passwords=bool(permit_empty_passwords),
        )
        if not config.valid_settings(settings):
            raise ValueError("invalid sshd settings (bad port or root-login value)")

        try:
            with open(SSHD_CONFIG, encoding="utf-8") as fh:
                current = fh.read()
        except OSError:
            current = ""
        candidate = config.apply_settings(current, settings)

        # Write the candidate beside the real file, validate it with `sshd -t`,
        # and only swap it in if it passes — so we never break a running sshd.
        directory = os.path.dirname(SSHD_CONFIG)
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gest.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(candidate)
            os.chmod(tmp, 0o644)
            ok, out = _run(commands.sshd_test_argv(tmp, sshd=_SSHD))
            if not ok:
                return False, f"config rejected by sshd -t, not applied:\n{out}"
            os.replace(tmp, SSHD_CONFIG)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

        reloaded, rout = _run([_RC_SERVICE, "sshd", "reload"])
        note = "reloaded sshd" if reloaded else f"saved, but reload failed: {rout}"
        return True, f"sshd_config updated (port {settings.port}); {note}"
