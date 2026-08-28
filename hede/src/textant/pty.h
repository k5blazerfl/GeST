#pragma once

#include <QObject>
#include <QByteArray>
#include <sys/types.h>

class QSocketNotifier;

// Owns the pseudo-terminal and the child shell process. Bytes the shell writes
// arrive as readyRead(); write() sends keystrokes down to it. A QSocketNotifier
// on the master fd drives reads — no polling.
class Pty : public QObject {
    Q_OBJECT
public:
    explicit Pty(QObject *parent = nullptr);
    ~Pty() override;

    // Fork a child running $SHELL (falls back to /bin/sh) on a fresh pty sized
    // rows x cols. Returns false if forkpty() failed.
    bool start(int rows, int cols);
    void write(const QByteArray &data);
    void resize(int rows, int cols);            // TIOCSWINSZ -> SIGWINCH
    bool isRunning() const { return m_pid > 0; }

signals:
    void readyRead(const QByteArray &data);
    void exited();

private:
    void onReadable();

    int m_fd = -1;
    pid_t m_pid = -1;
    QSocketNotifier *m_notifier = nullptr;
};
