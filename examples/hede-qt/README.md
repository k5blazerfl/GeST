# HeDE C++/Qt reference view for gestd

The concrete template for HeDE's Control Center: a Qt6 client that drives GeST over
D-Bus through **`qdbusxml2cpp`-generated bindings** — no Portage, no Python
in-process. It proves the **full path-B loop** on the *C++* side (v0.50.30–35 built
the Python service; this is a consumer): read/validate/render via gestd, and
**apply via the polkit root backend**.

`main.cpp` drives the **Hostname** module (the simplest, complete example) plus a
**System** write. The CMake build additionally generates and compiles typed proxies
for the **Software** and **Catalog** interfaces — they aren't wired into a view yet,
but compiling them keeps those templates honest (the `cpp-reference` CI job builds
the whole thing on every push, so a broken interface XML fails CI).

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

## The write side, broadened past `SetHostname`

`SetHostname` is only the first write. The reference also drives three more backend
interfaces headlessly, each pairing with a gestd read the client already does:

| Flag | Backend call | Interface | Shape it demonstrates |
|---|---|---|---|
| `--apply <name>` | `System.SetHostname(name, "/")` | `org.gentoo.gest.System` | `(s,s)→(b,s)` |
| `--apply-timezone <zone>` | `System.SetTimezone(zone, "/")` | same | a second method on one proxy |
| `--enable-service <name> <0\|1>` | `Services.SetEnabled(name, on)` | `org.gentoo.gest.Services` | a **second write interface**, `bool` arg |
| `--control-service <name> <act>` | `Services.Control(name, act)` | same | start/stop/restart |
| `--apply-sysctl <key> <value>` | `Sysctl.ApplySettings([(key,value)], "/")` | `org.gentoo.gest.Sysctl` | a **container write type**, `a(ss)` |

Run headless (no polkit agent) they were verified to reach the backend and be
**denied at the gate** — and the denials are per-interface distinct (*"Not authorized
to change system settings"* for System, *"…to manage services"* for Services),
proving each call lands on the right object.

**The `a(ss)` write type.** `Sysctl.ApplySettings` takes an array of `(key, value)`
structs — the write-side analogue of the read side's `aa{sv}`. `qdbusxml2cpp` can't
infer a C++ type for `(ss)`, so `sysctl_types.h` declares a tiny `SysctlSetting`
struct with `QDBusArgument` streaming operators, registers it
(`qDBusRegisterMetaType<SysctlSetting>()`), and the XML binds the arg to it with a
`QtTypeName.In0` annotation (`SysctlSettings = QList<SysctlSetting>`). The generated
proxy then takes `SysctlSettings` like any value. This is the pattern HeDE reuses for
every struct-typed argument.

## The `qdbusxml2cpp` mapping (the one gotcha)

`qdbusxml2cpp` doesn't infer C++ types for D-Bus containers — each container out-arg
needs a `QtTypeName` annotation in the XML:

| D-Bus | annotation value | note |
|---|---|---|
| `a{sv}` | `QVariantMap` | marshalled natively |
| `as` | `QStringList` | native, no annotation needed |
| `a{sx}` | `QMap<QString,qlonglong>` | native |
| `aa{sv}` (lists) | `QList<QVariantMap>` | register once: `qDBusRegisterMetaType<QList<QVariantMap>>()` |
| `a(ss)` **in-arg** | `SysctlSettings` (`QList<SysctlSetting>`) | `QtTypeName.In0`; register a struct with `QDBusArgument` operators — see the write side below |

So HeDE's package panel (Software: `ListInstalled`/`Search` → `aa{sv}`) registers
`QList<QVariantMap>` at startup, then iterates the returned list of property bags —
each map keyed by `cp`, `version`, `repository`, … exactly as `software_adapter`
produces them. See `interfaces/org.gentoo.gest.core1.Software.xml`.

## Adding a module

1. `gdbus introspect --session --dest org.gentoo.gest.Core --object-path <path> --xml`
   → save `interfaces/<iface>.xml`, add `QtTypeName` annotations for any containers.
2. `qt_add_dbus_interface(DBUS_SRCS interfaces/<iface>.xml <base>)` in CMake.
3. Call the generated proxy from a Qt view. Writes still go to the polkit backend.
