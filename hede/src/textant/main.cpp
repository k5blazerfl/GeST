#include "config.h"
#include "pty.h"
#include "terminalview.h"
#include "vtermsession.h"

#include <QApplication>

// Textant P0 — a first-light terminal: pty + libvterm + a QWidget surface that
// runs $SHELL. Ugly but usable; scrollback, selection, theming and default-terminal
// registration follow in P1/P2 (see docs/design/textant.md).
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Textant"));
    app.setApplicationDisplayName(QStringLiteral("Textant"));
    app.setDesktopFileName(QStringLiteral("textant"));

    constexpr int kRows = 24;
    constexpr int kCols = 80;

    const Config cfg = Config::load();

    Pty pty;
    VTermSession session(kRows, kCols);
    session.setScrollbackMax(cfg.scrollback);
    TerminalView view;
    view.setSession(&session);
    view.setPty(&pty);
    view.applyFont(cfg.fontFamily, cfg.fontSize);
    view.setWindowTitle(QStringLiteral("Textant"));

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
    view.show();          // first resizeEvent syncs the real grid to pty + session
    return app.exec();
}
