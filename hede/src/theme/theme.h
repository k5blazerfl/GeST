#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// A desktop appearance choice. The gated Appearance module will build one of
// these; helm-theme (and this lib) turn it into on-disk config.
struct ThemeSpec {
    bool dark = false;
    QString gtkTheme;  // e.g. "Adwaita-dark"; empty → derived from `dark`
    QString iconTheme; // e.g. "Papirus"; empty → left unset
    QString accent;    // "#RRGGBB"; stored for the shell's own palette
};

// --- pure generators (unit-tested) ---
QString effectiveGtkTheme(const ThemeSpec &s);     // gtkTheme or Adwaita[-dark]
QString gtkSettingsIni(const ThemeSpec &s);        // a GTK settings.ini body
ThemeSpec parseThemeArgs(const QStringList &args); // --dark/--light/--accent=…

// A labwc (openbox-3) themerc body for the "Helm" theme: the focused titlebar
// is tinted with the accent (falling back to the Harbor default so the bar is
// always coloured), the unfocused one uses a neutral surface. Colours follow
// the same luminance rule as the shell palette (see helm::contrastText).
QString themercBody(const ThemeSpec &s);

// --- boot-splash generators (the seamless-boot chain) ---
// The Harbor default accent, shared by the fallbacks below and themercBody.
QString defaultAccent(); // "#3aa6c4"

// A Plymouth script-theme body (hede.script): the Harbor scene under a thin
// progress tracker whose bar — and the pre-image fallback fill — track the
// accent (empty → Harbor default). The scene image is unchanged here; only the
// palette tracks the world (per-world scene art is a later slice).
QString plymouthScriptBody(const QString &accent);

// A GRUB theme body (theme.txt): the boot menu laid over background.png, with
// the letterbox (desktop-color) and the highlighted entry (selected_item_color)
// tinted to the accent (empty → Harbor default). Menu/label text stays a fixed
// legible neutral.
QString grubThemeBody(const QString &accent);

// Write the generated boot theme (hede.script + GRUB theme.txt) under ``dir``,
// as ``<dir>/plymouth/hede/hede.script`` and ``<dir>/grub/hede/theme.txt``.
// Returns the files written (empty on failure). The privileged installer emits
// to a root-owned dir with an explicit accent (--emit-boot-theme); the session
// stages under $XDG_DATA_HOME (stageBootTheme).
QStringList writeBootTheme(const QString &dir, const QString &accent);

// Stage the boot theme for the privileged installer to pick up: writeBootTheme
// under $XDG_DATA_HOME/hede/boot/ (user-writable). A root step (GeST's
// SyncBootTheme) installs these into /usr/share + /boot and rebuilds the
// initramfs — the boot splash can't repaint live like the desktop, so it's
// staged here and applied out of band. Returns the files written.
QStringList stageBootTheme(const QString &accent);

// The accent the shell/boot resolve for the active session: the explicit
// [appearance] accent if set, else the active world's accent (hede.conf
// [world] id, default "harbor"), else the Harbor default. Mirrors the shell's
// helm::effectiveAccent and applyThemeFromWorld's precedence.
QString activeAccent();

// The active world id (hede.conf [world] id, default "harbor") — the biome the
// boot splash scene tracks; pairs with activeAccent for the chrome.
QString activeWorldId();

// Copy world ``worldId``'s boot scene (World::bootPath) into ``dir`` as
// ``plymouth/hede/background.png``, so the splash art tracks the biome. Returns
// the written path, or empty if the world has no boot.png (the installed default
// is then left in place). Used by --emit-boot-theme.
QString emitBootScene(const QString &dir, const QString &worldId);

// Write the theme: GTK 3/4 settings.ini + (when persistAppearance) the
// [appearance] block in hede.conf (under $XDG_CONFIG_HOME) + the Helm labwc
// themerc (under $XDG_DATA_HOME). Returns the files written (empty on failure).
// persistAppearance=false skips the hede.conf [appearance] write — used when the
// accent is derived from the active world rather than an explicit user choice,
// so a world switch isn't frozen into appearance/accent. See applyThemeFromWorld.
QStringList applyTheme(const ThemeSpec &s, bool persistAppearance = true);

// Switch the active world: write hede.conf [world] id and drop any explicit
// [appearance] accent (picking a world adopts its colour), then regenerate the
// labwc + GTK theme from it (applyThemeFromWorld). Returns false if `id` names
// no installed world (nothing is changed). The hede.conf write is what a running
// shell (helm-bg / helm-panel via a config watcher) reacts to for a live switch.
bool setWorld(const QString &id);

// Regenerate the labwc titlebar + GTK theme from the active world: the accent
// is the explicit [appearance] accent if set, else the active world's accent
// (hede.conf [world] id, default "harbor"), else the Harbor default. Does NOT
// persist the accent (persistAppearance=false), so switching worlds keeps
// re-tinting the window chrome. Run at session start to match the shell palette
// (which resolves the same precedence live via helm::effectiveAccent).
QStringList applyThemeFromWorld();

} // namespace helm
