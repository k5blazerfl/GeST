# HeDE C++/Qt reference view for gestd

The concrete template for HeDE's Control Center: a Qt6 client that drives GeST over
D-Bus through **`qdbusxml2cpp`-generated bindings** — no Portage, no Python
in-process. It proves the **full path-B loop** on the *C++* side (v0.50.30–35 built
the Python service; this is a consumer): read/validate/render via gestd, and
**apply via the polkit root backend**.

Wired for the **Hostname** module (the simplest, complete example). The **Software**
interface XML is included as the next-step template.

## The two buses

```
                 session bus (unprivileged)                 system bus (polkit)
Qt view ──▶ org.gentoo.gest.Core / …core1.Hostname   ▶ org.gentoo.gest / …System
              GetState / Validate / Render (gestd)        SetHostname … (root backend)
              — read / validate / render —               — WRITE, polkit-gated —
```

The view reads through **gestd** and writes through the **root backend**; two
generated proxies, two buses. This is exactly HeDE's model.

## What it shows

```
interfaces/org.gentoo.gest.core1.Hostname.xml  ← gestd read side (session bus)
interfaces/org.gentoo.gest.System.xml          ← polkit root backend write side (system bus)
interfaces/org.gentoo.gest.core1.Software.xml  ← the package-panel template (aa{sv})
CMakeLists.txt     ← qt_add_dbus_interface() runs qdbusxml2cpp per interface
main.cpp           ← a QWidget panel that calls the proxies like local objects
```

`main.cpp` builds a Hostname panel: the current hostname (from `GetState`, an
`a{sv}` → `QVariantMap`), a field validated live (`Validate` → `(bool, QString)`),
a preview of the config a write would produce (`Render` → `QString`), and an
**Apply** button that calls `SetHostname` on the root backend (`(bool, QString)`),
then re-reads the current value from gestd. Apply is **polkit-gated**: a session
with a polkit agent prompts for the admin password; without one it is denied.

## Build & run

Needs `dev-qt/qtbase[dbus,widgets]` (provides `qdbusxml2cpp`), cmake, a C++17
compiler. On this repo it was built and run against a live gestd.

```sh
export PATH="/usr/lib64/qt6/bin:$PATH"          # where qdbusxml2cpp lives on Gentoo
cmake -S examples/hede-qt -B examples/hede-qt/build
cmake --build examples/hede-qt/build

gest-core &                                     # start gestd on the session bus
examples/hede-qt/build/gest-hede-ref            # the GUI (needs a display + a polkit agent for Apply)
QT_QPA_PLATFORM=offscreen examples/hede-qt/build/gest-hede-ref --once   # headless read proof
# → GetState -> hostname=emperor | Validate('emperor') -> ✓ valid | Render -> hostname="emperor"
examples/hede-qt/build/gest-hede-ref --apply myhost    # headless write proof (needs gest-backend)
# → SetHostname('myhost') -> ok=… output=…   (or a polkit "Not authorized" denial without an agent)
```

Both round-trips were run against a live system here: the read path returned the
current hostname, and `--apply` reached the root backend on the system bus, where
**polkit denied it** (no auth agent in a headless shell) — proving the gate is
active and the call is issued correctly.

## The `qdbusxml2cpp` mapping (the one gotcha)

`qdbusxml2cpp` doesn't infer C++ types for D-Bus containers — each container out-arg
needs a `QtTypeName` annotation in the XML:

| D-Bus | annotation value | note |
|---|---|---|
| `a{sv}` | `QVariantMap` | marshalled natively |
| `as` | `QStringList` | native, no annotation needed |
| `a{sx}` | `QMap<QString,qlonglong>` | native |
| `aa{sv}` (lists) | `QList<QVariantMap>` | register once: `qDBusRegisterMetaType<QList<QVariantMap>>()` |

So HeDE's package panel (Software: `ListInstalled`/`Search` → `aa{sv}`) registers
`QList<QVariantMap>` at startup, then iterates the returned list of property bags —
each map keyed by `cp`, `version`, `repository`, … exactly as `software_adapter`
produces them. See `interfaces/org.gentoo.gest.core1.Software.xml`.

## Adding a module

1. `gdbus introspect --session --dest org.gentoo.gest.Core --object-path <path> --xml`
   → save `interfaces/<iface>.xml`, add `QtTypeName` annotations for any containers.
2. `qt_add_dbus_interface(DBUS_SRCS interfaces/<iface>.xml <base>)` in CMake.
3. Call the generated proxy from a Qt view. Writes still go to the polkit backend.
