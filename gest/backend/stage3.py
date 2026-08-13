"""GeST root D-Bus interface for the stage3 module.

Registered at /org/gentoo/gest/Stage3. Downloads a Gentoo stage3 tarball,
**verifies its integrity** (mandatory BLAKE2B+SHA512 against the mirror's
``.DIGESTS``), best-effort checks its GPG signature, and unpacks it into a
confined install target root — streaming output like emerge (a batched
``Progress`` signal and a final ``Finished``) because download + unpack runs for
minutes and a blocking D-Bus method would exceed the call timeout. polkit-gated
with org.gentoo.gest.stage3.unpack; audit-logged. On the live CD it runs as root
(the DirectExecutor precondition); this interface is the privileged path.

Safety (the two invariants this module exists to enforce):

* The target root is confined to /mnt|/media|/run/media by
  ``mount.guard_target_root`` (which rejects ``/``) before anything is downloaded
  — unpacking a stage3 over the running system would destroy it.
* Hash verification is **mandatory and runs before any unpack**. A failed (or
  unverifiable) hash aborts the operation before ``tar`` is ever invoked.

The GPG signature check is deliberately **best-effort**: many live environments
do not have the Gentoo release keys in their keyring, so a missing key or a
missing ``gpg`` is reported honestly (verified / unverified / gpg-unavailable)
but does not hard-fail. Integrity (the hashes) is the hard gate; authenticity
(the signature) is advisory.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from gest.backend.audit import audit
from gest.backend.polkit import caller_uid, check_authorization
from gest.core.disk import mount
from gest.core.stage3 import commands, verify
from gest.ipc.interface import STAGE3_IFACE, STAGE3_PATH, STAGE3_POLKIT

_INTROSPECTION = f"""
<node>
  <interface name="{STAGE3_IFACE}">
    <method name="Unpack">
      <arg type="s" name="target_root" direction="in"/>
      <arg type="s" name="tarball_url" direction="in"/>
      <arg type="s" name="digests_text" direction="in"/>
      <arg type="s" name="signature_url" direction="in"/>
      <arg type="b" name="started" direction="out"/>
    </method>
    <signal name="Progress"><arg type="as" name="lines"/></signal>
    <signal name="Finished"><arg type="i" name="exit_code"/></signal>
  </interface>
</node>
"""

# Batch streamed output like the software/kernel backends (one signal per flush,
# bounded by a line cap and a time interval) so a chatty download or unpack can't
# storm the frontend with a signal per line.
_BATCH_MAX_LINES = 200
_BATCH_INTERVAL_MS = 100
_READ_CHUNK = 65536

_WGET = shutil.which("wget")
_CURL = shutil.which("curl")
_TAR = shutil.which("tar") or "/bin/tar"
_GPG = shutil.which("gpg")


def _download_argv(url: str, dest: str) -> list[str]:
    """Argv for downloading ``url`` to ``dest``, preferring wget (clean, periodic
    newline progress with dot:giga) and falling back to curl."""
    if _WGET:
        return [_WGET, "--progress=dot:giga", "-O", dest, url]
    curl = _CURL or "/usr/bin/curl"
    return [curl, "-L", "--fail", "-o", dest, url]


def _http_url(url: str) -> bool:
    """Only http(s) sources are accepted (rejects file://, and a leading '-' that
    a downloader could misread as a flag)."""
    return url.startswith(("https://", "http://"))


class _CommandStreamer:
    """Run one argv, streaming its merged output as batched ``Progress`` signals
    and calling ``on_exit(code)`` when it ends. The orchestrator emits the final
    ``Finished`` itself, so this only ever emits ``Progress``."""

    def __init__(self, argv, *, emit, on_exit):
        self._argv = argv
        self._emit = emit
        self._on_exit = on_exit
        self._buf: list[str] = []
        self._timer = 0
        self._partial = b""

    def start(self) -> None:
        proc = Gio.Subprocess.new(
            self._argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
        self._proc = proc
        self._stdout = proc.get_stdout_pipe()
        self._read_next()

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

    def _read_next(self, *_) -> None:
        self._stdout.read_bytes_async(
            _READ_CHUNK, GLib.PRIORITY_DEFAULT, None, self._on_chunk)

    def _on_chunk(self, src, res) -> None:
        try:
            chunk = src.read_bytes_finish(res)
        except GLib.Error:
            chunk = None
        data = chunk.get_data() if chunk is not None else b""
        if not data:  # EOF
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
        self._on_exit(code)


class _Stage3Runner:
    """Orchestrate one stage3 install: download → verify (mandatory) → gpg
    (best-effort) → unpack, streaming throughout and ending with one Finished."""

    def __init__(self, target_root, tarball_url, digests_text, signature_url,
                 *, emit, on_finished):
        self._root = target_root
        self._tarball_url = tarball_url
        self._digests_text = digests_text
        self._signature_url = signature_url
        self._emit = emit
        self._on_finished = on_finished
        self._filename = os.path.basename(tarball_url)
        self._workdir = ""
        self._tarball = ""
        self._sig = ""
        self._sig_downloaded = False

    # -- helpers -------------------------------------------------------------

    def _say(self, *lines: str) -> None:
        self._emit("Progress", GLib.Variant("(as)", (list(lines),)))

    def _finish(self, code: int) -> None:
        with contextlib.suppress(OSError):
            if self._workdir:
                shutil.rmtree(self._workdir, ignore_errors=True)
        self._emit("Finished", GLib.Variant("(i)", (code,)))
        self._on_finished(code)

    def _run(self, argv, on_exit) -> None:
        _CommandStreamer(argv, emit=self._emit, on_exit=on_exit).start()

    # -- phases --------------------------------------------------------------

    def start(self) -> None:
        # The tarball is large; stage it on the target root's own filesystem
        # (already mounted, ample space) rather than a RAM-backed /tmp.
        self._workdir = tempfile.mkdtemp(dir=self._root, prefix=".gest-stage3-")
        self._tarball = os.path.join(self._workdir, self._filename)
        self._sig = self._tarball + ".asc"
        self._say(f"Downloading {self._filename}", f"  from {self._tarball_url}")
        self._run(_download_argv(self._tarball_url, self._tarball), self._after_download)

    def _after_download(self, code: int) -> None:
        if code != 0 or not os.path.exists(self._tarball):
            self._say(f"!!! download failed (exit {code}) — aborting")
            self._finish(code or 1)
            return
        if _http_url(self._signature_url):
            self._say("Downloading signature (.asc)")
            self._run(_download_argv(self._signature_url, self._sig), self._after_sig)
        else:
            self._after_sig(1)

    def _after_sig(self, code: int) -> None:
        # A missing signature is not fatal (GPG is best-effort); note it and move
        # straight to the mandatory integrity check.
        self._sig_downloaded = code == 0 and os.path.exists(self._sig)
        self._verify_hashes()

    def _verify_hashes(self) -> None:
        """MANDATORY integrity gate — runs before any unpack. A failure aborts."""
        self._say("Verifying integrity (BLAKE2B + SHA512)…")
        try:
            with open(self._tarball, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            self._say(f"!!! cannot read downloaded tarball: {exc} — aborting")
            self._finish(1)
            return
        expected = verify.parse_digests(self._digests_text, self._filename)
        if not expected:
            self._say("!!! no BLAKE2B/SHA512 digest for this file in .DIGESTS — "
                      "refusing to unpack an unverifiable tarball")
            self._finish(1)
            return
        if not verify.verify_hashes(data, expected):
            self._say("!!! HASH MISMATCH — the download is corrupt or tampered; "
                      "aborting BEFORE unpack")
            self._finish(1)
            return
        self._say(f"  integrity OK ({', '.join(sorted(expected))})")
        self._gpg_verify()

    def _gpg_verify(self) -> None:
        """Best-effort authenticity check — reports status, never hard-fails."""
        if not self._sig_downloaded:
            self._say("GPG: no signature available — skipping authenticity check")
            self._unpack()
            return
        if not _GPG:
            self._say("GPG: gpg not installed — skipping authenticity check")
            self._unpack()
            return
        self._say("Verifying GPG signature (best-effort)…")
        self._run(commands.gpg_verify_argv(self._sig, self._tarball, gpg=_GPG),
                  self._after_gpg)

    def _after_gpg(self, code: int) -> None:
        if code == 0:
            self._say("  GPG signature VERIFIED against the keyring")
        else:
            # Commonly "No public key" on a live CD lacking the Gentoo release
            # keys — advisory only, integrity already passed, so we proceed.
            self._say("  GPG unverified (key missing or bad signature) — "
                      "continuing; integrity hashes already passed")
        self._unpack()

    def _unpack(self) -> None:
        self._say(f"Unpacking into {self._root}…")
        self._run(commands.tar_unpack_argv(self._tarball, self._root, tar=_TAR),
                  self._after_unpack)

    def _after_unpack(self, code: int) -> None:
        if code == 0:
            self._say(f"Stage3 unpacked into {self._root}")
        else:
            self._say(f"!!! unpack failed (exit {code})")
        self._finish(code)


class Stage3Service:
    """Implements the ``org.gentoo.gest.Stage3`` interface."""

    def __init__(self, connection: Gio.DBusConnection):
        self._conn = connection
        self._active = False
        node = Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION)
        connection.register_object(
            STAGE3_PATH, node.interfaces[0], self._on_call, None, None
        )

    def _emit(self, signal: str, variant: GLib.Variant) -> None:
        self._conn.emit_signal(None, STAGE3_PATH, STAGE3_IFACE, signal, variant)

    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        if method != "Unpack":
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD,
                f"No such method {method}")
            return
        uid = caller_uid(self._conn, sender)
        if not check_authorization(self._conn, sender, STAGE3_POLKIT):
            audit("Unpack", uid=uid, result="denied")
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.ACCESS_DENIED,
                "Not authorized to unpack a stage3")
            return
        target_root, tarball_url, digests_text, signature_url = params.unpack()
        # SAFETY GATE: reject anything not strictly under /mnt|/media|/run/media
        # (this rejects "/"). Do this before touching the network or disk.
        try:
            mount.guard_target_root(target_root)
        except ValueError as exc:
            audit("Unpack", uid=uid, result="refused", detail=str(exc))
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS, str(exc))
            return
        if not _http_url(tarball_url):
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.INVALID_ARGS,
                f"tarball URL must be http(s): {tarball_url!r}")
            return
        audit("Unpack", uid=uid, result="started",
              detail=f"stage3 → {target_root}")
        self._active = True
        runner = _Stage3Runner(
            target_root, tarball_url, digests_text, signature_url,
            emit=self._emit, on_finished=self._on_finished)
        runner.start()
        invocation.return_value(GLib.Variant("(b)", (True,)))

    def _on_finished(self, code: int) -> None:
        self._active = False
        audit("Unpack", result="ok" if code == 0 else "failed", detail=f"exit {code}")
