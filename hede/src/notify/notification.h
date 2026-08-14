#pragma once

#include <QString>
#include <QStringList>
#include <QVector>

namespace helm {

// A live notification (the subset the daemon renders + tracks).
struct Notification {
    uint id = 0;
    QString app;
    QString icon;
    QString summary;
    QString body;
    QStringList actions; // (key, label) pairs, flattened per the fdo spec
    int timeoutMs = 0;   // resolved: 0 = persist, >0 = auto-close after ms
};

// --- pure helpers (unit-tested) ---

// Monotonic id allocation; never returns 0 (0 means "allocate" in Notify).
uint nextNotificationId(uint last);

// fdo expire_timeout: <0 → server default; 0 → never expire; >0 → that many ms.
int resolveTimeout(int expireTimeout, int defaultMs);

// The capabilities we advertise via GetCapabilities().
QStringList serverCapabilities();

// --- store ops on a list keyed by id ---
int indexOfId(const QVector<Notification> &list, uint id);
void putNotification(QVector<Notification> &list, const Notification &n); // add or replace
void dropNotification(QVector<Notification> &list, uint id);

} // namespace helm
