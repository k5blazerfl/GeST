# Design: runtime detection and the dual privilege path

*Status: proposal · Target: `gest/core/exec/` + `gest/ipc/runtime.py` · Prerequisite for: storage provisioning and every installer module*

## Why

GeST's mutation model assumes an **installed system**: an unprivileged frontend
marshals every change over the system D-Bus to a root `gest-backend`, which asks
**polkit** to authorize the caller before running the tool. That is the correct
model on a running machine — it is the whole reason the frontend never touches
Portage or D-Bus mutation directly (the golden rule).

But the partitioner and the rest of the install-path modules are tested — and
ultimately *run* — from a **Gentoo minimal live CD/USB** on a target machine (see
the module-foundation roadmap and the live-CD testing note). That environment
breaks three assumptions at once:

- The user is **already root**. There is no privilege boundary to cross, so
  polkit's `CheckAuthorization` is asking whether root may act as root — it is
  redundant.
- **Polkit is generally not installed** on the minimal CD, and no authentication
  agent is running to answer a prompt.
- The **system D-Bus** may not be up, and `org.gentoo.gest.*` bus activation
  (the installed `.service` file) isn't in play.

So a mutation path that *requires* the polkit + D-Bus stack simply cannot run
there. GeST needs to detect its runtime and pick how mutations execute — without
forking the per-module logic, and without weakening the installed-system model.

## Two runtimes, one decision rule

| Runtime | How GeST is launched | Privilege path |
|---|---|---|
| **Installed system** | unprivileged user | D-Bus → root backend → **polkit gate** (today, unchanged) |
| **Live / already-root** | as root on a live CD (or root shell) | **run the tool in-process**, no D-Bus, no polkit |

The decision rule is deliberately simple and safe:

```
if os.geteuid() == 0:   -> DirectExecutor   (already root; polkit gate is meaningless)
else:                   -> DBusExecutor     (need escalation; keep the polkit contract)
```

An explicit override (`GEST_EXEC=direct|dbus`, or a `--exec` flag) exists for
testing and for the rare installed-but-running-as-root case, but the euid check
is the default and requires no configuration on the live CD.

**The security invariant:** `DirectExecutor` engages **only when the process is
already uid 0**. It never lets an unprivileged frontend run mutations directly —
that path still goes through D-Bus + polkit exactly as today. Direct mode does
not weaken the installed model; it only skips an authorization step that is
vacuous when the caller is already root.

## The abstraction: one runner, two executors

Today the subprocess-run-and-stream logic lives on the **root side** (in the
backend service): run argv, stream stdout line-by-line back as `Progress`
signals, emit `Finished`, honour the cross-session busy lock. In direct mode the
frontend process needs that same logic. So the design **extracts the runner into
a shared module** that both the backend service and a direct executor call — the
same lesson as the portage-config-core codecs (one implementation, two callers,
they can never diverge).

```
gest/core/exec/
  runner.py       # shared: run argv, stream lines, acquire/honour the busy lock,
                  #   return an exit result. No D-Bus, no polkit. Pure execution.
  executor.py     # Executor protocol: async run(argv, *, on_progress) -> Result
                  #   - DirectExecutor  : calls runner in-process (root only)
                  #   - DBusExecutor    : marshals to the backend, receives
                  #                       Progress/Finished signals (today's client)
  select.py       # detect runtime once; return the process-wide Executor
```

- **`Executor` protocol** — a single async method with the streaming callback
  shape the TUI already consumes (`runscreen.py`'s progress/finished callbacks).
  Callers depend on the protocol, not on D-Bus.
- **`DBusExecutor`** — today's `core/software/backend_client.py` dbus-next client,
  generalized: connect on the system bus, call the method, translate the
  backend's `BUSY_ERROR` into `BackendBusy`, forward `Progress`/`Finished` to
  `on_progress`/completion. This becomes the shared client for *all* modules
  instead of each re-implementing it.
- **`DirectExecutor`** — runs `runner.run(argv)` via `asyncio.create_subprocess_exec`,
  streaming each line straight to `on_progress`; raises `BackendBusy` from the
  same lock check. No bus, no signals, no polkit.
- **The backend service** keeps its polkit `CheckAuthorization` (via
  `get_sender()`) and audit logging, then delegates the actual work to
  `runner.run` — so the streaming/lock behaviour is identical to direct mode.

## What each module changes

Minimal and mechanical, because the module convention already isolates mutation
behind `backend_client`:

1. A module's `backend_client` stops constructing a bespoke D-Bus client and
   instead asks `exec.select` for the process-wide `Executor`, then calls
   `executor.run(argv, on_progress=…)`. Command builders (`commands.py`) are
   unchanged — the argv is identical on both paths.
2. `gest/ipc/interface.py` stays the single source of truth for bus names and
   polkit actions; a new `gest/ipc/runtime.py` (or `exec/select.py`) owns the
   euid/override detection so it lives in exactly one place.
3. Read/query paths are untouched — they already bypass the backend and use the
   in-process Portage/`lsblk` readers on both runtimes.

## Streaming, async, and the busy lock — parity on both paths

- **Async parity:** `DirectExecutor` presents the same async, callback-streaming
  interface as `DBusExecutor`, so `runscreen.py` and every module caller are
  agnostic to which is active.
- **Busy lock:** the cross-session package-management lock (v0.50.0, external
  emerge detection in `core/software/running.py`) moves into `runner.py` so it is
  enforced identically whether GeST is on the live CD or the installed system —
  and so it also guards the new destructive storage ops, not just emerge.
- **Audit logging** is a backend-only concern (it records *who* crossed the
  privilege boundary). In direct mode there is no boundary crossing to audit; the
  live-CD session is root throughout. Optionally `runner.py` can still log
  executed commands to the session log for a trail.

## Testing

- **Live-CD box:** boot the target machine from a Gentoo minimal CD/USB, launch
  GeST as root → `DirectExecutor` selected automatically, no polkit/D-Bus setup
  needed. This is the real test of the storage module.
- **Unit tests:** a `FakeExecutor` implementing the protocol records argv and
  replays canned progress lines — module logic is tested with no subprocess and
  no bus, matching the injected-`Runner` pattern the readers already use.
- **Installed system** regression: with a non-root euid, `DBusExecutor` is
  selected and the existing polkit-gated flow is exercised unchanged.

## Open questions

1. **Root on an installed system.** euid 0 there also selects direct mode
   (simpler, and polkit is still vacuous). Acceptable, or force D-Bus unless the
   override is set? Proposed: direct on any euid 0; document the override.
2. **Partial D-Bus availability.** If launched unprivileged but the backend
   isn't activatable, `DBusExecutor` should surface a clear "backend unavailable"
   error rather than hang — a connect timeout with an actionable message.
3. **Where `select` caches.** Detect once at startup and hold the `Executor` on
   the app context, vs. resolve per call. Proposed: once at startup; the runtime
   doesn't change mid-session.

## Non-goals

- Changing the installed-system security model. The polkit + D-Bus contract is
  untouched for unprivileged callers; this only adds an already-root fast path.
- Remote operation. GeST runs on the target machine itself (the live CD); there
  is no networked frontend/backend split.
- Reimplementing the backend's per-method polkit actions — they stay in
  `interface.py` and the installed `.policy` file.
