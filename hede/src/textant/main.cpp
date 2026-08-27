#include "pty.h"
#include "settings.h"
#include "terminalview.h"
#include "vtermsession.h"

#include "config.h"     // helm-common: helm::Config (hede.conf -> world accent)
#include "palette.h"    // helm-appearance: applyAppearance / effectiveAccent / barTint

#include <QApplication>
#include <QFileSystemWatcher>

// Textant P2 — the HeDE-native terminal: pty + libvterm + a themed QWidget that
// runs $SHELL, wears the active world's tint, and re-tints live on a world
// switch. (P0/P1 gave the terminal + scrollback/selection/config.)
int main(int argc, char **argv) {
    // launchDetached correctness: the HeDE shell exports
    // QT_WAYLAND_SHELL_INTEGRATION=layer-shell; a Qt app inheriting it comes up as
    // a frameless layer surface instead of a normal window. Scrub it before the
    // QApplication so Textant is always an ordinary xdg-toplevel, however launched.
    qunsetenv("QT_WAYLAND_SHELL_INTEGRATION");

    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Textant"));
    app.setApplicationDisplayName(QStringLiteral("Textant"));
    app.setDesktopFileName(QStringLiteral("textant"));

    // Match the shell's palette/style, and re-apply on a world/accent switch.
    helm::applyAppearance();
    helm::watchAppearance();

    const Settings cfg = Settings::load();

    constexpr int kRows = 24;
    constexpr int kCols = 80;

    Pty pty;
    VTermSession session(kRows, kCols);
    session.setScrollbackMax(cfg.scrollback);
    TerminalView view;
    view.setSession(&session);
    view.setPty(&pty);
    view.applyFont(cfg.fontFamily, cfg.fontSize);
    view.setOpacity(cfg.opacity);
    view.setWindowTitle(QStringLiteral("Textant"));

    // Tint the terminal surface from the active world's accent (helm-theme), and
    // re-tint live when hede.conf changes (a world switch).
    const auto applyWorldTint = [&session] {
        const helm::Config hc;
        const QColor accent = helm::effectiveAccent(hc);
        session.setDefaultColors(QColor(0xe9, 0xee, 0xf6), helm::barTint(accent));
    };
    applyWorldTint();

    const helm::Config hcForPath;
    auto *watcher = new QFileSystemWatcher(&app);
    watcher->addPath(hcForPath.path());
    QObject::connect(watcher, &QFileSystemWatcher::fileChanged, &app,
                     [watcher, applyWorldTint](const QString &path) {
                         applyWorldTint();
                         if (!watcher->files().contains(path))
                             watcher->addPath(path);   // re-arm after atomic replace
                     });

    // pty <-> session <-> view wiring.
    QObject::connect(&pty, &Pty::readyRead, &session, &VTermSession::writeInput);
    QObject::connect(&session, &VTermSession::outputReady, &pty,
                     [&pty](const QByteArray &b) { pty.write(b); });
    QObject::connect(&session, &VTermSession::titleChanged, &view,
                     [&view](const QString &t) {
                         view.setWindowTitle(t.isEmpty() ? QStringLiteral("Textant") : t);
                     });
    QObject::connect(&session, &VTermSession::bell, &app,
                     [] { QApplication::beep(); });
    QObject::connect(&pty, &Pty::exited, &app, &QApplication::quit);

    if (!pty.start(kRows, kCols)) {
        qWarning("textant: failed to start the shell");
        return 1;
    }

    view.resize(720, 430);
    view.show();
    return app.exec();
}
