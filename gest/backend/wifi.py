"""GeST root D-Bus interface for the Wi-Fi module (wpa_supplicant).

Registered on the shared bus name at /org/gentoo/gest/Wifi. Three methods:

* ``AddNetwork`` validates the SSID, hashes the passphrase with ``wpa_passphrase``
  (fed on stdin, never in argv) and strips the plaintext ``#psk`` comment, then
  writes/replaces the network block in /etc/wpa_supplicant/wpa_supplicant.conf
  (0600) and asks a running supplicant to reconfigure. A blank passphrase makes
  an open network.
* ``RemoveNetwork`` strips the block for an SSID.
* ``Scan`` finds a wireless interface with ``iw dev`` and returns nearby SSIDs.

polkit-gated with org.gentoo.gest.wifi.manage; audit-logged.
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
from gest.core import rootpath
from gest.core.wifi import commands, config
from gest.ipc.interface import WIFI_IFACE, WIFI_PATH, WIFI_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{WIFI_IFACE}">
    <method name="AddNetwork">
      <arg type="s" name="ssid" direction="in"/>
      <arg type="s" name="passphrase" direction="in"/>
      <arg type="s" name="root" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="RemoveNetwork">
      <arg type="s" name="ssid" direction="in"/>
      <arg type="s" name="root" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="Scan">
      <arg type="b" name="ok" direction="out"/>
      <arg type="as" name="ssids" direction="out"/>
    </method>
  </interface>
</node>
"""

_WPA_PASSPHRASE = shutil.which("wpa_passphrase") or "/usr/bin/wpa_passphrase"
_WPA_CLI = shutil.which("wpa_cli") or "/usr/bin/wpa_cli"
_IW = shutil.which("iw") or "/usr/sbin/iw"


def _run(argv: list[str], *, stdin: str | None = None, timeout: int | None = None):
    proc = subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=timeout)
    out = proc.stdout + (f"\n{proc.stderr}" if proc.stderr else "")
    return proc.returncode == 0, out.strip(), proc.stdout


def _atomic_write(path: str, text: str, mode: int) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gest.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class WifiService:
    """Implements the ``org.gentoo.gest.Wifi`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            WIFI_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method not in ("AddNetwork", "RemoveNetwork", "Scan"):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, WIFI_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to configure Wi-Fi")
            return
        try:
            if method == "Scan":
                ok, ssids = self._scan()
                audit(method, uid=uid, result="ok" if ok else "failed",
                      detail=f"{len(ssids)} ssids")
                invocation.return_value(GLib.Variant("(bas)", (ok, ssids)))
                return
            if method == "AddNetwork":
                ssid, passphrase, root = params.unpack()
                rootpath.guard_config_root(root)
                ok, out = self._add_network(ssid, passphrase, root)
                detail = f"add {ssid} root={root}"
            else:  # RemoveNetwork
                ssid, root = params.unpack()
                rootpath.guard_config_root(root)
                ok, out = self._remove_network(ssid, root)
                detail = f"remove {ssid} root={root}"
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        except (OSError, subprocess.SubprocessError) as exc:
            invocation.return_value(GLib.Variant("(bs)", (False, f"failed: {exc}")))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=detail)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _read_conf(self, root) -> str:
        try:
            with open(rootpath.resolve(root, config.WPA_CONF), encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""

    def _write_and_reconfigure(self, text: str, root) -> str:
        path = rootpath.resolve(root, config.WPA_CONF)
        _atomic_write(path, text, 0o600)
        if rootpath.is_target(root):
            return path
        # Best-effort: a running supplicant re-reads its config; harmless if none.
        with contextlib.suppress(Exception):
            _run(commands.wpa_cli_reconfigure_argv(wpa_cli=_WPA_CLI), timeout=5)
        return path

    def _add_network(self, ssid, passphrase, root):
        if not config.valid_ssid(ssid):
            raise ValueError("invalid SSID (1-32 bytes, no quotes/backslashes)")
        if passphrase:
            if not config.valid_passphrase(passphrase):
                raise ValueError("passphrase must be 8-63 printable characters")
            ok, out, stdout = _run(
                commands.wpa_passphrase_argv(ssid, wpa_passphrase=_WPA_PASSPHRASE),
                stdin=passphrase)
            block = config.sanitize_block(stdout)
            if not ok or not block:
                return False, f"wpa_passphrase failed:\n{out}"
        else:
            block = config.render_open_network(ssid)
        text = config.append_network(config.remove_network(self._read_conf(root), ssid), block)
        path = self._write_and_reconfigure(text, root)
        kind = "open" if not passphrase else "secured"
        note = " (target root; not reconfigured live)" if rootpath.is_target(root) else ""
        return True, f"added {kind} network {ssid} to {path}{note}"

    def _remove_network(self, ssid, root):
        if not config.valid_ssid(ssid):
            raise ValueError("invalid SSID")
        path = self._write_and_reconfigure(config.remove_network(self._read_conf(root), ssid), root)
        note = " (target root; not reconfigured live)" if rootpath.is_target(root) else ""
        return True, f"removed {ssid} from {path}{note}"

    def _scan(self):
        from gest.core.wifi import reader
        _ok, _out, dev_stdout = _run(commands.iw_dev_argv(iw=_IW))
        interfaces = reader.parse_iw_dev(dev_stdout)
        if not interfaces:
            return False, []
        try:
            ok, _out, scan_stdout = _run(
                commands.iw_scan_argv(interfaces[0], iw=_IW), timeout=15)
        except subprocess.SubprocessError:
            return False, []
        return ok, reader.parse_scan_ssids(scan_stdout)
