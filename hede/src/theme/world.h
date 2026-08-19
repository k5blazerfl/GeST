#pragma once

#include <QList>
#include <QString>

namespace helm {

// A "world" (biome): the packaged art + palette that defines HeDE's look —
// scene wallpaper, accent role, bar tint, and (later) the nine-slice window
// frame. Loaded from a helm.world/0.1 `theme.yaml` under a world directory
// (<datadir>/hede/worlds/<id>/). See docs/design/hede-theme.md.
//
// Slice 1 consumes the wallpaper scene + records the accent/bar tint; the
// appearance and panel modules pick those up in later slices, and the
// decoration (frame.png) lands when the nine-slice frames are wired.
struct World {
    QString id;      // "harbor"
    QString name;    // "Harbor"
    QString accent;  // "#RRGGBB" (empty if unset)
    QString baseDir; // absolute dir the world was loaded from (asset root)

    // wallpaper_art
    QString wallpaperImage; // filename relative to baseDir, e.g. "wallpaper.png"
    QString wallpaperFit;   // "cover" | "contain" | … (empty → treat as cover)

    // bar
    QString barStyle; // "glass" | "solid" (empty → glass)
    QString barTint;  // "cool" | "warm" | … (empty if unset)

    bool valid() const { return !id.isEmpty(); }

    // Absolute path to the wallpaper, or empty if the world defines none or the
    // file is missing on disk.
    QString wallpaperPath() const;
};

// Parse a helm.world/0.1 document. `baseDir` is recorded so wallpaperPath() can
// resolve the (relative) scene filename. Tolerant scalar reader — it reads the
// keys this struct needs and ignores the rest (schema, credit, decoration_art).
World parseWorldYaml(const QString &text, const QString &baseDir = QString());

// Locate and load world `id` from the HeDE world search path: $HELM_WORLDS_DIR
// first (dev/tests), then each XDG data dir's `hede/worlds` (so the packaged
// /usr/share/hede/worlds is found). Returns an invalid World if not found.
World loadWorld(const QString &id);

// Every world found on the search path, deduped by id (an earlier root shadows a
// later one), sorted by display name. For a world switcher / enumeration.
QList<World> listWorlds();

} // namespace helm
