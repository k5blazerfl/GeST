# Spike: Gangway Phase-5b — FreeRDP RAIL feasibility

*Status: spike (host-validation protocol + running findings) · Gates: Gangway Phase-5b engine (items A/B/E of [`gangway-phase5-scope.md`](gangway-phase5-scope.md) §2) · Depends on: [Flotilla guest-enablement](flotilla.md) §5 (a provisioned Windows vessel — `flotilla launch --provision --remote-app`), a real X server (Xwayland), a pinned FreeRDP · Never CI — matches `gest/core/rdp/__init__.py`*

> This is the **1–2 day host-validation spike** the Phase-5 scope demands before
> any RAIL *engine* code is written ([`gangway-phase5-scope.md`](gangway-phase5-scope.md)
> §3, "Phase 5b — the engine (gated on a spike)"). It answers one question with a
> reproducible measurement: **does `xfreerdp3 /app:` under Xwayland give us one
> real, stably-identified X11 toplevel per remote Windows app?** GREEN unlocks the
> engine pivot; RED means we hold and say so.

## 0. The question, precisely

The seamless "a Windows app that lives here" experience needs three things true at
once ([`gangway-phase5-scope.md`](gangway-phase5-scope.md) §1a). This spike proves
or disproves **exactly the first two**, which are the risky, upstream-dependent
ones:

1. **N toplevels, not one surface.** The X11 `xfreerdp` client must emit one real
   X11 toplevel *per* remote RemoteApp window (SDL/Wayland clients render into a
   single surface and cannot — hence the client swap). ✔ = a new window id appears
   in the root `_NET_CLIENT_LIST` for each launched app.
2. **A usable, stable `WM_CLASS`.** Each toplevel must carry a non-empty `WM_CLASS`
   that is **the same every launch**, because that class is the identity key the
   Customs spine matches on (`gest/core/customs/identity.py`, X11 branch) — a class
   that churns per launch can't be mapped to a `.desktop`.
3. **Not blocked by the live regression.** [FreeRDP #12391](https://github.com/FreeRDP/FreeRDP/issues/12391)
   (RemoteApp windows silently missing on `xfreerdp3`) must not bite on the pinned
   version — and, per its sibling [#12397](https://github.com/FreeRDP/FreeRDP/issues/12397)
   ("works the first few runs, then fails"), it must hold across **repeated**
   launches, not just once.

(The third leg — real taskbar identity — is the **already-shipped** phase-5a spine,
draft PR #194. This spike does not re-test it.)

## 1. Findings so far — the pin (2026-08-21)

The spike's central unknown when the scope doc was written ("even the mature X11
path is currently fragile") now has an answer from upstream:

| Ref | What | State |
|---|---|---|
| [#12391](https://github.com/FreeRDP/FreeRDP/issues/12391) | RemoteApp windows don't appear on `xfreerdp3` (regressed 3.22→3.23) | **CLOSED**, milestone **3.24.0** |
| [PR #12392](https://github.com/FreeRDP/FreeRDP/pull/12392) | `[client,x11] improve rails window locking` — the fix | **MERGED** 2026-02-27 (`56d4139`) |
| [#12397](https://github.com/FreeRDP/FreeRDP/issues/12397) | `/app:program` crash/freeze on login (3.23.0), the flakiness sibling | **CLOSED** 2026-02-28 |

**⇒ Pin FreeRDP ≥ 3.24.0.** 3.23.0 is the known-broken release; the fix is a RAIL
*window-locking* change, so the repeated-launch check in this protocol is not
paranoia — it targets the exact failure mode #12397 described. The harness warns if
the client predates 3.24.0.

> These are desk findings from the issue tracker. They set the version to test;
> they do **not** substitute for the measurement. The gate is still the live run
> below on our stack (Gentoo `net-misc/freerdp[X]` under an Xwayland HeDE session).

## 2. Prerequisites

- A **provisioned Windows vessel**, RemoteApp-ready, from the guest-enablement work:
  ```sh
  flotilla launch --os windows --iso <win.iso> \
      --provision --remote-app 'Notepad=C:\Windows\notepad.exe' \
      --remote-app 'Paint=C:\Windows\System32\mspaint.exe' --username flotilla
  ```
  Install Windows (the `autounattend.xml` injects virtio + creates the account +
  runs `firstboot.ps1`), then confirm it is reachable: `flotilla address <vessel>`.
  The RemoteApp **aliases** to pass `--app` are the `RemoteAppProgram.key`s
  (sanitized exe basenames: `notepad`, `mspaint`).
- **FreeRDP ≥ 3.24.0 with the X11 client**: `emerge net-misc/freerdp` with the `X`
  USE flag; confirm `xfreerdp3 --version`.
- An **X server**: a HeDE/Wayland session exports Xwayland (`$DISPLAY` set), or a
  plain X11 session. `xfreerdp3` is an X11 client; RAIL toplevels land on that X
  server. `x11-apps/xprop` present.
- The guest password available as `GANGWAY_SPIKE_PASSWORD` (throwaway spike cred —
  the real one lives in the Keychain via Gangway `set-password`; never put it on a
  command line).

## 3. Run it

```sh
GANGWAY_SPIKE_PASSWORD='<guest pw>' \
scripts/host-validation/rail-spike.py \
    --host "$(flotilla address winvm)" --user flotilla \
    --app notepad --app mspaint --runs 5
```

What the harness does, per app, per run: snapshot the root `_NET_CLIENT_LIST`,
launch `xfreerdp3 /v:… /u:… /app:program:<alias> /sec:nla /cert:tofu /from-stdin`,
wait (≤`--timeout`) for a **new** window id to appear, let it settle, read its
`WM_CLASS` with `xprop`, tear the session down, repeat. Then it prints a per-app
PASS/FAIL and an overall **GREEN/RED** verdict (exit 0 = GREEN).

- `--dry-run` prints the exact probe argv without a VM (sanity-check the command).
- The pure logic (argv build, `xprop` parsing, verdict math) is unit-tested in
  `tests/test_rail_spike.py`; only the live launch/X-query edge is host-only.

**Manual equivalent** (if debugging the harness): `xprop -root _NET_CLIENT_LIST`
before and after a hand-run `xfreerdp3 … /app:program:notepad`, diff the ids, then
`xprop -id <new-id> WM_CLASS`.

## 4. Results — fill in on the host

| Client / version | App | Runs | Appeared | `WM_CLASS` (stable?) | Verdict |
|---|---|---|---|---|---|
| `xfreerdp3` 3.__.__ | notepad | 5 | _/5 | `______` (Y/N) | PASS/FAIL |
| `xfreerdp3` 3.__.__ | mspaint | 5 | _/5 | `______` (Y/N) | PASS/FAIL |

Record: FreeRDP version, whether the `WM_CLASS` instance/class pair is derived from
the app or is a generic `FreeRDP`/`xfreerdp` (affects item D's per-app `.desktop`
`StartupWMClass`), and any crash/hang (the #12397 signature).

## 5. Decision gate

- **GREEN** (every app: distinct toplevel every run, one stable non-empty
  `WM_CLASS`) → build the Phase-5b engine, in scope order:
  - **B (small):** RemoteApp fields on `RdpProfile` + `.rdp` round-trip + CLI args
    — `gest/core/rdp/model.py`, `rdpfile.py`, `gest/tui/gangway/cli.py`.
  - **A (medium):** the client/`/app:` branch in `gest/core/rdp/commands.py` (swap
    `sdl-freerdp` → `xfreerdp3` for RAIL mode; the argv this harness proved).
  - **D (small-medium):** per-app `.desktop` synthesis in `gest/core/rdp/launcher.py`,
    `StartupWMClass` = the class this spike recorded (feeds the 5a spine, PR #194).
  - **E (medium):** RemoteApp icon acquisition over the RAIL channel.
- **RED** (missing/again-vanishing windows, or a churning/blank `WM_CLASS`) →
  **hold.** Phase-5b stays upstream-gated; full-desktop Gangway + the 5a identity
  spine remain the shipped ceiling, exactly as the interop honesty note hedges.
  Re-run against the next FreeRDP release; record which version and which leg failed.

## 6. Non-goals (this spike only)

- Not the engine. No edits to `commands.py`/`model.py`/`launcher.py` here — the
  harness is standalone under `scripts/` and not shipped in the wheel.
- Not RAIL polish (icon blobs, window grouping, multi-monitor) — those are items
  D/E, downstream of a GREEN.
- Not VM lifecycle — the vessel must already be up (Flotilla's job, not Gangway's).

---

*Sources: [FreeRDP #12391](https://github.com/FreeRDP/FreeRDP/issues/12391) · [PR #12392](https://github.com/FreeRDP/FreeRDP/pull/12392) · [#12397](https://github.com/FreeRDP/FreeRDP/issues/12397) · [Gangway Phase-5 scope](gangway-phase5-scope.md) · [Flotilla design](flotilla.md)*
