#include "notifyadaptor.h"

#include "notification.h"
#include "notifyservice.h"

namespace helm {

NotifyAdaptor::NotifyAdaptor(NotifyService *service)
    : QDBusAbstractAdaptor(service), m_service(service) {
    // Relay the service's Qt signals out as D-Bus signals (signal→signal).
    connect(service, &NotifyService::closed, this, &NotifyAdaptor::NotificationClosed);
    connect(service, &NotifyService::actionInvoked, this, &NotifyAdaptor::ActionInvoked);
}

uint NotifyAdaptor::Notify(const QString &appName, uint replacesId, const QString &appIcon,
                           const QString &summary, const QString &body, const QStringList &actions,
                           const QVariantMap &hints, int expireTimeout) {
    Q_UNUSED(hints);
    return m_service->notify(appName, replacesId, appIcon, summary, body, actions, expireTimeout);
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

} // namespace helm
