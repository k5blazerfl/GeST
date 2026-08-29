#include "autostart.h"

#include "launch.h"

#include <QCoreApplication>

// helm-autostart — run the session's XDG autostart entries (autostart-spec):
// $XDG_CONFIG_HOME/autostart shadowing $XDG_CONFIG_DIRS/autostart, honoring
// Hidden and OnlyShowIn/NotShowIn against XDG_CURRENT_DESKTOP. Launched once
// from the labwc autostart file; entries start detached and this exits.
// EzRA's Startup tab manages the same entries.
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);

    const QString desktop =
        qEnvironmentVariable("XDG_CURRENT_DESKTOP", QStringLiteral("HeDE"))
            .section(QLatin1Char(':'), 0, 0);
    const QVector<helm::AutostartEntry> entries =
        helm::scanAutostart(helm::defaultAutostartDirs(), desktop);
    for (const helm::AutostartEntry &a : entries) {
        if (!a.enabled)
            continue;
        QStringList args = helm::commandArgv(a.entry);
        if (args.isEmpty())
            continue;
        const QString program = args.takeFirst();
        helm::launchDetached(program, args);
    }
    return 0;
}
