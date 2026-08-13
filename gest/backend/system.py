"""GeST root D-Bus interface for the system-settings module.

Registered on the shared bus name at /org/gentoo/gest/System. Sets the
hostname, timezone and locale by writing the OpenRC/Gentoo config files
atomically. polkit-gated with org.gentoo.gest.system.configure. All value
validation reuses the pure validators in gest.core.system.
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
from gest.core.system import console as console_core
from gest.core.system import hostname as hostname_core
from gest.core.system import locale as locale_core
from gest.core.system import timezone as timezone_core
from gest.ipc.interface import SYSTEM_IFACE, SYSTEM_PATH, SYSTEM_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{SYSTEM_IFACE}">
    <method name="SetHostname">
      <arg type="s" name="name" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetTimezone">
      <arg type="s" name="zone" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetLocale">
      <arg type="s" name="lang" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetKeymap">
      <arg type="s" name="keymap" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="SetConsoleFont">
      <arg type="s" name="font" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_HOSTNAME_CMD = shutil.which("hostname") or "/bin/hostname"
_ZONEINFO = "/usr/share/zoneinfo"


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


class SystemService:
    """Implements the ``org.gentoo.gest.System`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            SYSTEM_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        methods = {"SetHostname", "SetTimezone", "SetLocale", "SetKeymap", "SetConsoleFont"}
        if method not in methods:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, SYSTEM_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to change system settings")
            return
        try:
            (value,) = params.unpack()
            ok, out = getattr(self, f"_{method.lower()}")(value)
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        except OSError as exc:
            invocation.return_value(GLib.Variant("(bs)", (False, f"write failed: {exc}")))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=value)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _sethostname(self, name: str) -> tuple[bool, str]:
        if not hostname_core.valid_hostname(name):
            raise ValueError("invalid hostname")
        _atomic_write("/etc/conf.d/hostname", f'hostname="{name}"\n')
        proc = subprocess.run([_HOSTNAME_CMD, name], capture_output=True, text=True)
        return proc.returncode == 0, (proc.stderr.strip() or f"hostname set to {name}")

    def _settimezone(self, zone: str) -> tuple[bool, str]:
        if not timezone_core.valid_zone_name(zone):
            raise ValueError("invalid timezone")
        target = os.path.join(_ZONEINFO, zone)
        if not os.path.isfile(target):
            raise ValueError("unknown timezone")
        _atomic_write("/etc/timezone", f"{zone}\n")
        # atomically repoint /etc/localtime at the zone file
        tmp = "/etc/.gest.localtime"
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        os.symlink(target, tmp)
        os.replace(tmp, "/etc/localtime")
        return True, f"timezone set to {zone}"

    def _setlocale(self, lang: str) -> tuple[bool, str]:
        if not locale_core.valid_locale(lang):
            raise ValueError("invalid locale")
        _atomic_write("/etc/env.d/02locale", f'LANG="{lang}"\n')
        _atomic_write("/etc/locale.conf", f"LANG={lang}\n")
        return True, f"locale set to {lang} (run env-update or re-login to apply)"

    def _upsert_conf(self, path: str, key: str, value: str) -> None:
        """Read ``path`` (if present), upsert ``key="value"``, write it back."""
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = ""
        _atomic_write(path, console_core.set_conf_value(text, key, value))

    def _setkeymap(self, keymap: str) -> tuple[bool, str]:
        if not console_core.valid_keymap(keymap):
            raise ValueError("invalid keymap")
        self._upsert_conf(console_core.KEYMAPS_CONF, "keymap", keymap)
        return True, f"keymap set to {keymap} (applies on next boot / keymaps restart)"

    def _setconsolefont(self, font: str) -> tuple[bool, str]:
        if not console_core.valid_font(font):
            raise ValueError("invalid console font")
        self._upsert_conf(console_core.CONSOLEFONT_CONF, "consolefont", font)
        return True, f"console font set to {font} (applied on next boot or consolefont restart)"
