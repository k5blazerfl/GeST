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
    const QStringList args = app.arguments();
    const int tabFlag = args.indexOf(QStringLiteral("--tab"));
    if (tabFlag >= 0 && tabFlag + 1 < args.size())
        window.selectTab(args.at(tabFlag + 1));
    window.show();
    return app.exec();
}
