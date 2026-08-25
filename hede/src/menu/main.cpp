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
    helm::watchAppearance(); // re-tint live on a world/accent switch

    helm::LauncherMenu menu;
    menu.winId(); // realise the platform window

    // A full-screen transparent backdrop anchored to every edge: the pullout card
    // sits bottom-left inside it (positioned by the backdrop's layout, tucked above
    // the panel), and any click that misses the card dismisses the menu
    // (LauncherMenu::mousePressEvent) — the reliable click-outside grab that
    // layer-shell / WindowDeactivate don't give us on labwc.
    helm::applyLayerShell(
        menu.windowHandle(), LayerShellQt::Window::LayerTop,
        helm::edges(/*top*/ true, /*bottom*/ true, /*left*/ true, /*right*/ true),
        /*exclusiveZone*/ 0, LayerShellQt::Window::KeyboardInteractivityOnDemand);

    menu.show();
    return app.exec();
}
