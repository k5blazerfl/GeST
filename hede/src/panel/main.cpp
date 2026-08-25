#include "panel.h"

#include "config.h"
#include "layershell.h"
#include "layout.h"
#include "palette.h"

#include <QApplication>

// Phase 0 helm-panel: a QtWidgets bar promoted to a wlr-layer-shell surface,
// anchored to the bottom edge with an exclusive zone so maximized windows do
// not cover it. Contents: a Start button + a clock (see Panel).
int main(int argc, char **argv) {
    // Select the layer-shell Qt Wayland integration (the Qt 6.5+ replacement for
    // LayerShellQt::Shell::useLayerShell()). Must be set before QApplication.
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-panel"));
    app.setDesktopFileName(QStringLiteral("helm-panel"));
    helm::applyAppearance();
    helm::watchAppearance(); // re-tint live on a world/accent switch

    helm::Panel panel;
    panel.winId(); // realise the platform window so we can grab its QWindow

    // Promote to a layer-shell surface: anchor to the configured [panel] edge
    // (bottom by default, or top) and reserve an exclusive zone the height of the
    // bar so maximized windows don't cover it. Re-derived from config each call
    // so a live edge/height change re-anchors correctly.
    auto anchor = [&panel]() {
        const bool top = helm::PanelLayout::readEdge(helm::Config().path()) == QLatin1String("top");
        helm::applyLayerShell(
            panel.windowHandle(), LayerShellQt::Window::LayerTop,
            helm::edges(/*top*/ top, /*bottom*/ !top, /*left*/ true, /*right*/ true),
            panel.height(), LayerShellQt::Window::KeyboardInteractivityNone);
    };
    anchor();

    // Live config: rebuild the bar when hede.conf changes, then re-anchor the
    // surface (a changed edge or height takes effect without a restart).
    QObject::connect(&panel, &helm::Panel::reloaded, &panel, anchor);
    panel.watchConfig();

    panel.show();
    return app.exec();
}
