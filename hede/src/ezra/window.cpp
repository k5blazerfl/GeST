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
#include <QStatusBar>
#include <QTabWidget>
#include <QTableView>
#include <QTimer>
#include <QVBoxLayout>

#include <csignal>

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

    auto *tabs = new QTabWidget(this);
    tabs->addTab(buildProcessesTab(), tr("Processes"));
    tabs->addTab(buildPerformanceTab(), tr("Performance"));
    setCentralWidget(tabs);

    footer_ = new QLabel(this);
    statusBar()->addWidget(footer_);

    timer_ = new QTimer(this);
    timer_->setInterval(kTickMs);
    connect(timer_, &QTimer::timeout, this, &EzraWindow::refresh);
    timer_->start();
    refresh();
}

QWidget *EzraWindow::buildProcessesTab() {
    auto *page = new QWidget(this);
    auto *layout = new QVBoxLayout(page);

    filter_ = new QLineEdit(page);
    filter_->setPlaceholderText(tr("Filter by name, PID, or user"));
    filter_->setClearButtonEnabled(true);
    layout->addWidget(filter_);

    model_ = new ProcessModel(this);
    proxy_ = new QSortFilterProxyModel(this);
    proxy_->setSourceModel(model_);
    proxy_->setSortRole(ProcessModel::SortRole);
    proxy_->setFilterCaseSensitivity(Qt::CaseInsensitive);
    proxy_->setFilterKeyColumn(-1); // match on any column
    connect(filter_, &QLineEdit::textChanged, proxy_,
            &QSortFilterProxyModel::setFilterFixedString);

    table_ = new QTableView(page);
    table_->setModel(proxy_);
    table_->setSortingEnabled(true);
    table_->sortByColumn(ProcessModel::Cpu, Qt::DescendingOrder);
    table_->setSelectionBehavior(QAbstractItemView::SelectRows);
    table_->setSelectionMode(QAbstractItemView::SingleSelection);
    table_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table_->verticalHeader()->setVisible(false);
    table_->setShowGrid(false);
    table_->horizontalHeader()->setSectionResizeMode(QHeaderView::Interactive);
    table_->horizontalHeader()->setSectionResizeMode(ProcessModel::Name, QHeaderView::Stretch);
    table_->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(table_, &QTableView::customContextMenuRequested, this,
            &EzraWindow::showContextMenu);
    layout->addWidget(table_, 1);

    auto *buttonRow = new QHBoxLayout;
    buttonRow->addStretch(1);
    auto *endTask = new QPushButton(tr("End task"), page);
    connect(endTask, &QPushButton::clicked, this, [this] { endSelected(SIGTERM); });
    buttonRow->addWidget(endTask);
    layout->addLayout(buttonRow);

    return page;
}

QWidget *EzraWindow::buildPerformanceTab() {
    auto *page = new QWidget(this);
    auto *grid = new QGridLayout(page);
    cpuGraph_ = new HistoryGraph(tr("CPU"), HistoryGraph::Percent, page);
    memGraph_ = new HistoryGraph(tr("Memory"), HistoryGraph::Percent, page);
    diskGraph_ = new HistoryGraph(tr("Disk"), HistoryGraph::AutoScale, page);
    netGraph_ = new HistoryGraph(tr("Network"), HistoryGraph::AutoScale, page);
    grid->addWidget(cpuGraph_, 0, 0);
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
    const QModelIndex current = table_->selectionModel()->currentIndex();
    if (!current.isValid())
        return nullptr;
    return model_->sampleAt(proxy_->mapToSource(current).row());
}

void EzraWindow::endSelected(int signal) {
    if (const ProcessSample *p = selectedSample())
        ::kill(p->pid, signal);
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

void EzraWindow::showContextMenu(const QPoint &pos) {
    const QModelIndex index = table_->indexAt(pos);
    if (!index.isValid())
        return;
    table_->selectionModel()->setCurrentIndex(
        index, QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);

    QMenu menu(this);
    menu.addAction(tr("End task"), this, [this] { endSelected(SIGTERM); });
    menu.addAction(tr("Force kill"), this, [this] { endSelected(SIGKILL); });
    menu.addSeparator();
    menu.addAction(tr("Open file location"), this, &EzraWindow::openFileLocation);
    menu.addAction(tr("Copy command line"), this, &EzraWindow::copyCommandLine);
    menu.exec(table_->viewport()->mapToGlobal(pos));
}

} // namespace ezra
