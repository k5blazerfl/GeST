#include "startupmodel.h"

namespace ezra {

StartupModel::StartupModel(QObject *parent) : QAbstractTableModel(parent) {}

int StartupModel::rowCount(const QModelIndex &parent) const {
    return parent.isValid() ? 0 : rows_.size();
}

int StartupModel::columnCount(const QModelIndex &parent) const {
    return parent.isValid() ? 0 : ColumnCount;
}

QVariant StartupModel::data(const QModelIndex &index, int role) const {
    if (!index.isValid() || index.row() >= rows_.size())
        return {};
    const helm::AutostartEntry &a = rows_.at(index.row());
    if (role == Qt::DisplayRole) {
        switch (index.column()) {
        case Name:
            return a.entry.name.isEmpty() ? a.entry.id : a.entry.name;
        case Status: return a.enabled ? tr("Enabled") : tr("Disabled");
        case Command: return a.entry.exec;
        case Source: return a.system ? tr("System") : tr("User");
        }
    }
    if (role == Qt::ToolTipRole)
        return a.file;
    return {};
}

QVariant StartupModel::headerData(int section, Qt::Orientation orientation, int role) const {
    if (orientation != Qt::Horizontal || role != Qt::DisplayRole)
        return {};
    switch (section) {
    case Name: return tr("Name");
    case Status: return tr("Status");
    case Command: return tr("Command");
    case Source: return tr("Source");
    }
    return {};
}

void StartupModel::setEntries(const QVector<helm::AutostartEntry> &entries) {
    beginResetModel();
    rows_ = entries;
    endResetModel();
}

const helm::AutostartEntry *StartupModel::entryAt(int row) const {
    return row >= 0 && row < rows_.size() ? &rows_.at(row) : nullptr;
}

} // namespace ezra
