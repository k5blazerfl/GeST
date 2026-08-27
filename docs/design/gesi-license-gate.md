# GeSI License Gate — view + accept the agreements your choice entails

Status: **design** (proposed). Triggered by a baremetal dogfood failure, 2026-08-24.

## Motivation

The installer's license step is a single row on the **Base System** gate: a
three-rung policy picker (`BaseSystemStep._edit_license` → `_choice_modal`) that maps
to one `ACCEPT_LICENSE` string:

| Rung | `ACCEPT_LICENSE` | Covers |
|---|---|---|
| **Libre** | `@FREE` | free/open licenses only |
| **Redistributable** | `@BINARY-REDISTRIBUTABLE` | `@FREE` + binary firmware + the NVIDIA driver (`NVIDIA-r2`) — no click-throughs |
| **Full** | `@BINARY-REDISTRIBUTABLE @EULA` | everything, incl. click-through EULAs |

The rung is an **abstract label you pick blind.** Nothing shows you *what* you are
agreeing to, and nothing makes you *accept* it. That bit us hard: a user picked
**Libre** on an NVIDIA machine without realizing `@FREE` excludes both the firmware
their hardware needs and the NVIDIA driver they'd requested. The install ran for
**hours** and then died at the kernel step with an opaque masked-package wall —
`sys-kernel/genkernel[firmware]` (firmware USE is `+`default) pulls
`sys-kernel/linux-firmware`, which is license-masked under `@FREE`. The consequence
of the choice surfaced three phases and an hour later, as a Portage error, not at
the point of choosing.

A real OS installer makes you **read and accept** the licenses your install needs,
up front. GeSI should too.

## Principle

**Keep the three rungs.** They stay the way you choose a policy — do *not* replace
them with a computed license-closure browser. What we add is, at the license gate,
the ability to **see and explicitly accept the agreements the chosen rung entails**,
**pre-flight** (before the install runs) — not a runtime pop-up.

Scope boundary: this is the installer's own, pre-flight license handling. A
*runtime* install-time EULA prompt (some future third-party app on the booted
system) is a separate concern and out of scope here.

## The flow

License is its **own dedicated wizard gate** (`… → Base System → Licenses →
Your Account →`), not a row inside Base System. The **rung selection lives in this
gate** too, so it owns the whole consent flow end-to-end:

1. **Choose the rung** — the Libre / Redistributable / Full picker (moved here from
   Base System). Changing the rung re-computes the agreement list *and clears any
   prior per-agreement acceptance* — you re-consent to the new terms.
2. **Read + accept each agreement it entails** — one **row per *required*
   agreement** (the ones this hardware actually exercises), each showing its
   accepted state (`not yet` / `✓ accepted`). Opening a row is a **full-text
   viewer**: the agreement's real license text, scrollable, with the relevance line
   ("Required for THIS machine — …") and one **Accept** action carrying the explicit
   consent: **"By clicking Accept, you are agreeing to the terms above."** Accept
   soft-locks that agreement; Decline drops back to the rung picker.
3. **Continue is gated** — it stays refused until *every required agreement* is
   accepted (`licenses_accepted` is derived: all required names ⊆
   `accepted_licenses`). Libre entails nothing → the gate is just the rung + Continue.

Per-agreement, full-text, one honest Accept each — you can't advance without having
seen what you agreed to. Acceptance does not change what `ACCEPT_LICENSE` is written
to (that still comes from the rung); it makes the choice *conscious*.

## What each rung entails (the agreement list)

The rungs map to Gentoo license *groups*; the gate presents the **human-relevant
membership**, grouped, rather than dumping every atom:

- **Libre (`@FREE`)** — free/open software + documents only. The gate states plainly:
  *"Free licenses only. This excludes binary firmware and proprietary drivers — most
  hardware (Wi-Fi, NVIDIA GSP, the NVIDIA driver) will not work."* If the planned
  install needs firmware/NVIDIA (see Relevance), this is a **blocking warning** on
  this rung (see "Declining / incompatible choices").
- **Redistributable (`@BINARY-REDISTRIBUTABLE`)** — everything in Libre, **plus**
  the redistributable binary bucket: `linux-fw-redistributable` (Linux firmware),
  `NVIDIA-r2`/`NVIDIA-2025` (the NVIDIA driver), `intel-ucode`, and the per-vendor
  Wi-Fi/firmware licenses. No click-throughs.
- **Full (`@BINARY-REDISTRIBUTABLE @EULA`)** — everything in Redistributable, **plus**
  the click-through EULA pile (`NVIDIA-CUDA`, `google-chrome`, `Steam`, `RAR`, …). The
  gate notes that these are click-through licenses and that Full accepts them all in
  advance.

`@BINARY-REDISTRIBUTABLE` literally begins with `@FREE`, and Full is a strict superset
of Redistributable, so the list is presented **incrementally** — each rung shows what
it *adds* over the one below, which keeps it short and legible.

## Relevance — highlight what *this* install actually uses

The `@EULA` group alone is ~60 licenses; showing all of them is noise. The gate
computes the **subset the concrete plan will exercise** and surfaces those:

- **Firmware** (`linux-fw-redistributable` + the specific fw licenses): needed by
  virtually every real-hardware install — `genkernel[firmware]` pulls
  `linux-firmware`, and `InstallGpuDrivers` installs it unconditionally.
- **NVIDIA driver** (`NVIDIA-r2`): needed iff `plan.gpu.nvidia_proprietary` (the GPU
  auto-detect / the user opted into the proprietary stack).
- **A specific EULA** (e.g. `google-chrome`, `NVIDIA-CUDA`): needed iff a package in
  the selected feature set / role pulls it. For a stock HeDE desktop this is usually
  **empty** — which is worth telling the user (it means Full vs Redistributable makes
  no practical difference for them).

Entries the install will actually use are marked (e.g. `● required by this install`);
the rest of the rung's coverage is available but de-emphasised. This turns the abstract
rung into a concrete "here's what your machine needs, and your rung covers it (or
doesn't)" statement.

**Worked example — Intel/AMD box, Full rung.** `plan.gpu.nvidia_proprietary` is
`False` (no NVIDIA detected), so `driver_atoms` yields firmware only and
`package_license` accepts `linux-fw-redistributable` and *not* `NVIDIA-r2`. The gate
therefore marks **firmware** `● required by this install` and shows **NVIDIA driver**
de-emphasised as *"covered by Full, but your hardware doesn't use it."* The `@EULA`
pile is likewise unmarked unless a selected package pulls a specific EULA. So Full on
an AMD/Intel machine asks the user to accept exactly the firmware terms the install
exercises — the broad `@BINARY-REDISTRIBUTABLE @EULA` policy still *covers* NVIDIA-r2,
but nothing installs it, so it's never surfaced as something to read. This is the
"pull only the applicable agreements" behaviour: relevance is computed from the
detected plan, not from the rung's static coverage.

## Declining / incompatible choices

Because the accept step is explicit, the gate can catch the exact trap that motivated
this:

- If the chosen rung **does not cover** something the install requires (Libre on an
  NVIDIA/firmware machine), the gate shows a **blocker** at the license gate itself:
  *"Libre can't provide the firmware / NVIDIA driver this machine needs. Choose
  Redistributable or Full, or change your GPU/feature choices."* — right there, before
  a single package is emerged, instead of a masked-package wall at genkernel.
- A genuinely-libre install (no proprietary hardware wanted) is still valid: the gate
  lets Libre through, and the engine's stopgap (below) builds a firmware-free kernel.

## Data model

A pure function in `gest/core/install/` (testable, no I/O beyond reading license text):

```
license_agreements(plan) -> LicenseReview
```

where `LicenseReview` carries, per rung:

- `groups: list[str]` — the `ACCEPT_LICENSE` tokens the rung sets (from
  `LICENSE_POLICIES`, unchanged).
- `entails: list[Agreement]` — the human-facing agreement rows the rung *adds* over
  the rung below: `Agreement(name, group, one_line, required_by_this_install: bool,
  text_path)`.
- `blockers: list[str]` — messages when the rung can't satisfy a required agreement.

`required_by_this_install` is computed from the plan: firmware (always for real
hardware), `NVIDIA-r2` (from `plan.gpu.nvidia_proprietary`), and any `@EULA` license a
selected package's `LICENSE` pulls in (best-effort; can start with a small curated
map and grow). The rung → `ACCEPT_LICENSE` mapping (`license_accept_value`) is
**unchanged** — this function only *describes and gates*, it doesn't decide the value.

## UI

Reuse the wizard's existing widgets:

- The rung picker stays the current `_choice_modal` on the Base System gate.
- The **agreement list + accept** is a new modal (or an expansion of the license
  detail panel) listing `entails` with a `[View]` action per row and an **Accept**
  affirmation gating "Continue". `[View]` pushes a scrollable text modal reading
  `/var/db/repos/gentoo/licenses/<name>` (fall back to a short built-in summary if
  the file is absent, e.g. on a non-Gentoo dev host).
- The Review gate shows the accepted rung + a one-line "N agreements accepted"
  and re-blocks if the plan changed to need an agreement the rung doesn't cover.

## Code touch points

- `gest/core/install/plan.py` — `LICENSE_POLICIES` / `license_accept_value` (source of
  truth, unchanged); add `license_agreements()` + the `Agreement`/`LicenseReview`
  types here or a sibling module.
- `gest/tui/screens/install/wizard.py` — `BaseSystemStep`: the license row grows the
  view+accept modal; `validate()` returns a blocker when the rung can't cover a
  required agreement; a `licenses_accepted` flag on `InstallSelections`.
- `gest/tui/screens/install/review.py` — reflect accepted state; re-block on drift.
- `gest/core/install/registry.py` — `WriteMakeConf` still writes `ACCEPT_LICENSE` from
  the rung; no change to the value.
- License text source: `/var/db/repos/gentoo/licenses/` (present on the live medium).

## Stopgap (independent of this gate)

Land first, since it turns today's opaque failure into a clean one regardless of when
the full gate ships (tracked separately):

- **Warn** on the Libre rung that it excludes firmware + proprietary drivers.
- **Don't hard-crash under Libre**: when the policy is `libre`, set
  `sys-kernel/genkernel -firmware` (package.use) and skip the firmware/NVIDIA atoms in
  `InstallGpuDrivers`, so a genuinely-libre install *completes* firmware-free instead
  of dying at genkernel. (This restores the old `USE=-firmware` skip, conditionally.)

## Phasing

1. **Stopgap** — Libre warning + `genkernel[-firmware]`/atom-skip under Libre. ✅
2. **`license_agreements()`** + tests (pure; the agreement list + relevance + blockers). ✅
3. **View+accept** wired into `BaseSystemStep` (single list + one accept). ✅ (superseded)
4. **Own gate + per-agreement full-viewers** — promoted out of Base System to a
   dedicated `LicenseStep` (rung selection moved in); each required agreement is a
   full-text viewer with its own "By clicking Accept…" consent, soft-locked into
   `sel.accepted_licenses`; `licenses_accepted` derived; Continue gated on all
   required accepted. ✅ (`gest/tui/screens/install/wizard.py`,
   `tests/test_wizard_license_gate.py`)
5. **EULA relevance map** grown as packages that pull `@EULA` licenses are added to
   the feature/role sets. (ongoing)
6. **Qt parity** — the same gate model in the Control Center / future Qt wizard
   (`licensing.py` is already frontend-agnostic). (planned)

## Non-goals

- Replacing the three rungs with a computed license browser (explicitly rejected).
- A runtime, post-boot EULA prompt for third-party apps (separate concern).
- Editing `ACCEPT_LICENSE` by hand in the gate (the rung remains the single lever).
