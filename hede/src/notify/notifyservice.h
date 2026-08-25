#pragma once

#include <QObject>
#include <QVariantMap>
#include <QVector>

#include "notification.h"

namespace helm {

class ToastStack;

// Core notification server: owns the store, the persistent history, and the
// toast stack; allocates ids, resolves timeouts. D-Bus is layered on top by
// NotifyAdaptor. `toasts` may be null (headless — the history path still works),
// and `historyPath` defaults to helm::defaultHistoryPath() (override in tests).
class NotifyService : public QObject {
    Q_OBJECT
  public:
    explicit NotifyService(ToastStack *toasts, QObject *parent = nullptr,
                           const QString &historyPath = QString());

    uint notify(const QString &app, uint replacesId, const QString &icon, const QString &summary,
                const QString &body, const QStringList &actions, int expireTimeout,
                int urgency = UrgencyNormal);
    void closeNotification(uint id, uint reason); // reason 3 = closed via API

    bool doNotDisturb() const { return m_dnd; }
    void setDoNotDisturb(bool on);

    // Lantern's memory: the persistent, newest-first history (survives a toast's
    // dismissal, unlike the active store). clearHistory empties it and persists.
    const QVector<Notification> &history() const { return m_history; }
    void clearHistory();

  signals:
    void closed(uint id, uint reason);
    void actionInvoked(uint id, const QString &key);
    void dndChanged(bool on);
    void added(const Notification &n); // a notification just entered the history
    void historyCleared();

  private:
    ToastStack *m_toasts;
    QVector<Notification> m_store;
    QVector<Notification> m_history;
    QString m_historyPath;
    uint m_lastId = 0;
    bool m_dnd = false;
    static constexpr int kDefaultTimeoutMs = 5000;
    static constexpr int kHistoryCap = 200; // keep the last N; older drop off
};

} // namespace helm
