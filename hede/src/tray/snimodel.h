#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// A StatusNotifierItem address: a bus name + object path.
struct SniId {
    QString service;
    QString path;
    QString key() const { return service + path; } // stable identifier
};

// The well-known host name a tray must register (per the SNI spec).
QString hostName(qint64 pid);

// Resolve the argument of RegisterStatusNotifierItem. Apps pass either a bus
// name, a "busname/path", or just an object path (with the sender as the name).
SniId parseItemService(const QString &arg, const QString &senderUnique);

// Split a key ("service/path") back into its parts (first '/' begins the path).
SniId splitKey(const QString &key);

// registry ops
bool addUnique(QStringList &list, const QString &key);
bool removeOne(QStringList &list, const QString &key);

} // namespace helm
