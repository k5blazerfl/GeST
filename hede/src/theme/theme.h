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

// Write the theme: GTK 3/4 settings.ini + the [appearance] block in hede.conf
// (under $XDG_CONFIG_HOME) + the Helm labwc themerc (under $XDG_DATA_HOME).
// Returns the files written (empty on failure).
QStringList applyTheme(const ThemeSpec &s);

} // namespace helm
