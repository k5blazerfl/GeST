#include "identitymap.h"

#include "desktopentry.h"

#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>

namespace helm {

IdentityResolver::IdentityResolver() { reload(); }

QString IdentityResolver::identityPath() {
    const QString base = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
    return base + QStringLiteral("/hede/customs/identity.json");
}

QString IdentityResolver::normalizeKey(const QString &key) {
    QString k = key.trimmed().toLower();
    const int nul = k.indexOf(QChar(u'\0'));
    if (nul >= 0)
        k = k.left(nul);
    return k;
}

void IdentityResolver::reload() {
    m_byKey.clear();
    QFile f(identityPath());
    if (!f.open(QIODevice::ReadOnly))
        return;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll());
    if (!doc.isObject())
        return;
    // Shape: {"version":1,"map":{ normalized_key: desktop_id }}.
    const QJsonObject map = doc.object().value(QStringLiteral("map")).toObject();
    for (auto it = map.begin(); it != map.end(); ++it) {
        const QString id = it.value().toString();
        if (!id.isEmpty())
            m_byKey.insert(normalizeKey(it.key()), id);
    }
}

WindowIdentity IdentityResolver::resolve(const QString &appId) const {
    const QString desktopId = m_byKey.value(normalizeKey(appId));
    if (desktopId.isEmpty())
        return {};
    const auto cached = m_cache.constFind(desktopId);
    if (cached != m_cache.constEnd())
        return cached.value();
    const WindowIdentity wi = entryForDesktopId(desktopId);
    if (wi.found)
        m_cache.insert(desktopId, wi); // memo hits only; a not-yet-installed
                                       // launcher is retried on the next rebuild
    return wi;
}

WindowIdentity IdentityResolver::entryForDesktopId(const QString &desktopId) const {
    const QString fileName = desktopId + QStringLiteral(".desktop");
    for (const QString &dirPath : defaultApplicationDirs()) {
        const QString path = QDir(dirPath).filePath(fileName);
        QFile f(path);
        if (!f.open(QIODevice::ReadOnly | QIODevice::Text))
            continue;
        const DesktopEntry e = parseDesktopEntry(QString::fromUtf8(f.readAll()), desktopId);
        WindowIdentity wi;
        wi.found = !e.name.isEmpty() || !e.icon.isEmpty();
        wi.iconName = e.icon;
        wi.name = e.name;
        return wi;
    }
    return {};
}

} // namespace helm
