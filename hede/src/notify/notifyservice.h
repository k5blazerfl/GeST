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
                const QString &body, const QStringList &actions, int expireTimeout);
    void closeNotification(uint id, uint reason); // reason 3 = closed via API

  signals:
    void closed(uint id, uint reason);
    void actionInvoked(uint id, const QString &key);

  private:
    ToastStack *m_toasts;
    QVector<Notification> m_store;
    uint m_lastId = 0;
    static constexpr int kDefaultTimeoutMs = 5000;
};

} // namespace helm
