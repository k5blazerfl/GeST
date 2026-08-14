#pragma once

#include <QObject>
#include <QVariantMap>
#include <QVector>

#include "notification.h"

namespace helm {

class ToastStack;

// Core notification server: owns the store + the toast stack, allocates ids,
// resolves timeouts. D-Bus is layered on top by NotifyAdaptor.
class NotifyService : public QObject {
    Q_OBJECT
  public:
    explicit NotifyService(ToastStack *toasts, QObject *parent = nullptr);

    uint notify(const QString &app, uint replacesId, const QString &icon, const QString &summary,
                const QString &body, const QStringList &actions, int expireTimeout,
                int urgency = UrgencyNormal);
    void closeNotification(uint id, uint reason); // reason 3 = closed via API

    bool doNotDisturb() const { return m_dnd; }
    void setDoNotDisturb(bool on);

  signals:
    void closed(uint id, uint reason);
    void actionInvoked(uint id, const QString &key);
    void dndChanged(bool on);

  private:
    ToastStack *m_toasts;
    QVector<Notification> m_store;
    uint m_lastId = 0;
    bool m_dnd = false;
    static constexpr int kDefaultTimeoutMs = 5000;
};

} // namespace helm
