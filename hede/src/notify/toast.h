#pragma once

#include <QHash>
#include <QWidget>

#include "notification.h"

class QVBoxLayout;
class QTimer;

namespace helm {

// A stack of toast cards in the top-right corner (one layer-shell surface that
// grows with content). Emits when a toast is dismissed or its default action is
// invoked, so the service can relay NotificationClosed / ActionInvoked.
class ToastStack : public QWidget {
    Q_OBJECT
  public:
    explicit ToastStack(QWidget *parent = nullptr);

    void showNotification(const Notification &n); // add or update
    void closeNotification(uint id);              // remove without emitting

  signals:
    void dismissed(uint id, uint reason); // 1 expired, 2 user
    void actionInvoked(uint id, const QString &key);

  private:
    void expire(uint id);
    void userClicked(uint id, bool hasDefault);

    QVBoxLayout *m_layout;
    QHash<uint, QWidget *> m_cards;
    QHash<uint, QTimer *> m_timers;
};

} // namespace helm
