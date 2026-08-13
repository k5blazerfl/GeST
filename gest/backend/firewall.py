"""GeST root D-Bus interface for the firewall module (nftables).

Registered on the shared bus name at /org/gentoo/gest/Firewall. A single method,
``ApplyPolicy``, takes the *primitives* of a simple firewall (default input
policy, ping allowance, inbound TCP/UDP ports), re-renders the ruleset
server-side (never trusting caller-supplied nftables text), writes it to
``/etc/nftables.nft`` atomically, validates it with ``nft -c -f`` and loads it
with ``nft -f`` — which nft applies as one atomic transaction, so a bad ruleset
can never leave the host half-filtered. polkit-gated with
org.gentoo.gest.firewall.manage; every action is audit-logged.
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
from gest.core.firewall import commands, nft
from gest.core.firewall.model import FirewallPolicy
from gest.ipc.interface import FIREWALL_IFACE, FIREWALL_PATH, FIREWALL_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{FIREWALL_IFACE}">
    <method name="ApplyPolicy">
      <arg type="s" name="default_input" direction="in"/>
      <arg type="b" name="allow_ping" direction="in"/>
      <arg type="ai" name="tcp_ports" direction="in"/>
      <arg type="ai" name="udp_ports" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="EnableAtBoot">
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
  </interface>
</node>
"""

_NFT = shutil.which("nft") or "/usr/sbin/nft"
_RC_SERVICE = shutil.which("rc-service") or "/sbin/rc-service"
_RC_UPDATE = shutil.which("rc-update") or "/sbin/rc-update"


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


class FirewallService:
    """Implements the ``org.gentoo.gest.Firewall`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            FIREWALL_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method not in ("ApplyPolicy", "EnableAtBoot"):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, FIREWALL_POLKIT):
            audit(method, uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to change the firewall")
            return
        try:
            if method == "ApplyPolicy":
                default_input, allow_ping, tcp_ports, udp_ports = params.unpack()
                ok, out = self._apply_policy(default_input, allow_ping, tcp_ports, udp_ports)
                detail = f"input={default_input} tcp={list(tcp_ports)} udp={list(udp_ports)}"
            else:  # EnableAtBoot
                ok, out = self._enable_at_boot()
                detail = "enable nftables at boot"
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        except OSError as exc:
            invocation.return_value(GLib.Variant("(bs)", (False, f"write failed: {exc}")))
            return
        audit(method, uid=uid, result="ok" if ok else "failed", detail=detail)
        invocation.return_value(GLib.Variant("(bs)", (ok, out)))

    def _apply_policy(self, default_input, allow_ping, tcp_ports, udp_ports):
        policy = FirewallPolicy(
            default_input=default_input,
            allow_ping=bool(allow_ping),
            tcp_ports=[int(p) for p in tcp_ports],
            udp_ports=[int(p) for p in udp_ports],
        )
        if not nft.valid_policy(policy):
            raise ValueError("invalid firewall policy (bad default or port out of range)")
        _atomic_write(nft.NFT_PATH, nft.render_ruleset(policy))
        ok, out = _run(commands.nft_check_argv(nft.NFT_PATH, nft=_NFT))
        if not ok:
            return False, f"ruleset failed validation, not loaded:\n{out}"
        ok, out = _run(commands.nft_load_argv(nft.NFT_PATH, nft=_NFT))
        return ok, out or f"firewall applied and saved to {nft.NFT_PATH}"

    def _enable_at_boot(self):
        """Persist the live ruleset and enable the nftables service at boot.

        Order matters on OpenRC: ``save`` first (dump the *current* ruleset to the
        service's save file), then enable — never ``start``, which would restore a
        stale save file over the rules we just applied.
        """
        ok, out = _run([_RC_SERVICE, "nftables", "save"])
        if not ok:
            return False, f"could not save the current ruleset:\n{out}"
        ok, out = _run([_RC_UPDATE, "add", "nftables", "default"])
        return ok, out or "nftables enabled at boot (current ruleset saved)"
