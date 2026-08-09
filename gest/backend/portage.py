"""GeST root D-Bus interface for the unified Portage-configuration module.

Registered at ``/org/gentoo/gest/Portage``. Exposes one generic method::

    WriteConfig(writes: a(ssu)) -> ok: b

where each ``(path, text, mode)`` describes a file under ``/etc/portage/`` to
write atomically (``text == ""`` deletes it). This replaces the per-surface
``SetMakeconf`` / ``SetPackageUse`` / ``SetPackageConfig`` methods; the frontend
renders the full new contents (previewing the diff for the user) and this
service is the single trusted gate that validates and applies them.

Because the caller is unprivileged, safety lives here:

* every path must resolve (after ``realpath``, defeating symlink escapes) to a
  location inside ``/etc/portage/``;
* the content is re-validated against the surface's grammar;
* all writes are validated before any is applied (fail-fast, no partial batch);
* the whole batch is gated by ``org.gentoo.gest.portage.configure``.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.portage import paths, write
from gest.core.portage.codec import atomfile, ini, shell
from gest.ipc.interface import PORTAGE_IFACE, PORTAGE_PATH, PORTAGE_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{PORTAGE_IFACE}">
    <method name="WriteConfig">
      <arg type="a(ssu)" name="writes" direction="in"/>
      <arg type="b" name="ok" direction="out"/>
    </method>
  </interface>
</node>
"""

# A package atom (category/name), the key of every package.* line.
_ATOM_RE = re.compile(r"^[a-z0-9][a-z0-9+._-]*/[a-zA-Z0-9+._-]+$")
_MAX_BYTES = 1 << 20  # 1 MiB — a sanity ceiling; config files are tiny


def _validate_content(path: str, text: str) -> str:
    """Return "" if ``text`` is a valid body for the surface at ``path``.

    On failure returns a human-readable reason. Empty ``text`` (a deletion) is
    always valid.
    """
    if not text:
        return ""
    if "\0" in text:
        return "NUL byte in content"
    if len(text.encode("utf-8")) > _MAX_BYTES:
        return "content too large"
    base = os.path.basename(path)
    if base == "make.conf":
        for name, value, _s, _e in shell.assignments(text):
            if not shell.valid_name(name) or not shell.valid_value(value):
                return f"invalid make.conf assignment: {name}"
        return ""
    if "/package." in path:
        for row in atomfile.parse(text):
            if not _ATOM_RE.match(row.atom):
                return f"invalid package atom: {row.atom}"
        return ""
    if "/binrepos.conf/" in path or "/repos.conf/" in path:
        ini.parse(text)  # raises nothing; malformed lines are ignored
        return ""
    return "not a writable Portage surface"


def _validate_path(path: str) -> str:
    """Return "" if ``path`` is a safe target inside /etc/portage, else a reason."""
    if not os.path.isabs(path):
        return "path is not absolute"
    root = paths.config_root()
    if not write.is_within_etc_portage(path, root):
        return "path is outside /etc/portage"
    real = os.path.realpath(path)  # resolve symlinks in existing parents
    if not write.is_within_etc_portage(real, root):
        return "path resolves outside /etc/portage"
    return ""


def _apply_one(path: str, text: str, mode: int) -> None:
    """Atomically write ``text`` to ``path`` (or delete ``path`` when empty)."""
    if not text:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)
        return
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".gest.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode or 0o644)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


class PortageService:
    """Implements the ``org.gentoo.gest.Portage`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            PORTAGE_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "WriteConfig":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        (writes,) = params.unpack()
        self._write_config(writes, sender, invocation)

    def _write_config(self, writes, sender, invocation) -> None:
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, PORTAGE_POLKIT):
            audit("portage.WriteConfig", uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to modify Portage configuration")
            return
        if not writes:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                "no writes requested")
            return
        # Validate the whole batch before applying any of it.
        plan: list[tuple[str, str, int]] = []
        for path, text, mode in writes:
            reason = _validate_path(path) or _validate_content(path, text)
            if reason:
                audit("portage.WriteConfig", uid=uid, result="denied", detail=path)
                invocation.return_error_literal(
                    Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                    f"{reason}: {path}")
                return
            plan.append((path, text, int(mode)))
        try:
            for path, text, mode in plan:
                _apply_one(path, text, mode)
        except OSError as exc:
            audit("portage.WriteConfig", uid=uid, result="failed", detail=str(exc))
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.FAILED, f"write failed: {exc}")
            return
        audit("portage.WriteConfig", uid=uid, result="ok",
              detail=",".join(p for p, _t, _m in plan))
        invocation.return_value(GLib.Variant("(b)", (True,)))
