"""GeST root D-Bus interface for the kernel-build module.

Registered at /org/gentoo/gest/Kernel. Builds a kernel (genkernel, or a manual
make pipeline) and streams its output like emerge does — a batched ``Progress``
signal and a final ``Finished`` — since a build runs for minutes and a blocking
D-Bus method would exceed the call timeout. polkit-gated with
org.gentoo.gest.kernel.build; the argv is re-derived server-side from the shared
pipeline builder and audit-logged.
"""

from __future__ import annotations

import shutil

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.kernel import build
from gest.ipc.interface import KERNEL_IFACE, KERNEL_PATH, KERNEL_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{KERNEL_IFACE}">
    <method name="Build">
      <arg type="s" name="method" direction="in"/>
      <arg type="s" name="source_dir" direction="in"/>
      <arg type="u" name="jobs" direction="in"/>
      <arg type="s" name="kernel_config" direction="in"/>
      <arg type="b" name="initramfs" direction="in"/>
      <arg type="s" name="kver" direction="in"/>
      <arg type="b" name="started" direction="out"/>
    </method>
    <signal name="Progress"><arg type="as" name="lines"/></signal>
    <signal name="Finished"><arg type="i" name="exit_code"/></signal>
  </interface>
</node>
"""

# Coalesce streamed output the same way the software backend does (see its
# comments): one signal per flush, bounded by a line cap and a time interval.
_BATCH_MAX_LINES = 200
_BATCH_INTERVAL_MS = 100
_READ_CHUNK = 65536


def _resolve(argv: list[str]) -> list[str]:
    """Resolve argv[0] to an absolute path (activation PATH can be minimal)."""
    return [shutil.which(argv[0]) or argv[0], *argv[1:]]


class _PipelineStreamer:
    """Run a list of argv sequentially, streaming output as batched Progress
    signals and ending with one Finished(exit_code) — the first non-zero exit
    stops the pipeline (like ``&&`` between commands)."""

    def __init__(self, argv_list, *, emit, on_finished):
        self._argv_list = argv_list
        self._emit = emit                 # emit(signal_name, GLib.Variant)
        self._on_finished = on_finished   # on_finished(exit_code) after the signal
        self._index = 0
        self._buf: list[str] = []
        self._timer = 0
        self._partial = b""

    def start(self) -> None:
        self._run_current()

    # -- batching -----------------------------------------------------------

    def _emit_buffered(self) -> None:
        if self._buf:
            self._emit("Progress", GLib.Variant("(as)", (list(self._buf),)))
            self._buf.clear()

    def _flush_now(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self._emit_buffered()

    def _on_timer(self) -> bool:
        self._timer = 0
        self._emit_buffered()
        return False

    def _queue_line(self, raw: bytes) -> None:
        self._buf.append(raw.decode("utf-8", "replace"))
        if len(self._buf) >= _BATCH_MAX_LINES:
            self._flush_now()

    # -- per-step read loop -------------------------------------------------

    def _run_current(self) -> None:
        proc = Gio.Subprocess.new(
            self._argv_list[self._index],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
        self._proc = proc
        self._stdout = proc.get_stdout_pipe()
        self._partial = b""
        self._read_next()

    def _read_next(self, *_) -> None:
        self._stdout.read_bytes_async(_READ_CHUNK, GLib.PRIORITY_DEFAULT, None, self._on_chunk)

    def _on_chunk(self, src, res) -> None:
        try:
            chunk = src.read_bytes_finish(res)
        except GLib.Error:
            chunk = None
        data = chunk.get_data() if chunk is not None else b""
        if not data:                       # EOF for this step
            if self._partial:
                self._queue_line(self._partial)
                self._partial = b""
            self._flush_now()
            self._proc.wait_async(None, self._on_done)
            return
        lines = (self._partial + data).split(b"\n")
        self._partial = lines.pop()
        for raw in lines:
            self._queue_line(raw)
        if self._buf and self._timer == 0:
            self._timer = GLib.timeout_add(_BATCH_INTERVAL_MS, self._on_timer)
        self._read_next()

    def _on_done(self, p, res) -> None:
        p.wait_finish(res)
        code = p.get_exit_status() if p.get_if_exited() else -1
        if code != 0 or self._index + 1 >= len(self._argv_list):
            self._emit("Finished", GLib.Variant("(i)", (code,)))
            self._on_finished(code)
            return
        self._index += 1
        self._run_current()


class KernelService:
    """Implements the ``org.gentoo.gest.Kernel`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        self._active = False
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            KERNEL_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _emit(self, signal: str, variant: GLib.Variant) -> None:
        self._conn.emit_signal(None, KERNEL_PATH, KERNEL_IFACE, signal, variant)

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "Build":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, KERNEL_POLKIT):
            audit("Build", uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to build a kernel")
            return
        build_method, source_dir, jobs, kernel_config, initramfs, kver = params.unpack()
        config = build.BuildConfig(
            method=build_method, source_dir=source_dir, jobs=int(jobs),
            kernel_config=kernel_config, initramfs=bool(initramfs), kver=kver)
        try:
            argv_list = [_resolve(step.argv) for step in build.build_steps(config)]
        except ValueError as exc:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        audit("Build", uid=uid, result="started", detail=f"kernel build ({build_method})")
        self._active = True
        streamer = _PipelineStreamer(
            argv_list, emit=self._emit, on_finished=self._on_finished)
        streamer.start()
        invocation.return_value(GLib.Variant("(b)", (True,)))

    def _on_finished(self, code: int) -> None:
        self._active = False
        audit("Build", result="ok" if code == 0 else "failed", detail=f"exit {code}")
