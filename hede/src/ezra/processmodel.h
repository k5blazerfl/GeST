// The Processes table model. Rows are merged in place by pid on every
// refresh (update existing, append new, remove dead) so view selection and
// scroll position survive the 2-second tick; sorting is the view's
// QSortFilterProxyModel's job. Core-only — lives in ezra-lib for testing.
#pragma once

#include "sampler.h"

#include <QAbstractTableModel>

namespace ezra {

class ProcessModel : public QAbstractTableModel {
    Q_OBJECT
public:
    // One model serves both process views: Processes shows the first five
    // columns and hides the rest; Details shows everything.
    enum Column { Name, Pid, User, Cpu, Memory, Ppid, State, Threads, Nice, CommandLine, ColumnCount };
    static constexpr int kProcessesColumnCount = Ppid; // first Details-only column
    // Raw values for sorting (display strings don't sort numerically).
    enum Role { SortRole = Qt::UserRole, PidRole };

    explicit ProcessModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = {}) const override;
    int columnCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QVariant headerData(int section, Qt::Orientation orientation, int role) const override;

    void setSamples(const QVector<ProcessSample> &samples);
    const ProcessSample *sampleAt(int row) const;

private:
    QVector<ProcessSample> rows_;
    QHash<int, int> rowByPid_;
};

} // namespace ezra
