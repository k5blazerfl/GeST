#pragma once

#include "notification.h"

#include <QObject>
#include <QVector>

namespace helm {

// Lantern's D-Bus client of helm-notifyd's HeDE extension interface
// (org.gentoo.hede.Notifications — slice 2): reads the history, clears it,
// toggles do-not-disturb, and relays the daemon's live signals as Qt signals.
class LanternClient : public QObject {
    Q_OBJECT
  public:
    explicit LanternClient(QObject *parent = nullptr);

    bool daemonAvailable() const;             // is helm-notifyd on the bus?
    QVector<Notification> history() const;    // GetHistory(), parsed
    void clearHistory();                      // ClearHistory()
    bool doNotDisturb() const;                // DoNotDisturb property
    void setDoNotDisturb(bool on);            // SetDoNotDisturb()

    // Pure: parse the JSON array GetHistory returns (reuses deserializeHistory).
    static QVector<Notification> parseHistory(const QString &json);

  Q_SIGNALS:
    void historyChanged();  // a notification arrived, or the history was cleared
    void dndChanged(bool on);

  private Q_SLOTS:
    void onNotificationAdded(const QString &json);
    void onHistoryCleared();
    void onDoNotDisturbChanged(bool on);
};

} // namespace helm
