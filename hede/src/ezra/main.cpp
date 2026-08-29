#include "window.h"

#include "palette.h"

#include <QApplication>

// ezra — EzRA, the HeDE task manager (docs/design/ezra.md). An ordinary
// xdg-toplevel window like barnacle: labwc draws the SSD titlebar. Bound to
// Ctrl+Shift+Esc in data/labwc/rc.xml.
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("ezra"));
    app.setApplicationDisplayName(QStringLiteral("EzRA"));
    app.setDesktopFileName(QStringLiteral("ezra"));
    helm::applyAppearance();
    helm::watchAppearance(); // re-tint live on a world/accent switch

    ezra::EzraWindow window;
    window.show();
    return app.exec();
}
