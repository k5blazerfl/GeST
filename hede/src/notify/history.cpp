#include "history.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QStandardPaths>

namespace helm {

void appendHistory(QVector<Notification> &history, const Notification &n, int cap) {
    const int existing = indexOfId(history, n.id);
    if (existing >= 0)
        history.remove(existing); // a replaces_id update moves to the front
    history.prepend(n);
    if (cap > 0)
        while (history.size() > cap)
            history.removeLast(); // drop the oldest beyond the cap
}

QJsonObject notificationToJson(const Notification &n) {
    QJsonObject o;
    o[QStringLiteral("id")] = static_cast<qint64>(n.id);
    o[QStringLiteral("app")] = n.app;
    o[QStringLiteral("icon")] = n.icon;
    o[QStringLiteral("summary")] = n.summary;
    o[QStringLiteral("body")] = n.body;
    o[QStringLiteral("actions")] = QJsonArray::fromStringList(n.actions);
    o[QStringLiteral("timeoutMs")] = n.timeoutMs;
    o[QStringLiteral("urgency")] = n.urgency;
    o[QStringLiteral("received")] = n.received.toString(Qt::ISODate);
    o[QStringLiteral("seen")] = n.seen;
    return o;
}

Notification notificationFromJson(const QJsonObject &o) {
    Notification n;
    n.id = static_cast<uint>(o.value(QStringLiteral("id")).toInteger());
    n.app = o.value(QStringLiteral("app")).toString();
    n.icon = o.value(QStringLiteral("icon")).toString();
    n.summary = o.value(QStringLiteral("summary")).toString();
    n.body = o.value(QStringLiteral("body")).toString();
    const QJsonArray acts = o.value(QStringLiteral("actions")).toArray();
    for (const QJsonValue &v : acts)
        n.actions.append(v.toString());
    n.timeoutMs = o.value(QStringLiteral("timeoutMs")).toInt();
    n.urgency = o.value(QStringLiteral("urgency")).toInt(UrgencyNormal);
    n.received = QDateTime::fromString(o.value(QStringLiteral("received")).toString(), Qt::ISODate);
    n.seen = o.value(QStringLiteral("seen")).toBool();
    return n;
}

QByteArray serializeHistory(const QVector<Notification> &history) {
    QJsonArray arr;
    for (const Notification &n : history)
        arr.append(notificationToJson(n));
    return QJsonDocument(arr).toJson(QJsonDocument::Compact);
}

QVector<Notification> deserializeHistory(const QByteArray &json) {
    QVector<Notification> out;
    const QJsonDocument doc = QJsonDocument::fromJson(json);
    if (!doc.isArray())
        return out;
    const QJsonArray arr = doc.array();
    out.reserve(arr.size());
    for (const QJsonValue &v : arr)
        if (v.isObject())
            out.append(notificationFromJson(v.toObject()));
    return out;
}

bool saveHistory(const QString &path, const QVector<Notification> &history) {
    const QString dir = QFileInfo(path).absolutePath();
    if (!dir.isEmpty() && !QDir().mkpath(dir))
        return false;
    QFile f(path);
    if (!f.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    const QByteArray bytes = serializeHistory(history);
    return f.write(bytes) == bytes.size();
}

QVector<Notification> loadHistory(const QString &path) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly))
        return {}; // absent/unreadable → a fresh, empty history
    return deserializeHistory(f.readAll());
}

QString defaultHistoryPath() {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
    return base + QStringLiteral("/hede/notifications.json");
}

} // namespace helm
