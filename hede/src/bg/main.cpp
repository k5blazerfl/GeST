#include "backgroundwidget.h"
#include "wallpaper.h"

#include "config.h"
#include "layershell.h"

#include <QApplication>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QGuiApplication>
#include <QList>
#include <QPointer>
#include <QScreen>
#include <QWindow>

namespace {

// One full-output background surface on the given screen.
helm::BackgroundWidget *spawnBackground(const helm::Wallpaper &wp, QScreen *screen) {
    auto *bg = new helm::BackgroundWidget(wp);
    bg->setAttribute(Qt::WA_DeleteOnClose);
    bg->winId(); // realise the platform window
    if (QWindow *win = bg->windowHandle()) {
        win->setScreen(screen);
        // Background layer, all edges, exclusiveZone -1 => fill the whole output
        // and sit *under* panels (ignore their exclusive zones).
        helm::applyLayerShell(win, LayerShellQt::Window::LayerBackground,
                              helm::edges(true, true, true, true), -1,
                              LayerShellQt::Window::KeyboardInteractivityNone);
    }
    bg->showFullScreen();
    return bg;
}

} // namespace

// helm-bg: draws the wallpaper on every output as a background layer-shell
// surface. The wallpaper is resolved from the active world (see loadWallpaper),
// and reloaded live when hede.conf changes so a world switch takes effect
// without a restart.
int main(int argc, char **argv) {
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-bg"));

    QList<QPointer<helm::BackgroundWidget>> live;
    auto spawnAll = [&live](const helm::Wallpaper &wp) {
        for (QScreen *s : QGuiApplication::screens())
            live << spawnBackground(wp, s);
    };
    spawnAll(helm::loadWallpaper(helm::Config()));

    // Cover monitors hotplugged after start-up too (re-reading current config).
    QObject::connect(qGuiApp, &QGuiApplication::screenAdded, [&live](QScreen *s) {
        live << spawnBackground(helm::loadWallpaper(helm::Config()), s);
    });

    // Live reload on a world/config switch: tear every surface down and rebuild
    // from the freshly resolved wallpaper.
    const QString cfgPath = helm::Config().path();
    auto *watcher = new QFileSystemWatcher(&app);
    // Watch the directory too: QSettings rewrites via a temp file + rename, which
    // drops the per-file watch, so we re-arm on every signal.
    watcher->addPath(QFileInfo(cfgPath).absolutePath());
    if (QFileInfo::exists(cfgPath))
        watcher->addPath(cfgPath);
    auto reload = [&live, &spawnAll, watcher, cfgPath]() {
        if (!watcher->files().contains(cfgPath) && QFileInfo::exists(cfgPath))
            watcher->addPath(cfgPath); // re-arm after an atomic rewrite
        const helm::Wallpaper wp = helm::loadWallpaper(helm::Config());
        for (auto &w : live)
            if (w)
                w->close(); // WA_DeleteOnClose
        live.clear();
        spawnAll(wp);
    };
    QObject::connect(watcher, &QFileSystemWatcher::fileChanged, &app, reload);
    QObject::connect(watcher, &QFileSystemWatcher::directoryChanged, &app, reload);

    return app.exec();
}
