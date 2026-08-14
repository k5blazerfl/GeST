#include "coreclient.h"

#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusServiceWatcher>

namespace helm {

// Kept in sync with gest/ipc/interface.py (SHELL_*).
static constexpr auto kService = "org.gentoo.gest.Shell";
static constexpr auto kPath = "/org/gentoo/gest/Shell";
static constexpr auto kIface = "org.gentoo.gest.Shell";

CoreClient::CoreClient(QObject *parent) : QObject(parent) {
    QDBusConnection bus = QDBusConnection::sessionBus();
    m_watcher = new QDBusServiceWatcher(QString::fromLatin1(kService), bus,
                                        QDBusServiceWatcher::WatchForRegistration |
                                            QDBusServiceWatcher::WatchForUnregistration,
                                        this);
    connect(m_watcher, &QDBusServiceWatcher::serviceRegistered, this, [this] { connectService(); });
    connect(m_watcher, &QDBusServiceWatcher::serviceUnregistered, this, [this] {
        setAvailable(false);
        setUpdateCount(0);
    });
    connectService(); // handle the service already being up
}

void CoreClient::connectService() {
    QDBusConnection::sessionBus().connect(
        QString::fromLatin1(kService), QString::fromLatin1(kPath), QString::fromLatin1(kIface),
        QStringLiteral("UpdatesChanged"), this, SLOT(onUpdatesChanged(uint)));
    fetch();
}

void CoreClient::fetch() {
    QDBusInterface iface(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                         QString::fromLatin1(kIface), QDBusConnection::sessionBus());
    setAvailable(iface.isValid());
    if (!iface.isValid())
        return;
    const QVariant v = iface.property("UpdateCount");
    if (v.isValid())
        setUpdateCount(v.toInt());
}

void CoreClient::onUpdatesChanged(uint count) {
    setAvailable(true);
    setUpdateCount(static_cast<int>(count));
}

void CoreClient::setAvailable(bool a) {
    if (m_available != a) {
        m_available = a;
        emit availabilityChanged(a);
    }
}

void CoreClient::setUpdateCount(int c) {
    if (m_updateCount != c) {
        m_updateCount = c;
        emit updateCountChanged(c);
    }
}

} // namespace helm
