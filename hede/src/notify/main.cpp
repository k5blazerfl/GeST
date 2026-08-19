#include "notifyadaptor.h"
#include "notifyservice.h"
#include "toast.h"

#include "config.h"
#include "layershell.h"
#include "palette.h"

#include <QApplication>
#include <QDBusConnection>
#include <QWindow>

#include <cstdio>

// helm-notifyd: the org.freedesktop.Notifications daemon. Renders toasts in the
// bottom-right corner (above the bar, Windows-familiar) and speaks the fdo
// notification spec over the session bus.
int main(int argc, char **argv) {
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-notifyd"));
    helm::applyAppearance();
    helm::watchAppearance(); // re-tint live on a world/accent switch

    auto *toasts = new helm::ToastStack;
    toasts->winId();
    if (QWindow *win = toasts->windowHandle()) {
        // Bottom-right, clear of the bar (right + bottom margins).
        const int bottom = helm::Config().panelHeight() + 8;
        helm::applyLayerShell(win, LayerShellQt::Window::LayerOverlay,
                              helm::edges(/*top*/ false, /*bottom*/ true, /*left*/ false,
                                          /*right*/ true),
                              /*exclusiveZone*/ 0, LayerShellQt::Window::KeyboardInteractivityNone,
                              QMargins(0, 0, 8, bottom));
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
