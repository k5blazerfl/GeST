#include "launch.h"

#include <QProcess>
#include <QProcessEnvironment>

namespace helm {

bool launchDetached(const QString &program, const QStringList &arguments) {
    QProcess proc;
    proc.setProgram(program);
    proc.setArguments(arguments);
    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    // Drop Qt's client-side decoration (which doesn't draw under labwc) so the
    // compositor server-side-decorates the window. Without this a menu-launched
    // Qt app is frameless — the CSD titlebar never renders and no SSD is offered.
    env.insert(QStringLiteral("QT_WAYLAND_DISABLE_WINDOWDECORATION"), QStringLiteral("1"));
    proc.setProcessEnvironment(env);
    return proc.startDetached();
}

} // namespace helm
