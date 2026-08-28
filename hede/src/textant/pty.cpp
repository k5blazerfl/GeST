#include "pty.h"

#include <QSocketNotifier>

#include <pty.h>          // forkpty()
#include <unistd.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <csignal>
#include <cstdlib>
#include <cerrno>

Pty::Pty(QObject *parent) : QObject(parent) {}

Pty::~Pty() {
    if (m_notifier)
        m_notifier->setEnabled(false);
    if (m_pid > 0)
        ::kill(m_pid, SIGHUP);
    if (m_fd >= 0)
        ::close(m_fd);
}

bool Pty::start(int rows, int cols) {
    struct winsize ws {};
    ws.ws_row = static_cast<unsigned short>(rows > 0 ? rows : 24);
    ws.ws_col = static_cast<unsigned short>(cols > 0 ? cols : 80);

    int master = -1;
    pid_t pid = ::forkpty(&master, nullptr, nullptr, &ws);
    if (pid < 0)
        return false;

    if (pid == 0) {
        // Child: hand the pty off to an interactive shell.
        ::setenv("TERM", "xterm-256color", 1);
        ::unsetenv("COLUMNS");
        ::unsetenv("LINES");
        const char *shell = ::getenv("SHELL");
        if (!shell || !*shell)
            shell = "/bin/sh";
        ::execl(shell, shell, "-i", nullptr);
        ::_exit(127);    // exec failed
    }

    // Parent: drive the master fd non-blocking off a read notifier.
    m_fd = master;
    m_pid = pid;
    ::fcntl(m_fd, F_SETFL, ::fcntl(m_fd, F_GETFL, 0) | O_NONBLOCK);
    m_notifier = new QSocketNotifier(m_fd, QSocketNotifier::Read, this);
    connect(m_notifier, &QSocketNotifier::activated, this, &Pty::onReadable);
    return true;
}

void Pty::write(const QByteArray &data) {
    if (m_fd < 0)
        return;
    qsizetype off = 0;
    while (off < data.size()) {
        ssize_t n = ::write(m_fd, data.constData() + off, static_cast<size_t>(data.size() - off));
        if (n < 0) {
            if (errno == EINTR)
                continue;
            break;    // EAGAIN etc. — keystrokes are tiny; drop rather than block
        }
        off += n;
    }
}

void Pty::resize(int rows, int cols) {
    if (m_fd < 0 || rows <= 0 || cols <= 0)
        return;
    struct winsize ws {};
    ws.ws_row = static_cast<unsigned short>(rows);
    ws.ws_col = static_cast<unsigned short>(cols);
    ::ioctl(m_fd, TIOCSWINSZ, &ws);
}

void Pty::onReadable() {
    char buf[8192];
    for (;;) {
        ssize_t n = ::read(m_fd, buf, sizeof(buf));
        if (n > 0) {
            emit readyRead(QByteArray(buf, static_cast<int>(n)));
            if (n < static_cast<ssize_t>(sizeof(buf)))
                break;                 // likely drained
        } else if (n == 0) {
            m_notifier->setEnabled(false);
            emit exited();
            break;
        } else {
            if (errno == EINTR)
                continue;
            if (errno == EAGAIN || errno == EWOULDBLOCK)
                break;                 // drained — nothing left for now
            // Linux returns -1/EIO (not 0) once the slave is closed: the shell
            // is gone. Treat any other error as end-of-session too.
            m_notifier->setEnabled(false);
            emit exited();
            break;
        }
    }
}
