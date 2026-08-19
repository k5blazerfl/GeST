#pragma once

#include <QColor>
#include <QIcon>
#include <QPalette>
#include <QSize>
#include <QString>

namespace helm {

// --- pure (unit-tested) ---
// Readable text colour (black/white) for a given background.
QColor contrastText(const QColor &bg);
// A shell palette: dark or light base, `accent` as the Highlight (if valid).
QPalette buildPalette(bool dark, const QColor &accent);

// The default HeDE accent — Harbor teal (helm.theme worlds.harbor). The final
// fallback when neither the user nor the active world supplies one.
QColor harborAccent();

// The accent the shell should use, in precedence order: an explicit
// [appearance] accent (the user's choice via helm-theme) wins; else the active
// world's accent (hede.conf [world] id, default "harbor"), so switching worlds
// re-tints the whole shell; else harborAccent(). `cfg` is the HeDE config.
class Config;
QColor effectiveAccent(const Config &cfg);

// A Qt style sheet for the HeDE shell surfaces — the glass bar plus the shared
// Helm token look (fonts, radii, accent selection) — derived from the
// appearance choice. Applied globally by applyAppearance().
QString styleSheet(bool dark, const QColor &accent);

// The light glyph colour used on the dark glass bar (text + recoloured icons),
// so bar contents read as one monochrome family.
QColor barGlyphColor();

// The deep "glass" tint for the bar / pullout / toast surfaces, derived from the
// accent's hue (a dark, desaturated version) so each world's chrome carries its
// own colour: Harbor teal → the deep navy-teal glass; a warm accent → warm
// glass. An achromatic accent falls back to the Harbor hue.
QColor barTint(const QColor &accent);

// A theme icon recoloured to a flat `color` glyph (the tokens' mask_recolor:
// mask the icon's alpha with the colour). Used to make bar applet icons legible
// on the dark bar regardless of the installed icon theme. Returns the original
// icon if it can't be resolved/rendered.
QIcon tintedIcon(const QString &themeName, const QColor &color, const QSize &size);

// Read hede.conf [appearance] (written by helm-theme) and apply the palette +
// Fusion style to the running QApplication. No-op if nothing is themed, so the
// shell keeps its native look until the user picks a theme.
void applyAppearance();

// Watch hede.conf and re-run applyAppearance() whenever it changes, so a live
// world/accent switch (helm-theme --world) re-tints the running shell surfaces
// without a restart. Owns a QFileSystemWatcher parented to the application. Call
// once, after applyAppearance(), from each shell process (panel/menu/notify).
void watchAppearance();

} // namespace helm
