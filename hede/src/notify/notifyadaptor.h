#pragma once

#include <QDBusAbstractAdaptor>
#include <QStringList>
#include <QVariantMap>

namespace helm {

class NotifyService;

// org.freedesktop.Notifications D-Bus interface, backed by NotifyService.
class NotifyAdaptor : public QDBusAbstractAdaptor {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.freedesktop.Notifications")
  public:
    explicit NotifyAdaptor(NotifyService *service);

  public slots: // NOLINT — D-Bus method names must match the spec exactly
    uint Notify(const QString &appName, uint replacesId, const QString &appIcon,
                const QString &summary, const QString &body, const QStringList &actions,
                const QVariantMap &hints, int expireTimeout);
    void CloseNotification(uint id);
    QStringList GetCapabilities();
    QString GetServerInformation(QString &vendor, QString &version, QString &specVersion);

  signals:
    void NotificationClosed(uint id, uint reason);
    void ActionInvoked(uint id, const QString &actionKey);

  private:
    NotifyService *m_service;
};

} // namespace helm
