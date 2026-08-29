// The Startup tab model over helm::scanAutostart — the XDG autostart
// entries the session's helm-autostart runner actually executes. Reset per
// rescan (the list is small and rescans happen on tab entry / toggle).
#pragma once

#include "autostart.h"

#include <QAbstractTableModel>

namespace ezra {

class StartupModel : public QAbstractTableModel {
    Q_OBJECT
public:
    enum Column { Name, Status, Command, Source, ColumnCount };

    explicit StartupModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = {}) const override;
    int columnCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QVariant headerData(int section, Qt::Orientation orientation, int role) const override;

    void setEntries(const QVector<helm::AutostartEntry> &entries);
    const helm::AutostartEntry *entryAt(int row) const;

private:
    QVector<helm::AutostartEntry> rows_;
};

} // namespace ezra
