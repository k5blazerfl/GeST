# Design: Hiedi as a separable, opt-in layer over HeDE

*Status: DECIDED (2026-08-19) · Scope: how Hiedi — HeDE's local-first AI
assistant — is packaged, released, and integrated so it stays **optional** and
does not weigh on the base desktop · Depends on: HeDE's shell exposing a plug-in /
discovery seam; the Qt frontend + Keychain (Hiedi reuses these) · Defers: the
assistant's own product design (see [Hiedi agent vision]) — this doc is only about
the **boundary***

> **Hiedi** is HeDE's first-class, local-first AI project-planning assistant (the
> companion German-Shepherd mascot; Ollama by default, optional Claude). It is
> **bleeding-edge**: it wants a GPU / a local LLM runtime, and most people don't
> have the hardware — or the need. So it must never be something a plain HeDE
> desktop is forced to carry.

## Current state — the repo/package split already shipped

The **codebase split is done** (Hiedi v0.1.0, 2026-08-15): Hiedi lives in its own
public repo `k5blazerfl/Hiedi`, is packaged in Amphitheater as a **standalone
`gui-apps/hiedi`** (its own `hiedid` daemon on `org.hede.hiedi`, consuming the
Keychain over the Secret Service **bus** — it does *not* import gest), and is
hand-maintained in Amphitheater (not on GeST's Overlay-sync CI). So "pull Hiedi
into its own codebase" is already true.

What this doc **decides** is the remaining, load-bearing part: the **dependency
boundary** — that HeDE never *depends* on Hiedi, and how Hiedi attaches without
weighing on the base desktop.

## The problem

If Hiedi lives *inside* `gui-apps/hede`, then every HeDE install — and every GeSI
ISO / on-disk install — inherits its dependency closure: Ollama, a Python ML
stack, model runtimes, GPU userspace. That is:

- **Weight the base desktop can't afford.** The installer's default desktop
  closure is already ~200 packages; the GeSI ISO already brushes the 2 GiB
  release-asset limit. The AI stack would blow past both — for a feature most
  users won't run. (See [desktop-provisioning].)
- **Release-cadence coupling.** Hiedi is fast-moving and experimental; HeDE is the
  stable shell people log into every day. Tying their releases together drags one
  or the other.
- **Hardware-gating smeared across the desktop.** GPU/LLM constraints belong in
  one package's ebuild, not spread through the shell.

## Decision

**Hiedi stays its own package/codebase (already true), and — the load-bearing
rule — HeDE does not depend on it.**

1. **Package boundary — `gui-apps/hiedi`, standalone (done).** Its own ebuild in
   Amphitheater with its **own** RDEPEND for the AI stack (Ollama/model runtime),
   `~arch`. **The rule to hold:** `gui-apps/hede` must **never** RDEPEND on it. The
   only permitted link is an **optional `hede[hiedi]` USE flag, default off**, that
   pulls `gui-apps/hiedi` for users who explicitly want it. A base install — and
   the installer's default desktop — never emerges the AI stack.

2. **Repo boundary — its own repo + cadence (done).** Hiedi lives in
   `k5blazerfl/Hiedi` and releases on its **own cadence**, independent of HeDE.
   (Unlike `hede/`, it's hand-maintained in Amphitheater rather than on the
   Overlay-sync CI — a Hiedi tidelock tags the Hiedi repo then updates the
   Amphitheater ebuild by hand.)

3. **Integration — loose, one-directional, discovery-based.** This is the crux and
   the part still to build.
   - HeDE ships an **inert "Hiedi slot"**: a panel button / dock entry / menu
     category that is simply **absent (or disabled) when Hiedi isn't installed**.
   - Hiedi **registers into that slot** via discovery — a shipped `.desktop`
     entry (Customs) and/or a small well-known D-Bus name — **not** by HeDE
     importing Hiedi code.
   - **HeDE code never references Hiedi.** Uninstalling Hiedi leaves HeDE
     byte-for-byte unchanged; installing it lights the slot up. That is the entire
     contract, and keeping it this thin is what keeps HeDE maintainable.
   - **Start at the loosest coupling** (a discovered `.desktop` app + a panel slot)
     and only tighten toward deeper shell embedding if a real need appears.

4. **Shared dependencies flow one way.** Hiedi reuses the **Qt frontend** and the
   **Keychain** ([Hiedi agent vision]); those never reuse Hiedi. Standard layering
   — the assistant sits on top of the platform, not woven into it.

## What lives where

| Concern | Home |
|---|---|
| The shell, session, panel, greeter | `gui-apps/hede` (base) |
| The **Hiedi slot** (inert discovery point) | `gui-apps/hede` — tiny, dependency-free |
| The assistant, LLM plumbing, Voyage/Chart/Logbook model, mascot | `gui-apps/hiedi` (opt-in) |
| Ollama / model runtime / GPU userspace | Hiedi's RDEPEND only |
| Qt frontend, Keychain | shared platform; depended on by Hiedi |

## Consequences

- **HeDE stays lean and stable**; its releases don't gate on the AI feature.
- **Hiedi is genuinely opt-in** — `emerge gui-apps/hiedi` (or `hede[hiedi]`) only
  if you have the GPU and want it. No hidden default that surprises light installs.
- **The installer's default desktop stays small** — protecting install speed and
  the ISO size limit.
- **One clean seam to maintain**: the discovery contract. Everything else is
  packaging that already has a proven precedent (the HeDE mirror).

## Non-goals / deferred

- The assistant's product design (nautical model, local-vs-cloud policy, art
  pipeline) — unchanged; owned by [Hiedi agent vision] and `~/hiedi-lab`.
- Deep in-shell embedding (Hiedi drawing inside the panel/compositor). Possible
  later, but only after the loose `.desktop`/D-Bus contract proves insufficient —
  and it must never require HeDE to depend on Hiedi.

[Hiedi agent vision]: (memory) hiedi-agent-vision
[HeDE mirrors to own repo]: (memory) hede-mirrors-to-own-repo
[desktop-provisioning]: ./desktop-provisioning.md
[desktop-environment]: ./desktop-environment.md
