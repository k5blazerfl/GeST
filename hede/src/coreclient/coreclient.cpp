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
    connect(m_watcher, &QDBusServiceWatcher::serviceUnregistered, this,
            [this] { setAvailable(false); });
    connectService(); // handle the service already being up
}

bool CoreClient::batteryCharging() const {
    return m_batStatus == QLatin1String("Charging") || m_batStatus == QLatin1String("Full");
}

void CoreClient::connectService() {
    QDBusConnection bus = QDBusConnection::sessionBus();
    const QString svc = QString::fromLatin1(kService);
    const QString path = QString::fromLatin1(kPath);
    const QString iface = QString::fromLatin1(kIface);
    // Any change signal → re-read the scalar properties (old-style connect drops
    // the extra uint arg of UpdatesChanged).
    for (const char *sig : {"UpdatesChanged", "NetworkChanged", "BatteryChanged"})
        bus.connect(svc, path, iface, QLatin1String(sig), this, SLOT(refetch()));
    refetch();
}

void CoreClient::refetch() {
    QDBusInterface iface(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                         QString::fromLatin1(kIface), QDBusConnection::sessionBus());
    setAvailable(iface.isValid());
    if (!iface.isValid())
        return;

    const int uc = iface.property("UpdateCount").toInt();
    if (uc != m_updateCount) {
        m_updateCount = uc;
        emit updateCountChanged(uc);
    }

    const bool nc = iface.property("NetworkConnected").toBool();
    const QString nk = iface.property("NetworkKind").toString();
    const QString ni = iface.property("NetworkIface").toString();
    if (nc != m_netConnected || nk != m_netKind || ni != m_netIface) {
        m_netConnected = nc;
        m_netKind = nk.isEmpty() ? QStringLiteral("none") : nk;
        m_netIface = ni;
        emit networkChanged();
    }

    const bool bp = iface.property("BatteryPresent").toBool();
    const int pct = iface.property("BatteryPercent").toInt();
    const QString bs = iface.property("BatteryStatus").toString();
    if (bp != m_batPresent || pct != m_batPercent || bs != m_batStatus) {
        m_batPresent = bp;
        m_batPercent = pct;
        m_batStatus = bs.isEmpty() ? QStringLiteral("Unknown") : bs;
        emit batteryChanged();
    }
}

void CoreClient::setAvailable(bool a) {
    if (m_available != a) {
        m_available = a;
        emit availabilityChanged(a);
    }
}

} // namespace helm
