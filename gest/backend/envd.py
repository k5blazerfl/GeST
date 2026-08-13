"""GeST root D-Bus interface for the env.d module.

Registered on the shared bus name at /org/gentoo/gest/Envd. ``ApplyVars``
validates the VAR=value pairs, writes them to the GeST drop-in
(/etc/env.d/99gest) atomically, and runs ``env-update`` to regenerate
/etc/profile.env. polkit-gated with org.gentoo.gest.envd.manage; audit-logged.
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
from gest.core.envd import commands, config
from gest.ipc.interface import ENVD_IFACE, ENVD_PATH, ENVD_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{ENVD_IFACE}">
    <method name="ApplyVars">
      <arg type="a(ss)" name="variables" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_ENV_UPDATE = shutil.which("env-update") or "/usr/sbin/env-update"


def _run(argv: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip()


def _atomic_write(path: str, text: str) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gest.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class EnvdService:
    """Implements the ``org.gentoo.gest.Envd`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            ENVD_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "ApplyVars":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, ENVD_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to change environment variables")
            return
        try:
            (pairs,) = params.unpack()
            ok, out = self._apply(pairs)
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        except OSError as exc:
            invocation.return_value(GLib.Variant("(bs)", (False, f"write failed: {exc}")))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=f"{len(pairs)} vars")
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _apply(self, pairs):
        variables = {str(k): str(v) for k, v in pairs}
        for name, value in variables.items():
            if not (config.valid_name(name) and config.valid_value(value)):
                raise ValueError(f"invalid environment variable: {name!r}")
        _atomic_write(config.ENVD_DROPIN, config.render_conf(variables))
        ok, out = _run(commands.env_update_argv(env_update=_ENV_UPDATE))
        if not variables:
            return ok, out or "cleared the GeST env.d drop-in; ran env-update"
        return ok, out or f"applied {len(variables)} variable(s); ran env-update"
