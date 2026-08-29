// The Users tab model: per-user resource rollup (rollupByUser). Rows are
// few and carry no selection-bound actions, so a plain reset per tick is
// fine. Core-only — lives in ezra-lib for testing.
#pragma once

#include "sampler.h"

#include <QAbstractTableModel>

namespace ezra {

class UserModel : public QAbstractTableModel {
    Q_OBJECT
public:
    enum Column { User, Processes, Cpu, Memory, ColumnCount };
    enum Role { SortRole = Qt::UserRole };

    explicit UserModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = {}) const override;
    int columnCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QVariant headerData(int section, Qt::Orientation orientation, int role) const override;

    void setRollups(const QVector<UserRollup> &rollups);

private:
    QVector<UserRollup> rows_;
};

} // namespace ezra
