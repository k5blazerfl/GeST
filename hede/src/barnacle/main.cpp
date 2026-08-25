#include "window.h"

#include "palette.h"

#include <QApplication>

// helm-barnacle — the HeDE panel editor (docs/design/barnacle.md). An ordinary
// xdg-toplevel window (like sefe): arrange the applets on the bar and every
// change is written to hede.conf [panel] applets, which the bar picks up live
// (Panel::watchConfig). labwc draws the (SSD) titlebar; the session exports
// QT_WAYLAND_DISABLE_WINDOWDECORATION so Qt doesn't also draw one.
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-barnacle"));
    app.setApplicationDisplayName(QStringLiteral("Barnacle"));
    app.setDesktopFileName(QStringLiteral("barnacle"));
    helm::applyAppearance();
    helm::watchAppearance(); // re-tint live on a world/accent switch

    helm::BarnacleWindow window;
    window.show();
    return app.exec();
}
