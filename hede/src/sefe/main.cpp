#include "window.h"

#include "palette.h"

#include <QApplication>
#include <QUrl>

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

    // Open a folder or archive passed on the command line, or via a file
    // association (Exec=sefe %U hands us a file:// URL). Archives open
    // browsed-in-place; empty opens Home. Seahorse is now the archive handler
    // too — the standalone Hold app folded in here.
    QString startPath;
    const QStringList args = app.arguments();
    if (args.size() > 1) {
        const QUrl url(args.at(1));
        startPath = url.isLocalFile() ? url.toLocalFile() : args.at(1);
    }

    helm::sefe::SefeWindow window(startPath);
    window.show();
    return app.exec();
}
