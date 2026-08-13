#include "panel.h"

#include <QApplication>

#include <LayerShellQt/Window>

// Phase 0 helm-panel: a QtWidgets bar promoted to a wlr-layer-shell surface,
// anchored to the bottom edge with an exclusive zone so maximized windows do
// not cover it. Contents: a Terminal button + a clock (see Panel).
int main(int argc, char **argv) {
    // Select the layer-shell Qt Wayland integration (the Qt 6.5+ replacement for
    // LayerShellQt::Shell::useLayerShell()). Must be set before QApplication.
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-panel"));
    app.setDesktopFileName(QStringLiteral("helm-panel"));

    helm::Panel panel;
    panel.winId(); // realise the platform window so we can grab its QWindow

    if (auto *ls = LayerShellQt::Window::get(panel.windowHandle())) {
        ls->setLayer(LayerShellQt::Window::LayerTop);
        LayerShellQt::Window::Anchors anchors;
        anchors |= LayerShellQt::Window::AnchorBottom;
        anchors |= LayerShellQt::Window::AnchorLeft;
        anchors |= LayerShellQt::Window::AnchorRight;
        ls->setAnchors(anchors);
        ls->setExclusiveZone(panel.height());
        ls->setKeyboardInteractivity(LayerShellQt::Window::KeyboardInteractivityNone);
    }

    panel.show();
    return app.exec();
}
