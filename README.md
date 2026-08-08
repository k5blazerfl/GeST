# GeST — Gentoo System Tool

[![CI](https://github.com/k5blazerfl/GeST/actions/workflows/ci.yml/badge.svg)](https://github.com/k5blazerfl/GeST/actions/workflows/ci.yml)

A modular, YaST-style system-administration tool for Gentoo. Where openSUSE has
YaST2, Gentoo has a pile of excellent-but-disjoint CLIs (`emerge`, `equery`,
`rc-update`, …). GeST aims to unify them behind one coherent interface —
starting with a full-screen text UI, with a Qt/KDE frontend planned.

> **Status:** usable. The **software (Portage) module** is complete —
> search, install, USE/keyword/mask editing, `@world` update, depclean, sync,
> and news — driven through the polkit-gated root backend. An OpenRC
> **Services module** (start/stop/enable) is in too. See the roadmap.

## Architecture

The design copies YaST's most durable idea — a hard separation between
frontends, module logic, and a privileged backend — so a second frontend is a
new renderer, not a rewrite.

```
 frontends ──► core ──► backend
  (TUI)     (modules)  (root, D-Bus + polkit)

 gest/tui/        Textual full-screen frontend (this release)
 gest/core/       frontend-agnostic modules — the real logic
   software/        Portage: model, reader (queries), backend_client (mutations)
 gest/ipc/        the shared D-Bus + polkit contract (names in one place)
 gest/backend/    root D-Bus service, one process, polkit-gated
 data/            system data files (D-Bus policy, activation, polkit actions)
```

**Golden rule:** frontends never touch Portage or D-Bus directly. They call
`core`; `core` is the only thing that speaks to `backend`.

- **Queries** (installed list, search, USE flags) use the in-process **Portage
  Python API** — structured and fast, never `emerge` output scraping.
- **Mutations** (merge, unmerge, edit `/etc/portage`, sync) are the backend's
  job: an unprivileged frontend asks the root service over the system bus, and
  **polkit** decides whether the user is allowed.

## Running (development)

The venv must see the *system* Portage, so create it with system site-packages:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install textual dbus-next
./bin/gest            # launch the TUI
```

The main menu is a two-pane **Control Center**: **↑/↓** move within a pane,
**→**/**Enter** drops from a category into its module list, **Enter** launches a
module, **Esc**/**←** goes back, **F9**/**q** quits.

### Frontend migration: Textual → urwid

GeST is migrating its TUI from Textual to **urwid** (which is packaged in
`::gentoo`; Textual is not). The urwid frontend is being built in parallel under
`gest/uwui/` and can be launched with `gest-uw` — it currently has the Control
Center and the Portage news viewer, with the other modules ported over
subsequent releases. The Textual frontend (`gest`) remains the default until the
port is complete. The `gest/core`, `gest/ipc`, and `gest/backend` layers are
frontend-agnostic and unchanged.

## Tests

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

The reader tests are integration tests against the host's live Portage DB; the
TUI tests drive the interface headlessly via Textual's pilot.

## Privileged backend

Not required for the read-only TUI. To enable install/remove later, install the
system data files (as root) — see [`gest/backend/README.md`](gest/backend/README.md).

## Installing system-wide (recommended)

The development flow above runs GeST from the working tree. For a real
install — where the **root backend loads the installed package from system
paths**, not your home directory — use the Gentoo ebuild in
[`packaging/`](packaging/README.md):

```bash
# register the bundled overlay, then:
sudo emerge -av app-admin/gest
sudo rc-service dbus reload
gest
```

See [`packaging/README.md`](packaging/README.md) for the full overlay setup.
The dev `install-backend.sh` remains for hacking on the backend from a
working tree.

## Roadmap

- [x] Layered skeleton: core + TUI + IPC contract
- [x] YaST-style two-pane Control Center menu + reusable chrome widgets
      (function-key footer, bracket buttons)
- [x] Software Management, YaST sw_single-style — dropdown menu bar +
      filter sidebar + package table + live detail pane
- [x] Transactional package selection — mark packages with Space, commit
      them together with Accept (one multi-atom emerge)
- [x] Install / update / remove marks (Space / r) with a two-phase Accept
      (batched emerge, then batched --depclean)
- [x] Filter sidebar search-in: Name + Summary (description) fields;
      Dependencies ▸ check marked resolves the pending set
- [x] Software module — read path (list / search / info, USE flags, @world)
- [x] Backend scaffold: D-Bus service, polkit actions, system data files
- [x] Install flow: `emerge --pretend` preview → confirm → streamed merge
      (preview runs as the user; the live merge needs the root backend installed)
- [x] USE-flag editing (`package.use`) — tri-state per flag, written via the
      polkit-gated backend, then applied with a `--changed-use` rebuild
- [x] Keyword acceptance + mask editing (`package.accept_keywords`,
      `package.mask`, `package.unmask`) via a generalized backend config writer
- [x] `@world` system update (`emerge -uDN @world`) — preview + streamed merge
- [x] Unmerge / cleanup — safe `--depclean` removal (per-package + whole-system)
      with preview + streamed output
- [x] Tree sync (`emerge --sync`) + Portage news viewer (`eselect news`)
- [x] News mark-read — polkit-gated backend action (`eselect news read`,
      per-item or all) so unprivileged users can clear the read-state
- [x] Services module (OpenRC) — list, start/stop/restart, enable/disable
- [x] Service detail view — description + dependency graph (needs / uses /
      wants / needed-by), read-only, opened with Enter
- [x] Users & Groups module — list users/groups; add / edit / delete users,
      add / delete groups (polkit-gated useradd/usermod/userdel/groupadd/groupdel)
- [x] User passwords (chpasswd via stdin) + group membership (gpasswd);
      the edit form prefills a user's current supplementary groups
- [x] System category — Hostname, Timezone and Locale editors
      (polkit-gated writes to /etc/conf.d/hostname, /etc/localtime, /etc/env.d)
- [x] Network module — list interfaces (ip -j addr), bring links up/down,
      and edit netifrc config (DHCP / static IP+gateway in /etc/conf.d/net)
- [ ] systemd support in Services (out of scope — OpenRC only)
- [x] Backend hardening — every privileged action is audit-logged
      (authpriv, with caller uid); dispatch/auth round-trips are tested
- [~] Frontend migration Textual → urwid (in ::gentoo) — foundation +
      Control Center + news + services + system ported; other modules in progress
- [ ] Qt/KDE frontend over the same `core`
```
