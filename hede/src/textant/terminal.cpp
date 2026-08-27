#include "terminal.h"

#include "pty.h"
#include "terminalview.h"
#include "vtermsession.h"

#include <QApplication>
#include <QVBoxLayout>

Terminal::Terminal(const Settings &cfg, QWidget *parent) : QWidget(parent) {
    m_pty = new Pty(this);
    m_session = new VTermSession(24, 80, this);
    m_session->setScrollbackMax(cfg.scrollback);

    m_view = new TerminalView(this);
    m_view->setSession(m_session);
    m_view->setPty(m_pty);
    m_view->applyFont(cfg.fontFamily, cfg.fontSize);
    m_view->setOpacity(cfg.opacity);

    auto *lay = new QVBoxLayout(this);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->addWidget(m_view);
    setFocusProxy(m_view);

    connect(m_pty, &Pty::readyRead, m_session, &VTermSession::writeInput);
    connect(m_session, &VTermSession::outputReady, m_pty,
            [this](const QByteArray &b) { m_pty->write(b); });
    connect(m_session, &VTermSession::titleChanged, this, [this](const QString &t) {
        m_title = t.isEmpty() ? QStringLiteral("Textant") : t;
        emit titleChanged(m_title);
    });
    connect(m_session, &VTermSession::bell, this, [] { QApplication::beep(); });
    connect(m_pty, &Pty::exited, this, &Terminal::finished);
}

void Terminal::startShell() {
    if (!m_pty->start(24, 80))
        qWarning("textant: failed to start the shell");
}

void Terminal::setWorldColors(const QColor &fg, const QColor &bg) {
    m_session->setDefaultColors(fg, bg);
}
