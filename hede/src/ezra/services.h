// The Services tab engine: systemd's Manager over the system D-Bus — real
// units, not a facsimile (HeDE is systemd-only). ServiceManager wraps
// ListUnits (async) and the Start/Stop/RestartUnit verbs; ServiceModel is
// the table on top. Start/stop of system units is polkit-gated
// (auth_admin) — a denial surfaces as the actionFailed signal, it is not
// EzRA's job to escalate.
#pragma once

#include <QAbstractTableModel>
#include <QDBusArgument>
#include <QDBusObjectPath>
#include <QVector>

namespace ezra {

// One row of org.freedesktop.systemd1.Manager.ListUnits: a(ssssssouso).
struct UnitInfo {
    QString name;        // "foo.service"
    QString description;
    QString loadState;   // loaded / not-found / masked
    QString activeState; // active / inactive / failed
    QString subState;    // running / dead / exited …
    QString followed;
    QDBusObjectPath objectPath;
    uint jobId = 0;
    QString jobType;
    QDBusObjectPath jobPath;
};

QDBusArgument &operator<<(QDBusArgument &arg, const UnitInfo &unit);
const QDBusArgument &operator>>(const QDBusArgument &arg, UnitInfo &unit);

class ServiceManager : public QObject {
    Q_OBJECT
public:
    explicit ServiceManager(QObject *parent = nullptr);

    void refresh(); // async ListUnits; emits servicesChanged with .service units

    // verb: "StartUnit" | "StopUnit" | "RestartUnit"; refreshes on success.
    void runVerb(const QString &verb, const QString &unitName);

signals:
    void servicesChanged(const QVector<UnitInfo> &services);
    void actionFailed(const QString &unitName, const QString &message);
};

class ServiceModel : public QAbstractTableModel {
    Q_OBJECT
public:
    enum Column { Name, Status, Description, ColumnCount };

    explicit ServiceModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = {}) const override;
    int columnCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QVariant headerData(int section, Qt::Orientation orientation, int role) const override;

    void setServices(const QVector<UnitInfo> &services);
    const UnitInfo *serviceAt(int row) const;

private:
    QVector<UnitInfo> rows_;
};

} // namespace ezra

Q_DECLARE_METATYPE(ezra::UnitInfo)
