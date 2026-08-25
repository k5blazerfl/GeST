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

// HeDE-specific extension interface on the same object: do-not-disturb toggle.
class HedeNotifyAdaptor : public QDBusAbstractAdaptor {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.gentoo.hede.Notifications")
    Q_PROPERTY(bool DoNotDisturb READ doNotDisturb)
  public:
    explicit HedeNotifyAdaptor(NotifyService *service);
    bool doNotDisturb() const;

  public slots: // NOLINT
    void SetDoNotDisturb(bool on);
    // Lantern history: a JSON array of past notifications, newest first (the
    // client parses it with helm::deserializeHistory). JSON keeps the wire
    // simple — no custom D-Bus struct marshalling for a same-project client.
    QString GetHistory();
    void ClearHistory();

  signals:
    void DoNotDisturbChanged(bool on);
    void NotificationAdded(const QString &json); // the newly-arrived notification, as JSON
    void HistoryCleared();

  private:
    NotifyService *m_service;
};

} // namespace helm
