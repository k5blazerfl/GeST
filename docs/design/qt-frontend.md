# Design: the GeST Qt frontend (module framework) — HeDE Phase 2c

*Status: spec+build · Scope: `gest/qt/` — the embeddable module framework + the standalone `gest-settings` Control Center · Depends on: [desktop-environment](desktop-environment.md) §9, [hede-phase2](hede-phase2.md) §3, GeST `core` · Gate: **lifted 2026-08-14** (see [[qt-frontend-gated-on-tui]]) · Milestone: `gest-settings` opens a category sidebar of modules, each a `core`-driven widget; the same widgets embed in HeDE later (2d)*

## 1. Decisions

- **Language: PySide6.** The Qt frontend is a *second renderer over `core`* (like
  the urwid TUI), so it must call `gest.core` **in-process** — the same Portage
  Python API and readers the TUI uses. PySide6 gives that for free in one
  language; a C++/Qt frontend would have to proxy every read/write over the seam.
  (The HeDE *shell* stays C++/Qt and talks to `core` over the seam; the *frontend*
  is Python/Qt and talks to `core` directly. Two different consumers, chosen per
  their constraints.)
- **A module = a widget + a descriptor.** Modules never assume their host, so the
  same widget runs in `gest-settings` (standalone) and, later, embedded in a HeDE
  popover (2d).
- **The registry is Qt-free.** Descriptors + factories are plain Python (no PySide
  import), so ordering/grouping is unit-testable headless; only the widgets need Qt.

## 2. The contract (`gest/qt/registry.py`)

```python
@dataclass(frozen=True)
class ModuleDescriptor:
    id: str; title: str; category: str; icon: str = ""

@dataclass
class ModuleEntry:
    descriptor: ModuleDescriptor
    factory: Callable[[], QWidget]   # builds the module widget (lazy)

class Registry:
    def register(descriptor, factory) -> None
    def entries() -> list[ModuleEntry]
    def by_category() -> dict[str, list[ModuleEntry]]   # grouped, sorted
```

- `factory` is opaque to the registry (never called there), so the registry has no
  Qt dependency and instantiation is **lazy** — a module's `core` reader runs only
  when the module is first opened, not at startup.

## 3. The host (`gest/qt/app.py`)

`ControlCenter` (a `QWidget`): a category tree on the left (from
`registry.by_category()`), a `QStackedWidget` on the right. Selecting a module
lazily calls its factory (cached), adds the widget to the stack, and shows it —
the YaST / KDE System-Settings shape. `gest-settings` = `main()` that builds the
registry, constructs `ControlCenter`, and runs.

## 4. Modules in this increment (`gest/qt/modules/`)

Read-only demonstrators that prove the framework end-to-end over real `core`
readers (no mutations yet):

- **Hardware** (category *System*) — `core/hardware.inventory()` sections.
- **Software** (category *Software*) — `core/software.reader.counts()` summary.

Mutating modules (Network, Software actions, Appearance) come next; they route
`widget → core → polkit backend`, exactly as the TUI does.

## 5. Embedding (2d, next)

Because a module is a widget + descriptor with no host assumptions, HeDE's panel
will host a single module widget in a layer-shell popover (e.g. the network
applet → the Network module). No frontend change needed beyond a small embed
entry point (`gest-settings --embed <id>` or an in-process host).

## 6. Testing

- **Registry** — pure unit tests (register, dedupe, `by_category` grouping/order);
  no Qt.
- **Host** — an offscreen (`QT_QPA_PLATFORM=offscreen`) smoke test builds
  `ControlCenter` over a registry of **fake** modules and checks the sidebar +
  that selecting one shows a widget — the framework, without running `core`.
- **Modules** — their `core` readers are already tested at the `core` level.

## 7. Packaging

`gest-settings` console script in `pyproject`; **PySide6** as an optional-dependency
extra (`[qt]`) so the TUI install stays lean. The gest ebuild gains a `qt` USE flag
(pulls `dev-python/pyside6`) at the next release — the overlay is CI-owned, so not
hand-edited here.
