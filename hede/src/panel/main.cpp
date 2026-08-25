#include "panel.h"

#include "layershell.h"
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

    // Promote to a layer-shell surface, reserving an exclusive zone the height of
    // the bar. Factored so a live [panel] height change can re-reserve it.
    auto anchorBar = [&panel](int height) {
        helm::applyLayerShell(
            panel.windowHandle(), LayerShellQt::Window::LayerTop,
            helm::edges(/*top*/ false, /*bottom*/ true, /*left*/ true, /*right*/ true), height,
            LayerShellQt::Window::KeyboardInteractivityNone);
    };
    anchorBar(panel.height());

    // Live config: rebuild the bar when hede.conf changes, and re-reserve the
    // exclusive zone if the height changed with it.
    QObject::connect(&panel, &helm::Panel::heightChanged, &panel, anchorBar);
    panel.watchConfig();

    panel.show();
    return app.exec();
}
