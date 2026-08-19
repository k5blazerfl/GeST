#include "theme.h"

#include <QCoreApplication>
#include <QProcess>

#include <cstdio>

// helm-theme: apply a HeDE appearance choice to GTK + the shell palette + the
// labwc titlebar skin.
//   helm-theme --dark --accent=#33d6c8 [--gtk-theme=Adwaita-dark] [--icon-theme=Papirus]
//   helm-theme --from-world   (seed from the active biome; run at session start)
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    const QStringList args = app.arguments().mid(1);
    const QStringList written = args.contains(QStringLiteral("--from-world"))
                                    ? helm::applyThemeFromWorld()
                                    : helm::applyTheme(helm::parseThemeArgs(args));
    if (written.isEmpty()) {
        std::fprintf(stderr, "helm-theme: failed to write any config\n");
        return 1;
    }
    for (const QString &p : written)
        std::printf("wrote %s\n", qPrintable(p));

    // Best-effort live re-tint: labwc --reconfigure signals the running
    // compositor (via $LABWC_PID) to re-read its themerc. Harmless no-op if
    // there's no session or labwc isn't running.
    if (qEnvironmentVariableIsSet("WAYLAND_DISPLAY"))
        QProcess::startDetached(QStringLiteral("labwc"), {QStringLiteral("--reconfigure")});
    return 0;
}
