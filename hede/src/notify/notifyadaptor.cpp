#include "notifyadaptor.h"

#include "history.h"
#include "notification.h"
#include "notifyservice.h"

#include <QDBusVariant>
#include <QJsonDocument>

namespace helm {

static int urgencyFromHints(const QVariantMap &hints) {
    if (!hints.contains(QStringLiteral("urgency")))
        return UrgencyNormal;
    QVariant v = hints.value(QStringLiteral("urgency"));
    if (v.canConvert<QDBusVariant>())
        v = v.value<QDBusVariant>().variant();
    bool ok = false;
    const int u = v.toInt(&ok);
    return ok ? u : UrgencyNormal;
}

NotifyAdaptor::NotifyAdaptor(NotifyService *service)
    : QDBusAbstractAdaptor(service), m_service(service) {
    // Relay the service's Qt signals out as D-Bus signals (signal→signal).
    connect(service, &NotifyService::closed, this, &NotifyAdaptor::NotificationClosed);
    connect(service, &NotifyService::actionInvoked, this, &NotifyAdaptor::ActionInvoked);
}

uint NotifyAdaptor::Notify(const QString &appName, uint replacesId, const QString &appIcon,
                           const QString &summary, const QString &body, const QStringList &actions,
                           const QVariantMap &hints, int expireTimeout) {
    return m_service->notify(appName, replacesId, appIcon, summary, body, actions, expireTimeout,
                             urgencyFromHints(hints));
}

void NotifyAdaptor::CloseNotification(uint id) {
    m_service->closeNotification(id, 3); // 3 = closed by CloseNotification call
}

QStringList NotifyAdaptor::GetCapabilities() {
    return serverCapabilities();
}

QString NotifyAdaptor::GetServerInformation(QString &vendor, QString &version,
                                            QString &specVersion) {
    vendor = QStringLiteral("HeDE");
    version = QStringLiteral("0.1");
    specVersion = QStringLiteral("1.2");
    return QStringLiteral("helm-notifyd");
}

// --- HeDE do-not-disturb extension ---

HedeNotifyAdaptor::HedeNotifyAdaptor(NotifyService *service)
    : QDBusAbstractAdaptor(service), m_service(service) {
    connect(service, &NotifyService::dndChanged, this, &HedeNotifyAdaptor::DoNotDisturbChanged);
    // Relay a new arrival out as JSON so a client can prepend it live.
    connect(service, &NotifyService::added, this, [this](const Notification &n) {
        emit NotificationAdded(
            QString::fromUtf8(QJsonDocument(notificationToJson(n)).toJson(QJsonDocument::Compact)));
    });
    connect(service, &NotifyService::historyCleared, this, &HedeNotifyAdaptor::HistoryCleared);
}

bool HedeNotifyAdaptor::doNotDisturb() const {
    return m_service->doNotDisturb();
}

void HedeNotifyAdaptor::SetDoNotDisturb(bool on) {
    m_service->setDoNotDisturb(on);
}

QString HedeNotifyAdaptor::GetHistory() {
    return QString::fromUtf8(serializeHistory(m_service->history()));
}

void HedeNotifyAdaptor::ClearHistory() {
    m_service->clearHistory();
}

} // namespace helm
