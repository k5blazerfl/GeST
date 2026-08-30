#include "gqwindow.h"

#include "layershell.h"
#include "palette.h"

#include <QApplication>
#include <QDir>
#include <QLockFile>

// helm-gq — General Quarters, the Ctrl+Alt+Del interrupt surface. A
// full-screen LayerOverlay with exclusive keyboard (the helm-menu backdrop
// pattern): Esc or a scrim click dismisses; the verbs act through logind.
int main(int argc, char **argv) {
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-gq"));
    app.setDesktopFileName(QStringLiteral("helm-gq"));
    helm::applyAppearance();

    // One instance: mashing Ctrl+Alt+Del must not stack interrupt screens.
    QLockFile lock(QDir::temp().filePath(QStringLiteral("helm-gq.lock")));
    lock.setStaleLockTime(0);
    if (!lock.tryLock(0))
        return 0;

    helm::GqWindow window;
    window.winId(); // realise the platform window before layer promotion
    helm::applyLayerShell(
        window.windowHandle(), LayerShellQt::Window::LayerOverlay,
        helm::edges(/*top*/ true, /*bottom*/ true, /*left*/ true, /*right*/ true),
        /*exclusiveZone*/ 0, LayerShellQt::Window::KeyboardInteractivityExclusive);
    window.show();
    return app.exec();
}
