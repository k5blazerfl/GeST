#include "snimodel.h"

namespace helm {

QString hostName(qint64 pid) {
    return QStringLiteral("org.kde.StatusNotifierHost-%1").arg(pid);
}

SniId parseItemService(const QString &arg, const QString &senderUnique) {
    SniId id;
    if (arg.startsWith(QLatin1Char('/'))) {
        // just an object path → the sender owns it
        id.service = senderUnique;
        id.path = arg;
    } else if (const int slash = arg.indexOf(QLatin1Char('/')); slash >= 0) {
        id.service = arg.left(slash);
        id.path = arg.mid(slash);
    } else {
        id.service = arg;
        id.path = QStringLiteral("/StatusNotifierItem");
    }
    return id;
}

SniId splitKey(const QString &key) {
    SniId id;
    const int slash = key.indexOf(QLatin1Char('/'));
    if (slash < 0) {
        id.service = key;
        id.path = QStringLiteral("/StatusNotifierItem");
    } else {
        id.service = key.left(slash);
        id.path = key.mid(slash);
    }
    return id;
}

bool addUnique(QStringList &list, const QString &key) {
    if (list.contains(key))
        return false;
    list.append(key);
    return true;
}

bool removeOne(QStringList &list, const QString &key) {
    return list.removeOne(key);
}

} // namespace helm
