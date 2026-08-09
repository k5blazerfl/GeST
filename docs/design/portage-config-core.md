# Design: a unified Portage configuration core

*Status: proposal · Target: `gest/core/portage/` · Author-of-record: design doc, not yet implemented*

## Why

The Gentoo Handbook's [Base installation page][handbook] is, read closely, a tour
of **one directory**: nearly every step writes a file under `/etc/portage/`.
`make.conf` compile flags and `USE`; the ebuild repository in `repos.conf/`;
binary hosts in `binrepos.conf/`; per-package pins in `package.use/`,
`package.accept_keywords/`, `package.mask/`, `package.license/`;
`CPU_FLAGS_X86` and `VIDEO_CARDS` drop-ins. That directory *is* the machine's
identity, and — unlike partitioning or the stage3 unpack — every knob on it is
re-touched for the life of the system. It is exactly the surface a YaST
equivalent exists to manage.

GeST already edits several of these, but through **three parallel, unaware
implementations**:

| Surface | Parser today | Write RPC today | Owning module |
|---|---|---|---|
| `make.conf` | shell-assignment, `makeconf/reader.py` | `set_makeconf(name, value)` | `core/makeconf` |
| `package.use/gest` | line-token, `software/useflags.py` | `set_package_use(atom, line)` | `core/software` |
| `package.{accept_keywords,mask,unmask}/gest` | line-token, `software/pkgconfig.py` | `set_package_config(kind, atom, line)` | `core/software` |
| `repos.conf/*.conf` | INI, `repos/reader.py` | `eselect repository …` argv | `core/repos` |

Three grammars, three write mechanisms, one overloaded polkit action
(`software.modify-config`), and each writer re-implements its own atomic
`mkstemp`+`os.replace`. Two whole surfaces from the handbook —
`binrepos.conf/` (binhost) and `package.license/` — have **no** module at all,
and the auto-detectable `CPU_FLAGS_X86` / `VIDEO_CARDS` drop-ins aren't wired.

Adding the missing surfaces the current way means a fourth and fifth copy of the
same pattern. This proposes folding all of it onto one core layer.

## Goals

1. **One home** for reading, modelling, and rendering everything under
   `/etc/portage/`: `gest/core/portage/`.
2. **One privileged write contract** — a single generic backend RPC and polkit
   action — replacing the three special-purpose ones, with atomic writes and
   validation in exactly one place.
3. **Fragment ownership**: GeST only ever writes files it owns; it never
   rewrites a hand-edited `make.conf` wholesale or clobbers a user's
   `package.use/` file. (The current `makeconf` renderer is format-preserving,
   which is good; the design keeps that property and extends the same courtesy
   everywhere.)
4. **Non-breaking migration**: existing modules (`software`, `makeconf`,
   `repos`) keep working while they move onto the core one at a time.
5. **Additive**: binhost, per-package licenses, and hardware-derived drop-ins
   become small modules on top of the core, not new subsystems.

Non-goals: reimplementing Portage's own config resolution (we read effective
state from the `portage` Python API as today), and touching the systemd/OpenRC
split (out of scope per the roadmap).

## The shape of the problem: three grammars, one directory

Everything under `/etc/portage/` is one of three file grammars. The core needs
exactly three codecs, and no more:

1. **Shell assignments** — `make.conf`. `NAME="value"` with line continuations
   and `${VAR}` refs. Already handled well by `makeconf/reader.py` (`variables`,
   `render`, `valid_name`, `valid_value`) — this becomes `portage/codec/shell.py`
   verbatim.
2. **INI sections** — `repos.conf/*.conf`, `binrepos.conf/*.conf`. `[section]`
   + `key = value`, with a `[DEFAULT]` block. Already handled by
   `repos/reader.py` (`parse_repos_conf`); generalise it (it currently hardcodes
   `main-repo` handling) into `portage/codec/ini.py`.
3. **Atom-keyed lines** — every `package.*` file: `cat/pkg tokens…`, one atom
   per line, comment lines preserved. Handled *twice* today
   (`software/useflags.render_file` and the backend's
   `_write_package_config`); unify as `portage/codec/atomfile.py`, which both
   the reader (preview) and the backend (write) call so they can never diverge.

## Layering

The existing per-module convention (`model` / `reader` / `commands` /
`backend_client`) stays. The core just adds a shared sub-package the modules
lean on:

```
gest/core/portage/
  paths.py        # single source of truth for /etc/portage/* locations,
                  #   honouring portage.settings["PORTAGE_CONFIGROOT"]
  codec/
    shell.py      # make.conf assignments  (from makeconf/reader.py)
    ini.py        # repos.conf / binrepos.conf sections (from repos/reader.py)
    atomfile.py   # package.* atom-keyed lines (from useflags + pkgconfig + backend)
  fragments.py    # the ownership model: which file GeST owns per surface
  model.py        # Var, Section, AtomLine dataclasses (slots)
  reader.py       # unprivileged effective-state reads (thin over codecs + portage API)
  write.py        # ConfigWrite value type: (path, new_full_text) the backend applies
```

Pure codecs (no I/O) → reader (unprivileged, injectable `Runner`/path for tests,
matching the `datetime/reader.py` pattern) → a single `write.py` value type that
describes *what file should contain what text*, which the backend applies.

### The write value type

Rather than N verb-specific RPCs, the core produces a `ConfigWrite`:

```python
@dataclass(slots=True, frozen=True)
class ConfigWrite:
    path: str          # absolute, must resolve under /etc/portage/ (backend re-checks)
    text: str          # full new file contents ("" means delete the file)
    mode: int = 0o644
```

The frontend renders the *preview* (old vs new text — the `useflags.preview`
pattern, already how the Software UI shows pending changes), the user accepts,
and the core hands the backend one or more `ConfigWrite`s.

## The unified backend contract

Replace `set_makeconf`, `set_package_config`, `set_package_use` with one method
on a new `org.gentoo.gest.Portage` interface:

```
WriteConfig(a(sst)) -> b      # array of (path, text, mode); applied atomically-ish
```

Rules the backend enforces (this is where safety lives, since the frontend is
untrusted):

- **Path allow-listing**: each `path` must, after `realpath`, sit under
  `/etc/portage/` and match a known surface pattern (`make.conf`,
  `repos.conf/*.conf`, `binrepos.conf/*.conf`, `package.*/…`). Reject anything
  else — no writing `/etc/portage/../../shadow`.
- **Per-surface content validation** re-run server-side using the same codec:
  a `make.conf` write must re-parse as valid assignments; an atomfile write's
  atoms must be valid `cat/pkg`. The frontend validating is a convenience; the
  backend validating is the contract.
- **Atomic per file**: the existing `_atomic_write_file` (`mkstemp` in the
  target dir → `chmod` → `os.replace`), lifted to a shared helper. `text == ""`
  → unlink. A multi-file `WriteConfig` writes each atomically; full
  cross-file transactionality (all-or-nothing) is noted as an open question
  below — per-file atomicity matches today's behaviour and is enough for v1.
- **One polkit action**: `org.gentoo.gest.portage.configure`, replacing the
  overloaded `software.modify-config`. (`repos` currently borrows
  `modify-config`; it moves onto this cleanly.)

`interface.py` gains `PORTAGE_PATH`, `PORTAGE_IFACE`, `PORTAGE_POLKIT`, and the
matching entries land in the installed `org.gentoo.gest.policy` /
`.conf` data files — the whole reason those names live in one module.

## Fragment ownership — the core's most important rule

Two write disciplines, chosen per surface:

- **Drop-in files GeST fully owns.** For the `package.*` surfaces GeST already
  writes a single `gest` file (`package.use/gest`, `package.mask/gest`, …).
  Keep that: GeST owns `…/gest` end to end and never touches sibling files a
  user or another tool created. `binrepos.conf/gest.conf` and
  `package.license/gest` follow the same rule.
- **Numbered drop-ins for hardware-derived config.** The handbook writes
  `CPU_FLAGS_X86` to `package.use/00cpu-flags` and `VIDEO_CARDS` to
  `package.use/00video_cards`. GeST should own *its own* numbered fragment
  (e.g. `package.use/50gest-cpuflags`) rather than the handbook's `00…` name,
  so re-running detection is idempotent and never fights a file the user hand-made.
  `log()` when detection would change the fragment.
- **`make.conf` is the one file GeST edits in place** because it's
  conventionally a single hand-owned file with no `.d` fragment mechanism. The
  format-preserving `shell.render` (replace the effective assignment in place,
  else append; keep every comment and blank line) is exactly right and must not
  regress. Anything that *can* be a drop-in (USE pins, licenses, cpuflags)
  should be, leaving `make.conf` edits to genuinely global scalars
  (`MAKEOPTS`, `ACCEPT_LICENSE`, `FEATURES`, `GENTOO_MIRRORS`, `VIDEO_CARDS`).

## Migration (non-breaking, one module at a time)

1. **Land the core** with codecs moved (not rewritten) from their current homes,
   plus the new `portage/write.py` and `paths.py`. Add `WriteConfig` +
   `portage.configure` to the backend and IPC, alongside the old RPCs.
2. **Repoint `makeconf`** to build a `ConfigWrite` via `shell.render` and call
   `WriteConfig`; delete `set_makeconf`.
3. **Repoint `software`** USE/keyword/mask writers onto `atomfile` +
   `WriteConfig`; delete `set_package_use` / `set_package_config`. The backend's
   `_write_package_config` logic *becomes* `atomfile.upsert`, called from both
   sides.
4. **Repoint `repos`** reads onto `codec/ini`. Its *writes* stay on `eselect
   repository` (that's the correct tool and adds the repo to `repos.conf` for
   us) — the core just gives it shared parsing. This shows the design doesn't
   force everything through `WriteConfig`; `eselect`/`emerge`-shaped surfaces
   keep their proper backends.
5. **Remove** the three superseded RPCs and the `modify-config` action once no
   caller remains. Tests move alongside (`tests/test_makeconf*`,
   `test_useflags*`, `test_repos*` already exist — they get a
   `test_portage_core.py` sibling for the codecs).

Each step is independently shippable and testable.

## What the core unlocks (the handbook gaps)

Small modules, each a reader + a `ConfigWrite` builder, no new plumbing:

- **Binhost** (`core/portage` + a `binhost` view): read/write
  `binrepos.conf/gest.conf` (INI codec) — `sync-uri`, `priority`,
  `verify-signature`, the x86-64-v3 tier stacking; plus a `getbinpkg` /
  `binpkg-request-signature` toggle in `FEATURES` (shell codec) and a note to
  run `getuto`. Directly the handbook's "Optional: binary package host" step.
- **Per-package licenses**: `package.license/gest` (atomfile codec) — the
  `app-arch/unrar unRAR` style acceptance, complementing the global
  `ACCEPT_LICENSE` already editable via `makeconf`.
- **CPU flags / video cards**: run `cpuid2cpuflags` (read side) and detect the
  GPU vendor, offer to write `package.use/50gest-cpuflags` and a
  `VIDEO_CARDS` line — turning two manual handbook steps into one detected,
  reviewable diff.
- **Mirror selection**: benchmark mirrors and write `GENTOO_MIRRORS` in
  `make.conf` (shell codec), the `mirrorselect -o >> make.conf` step, but
  reviewable.

## Testing

- **Codec round-trips** (pure, no I/O): parse → render → re-parse is stable;
  format preservation for `shell` (comments/blanks/continuations survive); atom
  upsert only touches the target atom's line; INI `[DEFAULT]` handling.
- **Reader** with injected paths/`Runner` (existing pattern) over fixture
  `/etc/portage/` trees.
- **Backend contract**: path allow-list rejects traversal; server-side
  re-validation rejects malformed content; atomic replace leaves no partial file
  on write failure (the current `_write_package_config` already has the
  temp-cleanup path to assert against).

## Open questions

1. **Multi-file transactionality.** `WriteConfig` takes several files; do we need
   all-or-nothing across them (write-all-to-temp, then rename-all)? Per-file
   atomicity matches today; cross-file rollback is more code for a rare need.
   Proposed: per-file for v1, revisit if a real caller needs a coupled write.
2. **Reconciling GeST's `gest` fragment with hand edits to the same atom in a
   sibling file.** If a user pins `cat/pkg foo` in their own `package.use/zzz`,
   GeST's `gest` file can still write `-foo`; last-file-wins is Portage's rule,
   not ours to arbitrate — but the UI should *show* the effective conflict (read
   effective state from the `portage` API, which we already do in
   `useflags._base_state`).
3. **Naming of the owned numbered fragment** (`50gest-cpuflags` vs adopting the
   handbook's `00cpu-flags`). Owning a distinct name is safer; adopting the
   handbook name matches muscle memory. Proposed: own a distinct name, document it.

[handbook]: https://wiki.gentoo.org/wiki/Handbook:AMD64/Installation/Base
