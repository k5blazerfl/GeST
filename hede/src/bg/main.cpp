#include "backgroundwidget.h"
#include "wallpaper.h"

#include "config.h"
#include "layershell.h"

#include <QApplication>
#include <QGuiApplication>
#include <QScreen>
#include <QWindow>

namespace {

// One full-output background surface on the given screen.
void spawnBackground(const helm::Wallpaper &wp, QScreen *screen) {
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
}

} // namespace

// helm-bg: draws the wallpaper on every output as a background layer-shell
// surface. Phase 1: solid colour or a single image with a fit mode.
int main(int argc, char **argv) {
    qputenv("QT_WAYLAND_SHELL_INTEGRATION", "layer-shell");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("helm-bg"));

    const helm::Config cfg;
    const helm::Wallpaper wp = helm::loadWallpaper(cfg);

    const auto screens = QGuiApplication::screens();
    for (QScreen *s : screens)
        spawnBackground(wp, s);

    // Cover monitors hotplugged after start-up too.
    QObject::connect(qGuiApp, &QGuiApplication::screenAdded,
                     [wp](QScreen *s) { spawnBackground(wp, s); });

    return app.exec();
}
