"""GeST root D-Bus service for the software (Portage) module.

Runs as root on the *system* bus. Uses GLib/Gio because the method-invocation
object exposes the caller's bus name (``invocation.get_sender()``), which we
need to ask polkit whether that caller is authorized.

Contract (interface ``org.gentoo.gest.Software``):

    InstallPreview(atom: s) -> report: s   # `emerge --pretend`, no auth needed
    Install(atom: s)        -> started: b  # polkit-gated; streams via signals
    Progress(line: s)                      # signal: one line of emerge output
    Finished(exit_code: i)                 # signal: the merge has ended

This module is installed and started as root; it is not importable usefully
from the unprivileged frontend. See ``backend/README.md``.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from gest.ipc.interface import BUS_NAME, SOFTWARE_IFACE, SOFTWARE_PATH, polkit_action

# D-Bus introspection describing the surface above.
_INTROSPECTION = f"""
<node>
  <interface name="{SOFTWARE_IFACE}">
    <method name="InstallPreview">
      <arg type="s" name="atom" direction="in"/>
      <arg type="s" name="report" direction="out"/>
    </method>
    <method name="Install">
      <arg type="s" name="atom" direction="in"/>
      <arg type="b" name="started" direction="out"/>
    </method>
    <method name="Rebuild">
      <arg type="s" name="atom" direction="in"/>
      <arg type="b" name="started" direction="out"/>
    </method>
    <method name="SetPackageUse">
      <arg type="s" name="atom" direction="in"/>
      <arg type="s" name="line" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="SetPackageConfig">
      <arg type="s" name="kind" direction="in"/>
      <arg type="s" name="atom" direction="in"/>
      <arg type="s" name="line" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <signal name="Progress"><arg type="s" name="line"/></signal>
    <signal name="Finished"><arg type="i" name="exit_code"/></signal>
  </interface>
</node>
"""

# emerge invocation flags shared by preview and real merges. --color n keeps the
# output clean for a TUI; --pretend is added only for the preview.
_EMERGE = shutil.which("emerge") or "/usr/bin/emerge"


class SoftwareService:
    """Implements the ``org.gentoo.gest.Software`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        self._iface = node.interfaces[0]
        connection.register_object(
            SOFTWARE_PATH,
            self._iface,
            self._on_method_call,
            None,
            None,
        )

    # -- D-Bus dispatch -----------------------------------------------------

    def _on_method_call(
        self, conn, sender, path, iface, method, params, invocation
    ):
        if method == "InstallPreview":
            (atom,) = params.unpack()
            self._install_preview(atom, invocation)
        elif method == "Install":
            (atom,) = params.unpack()
            self._install(atom, sender, invocation)
        elif method == "Rebuild":
            (atom,) = params.unpack()
            self._rebuild(atom, sender, invocation)
        elif method == "SetPackageUse":
            atom, line = params.unpack()
            self._set_package_use(atom, line, sender, invocation)
        elif method == "SetPackageConfig":
            kind, atom, line = params.unpack()
            self._set_package_config(kind, atom, line, sender, invocation)
        else:
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}",
            )

    # -- methods ------------------------------------------------------------

    def _install_preview(self, atom: str, invocation) -> None:
        """`emerge --pretend` — read-only, so no polkit check required."""
        try:
            proc = Gio.Subprocess.new(
                [_EMERGE, "--pretend", "--verbose", "--color", "n", atom],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE,
            )
            ok, out, _ = proc.communicate_utf8(None, None)
            invocation.return_value(GLib.Variant("(s)", (out or "",)))
        except GLib.Error as exc:  # pragma: no cover - depends on live system
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.FAILED,
                f"preview failed: {exc.message}",
            )

    def _install(self, atom: str, sender: str, invocation) -> None:
        if not self._check_authorized(sender, polkit_action("install")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.ACCESS_DENIED,
                "Not authorized to install packages",
            )
            return
        # Authorized: start the merge and stream output asynchronously.
        invocation.return_value(GLib.Variant("(b)", (True,)))
        self._spawn_streaming([_EMERGE, "--color", "n", atom])

    def _rebuild(self, atom: str, sender: str, invocation) -> None:
        """Rebuild a package to apply changed USE flags (--changed-use)."""
        if not self._check_authorized(sender, polkit_action("install")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to rebuild packages")
            return
        invocation.return_value(GLib.Variant("(b)", (True,)))
        self._spawn_streaming([_EMERGE, "--changed-use", "--color", "n", atom])

    # -- package.use write ---------------------------------------------------

    _ATOM_RE = re.compile(r"^[a-z0-9][a-z0-9+._-]*/[a-zA-Z0-9+._-]+$")

    _ALLOWED_KINDS = ("use", "accept_keywords", "mask", "unmask")

    def _set_package_use(self, atom, line, sender, invocation):
        self._set_package_config("use", atom, line, sender, invocation)

    def _set_package_config(self, kind, atom, line, sender, invocation):
        if not self._check_authorized(sender, polkit_action("modify-config")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to modify Portage configuration")
            return
        if kind not in self._ALLOWED_KINDS:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                f"unknown config kind: {kind}")
            return
        if "\n" in atom or "\n" in line or not self._ATOM_RE.match(atom):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "invalid package atom")
            return
        if line and line.split()[0] != atom:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "line does not match atom")
            return
        try:
            self._write_package_config(kind, atom, line)
        except OSError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.FAILED,
                f"write failed: {exc}")
            return
        invocation.return_value(GLib.Variant("(b)", (True,)))

    @staticmethod
    def _write_package_use(atom, line, directory="/etc/portage/package.use"):
        SoftwareService._write_package_config("use", atom, line, directory)

    @staticmethod
    def _write_package_config(kind, atom, line, directory=None):
        if directory is None:
            directory = f"/etc/portage/package.{kind}"
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "gest")
        try:
            with open(path, encoding="utf-8") as fh:
                existing = fh.read().splitlines()
        except OSError:
            existing = []
        kept = [
            ln for ln in existing
            if not (ln.strip() and not ln.strip().startswith("#")
                    and ln.split()[0] == atom)
        ]
        if line:
            kept.append(line)
        text = "\n".join(kept).strip()
        text = text + "\n" if text else ""
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gest.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- polkit -------------------------------------------------------------

    def _check_authorized(self, sender: str, action_id: str) -> bool:
        """Ask polkit whether ``sender`` may perform ``action_id``."""
        try:
            authority = Gio.DBusProxy.new_sync(
                self._conn,
                Gio.DBusProxyFlags.NONE,
                None,
                "org.freedesktop.PolicyKit1",
                "/org/freedesktop/PolicyKit1/Authority",
                "org.freedesktop.PolicyKit1.Authority",
                None,
            )
            subject = GLib.Variant(
                "(sa{sv})",
                ("system-bus-name", {"name": GLib.Variant("s", sender)}),
            )
            result = authority.call_sync(
                "CheckAuthorization",
                GLib.Variant("((sa{sv})sa{ss}us)", (subject, action_id, {}, 1, "")),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            is_authorized, _challenge, _details = result.unpack()
            return bool(is_authorized)
        except GLib.Error:  # pragma: no cover - depends on live polkit
            return False

    # -- streaming ----------------------------------------------------------

    def _emit(self, signal: str, variant: GLib.Variant) -> None:
        self._conn.emit_signal(None, SOFTWARE_PATH, SOFTWARE_IFACE, signal, variant)

    def _spawn_streaming(self, argv: list[str]) -> None:
        proc = Gio.Subprocess.new(
            argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
        )
        stream = Gio.DataInputStream.new(proc.get_stdout_pipe())

        def read_next(*_):
            stream.read_line_async(GLib.PRIORITY_DEFAULT, None, on_line)

        def on_line(src, res):
            try:
                line, _len = src.read_line_finish_utf8(res)
            except GLib.Error:
                line = None
            if line is None:
                proc.wait_async(None, on_done)
                return
            self._emit("Progress", GLib.Variant("(s)", (line,)))
            read_next()

        def on_done(p, res):
            p.wait_finish(res)
            code = p.get_exit_status() if p.get_if_exited() else -1
            self._emit("Finished", GLib.Variant("(i)", (code,)))

        read_next()


def main() -> int:
    loop = GLib.MainLoop()

    def on_bus_acquired(conn, name):
        SoftwareService(conn)

    def on_name_lost(conn, name):
        sys.stderr.write(f"gest-backend: lost/could not acquire name {name}\n")
        loop.quit()

    Gio.bus_own_name(
        Gio.BusType.SYSTEM,
        BUS_NAME,
        Gio.BusNameOwnerFlags.NONE,
        on_bus_acquired,
        None,
        on_name_lost,
    )
    loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
