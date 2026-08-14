#include "panel.h"

#include "layershell.h"

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

    helm::Panel panel;
    panel.winId(); // realise the platform window so we can grab its QWindow

    helm::applyLayerShell(
        panel.windowHandle(), LayerShellQt::Window::LayerTop,
        helm::edges(/*top*/ false, /*bottom*/ true, /*left*/ true, /*right*/ true), panel.height(),
        LayerShellQt::Window::KeyboardInteractivityNone);

    panel.show();
    return app.exec();
}
