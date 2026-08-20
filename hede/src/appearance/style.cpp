#include "palette.h"

// The HeDE shell style sheet — the Harbor glass look from the helm.theme
// contract (docs/design/hede-theme.md + hede-tokens.yaml), rendered as Qt QSS.
// applyAppearance() installs this on the QApplication, so every shell surface
// (bar, menu, toasts) speaks one visual language.

namespace helm {

QColor harborAccent() {
    // worlds.harbor.accent — the default when the user hasn't chosen one.
    return QColor(QStringLiteral("#3aa6c4"));
}

QColor barTint(const QColor &accent) {
    const QColor a = accent.isValid() ? accent : harborAccent();
    int h = a.hsvHue();
    if (h < 0)
        h = harborAccent().hsvHue(); // achromatic accent → Harbor hue
    // Deep + desaturated: the accent's hue at low value, high saturation. Tuned
    // so Harbor teal reproduces the shipped navy-teal glass and a warm accent
    // yields a warm glass. See tokens.surfaces.glass (world.bar_tint).
    return QColor::fromHsv(h, 190, 46);
}

QString styleSheet(bool dark, const QColor &accent) {
    Q_UNUSED(dark); // body light/dark is the palette's job; the bar is always deep glass
    const QColor a = accent.isValid() ? accent : harborAccent();
    const auto rgba = [](const QColor &c, double alpha) {
        return QStringLiteral("rgba(%1,%2,%3,%4)")
            .arg(c.red()).arg(c.green()).arg(c.blue()).arg(alpha, 0, 'f', 2);
    };
    const QString accentFill = rgba(a, 0.34);   // tokens.accent.selection_fill (34%)
    const QString accentEdge = rgba(a, 0.55);   // tokens.accent.selection_border (55%)
    const QColor glass = barTint(a);            // world-tinted deep glass
    const QString barGlass = rgba(glass, 0.82); // bar opacity (no compositor blur yet)
    const QString acrylicGlass = rgba(glass, 0.92); // pullouts + toasts: denser
    const QString glyph = barGlyphColor().name(); // light bar glyph colour (shared with icons)

    QString qss;

    // Shared token look — applies to every shell surface.
    qss += QStringLiteral(
        "* { font-family: \"Segoe UI\", \"Inter\", system-ui, sans-serif; }\n"
        "QAbstractItemView { outline: none; }\n"
        "QAbstractItemView::item { border-radius: 5px; padding: 2px 6px; }\n"
        "QAbstractItemView::item:selected { background: %1; color: palette(text); }\n"
        "QLineEdit { border: 1px solid rgba(127,127,127,0.35); border-radius: 4px;"
        " padding: 4px 8px; }\n"
        "QLineEdit:focus { border: 1px solid %2; }\n")
        .arg(accentFill, accentEdge);

    // The glass bar (#HelmBar). labwc has no backdrop-blur, so the token bar_tint
    // (alpha .44, designed to sit under a blur) is bumped opaque enough to stay
    // legible over a busy wallpaper — drop it back toward .44 once a compositor
    // blur protocol lands. Dark tint → light glyphs; hover reveals a glass chip;
    // the active window's tile carries the accent (radius = chip token, 5).
    qss += QStringLiteral(
        "#HelmBar { background: %3; border: none;"
        " border-top: 1px solid rgba(255,255,255,0.28); }\n"
        "#HelmBar QLabel { color: %1; background: transparent; }\n"
        "#HelmBar QToolButton, #HelmBar QPushButton {"
        " color: %1; background: transparent; border: none;"
        " border-radius: 5px; padding: 2px 8px; }\n"
        "#HelmBar QToolButton:hover, #HelmBar QPushButton:hover {"
        " background: rgba(255,255,255,0.14); }\n"
        "#HelmBar QToolButton:pressed, #HelmBar QPushButton:pressed,\n"
        "#HelmBar QToolButton:checked, #HelmBar QPushButton:checked {"
        " background: %2; }\n"
        // The ⎈ Start tile: a touch larger + roomier, still edgeless.
        "#HelmBar #HelmStart { font-size: 15px; font-weight: 600; padding: 0 10px; }\n")
        .arg(glyph, accentFill, barGlass);

    // The acrylic pullout (#HelmPullout) — THE standard for surfaces that emerge
    // from the bar (launcher now, quick-settings/tray later): heavier tint than
    // the bar, silver border on top + sides only, 7px top corners, flat bottom
    // that tucks behind the bar. No blur on labwc → opaque enough to read; drop
    // toward the token .44 once a blur protocol lands.
    qss += QStringLiteral(
        "#HelmPullout { background: %4;"
        " border: 1px solid rgba(255,255,255,0.22); border-bottom: none;"
        " border-top-left-radius: 7px; border-top-right-radius: 7px;"
        " border-bottom-left-radius: 0; border-bottom-right-radius: 0; }\n"
        "#HelmPullout QLabel { color: %1; background: transparent; }\n"
        "#HelmPullout QListWidget, #HelmPullout QListView {"
        " background: transparent; border: none; color: %1; }\n"
        "#HelmPullout QListWidget::item { color: %1; padding: 4px 8px; border-radius: 5px; }\n"
        "#HelmPullout QListWidget::item:selected { background: %2; color: %1; }\n"
        "#HelmPullout QLineEdit { background: rgba(255,255,255,0.10); color: %1;"
        " border: 1px solid rgba(255,255,255,0.18); border-radius: 5px; padding: 6px 10px; }\n"
        "#HelmPullout QLineEdit:focus { border: 1px solid %3; }\n"
        // Rail buttons (Control Center / Run / power): edgeless light glyphs,
        // hover-glass chip — same language as the bar.
        "#HelmPullout QToolButton, #HelmPullout QPushButton { color: %1;"
        " background: transparent; border: none; border-radius: 5px; padding: 6px 8px; }\n"
        "#HelmPullout QToolButton:hover, #HelmPullout QPushButton:hover {"
        " background: rgba(255,255,255,0.12); }\n"
        // The right rail: a hairline divider from the app list.
        "#HelmMenuRail { border-left: 1px solid rgba(255,255,255,0.14); }\n")
        .arg(glyph, accentFill, accentEdge, acrylicGlass);

    // Acrylic toast cards (#HelmToast) — bottom-right notifications. Same acrylic
    // material as the pullout but a free-floating card: full silver border + all
    // corners rounded, with an accent spine down the left edge as the urgency cue.
    qss += QStringLiteral(
        "#HelmToast { background: %3;"
        " border: 1px solid rgba(255,255,255,0.22); border-left: 3px solid %2;"
        " border-radius: 7px; }\n"
        "#HelmToast QLabel { color: %1; background: transparent; }\n"
        "#HelmToast #HelmToastTitle { color: %1; font-weight: 700; }\n")
        .arg(glyph, a.name(), acrylicGlass);

    return qss;
}

} // namespace helm
