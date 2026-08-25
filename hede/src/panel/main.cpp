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

    // Promote to a layer-shell surface: anchor to the configured [panel] edge and
    // reserve an exclusive zone the thickness of the bar so maximized windows
    // don't cover it. Horizontal edges (bottom/top) span left↔right and reserve
    // the bar's height; vertical edges (left/right) span top↔bottom and reserve
    // its width. Re-derived from config each call so a live edge/thickness change
    // re-anchors correctly (applyLayerShell is idempotent on the live surface).
    auto anchor = [&panel]() {
        const QString edge = helm::PanelLayout::readEdge(helm::Config().path());
        LayerShellQt::Window::Anchors anchors;
        int zone;
        if (edge == QLatin1String("top")) {
            anchors = helm::edges(true, false, true, true);
            zone = panel.height();
        } else if (edge == QLatin1String("left")) {
            anchors = helm::edges(true, true, true, false);
            zone = panel.width();
        } else if (edge == QLatin1String("right")) {
            anchors = helm::edges(true, true, false, true);
            zone = panel.width();
        } else { // bottom (default)
            anchors = helm::edges(false, true, true, true);
            zone = panel.height();
        }
        helm::applyLayerShell(panel.windowHandle(), LayerShellQt::Window::LayerTop, anchors, zone,
                              LayerShellQt::Window::KeyboardInteractivityNone);
    };
    anchor();

    // Live config: rebuild the bar when hede.conf changes, then re-anchor the
    // surface (a changed edge or height takes effect without a restart).
    QObject::connect(&panel, &helm::Panel::reloaded, &panel, anchor);
    panel.watchConfig();

    panel.show();
    return app.exec();
}
