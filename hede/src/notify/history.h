#pragma once

#include "notification.h"

#include <QByteArray>
#include <QJsonObject>
#include <QString>
#include <QVector>

// Lantern's notification history — the daemon's memory (docs/design/lantern.md).
// helm-notifyd today drops a notification the moment its toast expires; these
// pure helpers give it a durable, bounded, newest-first log that the Lantern
// drawer reads. All logic is Core-only and unit-tested; the daemon wiring and
// the D-Bus retrieval API are later slices.
namespace helm {

// Record `n` into `history` as the newest entry (index 0). If an entry with the
// same id already exists (a replaces_id update), it is removed and re-inserted
// at the front, so the list stays newest-first with no duplicates. When cap > 0,
// the oldest entries beyond `cap` are dropped; cap <= 0 means unbounded.
void appendHistory(QVector<Notification> &history, const Notification &n, int cap);

// JSON (de)serialisation of a single notification, including `received` (ISO
// 8601) and `seen`. Round-trips: fromJson(toJson(n)) == n.
QJsonObject notificationToJson(const Notification &n);
Notification notificationFromJson(const QJsonObject &o);

// A whole history list ↔ a compact JSON array (the on-disk form).
QByteArray serializeHistory(const QVector<Notification> &history);
QVector<Notification> deserializeHistory(const QByteArray &json);

// Persist / restore the history to a file. saveHistory creates the parent
// directory as needed and returns false on write failure; loadHistory returns
// an empty list when the file is absent or unreadable (a fresh install).
bool saveHistory(const QString &path, const QVector<Notification> &history);
QVector<Notification> loadHistory(const QString &path);

// The default on-disk location: $XDG_DATA_HOME/hede/notifications.json.
QString defaultHistoryPath();

} // namespace helm
