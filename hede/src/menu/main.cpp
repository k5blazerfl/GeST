#include "launchermenu.h"
#include "layershell.h"
#include "palette.h"

#include "config.h"

#include <QApplication>

// helm-menu: the Start menu. A layer-shell popup anchored bottom-left, tucked
// just above the panel (the pullout standard: it sits at the bar's chrome layer,
// bar in front, flat bottom against the bar). Phase 1 first cut: one instance
// per invocation; it quits after launching an app or on Esc.
int main(int argc, char **argv) {
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-menu"));
    app.setDesktopFileName(QStringLiteral("helm-menu"));
    helm::applyAppearance();

    const helm::Config cfg;

    helm::LauncherMenu menu;
    menu.winId(); // realise the platform window

    helm::applyLayerShell(
        menu.windowHandle(), LayerShellQt::Window::LayerTop, // bar's layer — bar stays in front
        helm::edges(/*top*/ false, /*bottom*/ true, /*left*/ true, /*right*/ false),
        /*exclusiveZone*/ 0, LayerShellQt::Window::KeyboardInteractivityOnDemand,
        QMargins(0, 0, 0, cfg.panelHeight()));

    menu.show();
    return app.exec();
}
