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
