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

QString styleSheet(bool dark, const QColor &accent) {
    Q_UNUSED(dark); // the bar tint is world-navy in every world; body mode is the palette's job
    const QColor a = accent.isValid() ? accent : harborAccent();
    const auto rgba = [](const QColor &c, double alpha) {
        return QStringLiteral("rgba(%1,%2,%3,%4)")
            .arg(c.red()).arg(c.green()).arg(c.blue()).arg(alpha, 0, 'f', 2);
    };
    const QString accentFill = rgba(a, 0.34);   // tokens.accent.selection_fill (34%)
    const QString accentEdge = rgba(a, 0.55);   // tokens.accent.selection_border (55%)

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
        "#HelmBar { background: rgba(11,38,46,0.82); border: none;"
        " border-top: 1px solid rgba(255,255,255,0.28); }\n"
        "#HelmBar QLabel { color: #eaf1f3; background: transparent; }\n"
        "#HelmBar QToolButton, #HelmBar QPushButton {"
        " color: #eaf1f3; background: transparent; border: none;"
        " border-radius: 5px; padding: 2px 8px; }\n"
        "#HelmBar QToolButton:hover, #HelmBar QPushButton:hover {"
        " background: rgba(255,255,255,0.14); }\n"
        "#HelmBar QToolButton:pressed, #HelmBar QPushButton:pressed,\n"
        "#HelmBar QToolButton:checked, #HelmBar QPushButton:checked {"
        " background: %1; }\n")
        .arg(accentFill);

    return qss;
}

} // namespace helm
