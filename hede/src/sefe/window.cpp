#include "window.h"

#include "sefe.h"

#include <QAbstractItemView>
#include <QFileSystemModel>
#include <QHeaderView>
#include <QStatusBar>
#include <QTreeView>

namespace helm::sefe {

SefeWindow::SefeWindow(QWidget *parent) : QMainWindow(parent) {
    const QString home = initialDir();
    setWindowTitle(helm::sefe::windowTitle(home)); // free fn, not QWidget::windowTitle()
    resize(920, 600);

    // Read-only for the Hull slice: browse but don't mutate. File operations
    // (rename/delete/paste) land in slice 3 with the keyboard contract.
    auto *model = new QFileSystemModel(this);
    model->setReadOnly(true);
    model->setRootPath(home);

    auto *view = new QTreeView(this);
    view->setModel(model);
    view->setRootIndex(model->index(home));
    view->setSelectionBehavior(QAbstractItemView::SelectRows);
    view->setSortingEnabled(true);
    view->sortByColumn(0, Qt::AscendingOrder);
    view->setColumnWidth(0, 320); // Name column
    view->header()->setStretchLastSection(true);
    setCentralWidget(view);

    statusBar()->showMessage(home);
}

} // namespace helm::sefe
