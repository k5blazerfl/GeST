#include "theme.h"
#include "world.h"

#include <QCoreApplication>
#include <QProcess>

#include <cstdio>

// helm-theme: apply a HeDE appearance choice to GTK + the shell palette + the
// labwc titlebar skin.
//   helm-theme --dark --accent=#33d6c8 [--gtk-theme=Adwaita-dark] [--icon-theme=Papirus]
//   helm-theme --from-world     (seed from the active biome; run at session start)
//   helm-theme --list-worlds    (installed worlds, tab-sep: id name accent wallpaper)
//   helm-theme --world=<id>     (switch to a world; a running shell re-themes live)
//   helm-theme --emit-boot-theme=<dir> [--accent=#hex] [--world=<id>]
//                               (write the tinted Plymouth + GRUB boot theme and
//                                the world's boot scene into <dir>, no session
//                                side-effects; GeST's root SyncBootTheme uses this
//                                to re-tint + rebuild the initramfs. Accent/world
//                                default to the active session.)
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    const QStringList args = app.arguments().mid(1);

    QString emitDir, emitWorld;
    for (const QString &a : args) {
        if (a.startsWith(QStringLiteral("--emit-boot-theme=")))
            emitDir = a.section(QLatin1Char('='), 1);
        else if (a.startsWith(QStringLiteral("--world=")))
            emitWorld = a.section(QLatin1Char('='), 1);
    }
    if (!emitDir.isEmpty()) {
        // The biome to emit: explicit --world, else the active world. Its accent
        // tints the chrome unless --accent overrides; its boot.png is the scene.
        const QString world = emitWorld.isEmpty() ? helm::activeWorldId() : emitWorld;
        QString accent = helm::parseThemeArgs(args).accent; // --accent= or empty
        if (accent.isEmpty())
            accent = helm::loadWorld(world).accent;
        if (accent.isEmpty())
            accent = helm::activeAccent();
        QStringList written = helm::writeBootTheme(emitDir, accent);
        if (written.isEmpty()) {
            std::fprintf(stderr, "helm-theme: failed to write boot theme to %s\n",
                         qPrintable(emitDir));
            return 1;
        }
        const QString scene = helm::emitBootScene(emitDir, world);
        if (!scene.isEmpty())
            written << scene;
        for (const QString &p : written)
            std::printf("wrote %s\n", qPrintable(p));
        return 0;
    }

    if (args.contains(QStringLiteral("--list-worlds"))) {
        // One world per line, tab-separated: id, name, accent, wallpaper path.
        // A GUI picker reads this to build thumbnails without re-resolving worlds.
        for (const helm::World &w : helm::listWorlds())
            std::printf("%s\t%s\t%s\t%s\n", qPrintable(w.id), qPrintable(w.name),
                        qPrintable(w.accent), qPrintable(w.wallpaperPath()));
        return 0;
    }

    QString worldId;
    for (const QString &a : args)
        if (a.startsWith(QStringLiteral("--world=")))
            worldId = a.section(QLatin1Char('='), 1);
    if (!worldId.isEmpty()) {
        if (!helm::setWorld(worldId)) {
            std::fprintf(stderr, "helm-theme: unknown world '%s'\n", qPrintable(worldId));
            return 1;
        }
        // Nudge the running compositor to re-read the freshly written themerc.
        if (qEnvironmentVariableIsSet("WAYLAND_DISPLAY"))
            QProcess::startDetached(QStringLiteral("labwc"), {QStringLiteral("--reconfigure")});
        std::printf("switched to world %s\n", qPrintable(worldId));
        return 0;
    }

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
