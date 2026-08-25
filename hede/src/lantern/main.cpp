#include "window.h"

#include "config.h"
#include "layershell.h"
#include "palette.h"

#include <QApplication>
#include <QWindow>

// helm-lantern — the HeDE notification center (docs/design/lantern.md). A
// right-edge wlr-layer-shell slide-out (LayerOverlay, exclusiveZone 0 so it
// floats over windows without reserving space), anchored full-height and clear
// of the bar. A one-shot surface like helm-menu: a trigger launches it, Esc /
// click-away dismisses it. It reads its history over D-Bus from helm-notifyd.
int main(int argc, char **argv) {
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-lantern"));
    app.setApplicationDisplayName(QStringLiteral("Notifications"));
    app.setDesktopFileName(QStringLiteral("helm-lantern"));
    helm::applyAppearance();
    helm::watchAppearance(); // re-tint live on a world/accent switch

    helm::LanternWindow win;
    win.winId(); // realise the platform window so we can grab its QWindow

    if (QWindow *w = win.windowHandle()) {
        const int bottom = helm::Config().panelHeight(); // clear the bar
        helm::applyLayerShell(w, LayerShellQt::Window::LayerOverlay,
                              helm::edges(/*top*/ true, /*bottom*/ true, /*left*/ false,
                                          /*right*/ true),
                              /*exclusiveZone*/ 0,
                              LayerShellQt::Window::KeyboardInteractivityOnDemand,
                              QMargins(0, 0, 0, bottom));
    }

    win.show();
    win.activateWindow();
    return app.exec();
}
