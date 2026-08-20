#include "holdwindow.h"

#include "archivemodel.h"
#include "holdcore.h"

#include <QAbstractItemView>
#include <QAction>
#include <QDesktopServices>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QHeaderView>
#include <QIcon>
#include <QItemSelectionModel>
#include <QStatusBar>
#include <QTemporaryDir>
#include <QToolBar>
#include <QTreeView>
#include <QUrl>

namespace helm::hold {

HoldWindow::HoldWindow(const QString &archivePath, QWidget *parent)
    : QMainWindow(parent), _archive(archivePath) {
    resize(760, 560);
    setWindowTitle(QFileInfo(_archive).fileName() + QStringLiteral(" — Hold"));

    _model = new ArchiveModel(_archive, this);

    auto *bar = addToolBar(QStringLiteral("Archive"));
    bar->setMovable(false);
    QAction *all = bar->addAction(QIcon::fromTheme(QStringLiteral("archive-extract")),
                                  QStringLiteral("Extract All…"));
    connect(all, &QAction::triggered, this, &HoldWindow::extractAll);
    QAction *sel = bar->addAction(QStringLiteral("Extract Selected…"));
    connect(sel, &QAction::triggered, this, &HoldWindow::extractSelected);

    _view = new QTreeView(this);
    _view->setModel(_model);
    _view->setSelectionMode(QAbstractItemView::ExtendedSelection);
    _view->setSelectionBehavior(QAbstractItemView::SelectRows);
    _view->setColumnWidth(0, 320);
    _view->header()->setStretchLastSection(true);
    connect(_view, &QTreeView::doubleClicked, this, &HoldWindow::openEntry);
    setCentralWidget(_view);

    statusBar()->showMessage(_model->ok() ? _archive
                                          : QStringLiteral("Could not read %1").arg(_archive));
}

HoldWindow::~HoldWindow() { delete _temp; }

QStringList HoldWindow::selectedInner() const {
    QStringList out;
    if (!_view->selectionModel())
        return out;
    for (const QModelIndex &idx : _view->selectionModel()->selectedIndexes()) {
        if (idx.column() == 0)
            out << _model->innerPath(idx);
    }
    return out;
}

void HoldWindow::extractAll() {
    const QString dest = QFileDialog::getExistingDirectory(this, QStringLiteral("Extract all to"));
    if (dest.isEmpty())
        return;
    const Result r = helm::hold::extractAll(_archive, dest); // free fn, not the member
    statusBar()->showMessage(r.ok ? QStringLiteral("Extracted to %1").arg(dest)
                                  : QStringLiteral("Extract failed: %1").arg(r.error));
}

void HoldWindow::extractSelected() {
    const QStringList inner = selectedInner();
    if (inner.isEmpty())
        return;
    const QString dest = QFileDialog::getExistingDirectory(this, QStringLiteral("Extract to"));
    if (dest.isEmpty())
        return;
    int done = 0;
    for (const QString &entry : inner) {
        if (extract(_archive, entry, dest).ok) // helm::hold::extract
            ++done;
    }
    statusBar()->showMessage(QStringLiteral("Extracted %1 of %2 to %3")
                                 .arg(done)
                                 .arg(inner.size())
                                 .arg(dest));
}

void HoldWindow::openEntry(const QModelIndex &index) {
    if (!index.isValid() || _model->isDir(index))
        return; // a directory just expands in the tree
    if (!_temp)
        _temp = new QTemporaryDir;
    if (!_temp->isValid())
        return;
    const QString inner = _model->innerPath(index);
    const Result r = extract(_archive, inner, _temp->path());
    if (!r.ok) {
        statusBar()->showMessage(QStringLiteral("Open failed: %1").arg(r.error));
        return;
    }
    QDesktopServices::openUrl(QUrl::fromLocalFile(QDir(_temp->path()).filePath(inner)));
}

} // namespace helm::hold
