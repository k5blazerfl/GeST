#include "usermodel.h"

#include <QLocale>

namespace ezra {

UserModel::UserModel(QObject *parent) : QAbstractTableModel(parent) {}

int UserModel::rowCount(const QModelIndex &parent) const {
    return parent.isValid() ? 0 : rows_.size();
}

int UserModel::columnCount(const QModelIndex &parent) const {
    return parent.isValid() ? 0 : ColumnCount;
}

QVariant UserModel::data(const QModelIndex &index, int role) const {
    if (!index.isValid() || index.row() >= rows_.size())
        return {};
    const UserRollup &u = rows_.at(index.row());

    if (role == SortRole) {
        switch (index.column()) {
        case User: return u.user;
        case Processes: return u.processes;
        case Cpu: return u.cpuPercent;
        case Memory: return u.rssBytes;
        }
        return {};
    }

    if (role == Qt::DisplayRole) {
        switch (index.column()) {
        case User: return u.user;
        case Processes: return u.processes;
        case Cpu: return QString::number(u.cpuPercent, 'f', 1) + QStringLiteral(" %");
        case Memory: return QLocale().formattedDataSize(qint64(u.rssBytes), 1);
        }
        return {};
    }

    if (role == Qt::TextAlignmentRole && index.column() != User)
        return int(Qt::AlignRight | Qt::AlignVCenter);

    return {};
}

QVariant UserModel::headerData(int section, Qt::Orientation orientation, int role) const {
    if (orientation != Qt::Horizontal || role != Qt::DisplayRole)
        return {};
    switch (section) {
    case User: return tr("User");
    case Processes: return tr("Processes");
    case Cpu: return tr("CPU");
    case Memory: return tr("Memory");
    }
    return {};
}

void UserModel::setRollups(const QVector<UserRollup> &rollups) {
    beginResetModel();
    rows_ = rollups;
    endResetModel();
}

} // namespace ezra
