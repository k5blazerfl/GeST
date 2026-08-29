#include "petbridge.h"

#include "notification.h"

#include <QByteArray>
#include <QString>

#include <fcntl.h>
#include <sys/types.h>
#include <unistd.h>

#include <cstdlib>

namespace helm {

// Same resolution as helm-pet's own control FIFO (and the Python bridge).
static QString petFifoPath() {
    const char *rt = ::getenv("XDG_RUNTIME_DIR");
    if (rt && *rt)
        return QString::fromUtf8(rt) + QStringLiteral("/hiedi-pet.ctl");
    return QStringLiteral("/tmp/hiedi-pet-%1.ctl").arg(static_cast<uint>(::getuid()));
}

void petNotify(const Notification &n) {
    QString text = n.summary.simplified();
    const QString body = n.body.simplified();
    if (!body.isEmpty() && body != text)
        text = text.isEmpty() ? body : text + QStringLiteral(" — ") + body;
    const QString app = n.app.simplified();
    if (!app.isEmpty() && !text.contains(app, Qt::CaseInsensitive))
        text = app + QStringLiteral(": ") + text;
    if (text.isEmpty())
        return;

    const QByteArray line = "notify " + text.toUtf8() + "\n";
    const int fd = ::open(petFifoPath().toLocal8Bit().constData(), O_WRONLY | O_NONBLOCK);
    if (fd < 0)
        return; // pet not running — drop silently
    const ssize_t w = ::write(fd, line.constData(), static_cast<size_t>(line.size()));
    (void)w;
    ::close(fd);
}

} // namespace helm
