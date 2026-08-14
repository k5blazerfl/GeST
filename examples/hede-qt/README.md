# HeDE C++/Qt reference view for gestd

The concrete template for HeDE's Control Center: a Qt6 client that consumes gestd
over D-Bus through **`qdbusxml2cpp`-generated bindings** — no Portage, no Python
in-process. It proves the read side of the HeDE path-B integration on the *C++*
side (v0.50.30–35 built the Python service; this is a consumer).

Wired for the **Hostname** module (the simplest, complete: read + validate +
render). The **Software** interface XML is included as the next-step template.

## What it shows

```
interfaces/*.xml   ← gestd interface definitions (captured via `gdbus introspect`,
                     + QtTypeName annotations mapping D-Bus containers to C++ types)
CMakeLists.txt     ← qt_add_dbus_interface() runs qdbusxml2cpp to generate a typed proxy
main.cpp           ← a QWidget panel that calls the proxy like a local object
```

`main.cpp` builds a Hostname panel: the current hostname (from `GetState`, an
`a{sv}` → `QVariantMap`), a field validated live (`Validate` → `(bool, QString)`),
and a preview of the config a write would produce (`Render` → `QString`). Applying
is a **write** — that goes to the polkit root backend, not gestd.

## Build & run

Needs `dev-qt/qtbase[dbus,widgets]` (provides `qdbusxml2cpp`), cmake, a C++17
compiler. On this repo it was built and run against a live gestd.

```sh
export PATH="/usr/lib64/qt6/bin:$PATH"          # where qdbusxml2cpp lives on Gentoo
cmake -S examples/hede-qt -B examples/hede-qt/build
cmake --build examples/hede-qt/build

gest-core &                                     # start gestd on the session bus
examples/hede-qt/build/gest-hede-ref            # the GUI (needs a display)
QT_QPA_PLATFORM=offscreen examples/hede-qt/build/gest-hede-ref --once   # headless proof
# → GetState -> hostname=emperor | Validate('emperor') -> ✓ valid | Render -> hostname="emperor"
```

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
