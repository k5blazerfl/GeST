// The EzRA main window: OG Task Manager layout — a tab row (Processes,
// Performance, Details now; Startup/Users/Services in later slices), a
// filter box, the process table with an "End task" button bottom-right, and
// a status-bar footer with machine totals. Plain labels throughout — the
// theming stops at the name.
#pragma once

#include "processmodel.h"
#include "sampler.h"
#include "services.h"
#include "usermodel.h"

#include <QMainWindow>

class QLabel;
class QLineEdit;
class QSortFilterProxyModel;
class QStackedWidget;
class QTabWidget;
class QTableView;
class QTimer;

namespace ezra {

class HistoryGraph;

class EzraWindow : public QMainWindow {
    Q_OBJECT
public:
    EzraWindow();

    // "processes" | "performance" | "details" (case-insensitive); unknown
    // names are ignored. For `ezra --tab performance` style launches.
    void selectTab(const QString &name);

private:
    void refresh();
    void endSelected(int signal);
    void setPriority(int nice);
    void openFileLocation();
    void copyCommandLine();
    void showContextMenu(QTableView *table, const QPoint &pos, bool details);
    const ProcessSample *selectedSample() const;
    QTableView *buildProcessTable(QWidget *parent, bool details);

    QWidget *buildProcessesTab();
    QWidget *buildDetailsTab();
    QWidget *buildPerformanceTab();
    QWidget *buildUsersTab();
    QWidget *buildServicesTab();

    ProcessSampler processSampler_;
    SystemSampler systemSampler_;
    ProcessModel *model_ = nullptr;
    UserModel *userModel_ = nullptr;
    ServiceModel *serviceModel_ = nullptr;
    ServiceManager *serviceManager_ = nullptr;
    QTableView *servicesTable_ = nullptr;
    int servicesTabIndex_ = -1;
    int tick_ = 0;
    QTabWidget *tabs_ = nullptr;
    QTableView *activeTable_ = nullptr; // the table the last action targeted
    QLineEdit *filter_ = nullptr;
    QTimer *timer_ = nullptr;

    QStackedWidget *cpuStack_ = nullptr; // page 0: overall graph, page 1: per-core grid
    HistoryGraph *cpuGraph_ = nullptr;
    QWidget *coreGrid_ = nullptr;
    QVector<HistoryGraph *> coreGraphs_; // created lazily once the core count is known
    HistoryGraph *memGraph_ = nullptr;
    HistoryGraph *diskGraph_ = nullptr;
    HistoryGraph *netGraph_ = nullptr;
    QLabel *footer_ = nullptr;
};

} // namespace ezra
