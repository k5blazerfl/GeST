#include "window.h"

#include "graph.h"
#include "launch.h"

#include <QApplication>
#include <QClipboard>
#include <QFileInfo>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QLocale>
#include <QMenu>
#include <QPushButton>
#include <QSortFilterProxyModel>
#include <QStackedWidget>
#include <QStatusBar>
#include <QTabWidget>
#include <QTableView>
#include <QTimer>
#include <QVBoxLayout>

#include <csignal>
#include <sys/resource.h>

namespace ezra {

namespace {
constexpr int kTickMs = 2000;

QString rate(double bytesPerSec) {
    return QLocale().formattedDataSize(qint64(bytesPerSec), 1) + QStringLiteral("/s");
}
} // namespace

EzraWindow::EzraWindow() {
    setWindowTitle(QStringLiteral("EzRA"));
    resize(760, 540);

    model_ = new ProcessModel(this);

    tabs_ = new QTabWidget(this);
    tabs_->addTab(buildProcessesTab(), tr("Processes"));
    tabs_->addTab(buildPerformanceTab(), tr("Performance"));
    tabs_->addTab(buildDetailsTab(), tr("Details"));
    setCentralWidget(tabs_);

    footer_ = new QLabel(this);
    statusBar()->addWidget(footer_);

    timer_ = new QTimer(this);
    timer_->setInterval(kTickMs);
    connect(timer_, &QTimer::timeout, this, &EzraWindow::refresh);
    timer_->start();
    refresh();
}

void EzraWindow::selectTab(const QString &name) {
    for (int i = 0; i < tabs_->count(); ++i)
        if (tabs_->tabText(i).compare(name, Qt::CaseInsensitive) == 0)
            tabs_->setCurrentIndex(i);
}

QTableView *EzraWindow::buildProcessTable(QWidget *parent, bool details) {
    auto *proxy = new QSortFilterProxyModel(parent);
    proxy->setSourceModel(model_);
    proxy->setSortRole(ProcessModel::SortRole);
    proxy->setFilterCaseSensitivity(Qt::CaseInsensitive);
    proxy->setFilterKeyColumn(-1); // match on any column

    auto *table = new QTableView(parent);
    table->setModel(proxy);
    table->setSortingEnabled(true);
    table->setSelectionBehavior(QAbstractItemView::SelectRows);
    table->setSelectionMode(QAbstractItemView::SingleSelection);
    table->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table->verticalHeader()->setVisible(false);
    table->setShowGrid(false);
    table->horizontalHeader()->setSectionResizeMode(QHeaderView::Interactive);
    table->horizontalHeader()->setSectionResizeMode(ProcessModel::Name, QHeaderView::Stretch);
    if (details) {
        // Details sorts by name like the OG; the dense column set is the point.
        table->sortByColumn(ProcessModel::Name, Qt::AscendingOrder);
    } else {
        table->sortByColumn(ProcessModel::Cpu, Qt::DescendingOrder);
        for (int col = ProcessModel::kProcessesColumnCount; col < ProcessModel::ColumnCount; ++col)
            table->setColumnHidden(col, true);
    }
    table->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(table, &QTableView::customContextMenuRequested, this,
            [this, table, details](const QPoint &pos) { showContextMenu(table, pos, details); });
    // Whichever table the user touches last is the target for End task etc.
    connect(table->selectionModel(), &QItemSelectionModel::currentChanged, this,
            [this, table] { activeTable_ = table; });
    return table;
}

QWidget *EzraWindow::buildProcessesTab() {
    auto *page = new QWidget(this);
    auto *layout = new QVBoxLayout(page);

    filter_ = new QLineEdit(page);
    filter_->setPlaceholderText(tr("Filter by name, PID, or user"));
    filter_->setClearButtonEnabled(true);
    layout->addWidget(filter_);

    QTableView *table = buildProcessTable(page, false);
    activeTable_ = table;
    auto *proxy = static_cast<QSortFilterProxyModel *>(table->model());
    connect(filter_, &QLineEdit::textChanged, proxy,
            &QSortFilterProxyModel::setFilterFixedString);
    layout->addWidget(table, 1);

    auto *buttonRow = new QHBoxLayout;
    buttonRow->addStretch(1);
    auto *endTask = new QPushButton(tr("End task"), page);
    connect(endTask, &QPushButton::clicked, this, [this] { endSelected(SIGTERM); });
    buttonRow->addWidget(endTask);
    layout->addLayout(buttonRow);

    return page;
}

QWidget *EzraWindow::buildDetailsTab() {
    auto *page = new QWidget(this);
    auto *layout = new QVBoxLayout(page);
    layout->addWidget(buildProcessTable(page, true), 1);
    return page;
}

QWidget *EzraWindow::buildPerformanceTab() {
    auto *page = new QWidget(this);
    auto *grid = new QGridLayout(page);

    // CPU tile: overall graph by default; right-click switches to the
    // per-core grid (built lazily once the core count is known).
    cpuStack_ = new QStackedWidget(page);
    cpuGraph_ = new HistoryGraph(tr("CPU"), HistoryGraph::Percent, page);
    coreGrid_ = new QWidget(page);
    new QGridLayout(coreGrid_);
    cpuStack_->addWidget(cpuGraph_);
    cpuStack_->addWidget(coreGrid_);
    cpuStack_->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(cpuStack_, &QWidget::customContextMenuRequested, this, [this](const QPoint &pos) {
        QMenu menu(this);
        QAction *overall = menu.addAction(tr("Overall utilization"));
        QAction *perCore = menu.addAction(tr("Logical processors"));
        for (QAction *a : {overall, perCore})
            a->setCheckable(true);
        (cpuStack_->currentIndex() == 0 ? overall : perCore)->setChecked(true);
        connect(overall, &QAction::triggered, this, [this] { cpuStack_->setCurrentIndex(0); });
        connect(perCore, &QAction::triggered, this, [this] { cpuStack_->setCurrentIndex(1); });
        menu.exec(cpuStack_->mapToGlobal(pos));
    });

    memGraph_ = new HistoryGraph(tr("Memory"), HistoryGraph::Percent, page);
    diskGraph_ = new HistoryGraph(tr("Disk"), HistoryGraph::AutoScale, page);
    netGraph_ = new HistoryGraph(tr("Network"), HistoryGraph::AutoScale, page);
    grid->addWidget(cpuStack_, 0, 0);
    grid->addWidget(memGraph_, 0, 1);
    grid->addWidget(diskGraph_, 1, 0);
    grid->addWidget(netGraph_, 1, 1);
    return page;
}

void EzraWindow::refresh() {
    const QVector<ProcessSample> processes = processSampler_.sample();
    model_->setSamples(processes);

    const SystemSampler::Snapshot snap = systemSampler_.sample();
    cpuGraph_->push(snap.cpuPercent,
                    QString::number(snap.cpuPercent, 'f', 0) + QStringLiteral(" %"));

    if (coreGraphs_.isEmpty() && !snap.perCorePercent.isEmpty()) {
        auto *grid = static_cast<QGridLayout *>(coreGrid_->layout());
        grid->setSpacing(4);
        const int columns = snap.perCorePercent.size() > 8 ? 4 : 2;
        for (int i = 0; i < snap.perCorePercent.size(); ++i) {
            auto *g = new HistoryGraph(QString::number(i), HistoryGraph::Percent,
                                       coreGrid_, QSize(80, 44));
            coreGraphs_.append(g);
            grid->addWidget(g, i / columns, i % columns);
        }
    }
    for (int i = 0; i < coreGraphs_.size() && i < snap.perCorePercent.size(); ++i)
        coreGraphs_[i]->push(snap.perCorePercent.at(i),
                             QString::number(snap.perCorePercent.at(i), 'f', 0)
                                 + QStringLiteral(" %"));

    const qulonglong usedKb =
        snap.mem.totalKb > snap.mem.availableKb ? snap.mem.totalKb - snap.mem.availableKb : 0;
    const double memPercent =
        snap.mem.totalKb ? 100.0 * double(usedKb) / double(snap.mem.totalKb) : 0.0;
    const QLocale locale;
    memGraph_->push(memPercent,
                    tr("%1 / %2").arg(locale.formattedDataSize(qint64(usedKb) * 1024, 1),
                                      locale.formattedDataSize(qint64(snap.mem.totalKb) * 1024, 1)));

    diskGraph_->push(snap.readBytesPerSec + snap.writeBytesPerSec,
                     tr("R %1  W %2").arg(rate(snap.readBytesPerSec), rate(snap.writeBytesPerSec)));
    netGraph_->push(snap.rxBytesPerSec + snap.txBytesPerSec,
                    tr("↓ %1  ↑ %2").arg(rate(snap.rxBytesPerSec), rate(snap.txBytesPerSec)));

    footer_->setText(tr("Processes: %1    CPU: %2 %    Memory: %3 %")
                         .arg(processes.size())
                         .arg(snap.cpuPercent, 0, 'f', 0)
                         .arg(memPercent, 0, 'f', 0));
}

const ProcessSample *EzraWindow::selectedSample() const {
    if (!activeTable_)
        return nullptr;
    const QModelIndex current = activeTable_->selectionModel()->currentIndex();
    if (!current.isValid())
        return nullptr;
    auto *proxy = static_cast<QSortFilterProxyModel *>(activeTable_->model());
    return model_->sampleAt(proxy->mapToSource(current).row());
}

void EzraWindow::endSelected(int signal) {
    if (const ProcessSample *p = selectedSample())
        if (::kill(p->pid, signal) != 0)
            statusBar()->showMessage(tr("Could not signal %1: permission denied").arg(p->name),
                                     4000);
}

void EzraWindow::setPriority(int nice) {
    if (const ProcessSample *p = selectedSample())
        if (::setpriority(PRIO_PROCESS, id_t(p->pid), nice) != 0)
            statusBar()->showMessage(
                tr("Could not set priority of %1: permission denied").arg(p->name), 4000);
}

void EzraWindow::openFileLocation() {
    const ProcessSample *p = selectedSample();
    if (!p)
        return;
    const QString exe =
        QFileInfo(QStringLiteral("/proc/%1/exe").arg(p->pid)).symLinkTarget();
    if (!exe.isEmpty())
        helm::launchDetached(QStringLiteral("sefe"), {QFileInfo(exe).absolutePath()});
}

void EzraWindow::copyCommandLine() {
    if (const ProcessSample *p = selectedSample())
        QApplication::clipboard()->setText(p->cmdline.isEmpty() ? p->name : p->cmdline);
}

void EzraWindow::showContextMenu(QTableView *table, const QPoint &pos, bool details) {
    const QModelIndex index = table->indexAt(pos);
    if (!index.isValid())
        return;
    activeTable_ = table;
    table->selectionModel()->setCurrentIndex(
        index, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);

    QMenu menu(this);
    menu.addAction(tr("End task"), this, [this] { endSelected(SIGTERM); });
    menu.addAction(tr("Force kill"), this, [this] { endSelected(SIGKILL); });
    if (details) {
        // Same rungs as the OG's Set priority; the labels are nice values.
        QMenu *priority = menu.addMenu(tr("Set priority"));
        const std::pair<const char *, int> rungs[] = {
            {QT_TR_NOOP("High (-10)"), -10}, {QT_TR_NOOP("Above normal (-5)"), -5},
            {QT_TR_NOOP("Normal (0)"), 0},   {QT_TR_NOOP("Below normal (10)"), 10},
            {QT_TR_NOOP("Low (19)"), 19},
        };
        for (const auto &[label, nice] : rungs)
            priority->addAction(tr(label), this, [this, nice = nice] { setPriority(nice); });
    }
    menu.addSeparator();
    menu.addAction(tr("Open file location"), this, &EzraWindow::openFileLocation);
    menu.addAction(tr("Copy command line"), this, &EzraWindow::copyCommandLine);
    menu.exec(table->viewport()->mapToGlobal(pos));
}

} // namespace ezra
