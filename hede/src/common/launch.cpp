#include "launch.h"

#include <QProcess>
#include <QProcessEnvironment>

namespace helm {

bool launchDetached(const QString &program, const QStringList &arguments) {
    QProcess proc;
    proc.setProgram(program);
    proc.setArguments(arguments);
    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    // The shell (helm-menu / helm-panel) runs with QT_WAYLAND_SHELL_INTEGRATION=
    // layer-shell so its OWN window is a layer surface. That env is inherited by
    // launched children, turning every menu/panel-launched Qt app into a layer
    // surface too — frameless, always-on-top, and unmanageable by labwc (the
    // Control Center came up as an unclosable fullscreen overlay). Drop it so
    // children get the default xdg-toplevel integration and labwc manages them
    // (titlebar, move, close) normally.
    env.remove(QStringLiteral("QT_WAYLAND_SHELL_INTEGRATION"));
    // Drop Qt's client-side decoration (which doesn't draw under labwc) so the
    // compositor server-side-decorates the now-toplevel window. Without this a
    // menu-launched Qt app is frameless — the CSD titlebar never renders.
    env.insert(QStringLiteral("QT_WAYLAND_DISABLE_WINDOWDECORATION"), QStringLiteral("1"));
    proc.setProcessEnvironment(env);
    return proc.startDetached();
}

} // namespace helm
