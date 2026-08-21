#!/usr/bin/env python3
"""Gangway Phase-5b **RAIL feasibility spike** — host-validated, never CI.

The Gangway Phase-5 scope (``docs/design/gangway-phase5-scope.md`` §3) gates the
seamless-RemoteApp *engine* (items B/A/E) behind a host-validation spike:

  1. On a real Windows VM/host, run ``xfreerdp /app:program:…`` under Xwayland on
     a **pinned** FreeRDP version.
  2. Confirm you get **distinct X11 toplevels** with a usable, **stable
     ``WM_CLASS``** per remote app.
  3. Confirm FreeRDP #12391 (RemoteApp windows silently missing on xfreerdp3) is
     not blocking on that version — and, because #12397 saw it "work the first few
     runs then fail", confirm it holds across **repeated** launches.

This harness automates that measurement. It launches the X11 ``xfreerdp3`` client
in RAIL (``/app:``) mode against an already-running, already-provisioned Windows
vessel (see ``flotilla launch --provision --remote-app`` — the guest-enablement
that populates the ``TSAppAllowList`` this probe references), diffs the X server's
toplevel list to catch the new window, reads its ``WM_CLASS``, repeats per app,
and prints a GREEN/RED verdict against the three criteria above.

It is intentionally standalone (no ``gest`` import, not shipped in the wheel) and
throwaway: it measures whether the engine pivot is safe to build. It is NOT the
engine — the production ``/app:`` argv lands in ``gest/core/rdp/commands.py`` only
once this spike is GREEN.

Pin note (as of 2026-08-21): #12391 is **fixed in FreeRDP 3.24.0** (PR #12392,
"[client,x11] improve rails window locking"); the 3.23.0 release is the broken
one — avoid it. This harness warns if the client is older than 3.24.0.

Usage:
    # against a provisioned vessel at 192.168.122.50, user 'flotilla':
    GANGWAY_SPIKE_PASSWORD=... \\
    scripts/host-validation/rail-spike.py \\
        --host 192.168.122.50 --user flotilla \\
        --app notepad --app mspaint --runs 5

    scripts/host-validation/rail-spike.py --host h --user u --app notepad --dry-run
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

# The version at/after which the RAIL X11 window regression (#12391) is fixed.
MIN_FREERDP = (3, 24, 0)
DEFAULT_CLIENT = "xfreerdp3"


# ======================================================================
# Pure helpers (unit-tested in tests/test_rail_spike.py) — no IO here.
# ======================================================================

def build_probe_argv(client: str, host: str, user: str, app_key: str, *,
                     port: int = 3389, from_stdin: bool = True,
                     extra: list[str] | None = None) -> list[str]:
    """The RAIL probe command: launch a single published RemoteApp by its
    ``TSAppAllowList`` alias (``/app:program:<key>``) on the **X11** client. NLA +
    trust-on-first-use to match how a provisioned vessel is reachable; the
    password is fed over stdin (``/from-stdin``), never on argv (``ps``-visible).

    This mirrors what the eventual engine (item A) would build, but is scoped to
    the spike — it deliberately omits ``/f``/``/size:`` so RAIL, not a desktop
    surface, is what we measure."""
    argv = [
        client,
        f"/v:{host}:{port}",
        f"/u:{user}",
        f"/app:program:{app_key}",
        "/sec:nla",
        "/cert:tofu",
    ]
    if extra:
        argv += extra
    if from_stdin:
        argv.append("/from-stdin")
    return argv


def parse_version(version_output: str) -> tuple[int, int, int] | None:
    """Extract ``(major, minor, patch)`` from ``xfreerdp3 --version`` output, e.g.
    ``This is FreeRDP version 3.24.0 (release)`` → ``(3, 24, 0)``. None if absent."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", version_output)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def version_ok(version: tuple[int, int, int] | None,
               minimum: tuple[int, int, int] = MIN_FREERDP) -> bool:
    return version is not None and version >= minimum


def parse_client_list(xprop_root_output: str) -> list[str]:
    """Window ids from ``xprop -root _NET_CLIENT_LIST`` output. The line looks like
    ``_NET_CLIENT_LIST(WINDOW): window id # 0x1a00007, 0x1c00003`` — return the
    ``0x…`` ids (empty list if the atom is absent / unset)."""
    if "_NET_CLIENT_LIST" not in xprop_root_output:
        return []
    ids = re.findall(r"0x[0-9a-fA-F]+", xprop_root_output)
    return ids


def parse_wm_class(xprop_output: str) -> tuple[str, str]:
    """``(instance, class)`` from ``xprop -id <w> WM_CLASS`` output:
    ``WM_CLASS(STRING) = "instance", "class"``. Empty strings if unset."""
    m = re.search(r'WM_CLASS\(STRING\)\s*=\s*"([^"]*)",\s*"([^"]*)"', xprop_output)
    return (m[1], m[2]) if m else ("", "")


@dataclass
class RunResult:
    appeared: bool          # a new X11 toplevel showed up after launch
    wm_instance: str = ""
    wm_class: str = ""
    note: str = ""


@dataclass
class AppVerdict:
    app_key: str
    runs: list[RunResult] = field(default_factory=list)

    @property
    def all_appeared(self) -> bool:
        return bool(self.runs) and all(r.appeared for r in self.runs)

    @property
    def classes(self) -> set[str]:
        return {r.wm_class for r in self.runs if r.appeared and r.wm_class}

    @property
    def stable_class(self) -> bool:
        """Exactly one non-empty WM_CLASS seen across every run that appeared."""
        return self.all_appeared and len(self.classes) == 1

    @property
    def passed(self) -> bool:
        return self.all_appeared and self.stable_class


def evaluate(verdicts: list[AppVerdict]) -> bool:
    """GREEN iff every probed app produced a distinct toplevel on every run with a
    single, stable, non-empty WM_CLASS."""
    return bool(verdicts) and all(v.passed for v in verdicts)


def summarize(verdicts: list[AppVerdict]) -> str:
    lines = ["", "==== RAIL spike results ===="]
    for v in verdicts:
        cls = ", ".join(sorted(v.classes)) or "(none)"
        n = len(v.runs)
        appeared = sum(1 for r in v.runs if r.appeared)
        flag = "PASS" if v.passed else "FAIL"
        lines.append(f"  [{flag}] {v.app_key}: appeared {appeared}/{n} run(s); "
                     f"WM_CLASS={{{cls}}}"
                     + ("" if v.stable_class else "  <- not a single stable class"))
    lines.append("")
    lines.append("VERDICT: " + ("GREEN — build the 5b engine (items B/A/E)."
                                 if evaluate(verdicts)
                                 else "RED — hold; 5b stays upstream-gated."))
    return "\n".join(lines)


# ======================================================================
# Host edge — spawns FreeRDP + queries the X server. Not CI-able.
# ======================================================================

def _capture(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except FileNotFoundError:
        return ""


def _client_list(display: str | None) -> set[str]:
    env_display = ["-display", display] if display else []
    out = _capture(["xprop", *env_display, "-root", "_NET_CLIENT_LIST"])
    return set(parse_client_list(out))


def _wm_class(win_id: str, display: str | None) -> tuple[str, str]:
    env_display = ["-display", display] if display else []
    return parse_wm_class(_capture(["xprop", *env_display, "-id", win_id, "WM_CLASS"]))


def _probe_once(argv: list[str], password: str, *, display: str | None,
                timeout: float, settle: float) -> RunResult:
    """Launch one RAIL session, wait for a new toplevel, read its WM_CLASS, tear
    the session down. The new-window diff is compositor-agnostic: xfreerdp is an
    X11 client, so its RAIL toplevel joins the (Xwayland) root's _NET_CLIENT_LIST."""
    before = _client_list(display)
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, text=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return RunResult(appeared=False, note=f"{argv[0]} not found")
    try:
        if proc.stdin:
            proc.stdin.write(password + "\n")
            proc.stdin.flush()
    except (BrokenPipeError, OSError):
        pass

    deadline = time.monotonic() + timeout
    new_ids: set[str] = set()
    while time.monotonic() < deadline:
        if proc.poll() is not None:  # client exited before a window appeared
            break
        new_ids = _client_list(display) - before
        if new_ids:
            break
        time.sleep(0.5)

    result = RunResult(appeared=bool(new_ids))
    if new_ids:
        time.sleep(settle)  # let RAIL set the final WM_CLASS
        # pick the first new window that carries a WM_CLASS
        for win_id in sorted(new_ids):
            inst, cls = _wm_class(win_id, display)
            if cls or inst:
                result.wm_instance, result.wm_class = inst, cls
                break
    else:
        result.note = "no new toplevel before timeout (#12391-class failure?)"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return result


def _preflight(client: str, io) -> tuple[int, int, int] | None:
    if not shutil.which("xprop"):
        io("ERROR: xprop not found — install x11-apps/xprop (needed to read WM_CLASS)")
        sys.exit(3)
    if not shutil.which(client):
        io(f"ERROR: {client} not found — install net-misc/freerdp[X] (X11 client)")
        sys.exit(3)
    version = parse_version(_capture([client, "--version"]))
    if version is None:
        io(f"WARN: could not determine {client} version")
    elif not version_ok(version):
        io(f"WARN: {client} {'.'.join(map(str, version))} < "
           f"{'.'.join(map(str, MIN_FREERDP))} — RAIL regression #12391 is fixed in "
           "3.24.0; results below this version are expected RED (upgrade before trusting a GREEN).")
    else:
        io(f"OK: {client} {'.'.join(map(str, version))} (>= 3.24.0, past #12391)")
    return version


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gangway Phase-5b RAIL feasibility spike.")
    ap.add_argument("--host", required=True, help="the provisioned Windows vessel's IP")
    ap.add_argument("--user", required=True, help="the guest account (vessel.unattend_username)")
    ap.add_argument("--port", type=int, default=3389)
    ap.add_argument("--app", action="append", required=True, metavar="KEY",
                    help="a TSAppAllowList alias to launch as a RemoteApp (repeatable)")
    ap.add_argument("--client", default=DEFAULT_CLIENT,
                    help=f"FreeRDP X11 client (default {DEFAULT_CLIENT})")
    ap.add_argument("--runs", type=int, default=5, help="launches per app (catch #12397 flakiness)")
    ap.add_argument("--timeout", type=float, default=30.0, help="seconds to wait for a window")
    ap.add_argument("--settle", type=float, default=1.5, help="seconds before reading WM_CLASS")
    ap.add_argument("--display", default=os.environ.get("DISPLAY"),
                    help="X display xfreerdp draws onto (Xwayland), default $DISPLAY")
    ap.add_argument("--dry-run", action="store_true", help="print the probe argv and exit")
    args = ap.parse_args(argv)

    def say(s: str) -> None:
        print(s, flush=True)

    if args.dry_run:
        for app in args.app:
            say(" ".join(build_probe_argv(args.client, args.host, args.user, app,
                                          port=args.port)))
        return 0

    _preflight(args.client, say)
    if not args.display:
        say("ERROR: no X display ($DISPLAY). xfreerdp3 must run under X11/Xwayland.")
        return 3
    password = os.environ.get("GANGWAY_SPIKE_PASSWORD") or getpass.getpass(
        f"password for {args.user}@{args.host} (throwaway spike cred): ")

    verdicts: list[AppVerdict] = []
    for app in args.app:
        v = AppVerdict(app_key=app)
        argv_probe = build_probe_argv(args.client, args.host, args.user, app, port=args.port)
        for i in range(1, args.runs + 1):
            say(f"  {app} run {i}/{args.runs} …")
            r = _probe_once(argv_probe, password, display=args.display,
                            timeout=args.timeout, settle=args.settle)
            state = (f"appeared WM_CLASS={r.wm_class!r}" if r.appeared
                     else f"NO WINDOW ({r.note})")
            say(f"    -> {state}")
            v.runs.append(r)
        verdicts.append(v)

    say(summarize(verdicts))
    return 0 if evaluate(verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
