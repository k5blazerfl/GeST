# Design: Lantern — the HeDE notification center

*Status: charting (2026-08-24) · Scope: a right-edge slide-out showing
notification history + a do-not-disturb toggle + clear-all · Depends on:
`helm-notify-lib` (the daemon's model + store), the `org.gentoo.hede.Notifications`
D-Bus interface (DnD, to be extended), `helm-wayland` (layer-shell),
`helm-appearance` (theming) · Relates to: [sefe.md](sefe.md) / barnacle (the
standalone-app + engine/UI-split scaffolds this follows)*

> **Lantern** is the light you raise to see what drifted in while you weren't
> looking. A right-edge surface that slides out to show your **notification
> history**, with a **do-not-disturb** toggle and **clear-all**. The lore:
> Nietzsche's madman lights a lantern in the bright morning to seek what everyone
> else ignores (*Gay Science* §125); Diogenes carried one through daylight Athens.
> The lantern keeps vigil — it holds what the toasts let go.

## The problem: the daemon has amnesia

`helm-notifyd` is a complete freedesktop notification daemon (`Notify`,
`CloseNotification`, `GetCapabilities`, toasts, a working DnD extension on
`org.gentoo.hede.Notifications`). But it **keeps no history**: `NotifyService`
holds a `QVector<Notification> m_store` of *active* notifications and
**drops each one the instant its toast expires or is dismissed**
(`notifyservice.cpp` — `dropNotification` on the ToastStack `dismissed` signal).
Nothing is retained, nothing is written to disk, and there is no API to fetch
past notifications, nor a "new notification arrived" signal. So a notification
center can't just *render* history — first the daemon has to *remember*.

## The shape: one engine, layered like Barnacle/SeFE

- **`helm-notify-lib`** grows a pure, unit-tested **history** layer (model +
  store + persistence). No Qt-Widgets, no D-Bus — just data.
- **`helm-notifyd`** wires that history in: stamp `received`, append to a bounded
  log, persist, and expose it over D-Bus (a new method + signal). The toast path
  is untouched.
- **`helm-lantern`** is the viewer: a right-edge `wlr-layer-shell` surface (the
  `applyLayerShell` + `applyAppearance` stack `helm-menu` already uses), a D-Bus
  client of the daemon, reusing the exact `dndtoggle` client pattern for DnD.

## Data model

`Notification` (in `helm-notify-lib`) gains two history-only fields — the toast
path ignores them:

- `QDateTime received` — stamped by the daemon on arrival.
- `bool seen` — the Lantern drawer flips it once it has shown the entry.

## Phasing (slices)

1. **History library** *(this slice — pure, fully unit-tested)* — `history.{h,cpp}`
   in `helm-notify-lib`: `appendHistory` (newest-first, dedupe-by-id so a
   `replaces_id` update moves to the front, bounded by a cap), JSON
   (de)serialisation of a notification (incl. `received`/`seen`),
   `serializeHistory`/`deserializeHistory`, and `saveHistory`/`loadHistory` to
   `$XDG_DATA_HOME/hede/notifications.json` (`defaultHistoryPath`). No daemon
   behaviour change yet — this is the memory Lantern will use.
2. **Daemon wiring + retrieval API** — `NotifyService` retains a persistent
   history alongside `m_store` (stamp `received`, `appendHistory`, save; load on
   startup; *don't* drop on toast dismiss). Expose it on
   `org.gentoo.hede.Notifications`: `GetHistory`, `ClearHistory`, and a
   `NotificationAdded` signal (mirroring how DnD already relays
   `DoNotDisturbChanged`).
3. **The Lantern surface** *(shipped)* — `helm-lantern`, a right-edge
   `LayerOverlay` slide-out: a header (title + DnD toggle + Clear all) over a
   scrollable, newest-first history list (title / body / relative time). A
   `LanternClient` wraps the slice-2 D-Bus API (`GetHistory`, `ClearHistory`,
   `SetDoNotDisturb`) and live-refreshes off `NotificationAdded`/`HistoryCleared`/
   `DoNotDisturbChanged`. A one-shot surface like `helm-menu`: dismiss on Esc /
   click-away. Pure `format` + `parseHistory` are unit-tested; the client+window
   were smoked end-to-end against the daemon on a private bus (needs a compositor
   to *see*). **Follow-up:** the tray/applet trigger that launches it (today it's
   the `helm-lantern` binary), and glanceable widgets (the v2 non-goal below).

## Non-goals (v1)

Glanceable **widgets** (weather, disk/system info) — the ambitious follow-up; v1
is history + DnD + clear-all only. Also: per-app filtering/muting, notification
*actions* replay from history (the app may be gone), and grouping/threading.
Lantern shows the log and lets you clear it; it does not become a second toast
system.
