#pragma once

#include <QColor>
#include <QPalette>

namespace helm {

// --- pure (unit-tested) ---
// Readable text colour (black/white) for a given background.
QColor contrastText(const QColor &bg);
// A shell palette: dark or light base, `accent` as the Highlight (if valid).
QPalette buildPalette(bool dark, const QColor &accent);

// Read hede.conf [appearance] (written by helm-theme) and apply the palette +
// Fusion style to the running QApplication. No-op if nothing is themed, so the
// shell keeps its native look until the user picks a theme.
void applyAppearance();

} // namespace helm
