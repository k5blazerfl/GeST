#include "services.h"

#include <QDBusConnection>
#include <QDBusMetaType>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>

#include <algorithm>

namespace ezra {

namespace {
const QString kService = QStringLiteral("org.freedesktop.systemd1");
const QString kPath = QStringLiteral("/org/freedesktop/systemd1");
const QString kManager = QStringLiteral("org.freedesktop.systemd1.Manager");

QDBusMessage managerCall(const QString &method) {
    return QDBusMessage::createMethodCall(kService, kPath, kManager, method);
}
} // namespace

QDBusArgument &operator<<(QDBusArgument &arg, const UnitInfo &unit) {
    arg.beginStructure();
    arg << unit.name << unit.description << unit.loadState << unit.activeState
        << unit.subState << unit.followed << unit.objectPath << unit.jobId
        << unit.jobType << unit.jobPath;
    arg.endStructure();
    return arg;
}

const QDBusArgument &operator>>(const QDBusArgument &arg, UnitInfo &unit) {
    arg.beginStructure();
    arg >> unit.name >> unit.description >> unit.loadState >> unit.activeState
        >> unit.subState >> unit.followed >> unit.objectPath >> unit.jobId
        >> unit.jobType >> unit.jobPath;
    arg.endStructure();
    return arg;
}

ServiceManager::ServiceManager(QObject *parent) : QObject(parent) {
    qDBusRegisterMetaType<UnitInfo>();
    qDBusRegisterMetaType<QList<UnitInfo>>();
}

void ServiceManager::refresh() {
    auto *watcher = new QDBusPendingCallWatcher(
        QDBusConnection::systemBus().asyncCall(managerCall(QStringLiteral("ListUnits"))), this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this,
            [this](QDBusPendingCallWatcher *w) {
                w->deleteLater();
                QDBusPendingReply<QList<UnitInfo>> reply = *w;
                if (reply.isError()) {
                    emit actionFailed(QString(), reply.error().message());
                    return;
                }
                QVector<UnitInfo> services;
                const QList<UnitInfo> units = reply.value();
                for (const UnitInfo &u : units)
                    if (u.name.endsWith(QStringLiteral(".service")))
                        services.append(u);
                std::sort(services.begin(), services.end(),
                          [](const UnitInfo &a, const UnitInfo &b) { return a.name < b.name; });
                emit servicesChanged(services);
            });
}

void ServiceManager::runVerb(const QString &verb, const QString &unitName) {
    QDBusMessage call = managerCall(verb);
    call << unitName << QStringLiteral("replace");
    auto *watcher =
        new QDBusPendingCallWatcher(QDBusConnection::systemBus().asyncCall(call), this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this,
            [this, unitName](QDBusPendingCallWatcher *w) {
                w->deleteLater();
                QDBusPendingReply<QDBusObjectPath> reply = *w;
                if (reply.isError())
                    emit actionFailed(unitName, reply.error().message());
                else
                    refresh();
            });
}

ServiceModel::ServiceModel(QObject *parent) : QAbstractTableModel(parent) {}

int ServiceModel::rowCount(const QModelIndex &parent) const {
    return parent.isValid() ? 0 : rows_.size();
}

int ServiceModel::columnCount(const QModelIndex &parent) const {
    return parent.isValid() ? 0 : ColumnCount;
}

QVariant ServiceModel::data(const QModelIndex &index, int role) const {
    if (!index.isValid() || index.row() >= rows_.size())
        return {};
    const UnitInfo &u = rows_.at(index.row());
    if (role == Qt::DisplayRole) {
        switch (index.column()) {
        case Name: return u.name;
        case Status:
            return u.loadState == QStringLiteral("masked")
                       ? u.loadState
                       : QStringLiteral("%1 (%2)").arg(u.activeState, u.subState);
        case Description: return u.description;
        }
    }
    if (role == Qt::ToolTipRole)
        return u.description;
    return {};
}

QVariant ServiceModel::headerData(int section, Qt::Orientation orientation, int role) const {
    if (orientation != Qt::Horizontal || role != Qt::DisplayRole)
        return {};
    switch (section) {
    case Name: return tr("Name");
    case Status: return tr("Status");
    case Description: return tr("Description");
    }
    return {};
}

void ServiceModel::setServices(const QVector<UnitInfo> &services) {
    beginResetModel();
    rows_ = services;
    endResetModel();
}

const UnitInfo *ServiceModel::serviceAt(int row) const {
    return row >= 0 && row < rows_.size() ? &rows_.at(row) : nullptr;
}

} // namespace ezra
