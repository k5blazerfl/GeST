// The EzRA main window: OG Task Manager layout — a tab row (Processes,
// Performance now; Startup/Users/Details/Services in later slices), a filter
// box, the process table with an "End task" button bottom-right, and a
// status-bar footer with machine totals. Plain labels throughout — the
// theming stops at the name.
#pragma once

#include "processmodel.h"
#include "sampler.h"

#include <QMainWindow>

class QLabel;
class QLineEdit;
class QSortFilterProxyModel;
class QTableView;
class QTimer;

namespace ezra {

class HistoryGraph;

class EzraWindow : public QMainWindow {
    Q_OBJECT
public:
    EzraWindow();

private:
    void refresh();
    void endSelected(int signal);
    void openFileLocation();
    void copyCommandLine();
    void showContextMenu(const QPoint &pos);
    const ProcessSample *selectedSample() const;

    QWidget *buildProcessesTab();
    QWidget *buildPerformanceTab();

    ProcessSampler processSampler_;
    SystemSampler systemSampler_;
    ProcessModel *model_ = nullptr;
    QSortFilterProxyModel *proxy_ = nullptr;
    QTableView *table_ = nullptr;
    QLineEdit *filter_ = nullptr;
    QTimer *timer_ = nullptr;

    HistoryGraph *cpuGraph_ = nullptr;
    HistoryGraph *memGraph_ = nullptr;
    HistoryGraph *diskGraph_ = nullptr;
    HistoryGraph *netGraph_ = nullptr;
    QLabel *footer_ = nullptr;
};

} // namespace ezra
