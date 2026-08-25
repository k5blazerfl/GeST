#include "client.h"

#include "history.h"

#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusReply>

namespace helm {

// The helm-notifyd object + the HeDE extension interface it exports (kept in
// sync with src/notify and src/quicksettings/dndtoggle.cpp).
static constexpr auto kService = "org.freedesktop.Notifications";
static constexpr auto kPath = "/org/freedesktop/Notifications";
static constexpr auto kHedeIface = "org.gentoo.hede.Notifications";

static QDBusInterface hedeIface() {
    return QDBusInterface(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                          QString::fromLatin1(kHedeIface), QDBusConnection::sessionBus());
}

LanternClient::LanternClient(QObject *parent) : QObject(parent) {
    QDBusConnection bus = QDBusConnection::sessionBus();
    bus.connect(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                QString::fromLatin1(kHedeIface), QStringLiteral("NotificationAdded"), this,
                SLOT(onNotificationAdded(QString)));
    bus.connect(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                QString::fromLatin1(kHedeIface), QStringLiteral("HistoryCleared"), this,
                SLOT(onHistoryCleared()));
    bus.connect(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                QString::fromLatin1(kHedeIface), QStringLiteral("DoNotDisturbChanged"), this,
                SLOT(onDoNotDisturbChanged(bool)));
}

bool LanternClient::daemonAvailable() const {
    return hedeIface().isValid();
}

QVector<Notification> LanternClient::history() const {
    QDBusInterface iface = hedeIface();
    if (!iface.isValid())
        return {};
    const QDBusReply<QString> reply = iface.call(QStringLiteral("GetHistory"));
    if (!reply.isValid())
        return {};
    return parseHistory(reply.value());
}

void LanternClient::clearHistory() {
    QDBusInterface iface = hedeIface();
    if (iface.isValid())
        iface.asyncCall(QStringLiteral("ClearHistory"));
}

bool LanternClient::doNotDisturb() const {
    QDBusInterface iface = hedeIface();
    return iface.isValid() && iface.property("DoNotDisturb").toBool();
}

void LanternClient::setDoNotDisturb(bool on) {
    QDBusInterface iface = hedeIface();
    if (iface.isValid())
        iface.asyncCall(QStringLiteral("SetDoNotDisturb"), on);
}

QVector<Notification> LanternClient::parseHistory(const QString &json) {
    return deserializeHistory(json.toUtf8());
}

void LanternClient::onNotificationAdded(const QString &) { emit historyChanged(); }
void LanternClient::onHistoryCleared() { emit historyChanged(); }
void LanternClient::onDoNotDisturbChanged(bool on) { emit dndChanged(on); }

} // namespace helm
