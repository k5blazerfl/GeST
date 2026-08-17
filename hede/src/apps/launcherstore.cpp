#include "launcherstore.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>

#include <algorithm>

namespace helm {

LauncherStore parseStore(const QByteArray &json) {
    LauncherStore s;
    const QJsonDocument doc = QJsonDocument::fromJson(json);
    if (!doc.isObject())
        return s;
    const QJsonObject root = doc.object();
    for (const QJsonValue &v : root.value(QStringLiteral("pinned")).toArray())
        if (v.isString())
            s.pinned << v.toString();
    const QJsonObject usage = root.value(QStringLiteral("usage")).toObject();
    for (auto it = usage.begin(); it != usage.end(); ++it) {
        const QJsonObject u = it.value().toObject();
        AppUsage a;
        a.count = u.value(QStringLiteral("count")).toInt();
        a.lastUsed = static_cast<qint64>(u.value(QStringLiteral("lastUsed")).toDouble());
        s.usage.insert(it.key(), a);
    }
    return s;
}

QByteArray serializeStore(const LauncherStore &s) {
    QJsonObject root;
    QJsonArray pinned;
    for (const QString &id : s.pinned)
        pinned.append(id);
    root.insert(QStringLiteral("pinned"), pinned);
    QJsonObject usage;
    for (auto it = s.usage.begin(); it != s.usage.end(); ++it) {
        QJsonObject u;
        u.insert(QStringLiteral("count"), it.value().count);
        u.insert(QStringLiteral("lastUsed"), static_cast<double>(it.value().lastUsed));
        usage.insert(it.key(), u);
    }
    root.insert(QStringLiteral("usage"), usage);
    return QJsonDocument(root).toJson(QJsonDocument::Compact);
}

QStringList recentIds(const LauncherStore &s, int n, const QStringList &exclude) {
    QStringList ids;
    for (auto it = s.usage.begin(); it != s.usage.end(); ++it)
        if (!exclude.contains(it.key()) && it.value().count > 0)
            ids << it.key();
    std::sort(ids.begin(), ids.end(), [&s](const QString &a, const QString &b) {
        const AppUsage &ua = s.usage[a];
        const AppUsage &ub = s.usage[b];
        if (ua.count != ub.count)
            return ua.count > ub.count;             // frequency first
        if (ua.lastUsed != ub.lastUsed)
            return ua.lastUsed > ub.lastUsed;        // then recency
        return a < b;                                // stable
    });
    if (n >= 0 && ids.size() > n)
        ids = ids.mid(0, n);
    return ids;
}

void recordLaunch(LauncherStore &s, const QString &id, qint64 nowEpoch) {
    if (id.isEmpty())
        return;
    AppUsage &a = s.usage[id];
    a.count += 1;
    a.lastUsed = nowEpoch;
}

void togglePin(LauncherStore &s, const QString &id) {
    if (id.isEmpty())
        return;
    if (s.pinned.contains(id))
        s.pinned.removeAll(id);
    else
        s.pinned << id;
}

QString launcherStorePath() {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
    return base + QStringLiteral("/hede/launcher.json");
}

LauncherStore loadStore() {
    QFile f(launcherStorePath());
    if (!f.open(QIODevice::ReadOnly))
        return {};
    return parseStore(f.readAll());
}

bool saveStore(const LauncherStore &s) {
    const QString path = launcherStorePath();
    QDir().mkpath(QFileInfo(path).absolutePath());
    QFile f(path);
    if (!f.open(QIODevice::WriteOnly | QIODevice::Truncate))
        return false;
    return f.write(serializeStore(s)) >= 0;
}

QStringList defaultPins(const QStringList &available) {
    // Installer-image staples, in a sensible order; kept only if present.
    static const QStringList wanted = {
        QStringLiteral("gest-install"), QStringLiteral("gest-settings"),
        QStringLiteral("foot"), QStringLiteral("firefox")};
    QStringList pins;
    for (const QString &id : wanted)
        if (available.contains(id))
            pins << id;
    return pins;
}

} // namespace helm
