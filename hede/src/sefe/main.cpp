#include "window.h"

#include "palette.h"

#include <QApplication>

// SeFE — the Seahorse File Explorer (docs/design/sefe.md). Slice 1 "Hull": an
// ordinary xdg-toplevel window — the FIRST in HeDE; the panel/menu/bg/notify
// binaries are all wlr-layer-shell surfaces — that opens Home read-only and is
// themed by the active biome. labwc draws the (SSD) titlebar; the session
// exports QT_WAYLAND_DISABLE_WINDOWDECORATION so Qt doesn't also draw one.
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("sefe"));
    app.setApplicationDisplayName(QStringLiteral("Seahorse"));
    app.setDesktopFileName(QStringLiteral("sefe"));
    helm::applyAppearance();
    helm::watchAppearance(); // re-tint live on a world/accent switch

    helm::sefe::SefeWindow window;
    window.show();
    return app.exec();
}
