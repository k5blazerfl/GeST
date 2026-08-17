#pragma once

#include <QColor>
#include <QPalette>
#include <QString>

namespace helm {

// --- pure (unit-tested) ---
// Readable text colour (black/white) for a given background.
QColor contrastText(const QColor &bg);
// A shell palette: dark or light base, `accent` as the Highlight (if valid).
QPalette buildPalette(bool dark, const QColor &accent);

// The default HeDE accent — Harbor teal (helm.theme worlds.harbor). Used when
// the user hasn't picked one, so the shell is Harbor-styled out of the box.
QColor harborAccent();

// A Qt style sheet for the HeDE shell surfaces — the glass bar plus the shared
// Helm token look (fonts, radii, accent selection) — derived from the
// appearance choice. Applied globally by applyAppearance().
QString styleSheet(bool dark, const QColor &accent);

// Read hede.conf [appearance] (written by helm-theme) and apply the palette +
// Fusion style to the running QApplication. No-op if nothing is themed, so the
// shell keeps its native look until the user picks a theme.
void applyAppearance();

} // namespace helm
