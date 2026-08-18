# ADR: Drydock ↔ Lutris interop — own recipe format, import-only bridge

*Status: decided (2026-08-17) · Scope: how Drydock relates to Lutris's install-script ecosystem — specifically the reserved "install-script notion" from [drydock.md:26](drydock.md) · Decision owners: HeDE/Drydock · Supersedes nothing; refines the open question at [drydock.md:213-215](drydock.md) ("Native Drydock vs. wrap Bottles")*

> This ADR closes one deliberately-parked decision in the Drydock design: what the
> "(later) install-script notion" ([drydock.md:26,171](drydock.md)) actually is, and
> how much of Lutris we pull to get it. It does **not** re-open Drydock's thesis —
> umu-first, Customs-native, Gentoo-native ([drydock.md:29-36](drydock.md)) all stand.

## Context

Lutris ([github.com/lutris/lutris](https://github.com/lutris/lutris), GPL-3.0) has
solved, at scale, the thing Drydock has only reserved a slot for: a **declarative
per-app install recipe** (its `ScriptInterpreter` reads YAML/JSON of files + a
sequence of actions) *and* a large community library of those recipes on lutris.net.
Drydock today defines no recipe format at all — the bottle model and prereq table are
persistent config, not an install script ([drydock.md:76-90,123-137](drydock.md)).

The question raised: **"can we pull from Lutris, but keep Drydock a unique Helm
subsystem?"** Two sub-questions — legal, and architectural.

### Legal footing

- GeST is **GPL-2.0-or-later** (`pyproject.toml`); Lutris is **GPL-3.0**. The
  "or-later" clause makes incorporating Lutris code license-compatible (the combined
  work distributes under GPL-3.0).
- Caveat: any file that *vendors* GPL-3.0 code becomes effectively **GPL-3.0-only**
  going forward — a one-way ratchet away from the "v2 option."
- **Prerequisite gap:** the repo has no root `LICENSE`/`COPYING` file (only the
  `pyproject.toml` field). Add the GPL text file **before** vendoring any third-party
  GPL code. Tracked as a follow-up in this ADR.

### The distinctiveness constraint

The design docs already forbid the wholesale path: *"No Lutris/Bottles replacement —
we integrate/adopt, not compete, and stay the thin native path"* ([drydock.md:194](drydock.md)),
and Defers list "reimplementing Lutris/Bottles wholesale"
([hede-windows-interop.md:3](hede-windows-interop.md)). Drydock's uniqueness rests on two
things Lutris structurally lacks: **Customs** integration (taskbar identity/icon/MIME
spine) and **Gentoo-native prerequisites** (USE/multilib/emerge via GeST's polkit'd
software core).

## Decision

**Drydock defines its own recipe format as the single source of truth, and ships a
one-way *importer* that converts Lutris install scripts into Drydock recipes. Drydock
does not vendor Lutris's interpreter, runner abstraction, runtime, or client.**

Concretely:

1. **Own format.** A native Drydock recipe (`helm.recipe`, YAML) is authored and
   executed by Drydock's own interpreter. It is the canonical artifact; nothing in the
   run path depends on Lutris being installed.
2. **Import bridge.** `drydock import-lutris <script.yml|slug>` parses a Lutris script
   and emits a Drydock recipe, mapping the subset of actions that have a native
   equivalent (table below) and **flagging** the rest as unsupported rather than
   silently dropping them. This is the mechanical form of the "optional Lutris/Bottles
   prefix adoption" already promised at [drydock.md:172](drydock.md).
3. **No runtime coupling.** Import is a build-time transform. A converted recipe runs
   through Drydock's existing umu/wine launch pipeline ([launch.py](../../gest/core/drydock/launch.py))
   and Customs export — never through Lutris code.
4. **Design reference, not code copy.** Lutris's action vocabulary informs Drydock's
   recipe schema (we learn the *shape* of the problem from mature prior art); we do not
   copy `lutris/installer/`. The one place code-level borrowing is sanctioned is
   small, isolated, mechanical reference data — **winetricks verb sets and DXVK/VKD3D
   setup sequences** — kept behind Drydock's own interfaces and attributed.

### Why not the alternatives

- **Vendor Lutris's interpreter** — rejected. Drags in Lutris's runner/runtime
  assumptions, couples Drydock to upstream internals, and is exactly the "reimplement
  Lutris" trap the docs forbid.
- **Own format, ignore Lutris entirely** — rejected. Forfeits the thousands of
  community install scripts; reinvents *content*, not just code.
- **Import-only bridge (chosen)** — gets the content library as *input* while keeping a
  distinct engine, schema, and integration surface. Interop, not fork.

## The recipe schema (sketch — to be finalized in a follow-up)

A Drydock recipe is the install-time complement to the persistent bottle model. Rough
shape, deliberately thinner than Lutris (no runner zoo, no emulator matrix — umu/wine
only):

```yaml
recipe: 1                     # schema version
app: { name, id, categories }
bottle: { runner, arch, verbs, dxvk, vkd3d }   # seeds the Bottle model
files:                        # url + filename, or user-provided:"reason"
  - { id, url, filename }
steps:                        # ordered Drydock actions (native verb set below)
  - extract: { src, dest }
  - winetricks: [ ... ]
  - wineexec: { exe, args }
programs:                     # what Customs exports as launchers
  - { name, exe, args, graphics: { ... } }
prereqs: auto                 # defer to prereq.py's atom+USE table
```

## Lutris action → Drydock mapping

The importer's coverage table. "Native" = a Drydock recipe verb exists/planned;
"Flag" = emit a warning + a `# TODO(manual)` marker in the output, don't fake it.

| Lutris directive | Drydock handling | Notes |
|---|---|---|
| `game:` (exe/args/workdir) | **Native** → `programs[]` entry | The Customs-exported launcher |
| `files:` (url/filename, `N/A:` user-provided) | **Native** → `files[]` | `N/A:` → user-provided prompt |
| `installer: extract` | **Native** → `extract` | zip/7z/tar/rar; innoextract for GOG |
| `installer: move` / `copy` / `merge` | **Native** → `move`/`copy` | |
| `installer: chmodx` | **Native** → `chmodx` | |
| `installer: execute` | **Native** → `execute` | host command w/ env |
| `installer: write_file`/`write_config`/`write_json` | **Native** → same verbs | INI/JSON writers |
| `task: create_prefix` | **Native** → bottle create (host op, [bottles.py](../../gest/core/drydock/bottles.py) — currently unbuilt) | |
| `task: wineexec` | **Native** → `wineexec` | |
| `task: winetricks` | **Native** → `winetricks` | maps to bottle `verbs` |
| `task: set_regedit` / `set_regedit_file` / `delete_registry_key` | **Native** → `regedit` verbs | |
| `task: winekill` / `eject_disc` | **Native** → same | |
| `system:` (env, cpu/audio/keyboard) | **Partial** → env into bottle `env`; the rest **Flag** | HeDE session owns audio/input, not the recipe |
| `wine:` runner config (DLL overrides, version, DXVK) | **Partial** → DXVK/version into bottle; DLL overrides **Native** | |
| `input_menu` / `insert-disc` | **Flag** | interactive; needs a Drydock UI story (deferred to Qt module) |
| `$STEAM:appid` file refs, `gogdl_setup` | **Flag** | store-integration out of scope for v1 import |
| `dosexec` / DOSBox, RetroArch, ScummVM, browser runners | **Reject** | non-Wine runners — explicitly outside Drydock's umu/wine scope |
| Lutris variables (`$GAMEDIR`, `$WINEBIN`, …) | **Native** → Drydock's own var set | 1:1 where meaningful; store-specific ones Flag |

Coverage is intentionally a **subset**: the importer converts the Wine/Proton install
path faithfully and is honest (via Flag/Reject) about everything that belongs to
Lutris's multi-runner world, which Drydock is not.

## Consequences

- **Positive:** the lutris.net script corpus becomes a seed source; Drydock keeps a
  thin, native, greppable recipe format; the umu/wine/Customs/Gentoo pipeline is
  untouched and remains the differentiator. No GPL-3.0 ratchet is triggered (import is
  a data transform, not vendored code).
- **Negative / cost:** a real interpreter + importer is net-new work (Drydock's host
  operations in `bottles.py` are still design-only, so `create_prefix`/`wineexec` land
  *with* this, not before it); the mapping table needs maintenance as Lutris evolves;
  Flag'd directives mean some imports need manual finishing.
- **Non-goals reaffirmed:** no Lutris runtime/runner/GTK code, no non-Wine runners, no
  store integrations in v1, anti-cheat still out ([drydock.md:194](drydock.md)).

## Follow-ups

1. Add a root `LICENSE`/`COPYING` (GPL-2.0-or-later text) — prerequisite for any
   third-party GPL borrowing.
2. Finalize the `helm.recipe` schema (field-level) and add it to `drydock.md` §-body.
3. Build Drydock's host operations in `bottles.py` (prefix create, winetricks, DXVK) —
   the interpreter's execution backend; scoped with interop phase 4.
4. Prototype `import-lutris` against 3–5 real lutris.net scripts to validate the
   mapping table before locking the schema.

---

*Sources: [Lutris installer script reference](https://github.com/lutris/lutris/blob/master/docs/installers.rst) · [Lutris architecture (DeepWiki)](https://deepwiki.com/lutris/lutris) · [Lutris on Gentoo Wiki](https://wiki.gentoo.org/wiki/Lutris)*
