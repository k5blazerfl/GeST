# gestd — the GeST core service (HeDE path-B scaffold)

**Why this exists.** HeDE (the Helm Desktop Environment) is a C++/Qt shell whose
Control Center *is* GeST. GeST's design rule is *frontends call `core`* — but a
C++ shell can't call Python `core` in-process. So `core`'s **unprivileged
read/validate/render** surface is promoted to a D-Bus service, `gestd`, that any
language can consume. Writes stay where they are: the polkit-gated **root
backend** (`gest-backend`). This package is the Phase-0 proof, wired for the
**Hostname** module.

```
HeDE C++/Qt shell ──(session bus, reads/validate/render)──▶ gestd  ──▶ core (Python, incl. Portage API)
        │
        └────────────(system bus, polkit)────────────────▶ gest-backend (root writes)
```

## Layout (the per-module template)

| File | Role |
|---|---|
| `gest/ipc/core_contract.py` | the **versioned** contract: names, paths, `core1.*` interfaces |
| `coreservice/hostname_adapter.py` | **pure** `core ↔ dict/tuple` marshalling — unit-tested, no D-Bus |
| `coreservice/hostname.py` | thin `dbus_next` `ServiceInterface` (variant packing only) |
| `coreservice/service.py` | `gest-core` — claims the session-bus name, exports the modules |
| `coreservice/refclient.py` | a HeDE Qt view in miniature (Python), proving the round-trip |

A new module = one adapter + one `ServiceInterface` + a line in `service._MODULES`.

## Contract (Hostname, `org.gentoo.gest.core1.Hostname`)

Session bus, name `org.gentoo.gest.Core`, path `/org/gentoo/gest/core/Hostname`:

| Method | Signature | Meaning |
|---|---|---|
| `GetState` | `() → a{sv}` | current state, e.g. `{"hostname": <s>}` — an extensible property bag |
| `Validate` | `(s) → (b, s)` | `(ok, message)` for a candidate hostname |
| `Render` | `(s) → s` | the `/etc/conf.d/hostname` text a write would produce (preview) |

*Applying* a hostname is a **write** → `System.SetHostname` on the root backend,
unchanged. Reads/validation/render never leave Python `core`, so C++ never
reimplements them or touches Portage.

## Try it

```sh
pip install -e .            # or run from the repo (pythonpath=".")
gest-core &                 # start gestd on the session bus
python -m gest.coreservice.refclient
# GetState : {'hostname': '...'}
# Validate('my-host') : ok=True  message=''
# Validate('bad host!') : ok=False message='invalid hostname ...'
# Render('my-host') : 'hostname="my-host"\n'
```

Introspect it (what a C++ client generates bindings from):

```sh
busctl --user introspect org.gentoo.gest.Core /org/gentoo/gest/core/Hostname
# gdbus introspect --session -d org.gentoo.gest.Core -o /org/gentoo/gest/core/Hostname
```

## Next (Phase 2+)

- **Software** over the contract — the Portage-heavy reads (list/search/detail/USE,
  the repo-sort), with streaming + pagination. This is the module that proves path
  B: the C++ side gets rich package data and never touches Portage.
- A reference **C++/Qt view** generated with `qdbusxml2cpp` from the introspection
  XML — the template HeDE follows per module.
- A **module descriptor** so HeDE's Control Center enumerates/embeds modules
  uniformly.
