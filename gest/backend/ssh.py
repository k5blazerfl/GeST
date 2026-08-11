"""GeST root D-Bus interface for the SSH deploy key.

Registered at /org/gentoo/gest/Ssh. Reads root's SSH public key, and — gated by
org.gentoo.gest.portage.configure and audit-logged — generates a passphraseless
ed25519 key (if none exists) and seeds github.com into root's known_hosts, so a
private GitHub ebuild overlay can be synced over SSH. Only ever exposes the
*public* key; the private key never leaves /root/.ssh.
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.repos import sshkey
from gest.ipc.interface import PORTAGE_POLKIT, SSH_IFACE, SSH_PATH

_INTROSPECTION = f"""
<node>
  <interface name="{SSH_IFACE}">
    <method name="DeployKey">
      <arg type="b" name="has_key" direction="out"/>
      <arg type="s" name="public_key" direction="out"/>
      <arg type="s" name="path" direction="out"/>
    </method>
    <method name="EnsureDeployKey">
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="public_key" direction="out"/>
      <arg type="s" name="path" direction="out"/>
      <arg type="s" name="message" direction="out"/>
    </method>
  </interface>
</node>
"""


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _capture(argv: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _ensure_known_host(host: str) -> None:
    """Append ``host``'s keys to root's known_hosts if not already present."""
    existing = _read(sshkey.KNOWN_HOSTS)
    if host in existing:
        return
    rc, out, _err = _capture(sshkey.keyscan_argv(host))
    if rc == 0 and out.strip():
        with contextlib.suppress(OSError), open(
                sshkey.KNOWN_HOSTS, "a", encoding="utf-8") as fh:
            fh.write(out if out.endswith("\n") else out + "\n")


class SshService:
    """Implements the ``org.gentoo.gest.Ssh`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(SSH_PATH, node.interfaces[0], self._on_call,
                                   None, None)

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method == "DeployKey":                       # read-only: no auth needed
            pub = _read(sshkey.PUB_PATH)
            invocation.return_value(
                GLib.Variant("(bss)", (bool(pub), pub, sshkey.PUB_PATH)))
            return
        if method != "EnsureDeployKey":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, PORTAGE_POLKIT):
            audit("EnsureDeployKey", uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to create the SSH deploy key")
            return
        ok, pub, message = self._ensure()
        audit("EnsureDeployKey", uid=uid, result="ok" if ok else "failed")
        invocation.return_value(
            GLib.Variant("(bsss)", (ok, pub, sshkey.PUB_PATH, message)))

    @staticmethod
    def _ensure() -> tuple[bool, str, str]:
        with contextlib.suppress(OSError):
            os.makedirs(sshkey.SSH_DIR, mode=0o700, exist_ok=True)
        generated = False
        if not os.path.exists(sshkey.KEY_PATH):
            comment = sshkey.default_comment(socket.gethostname())
            rc, _out, err = _capture(sshkey.keygen_argv(sshkey.KEY_PATH, comment))
            if rc != 0:
                return False, "", (err.strip() or "ssh-keygen failed")
            generated = True
        _ensure_known_host(sshkey.GITHUB_HOST)
        pub = _read(sshkey.PUB_PATH)
        if not pub:
            return False, "", "the key was created but its public half is unreadable"
        return True, pub, ("Generated a new deploy key." if generated
                           else "Using the existing key.")
