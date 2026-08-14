#include "notifyadaptor.h"
#include "notifyservice.h"
#include "toast.h"

#include "layershell.h"

#include <QApplication>
#include <QDBusConnection>
#include <QWindow>

#include <cstdio>

// helm-notifyd: the org.freedesktop.Notifications daemon. Renders toasts in the
// top-right corner and speaks the fdo notification spec over the session bus.
int main(int argc, char **argv) {
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-notifyd"));

    auto *toasts = new helm::ToastStack;
    toasts->winId();
    if (QWindow *win = toasts->windowHandle()) {
        helm::applyLayerShell(win, LayerShellQt::Window::LayerOverlay,
                              helm::edges(/*top*/ true, /*bottom*/ false, /*left*/ false,
                                          /*right*/ true),
                              /*exclusiveZone*/ 0, LayerShellQt::Window::KeyboardInteractivityNone,
                              QMargins(0, 8, 8, 0));
    }
    toasts->show();

    auto *service = new helm::NotifyService(toasts, &app);
    new helm::NotifyAdaptor(service);     // org.freedesktop.Notifications
    new helm::HedeNotifyAdaptor(service); // org.gentoo.hede.Notifications (DND)

    QDBusConnection bus = QDBusConnection::sessionBus();
    if (!bus.registerObject(QStringLiteral("/org/freedesktop/Notifications"), service)) {
        std::fprintf(stderr, "helm-notifyd: could not register D-Bus object\n");
        return 1;
    }
    if (!bus.registerService(QStringLiteral("org.freedesktop.Notifications"))) {
        std::fprintf(stderr, "helm-notifyd: org.freedesktop.Notifications already owned "
                             "(another daemon running?)\n");
        return 1;
    }

    return app.exec();
}
