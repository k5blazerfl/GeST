#pragma once

#include <QWidget>
#include <QColor>
#include <QString>

#include "settings.h"

class Pty;
class VTermSession;
class TerminalView;

// One terminal: a pty + libvterm session + view, wired together. A tab in the
// window owns one of these. (Before tabs this wiring lived in main().)
class Terminal : public QWidget {
    Q_OBJECT
public:
    explicit Terminal(const Settings &cfg, QWidget *parent = nullptr);

    void startShell();
    void setWorldColors(const QColor &fg, const QColor &bg);
    void applyFont(const QString &family, int pointSize);
    void copy();
    void paste();
    QString title() const { return m_title; }

signals:
    void titleChanged(const QString &title);
    void finished();                       // the shell exited

private:
    Pty *m_pty = nullptr;
    VTermSession *m_session = nullptr;
    TerminalView *m_view = nullptr;
    QString m_title = QStringLiteral("Textant");
};
