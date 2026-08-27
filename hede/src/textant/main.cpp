#include "mainwindow.h"
#include "settings.h"

#include "palette.h"    // helm-appearance: applyAppearance / watchAppearance

#include <QApplication>

// Textant — the HeDE terminal. pty + libvterm + themed QWidget views, now in a
// tabbed window. See docs/design/textant.md for the phasing (P0–P3).
int main(int argc, char **argv) {
    // launchDetached correctness: never inherit the shell's layer-shell integration.
    qunsetenv("QT_WAYLAND_SHELL_INTEGRATION");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Textant"));
    app.setApplicationDisplayName(QStringLiteral("Textant"));
    app.setDesktopFileName(QStringLiteral("textant"));

    helm::applyAppearance();
    helm::watchAppearance();

    MainWindow window(Settings::load());
    window.resize(760, 460);
    window.show();
    return app.exec();
}
