"""GeST root D-Bus service for the software (Portage) module.

Runs as root on the *system* bus. Uses GLib/Gio because the method-invocation
object exposes the caller's bus name (``invocation.get_sender()``), which we
need to ask polkit whether that caller is authorized.

Contract (interface ``org.gentoo.gest.Software``):

    InstallPreview(atom: s) -> report: s   # `emerge --pretend`, no auth needed
    Install(atom: s)        -> started: b  # polkit-gated; streams via signals
    Progress(lines: as)                    # signal: a batch of emerge output lines
    Finished(exit_code: i)                 # signal: the merge has ended

This module is installed and started as root; it is not importable usefully
from the unprivileged frontend. See ``backend/README.md``.
"""

from __future__ import annotations

import os
import re
import shutil
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

import gest
from gest.backend.audit import audit
from gest.backend.bootloader import BootloaderService
from gest.backend.datetime import DateTimeService
from gest.backend.disk import DiskService
from gest.backend.envd import EnvdService
from gest.backend.eselect import EselectService
from gest.backend.firewall import FirewallService
from gest.backend.kernel import KernelService
from gest.backend.network import NetworkService
from gest.backend.polkit import (
    authorization_is_granted,
    authorization_variant,
    caller_uid,
)
from gest.backend.portage import PortageService
from gest.backend.privilege import PrivilegeService
from gest.backend.repos import ReposService
from gest.backend.services import ServicesService
from gest.backend.ssh import SshService
from gest.backend.sshd import SshdService
from gest.backend.sysctl import SysctlService
from gest.backend.system import SystemService
from gest.backend.users import UsersService
from gest.backend.wifi import WifiService
from gest.core.repos import commands as repo_commands
from gest.core.software import news, world
from gest.core.software.running import external_emerge
from gest.ipc.interface import (
    BUS_NAME,
    BUSY_ERROR,
    SOFTWARE_IFACE,
    SOFTWARE_PATH,
    polkit_action,
)

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
    <method name="InstallMulti">
      <arg type="as" name="atoms" direction="in"/>
      <arg type="b" name="started" direction="out"/>
    </method>
    <method name="InstallBinaryMulti">
      <arg type="as" name="atoms" direction="in"/>
      <arg type="b" name="only" direction="in"/>
      <arg type="b" name="started" direction="out"/>
    </method>
    <method name="Rebuild">
      <arg type="s" name="atom" direction="in"/>
      <arg type="b" name="started" direction="out"/>
    </method>
    <method name="UpdateWorld">
      <arg type="b" name="started" direction="out"/>
    </method>
    <method name="Depclean">
      <arg type="s" name="atom" direction="in"/>
      <arg type="b" name="started" direction="out"/>
    </method>
    <method name="DepcleanMulti">
      <arg type="as" name="atoms" direction="in"/>
      <arg type="b" name="started" direction="out"/>
    </method>
    <method name="Sync">
      <arg type="b" name="started" direction="out"/>
    </method>
    <method name="SyncRepos">
      <arg type="as" name="names" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="MarkNewsRead">
      <arg type="s" name="selector" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="MarkNewsUnread">
      <arg type="s" name="selector" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
    <method name="Deselect">
      <arg type="as" name="atoms" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
      <arg type="s" name="output" direction="out"/>
    </method>
    <method name="PackageStatus">
      <arg type="b" name="busy" direction="out"/>
      <arg type="s" name="operation" direction="out"/>
    </method>
    <signal name="Progress"><arg type="as" name="lines"/></signal>
    <signal name="Finished"><arg type="i" name="exit_code"/></signal>
  </interface>
</node>
"""

# emerge invocation flags shared by preview and real merges. --color n keeps the
# output clean for a TUI; --pretend is added only for the preview.
_EMERGE = shutil.which("emerge") or "/usr/bin/emerge"
_ESELECT = shutil.which("eselect") or "/usr/bin/eselect"
_EMAINT = shutil.which("emaint") or "/usr/sbin/emaint"


# Exit after this many idle seconds so a re-activation picks up new code and
# the root service doesn't linger. Never exits while a merge is streaming. Also
# exit promptly (at the next check) once the installed code changes under us —
# an ``emerge gest`` upgrade — so the stale root service is replaced without a
# manual ``pkill``; the next D-Bus call re-activates the new code.
_IDLE_TIMEOUT = 120
_IDLE_CHECK = 10

# The version this process started with, and the package's __init__ on disk. When
# they diverge, GeST was updated while we were running.
_RUNNING_VERSION = gest.__version__
_GEST_INIT = gest.__file__


def _code_changed() -> bool:
    """True when GeST on disk has a different ``__version__`` than the running
    backend — i.e. it was upgraded since activation, so we should exit and let
    the next call start the new code."""
    try:
        with open(_GEST_INIT, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return bool(m) and m.group(1) != _RUNNING_VERSION

# Coalesce streamed output into one D-Bus signal per flush so a large (e.g.
# failing) build can't emit a signal per line and storm the frontend. Flush when
# the buffer fills or _BATCH_INTERVAL_MS elapses, whichever comes first — this
# bounds both the signal rate and the latency before a line reaches the TUI.
_BATCH_MAX_LINES = 200
_BATCH_INTERVAL_MS = 100
# Read the merge's output in chunks and split lines ourselves. A zero-length
# read is the one reliable EOF signal — GLib's read_line can return an empty
# string for both a blank line *and* EOF, which makes it unusable for detecting
# the end of the stream.
_READ_CHUNK = 65536


class SoftwareService:
    """Implements the ``org.gentoo.gest.Software`` interface."""

    def __init__(self, connection: Gio.DBusConnection, on_idle=None):
        self._conn = connection
        self._on_idle = on_idle
        self._active = 0  # package operations in progress (streaming + sync/deselect)
        self._operation = ""  # human label of the current op (for the cross-session lock)
        self._last_activity = GLib.get_monotonic_time()
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        self._iface = node.interfaces[0]
        connection.register_object(
            SOFTWARE_PATH,
            self._iface,
            self._on_method_call,
            None,
            None,
        )
        if on_idle is not None:
            GLib.timeout_add_seconds(_IDLE_CHECK, self._idle_check)

    # -- idle-exit ----------------------------------------------------------

    def _touch(self) -> None:
        self._last_activity = GLib.get_monotonic_time()

    # -- package-operation tracking (drives idle-exit + the cross-session lock) --

    def _begin_op(self, operation: str) -> None:
        """Mark a package operation as started: bump the active count and record a
        human label so other GeST sessions can see what is running."""
        self._active += 1
        self._operation = operation

    def _end_op(self) -> None:
        self._active = max(self._active - 1, 0)
        if self._active == 0:
            self._operation = ""
        self._touch()

    # -- the package-management lock (cross-session + external emerge) --------

    def _busy_message(self) -> str:
        """A ready-to-display sentence describing why package management is
        locked, or "" when it is free.

        Two sources, checked in order: an operation *this* shared backend is
        running (so any GeST session), then an ``emerge``/``emaint``/``ebuild``
        a user started by hand in a terminal. The external scan only runs when we
        are idle — when we are busy our own child would match it anyway.
        """
        if self._active > 0:
            op = self._operation or "A package operation"
            return f"{op} is running in another GeST session"
        external = external_emerge()
        if external:
            return f"An external {external} is running outside GeST"
        return ""

    def _reject_if_busy(self, invocation) -> bool:
        """If package management is locked, fail the call with BUSY_ERROR and
        return True; the handler must then return without starting anything.
        Checked before the polkit prompt so we never ask for authentication only
        to refuse. Race-free: the loop is single-threaded and polkit is a
        blocking call, so no other handler runs between this check and the
        _begin_op that follows in the same handler."""
        message = self._busy_message()
        if message:
            invocation.return_dbus_error(BUSY_ERROR, message)
            return True
        return False

    @staticmethod
    def _should_exit(active: int, idle_seconds: float, timeout: float,
                     code_changed: bool = False) -> bool:
        if active != 0:                       # never bail out mid-merge
            return False
        return code_changed or idle_seconds >= timeout

    def _idle_check(self) -> bool:
        idle = (GLib.get_monotonic_time() - self._last_activity) / 1_000_000
        if self._should_exit(self._active, idle, _IDLE_TIMEOUT, _code_changed()):
            if self._on_idle:
                self._on_idle()
            return False  # stop polling; the loop is quitting
        return True

    # -- D-Bus dispatch -----------------------------------------------------

    def _on_method_call(
        self, conn, sender, path, iface, method, params, invocation
    ):
        self._touch()
        if method == "InstallPreview":
            (atom,) = params.unpack()
            self._install_preview(atom, invocation)
        elif method == "Install":
            (atom,) = params.unpack()
            self._install(atom, sender, invocation)
        elif method == "InstallMulti":
            (atoms,) = params.unpack()
            self._install_multi(atoms, sender, invocation)
        elif method == "InstallBinaryMulti":
            atoms, only = params.unpack()
            self._install_binary_multi(atoms, only, sender, invocation)
        elif method == "Rebuild":
            (atom,) = params.unpack()
            self._rebuild(atom, sender, invocation)
        elif method == "UpdateWorld":
            self._update_world(sender, invocation)
        elif method == "Depclean":
            (atom,) = params.unpack()
            self._depclean(atom, sender, invocation)
        elif method == "DepcleanMulti":
            (atoms,) = params.unpack()
            self._depclean_multi(atoms, sender, invocation)
        elif method == "Sync":
            self._sync(sender, invocation)
        elif method == "SyncRepos":
            (names,) = params.unpack()
            self._sync_repos(names, sender, invocation)
        elif method == "MarkNewsRead":
            (selector,) = params.unpack()
            self._mark_news(selector, True, sender, invocation)
        elif method == "MarkNewsUnread":
            (selector,) = params.unpack()
            self._mark_news(selector, False, sender, invocation)
        elif method == "Deselect":
            (atoms,) = params.unpack()
            self._deselect(atoms, sender, invocation)
        elif method == "PackageStatus":
            self._package_status(invocation)
        else:
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}",
            )

    # -- methods ------------------------------------------------------------

    def _package_status(self, invocation) -> None:
        """Report whether package management is locked and a display sentence.

        Read-only (no polkit): the frontend polls this before opening a
        package-management module. Covers both a conflicting GeST session and an
        external terminal emerge (see :meth:`_busy_message`).
        """
        message = self._busy_message()
        invocation.return_value(GLib.Variant("(bs)", (bool(message), message)))

    def _install_preview(self, atom: str, invocation) -> None:
        """`emerge --pretend` — read-only, so no polkit check required."""
        try:
            proc = Gio.Subprocess.new(
                [_EMERGE, "--pretend", "--verbose", "--color", "n", atom],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE,
            )
            _ok, out, _ = proc.communicate_utf8(None, None)
            invocation.return_value(GLib.Variant("(s)", (out or "",)))
        except GLib.Error as exc:  # pragma: no cover - depends on live system
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.FAILED,
                f"preview failed: {exc.message}",
            )

    def _install(self, atom: str, sender: str, invocation) -> None:
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("install")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.ACCESS_DENIED,
                "Not authorized to install packages",
            )
            return
        # Authorized: start the merge and stream output asynchronously.
        invocation.return_value(GLib.Variant("(b)", (True,)))
        self._spawn_streaming([_EMERGE, "--color", "n", atom],
                              operation="A package install")

    def _install_multi(self, atoms, sender: str, invocation) -> None:
        """Merge several atoms in one emerge (the transactional Accept)."""
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("install")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to install packages")
            return
        atoms = list(atoms)
        if not atoms or any(not self._ATOM_RE.match(a) for a in atoms):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "invalid or empty package atom list")
            return
        invocation.return_value(GLib.Variant("(b)", (True,)))
        self._spawn_streaming([_EMERGE, "--color", "n", *atoms],
                              operation="A package install")

    def _install_binary_multi(self, atoms, only, sender: str, invocation) -> None:
        """Merge atoms as binary packages: emerge --getbinpkg [--usepkgonly].

        ``only`` forces binary (fails if no binpkg); otherwise emerge prefers a
        binary and falls back to building from source.
        """
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("install")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to install packages")
            return
        atoms = list(atoms)
        if not atoms or any(not self._ATOM_RE.match(a) for a in atoms):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "invalid or empty package atom list")
            return
        invocation.return_value(GLib.Variant("(b)", (True,)))
        argv = [_EMERGE, "--getbinpkg", "--color", "n"]
        if only:
            argv.insert(2, "--usepkgonly")
        self._spawn_streaming([*argv, *atoms], operation="A package install")

    def _rebuild(self, atom: str, sender: str, invocation) -> None:
        """Rebuild a package to apply changed USE flags (--changed-use)."""
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("install")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to rebuild packages")
            return
        invocation.return_value(GLib.Variant("(b)", (True,)))
        self._spawn_streaming([_EMERGE, "--changed-use", "--color", "n", atom],
                              operation="A package rebuild")

    def _update_world(self, sender: str, invocation) -> None:
        """Update the whole system: emerge -uDN @world."""
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("install")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to update the system")
            return
        invocation.return_value(GLib.Variant("(b)", (True,)))
        self._spawn_streaming([_EMERGE, "-uDN", "--color", "n", "@world"],
                              operation="A system update")

    def _depclean(self, atom: str, sender: str, invocation) -> None:
        """Safely remove packages: emerge --depclean [atom] (keeps needed deps)."""
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("remove")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to remove packages")
            return
        if atom and not self._ATOM_RE.match(atom):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "invalid package atom")
            return
        invocation.return_value(GLib.Variant("(b)", (True,)))
        argv = [_EMERGE, "--depclean", "--color", "n"]
        if atom:
            argv.append(atom)
        self._spawn_streaming(argv, operation="A package removal")

    def _depclean_multi(self, atoms, sender: str, invocation) -> None:
        """Remove several packages in one emerge --depclean (safe; keeps deps)."""
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("remove")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to remove packages")
            return
        atoms = list(atoms)
        if not atoms or any(not self._ATOM_RE.match(a) for a in atoms):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "invalid or empty package atom list")
            return
        invocation.return_value(GLib.Variant("(b)", (True,)))
        self._spawn_streaming([_EMERGE, "--depclean", "--color", "n", *atoms],
                              operation="A package removal")

    def _sync(self, sender: str, invocation) -> None:
        """Sync the Portage tree: emerge --sync."""
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("sync")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to sync the Portage tree")
            return
        invocation.return_value(GLib.Variant("(b)", (True,)))
        self._spawn_streaming([_EMERGE, "--sync", "--color", "n"],
                              operation="A Portage tree sync")

    def _sync_repos(self, names, sender: str, invocation) -> None:
        """Sync specific repositories by name (``emaint sync --repo <name>``).

        Used by Software Management's refresh-on-open: it syncs only the small,
        opted-in overlays, never the main tree (that's the Sync Portage Tree
        tool). Runs synchronously and returns an aggregate ``(ok, output)`` so
        the frontend can await it and surface any per-repo failure.
        """
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("sync")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to sync repositories")
            return
        names = list(names)
        if not names or any(not repo_commands.valid_name(n) for n in names):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "invalid or empty repository name list")
            return
        self._begin_op("A repository sync")  # don't idle-exit mid-sync
        outputs: list[str] = []
        ok_all = True
        try:
            for name in names:
                try:
                    proc = Gio.Subprocess.new(
                        [_EMAINT, "sync", "--repo", name],
                        Gio.SubprocessFlags.STDOUT_PIPE
                        | Gio.SubprocessFlags.STDERR_MERGE)
                    _ok, out, _err = proc.communicate_utf8(None, None)
                    code = proc.get_exit_status() if proc.get_if_exited() else -1
                except GLib.Error as exc:  # pragma: no cover - depends on live system
                    out, code = exc.message, -1
                if code != 0:
                    ok_all = False
                outputs.append(
                    f"=== {name}: {'ok' if code == 0 else 'failed'} ===\n"
                    f"{(out or '').strip()}")
        finally:
            self._end_op()
        audit("software.sync_repos", uid=caller_uid(self._conn, sender),
              result="ok" if ok_all else "failed", detail=",".join(names))
        invocation.return_value(GLib.Variant("(bs)", (ok_all, "\n".join(outputs))))

    def _deselect(self, atoms, sender: str, invocation) -> None:
        """Drop packages from the @world set (``emerge --deselect``).

        Unmerges nothing — it only removes the explicit-install record so a
        later depclean may reclaim them once no other package needs them. Runs
        synchronously (it just rewrites the world file) and returns
        ``(ok, output)`` so the frontend can await it and report the result.
        """
        if self._reject_if_busy(invocation):
            return
        if not self._check_authorized(sender, polkit_action("remove")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to deselect packages")
            return
        atoms = list(atoms)
        try:
            argv = world.deselect_argv(atoms, _EMERGE)
        except ValueError:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "invalid or empty package atom list")
            return
        self._begin_op("An @world set update")  # don't idle-exit mid-op
        try:
            proc = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
            _ok, out, _err = proc.communicate_utf8(None, None)
            code = proc.get_exit_status() if proc.get_if_exited() else -1
        except GLib.Error as exc:  # pragma: no cover - depends on live system
            out, code = exc.message, -1
        finally:
            self._end_op()
        ok = code == 0
        audit("software.deselect", uid=caller_uid(self._conn, sender),
              result="ok" if ok else "failed", detail=",".join(atoms))
        invocation.return_value(GLib.Variant("(bs)", (ok, (out or "").strip())))

    # -- news mark-read ------------------------------------------------------

    def _mark_news(self, selector: str, read: bool, sender: str,
                   invocation) -> None:
        """Mark Portage news items read / unread via `eselect news` (polkit).

        The news read-state under /var/lib/gentoo/news is root/portage-owned, so
        an unprivileged user often can't persist it — this does it for them.
        """
        if not self._check_authorized(sender, polkit_action("news")):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to mark news")
            return
        try:
            argv = news.mark_read_argv(selector, _ESELECT, read=read)
        except ValueError:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "invalid news selector")
            return
        try:
            proc = Gio.Subprocess.new(
                argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
            )
            proc.communicate_utf8(None, None)
            code = proc.get_exit_status() if proc.get_if_exited() else -1
        except GLib.Error as exc:  # pragma: no cover - depends on live system
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.FAILED,
                f"mark-read failed: {exc.message}")
            return
        invocation.return_value(GLib.Variant("(b)", (code == 0,)))

    # Package atom (category/name), validated before merges/removes. Portage
    # config writes now go through the org.gentoo.gest.Portage WriteConfig RPC.
    _ATOM_RE = re.compile(r"^[a-z0-9][a-z0-9+._-]*/[a-zA-Z0-9+._-]+$")

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
            result = authority.call_sync(
                "CheckAuthorization",
                authorization_variant(sender, action_id),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            is_authorized = authorization_is_granted(result)
            audit(action_id, uid=caller_uid(self._conn, sender),
                  result="authorized" if is_authorized else "denied")
            return is_authorized
        except GLib.Error:  # pragma: no cover - depends on live polkit
            return False

    # -- streaming ----------------------------------------------------------

    def _emit(self, signal: str, variant: GLib.Variant) -> None:
        self._conn.emit_signal(None, SOFTWARE_PATH, SOFTWARE_IFACE, signal, variant)

    def _spawn_streaming(self, argv: list[str], operation: str = "") -> None:
        self._begin_op(operation)
        proc = Gio.Subprocess.new(
            argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
        )
        stdout = proc.get_stdout_pipe()

        # Buffer complete lines and emit them in batches (see _BATCH_* above).
        # ``timer`` holds the id of a pending flush timeout, or 0 when none is
        # scheduled; ``partial`` holds the trailing bytes of a not-yet-complete
        # line carried across chunk reads.
        buf: list[str] = []
        timer = {"id": 0}
        partial = {"bytes": b""}

        def emit_buffered():
            if buf:
                self._emit("Progress", GLib.Variant("(as)", (list(buf),)))
                buf.clear()

        def flush_now():
            """Emit immediately and cancel any pending timed flush."""
            if timer["id"]:
                GLib.source_remove(timer["id"])
                timer["id"] = 0
            emit_buffered()

        def on_timer():
            timer["id"] = 0
            emit_buffered()
            return False  # one-shot

        def queue_line(raw: bytes):
            # Decode tolerantly: build output can still emit stray non-UTF-8
            # bytes; replace them rather than truncate the stream.
            buf.append(raw.decode("utf-8", "replace"))
            if len(buf) >= _BATCH_MAX_LINES:
                flush_now()          # buffer full — send this batch now

        def read_next(*_):
            stdout.read_bytes_async(
                _READ_CHUNK, GLib.PRIORITY_DEFAULT, None, on_chunk)

        def on_chunk(src, res):
            try:
                chunk = src.read_bytes_finish(res)
            except GLib.Error:
                chunk = None
            data = chunk.get_data() if chunk is not None else b""
            if not data:  # zero-length read == EOF
                if partial["bytes"]:               # a final unterminated line
                    queue_line(partial["bytes"])
                    partial["bytes"] = b""
                flush_now()
                proc.wait_async(None, on_done)
                return
            lines = (partial["bytes"] + data).split(b"\n")
            partial["bytes"] = lines.pop()         # trailing partial (or b"")
            for raw in lines:
                queue_line(raw)
            if buf and timer["id"] == 0:
                timer["id"] = GLib.timeout_add(_BATCH_INTERVAL_MS, on_timer)
            read_next()

        def on_done(p, res):
            p.wait_finish(res)
            code = p.get_exit_status() if p.get_if_exited() else -1
            self._emit("Finished", GLib.Variant("(i)", (code,)))
            self._end_op()

        read_next()


# Standard system executable directories. D-Bus activation can hand the service
# an empty or minimal PATH, in which case emerge can't find its sync/unpack
# helpers (git, rsync, bzip2, tar) and every repo sync fails with
# "!!! Command not found: <tool>". We ensure these are always on PATH.
_SYSTEM_PATH = (
    "/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin",
)


def _augmented_path(current: str) -> str:
    """Return ``current`` PATH with the standard system dirs guaranteed present
    (prepended), preserving any extra entries the activation env already had."""
    extra = [p for p in current.split(os.pathsep) if p and p not in _SYSTEM_PATH]
    return os.pathsep.join([*_SYSTEM_PATH, *extra])


def main() -> int:
    # D-Bus activation gives us a minimal environment (no LANG/LC_*), so emerge
    # and the other tools fall back to the C locale and emit non-UTF-8 bytes for
    # accented/special characters. Force a UTF-8 locale so their output renders
    # correctly in the TUI.
    os.environ["LC_ALL"] = "C.UTF-8"
    # Likewise the activation PATH can be empty/minimal, so emerge fails to find
    # rsync/git/bzip2 and all syncs (and unpacking) break. Guarantee a sane PATH.
    os.environ["PATH"] = _augmented_path(os.environ.get("PATH", ""))
    loop = GLib.MainLoop()

    def on_bus_acquired(conn, name):
        SoftwareService(conn, on_idle=loop.quit)
        ServicesService(conn)
        UsersService(conn)
        SystemService(conn)
        NetworkService(conn)
        EselectService(conn)
        BootloaderService(conn)
        ReposService(conn)
        SshService(conn)
        PortageService(conn)
        DiskService(conn)
        DateTimeService(conn)
        KernelService(conn)
        FirewallService(conn)
        SshdService(conn)
        PrivilegeService(conn)
        SysctlService(conn)
        EnvdService(conn)
        WifiService(conn)

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
