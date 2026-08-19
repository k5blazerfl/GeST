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

    // decoration_art — the nine-patch window frame (helm.frame/0.1). The insets
    // are the decoration margins (titlebar height + border thickness) in source
    // pixels; they match make-frame.py in the helm-titlebar-skins Voyage and the
    // helm Qt decoration plugin. The frame image's centre is transparent.
    QString frameImage;    // decoration_art.source, e.g. "frame.png" (empty → none)
    int frameTop = 40;     // titlebar band height
    int frameLeft = 8;     // side/bottom border thickness
    int frameRight = 8;
    int frameBottom = 8;

    bool valid() const { return !id.isEmpty(); }

    // Absolute path to the wallpaper, or empty if the world defines none or the
    // file is missing on disk.
    QString wallpaperPath() const;
    // Absolute path to the nine-patch frame image, or empty if none/missing.
    QString framePath() const;
    // Absolute path to the boot-optimised splash scene (``boot.png`` in the
    // world dir, by convention: 16:9, palette-reduced to stay initramfs-light),
    // or empty if none/missing. The seamless boot chain copies this over the
    // Plymouth background so the splash art tracks the active biome.
    QString bootPath() const;
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
