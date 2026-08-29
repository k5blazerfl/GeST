#include "processmodel.h"

#include <QLocale>

namespace ezra {

ProcessModel::ProcessModel(QObject *parent) : QAbstractTableModel(parent) {}

int ProcessModel::rowCount(const QModelIndex &parent) const {
    return parent.isValid() ? 0 : rows_.size();
}

int ProcessModel::columnCount(const QModelIndex &parent) const {
    return parent.isValid() ? 0 : ColumnCount;
}

QVariant ProcessModel::data(const QModelIndex &index, int role) const {
    if (!index.isValid() || index.row() >= rows_.size())
        return {};
    const ProcessSample &p = rows_.at(index.row());

    if (role == PidRole)
        return p.pid;

    if (role == SortRole) {
        switch (index.column()) {
        case Name: return p.name.toLower();
        case Pid: return p.pid;
        case User: return p.user;
        case Cpu: return p.cpuPercent;
        case Memory: return p.rssBytes;
        }
        return {};
    }

    if (role == Qt::DisplayRole) {
        switch (index.column()) {
        case Name: return p.name;
        case Pid: return p.pid;
        case User: return p.user;
        case Cpu: return QString::number(p.cpuPercent, 'f', 1) + QStringLiteral(" %");
        case Memory: return QLocale().formattedDataSize(qint64(p.rssBytes), 1);
        }
        return {};
    }

    if (role == Qt::ToolTipRole && index.column() == Name)
        return p.cmdline.isEmpty() ? p.name : p.cmdline;

    if (role == Qt::TextAlignmentRole
        && (index.column() == Cpu || index.column() == Memory || index.column() == Pid))
        return int(Qt::AlignRight | Qt::AlignVCenter);

    return {};
}

QVariant ProcessModel::headerData(int section, Qt::Orientation orientation, int role) const {
    if (orientation != Qt::Horizontal || role != Qt::DisplayRole)
        return {};
    switch (section) {
    case Name: return tr("Name");
    case Pid: return tr("PID");
    case User: return tr("User");
    case Cpu: return tr("CPU");
    case Memory: return tr("Memory");
    }
    return {};
}

void ProcessModel::setSamples(const QVector<ProcessSample> &samples) {
    QHash<int, int> incoming;
    incoming.reserve(samples.size());
    for (int i = 0; i < samples.size(); ++i)
        incoming.insert(samples.at(i).pid, i);

    // 1. Remove rows whose pid is gone (bottom-up keeps indices valid).
    for (int row = rows_.size() - 1; row >= 0; --row) {
        if (!incoming.contains(rows_.at(row).pid)) {
            beginRemoveRows({}, row, row);
            rows_.remove(row);
            endRemoveRows();
        }
    }

    // 2. Update surviving rows in place.
    rowByPid_.clear();
    for (int row = 0; row < rows_.size(); ++row) {
        rows_[row] = samples.at(incoming.value(rows_.at(row).pid));
        rowByPid_.insert(rows_.at(row).pid, row);
    }
    if (!rows_.isEmpty())
        emit dataChanged(index(0, 0), index(rows_.size() - 1, ColumnCount - 1));

    // 3. Append brand-new pids.
    QVector<ProcessSample> fresh;
    for (const ProcessSample &p : samples)
        if (!rowByPid_.contains(p.pid))
            fresh.append(p);
    if (!fresh.isEmpty()) {
        beginInsertRows({}, rows_.size(), rows_.size() + fresh.size() - 1);
        for (const ProcessSample &p : fresh) {
            rowByPid_.insert(p.pid, rows_.size());
            rows_.append(p);
        }
        endInsertRows();
    }
}

const ProcessSample *ProcessModel::sampleAt(int row) const {
    return row >= 0 && row < rows_.size() ? &rows_.at(row) : nullptr;
}

} // namespace ezra
