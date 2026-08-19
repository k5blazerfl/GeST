#include "window.h"

#include "addressbar.h"
#include "sefe.h"

#include <QAbstractItemView>
#include <QAction>
#include <QDesktopServices>
#include <QDir>
#include <QFileSystemModel>
#include <QFrame>
#include <QHeaderView>
#include <QIcon>
#include <QKeySequence>
#include <QListView>
#include <QListWidget>
#include <QModelIndex>
#include <QShortcut>
#include <QSplitter>
#include <QStackedWidget>
#include <QStatusBar>
#include <QToolBar>
#include <QTreeView>
#include <QUrl>

namespace helm::sefe {

SefeWindow::SefeWindow(QWidget *parent) : QMainWindow(parent) {
    resize(960, 620);

    // Shared model — read-only this slice (operations land in slice 3).
    _model = new QFileSystemModel(this);
    _model->setReadOnly(true);
    _model->setRootPath(initialDir());

    // --- toolbar: navigation + view toggle + address bar ---
    auto *bar = addToolBar(QStringLiteral("Navigation"));
    bar->setMovable(false);

    _backAct = bar->addAction(QIcon::fromTheme(QStringLiteral("go-previous")), QStringLiteral("Back"));
    _backAct->setShortcut(QKeySequence::Back);
    connect(_backAct, &QAction::triggered, this, &SefeWindow::goBack);

    _fwdAct = bar->addAction(QIcon::fromTheme(QStringLiteral("go-next")), QStringLiteral("Forward"));
    _fwdAct->setShortcut(QKeySequence::Forward);
    connect(_fwdAct, &QAction::triggered, this, &SefeWindow::goForward);

    _upAct = bar->addAction(QIcon::fromTheme(QStringLiteral("go-up")), QStringLiteral("Up"));
    _upAct->setShortcut(QKeySequence(Qt::ALT | Qt::Key_Up));
    connect(_upAct, &QAction::triggered, this, &SefeWindow::goUp);

    bar->addSeparator();

    _address = new AddressBar(this);
    connect(_address, &AddressBar::navigate, this,
            [this](const QString &dir) { navigateTo(dir); });
    bar->addWidget(_address);
    // Ctrl+L focuses the address bar for typing (Windows/browser convention).
    auto *editShortcut = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_L), this);
    connect(editShortcut, &QShortcut::activated, _address, &AddressBar::beginEdit);

    bar->addSeparator();
    auto *viewAct = bar->addAction(QIcon::fromTheme(QStringLiteral("view-list-details")),
                                   QStringLiteral("Toggle view"));

    // --- details + icons views over the shared model ---
    _details = new QTreeView(this);
    _details->setModel(_model);
    _details->setSelectionBehavior(QAbstractItemView::SelectRows);
    _details->setSortingEnabled(true);
    _details->sortByColumn(0, Qt::AscendingOrder);
    _details->setColumnWidth(0, 320);
    _details->header()->setStretchLastSection(true);
    connect(_details, &QTreeView::doubleClicked, this, &SefeWindow::openIndex);

    _icons = new QListView(this);
    _icons->setModel(_model);
    _icons->setViewMode(QListView::IconMode);
    _icons->setResizeMode(QListView::Adjust);
    _icons->setWrapping(true);
    _icons->setSpacing(12);
    _icons->setUniformItemSizes(true);
    connect(_icons, &QListView::doubleClicked, this, &SefeWindow::openIndex);

    _viewStack = new QStackedWidget(this);
    _viewStack->addWidget(_details); // 0 = details
    _viewStack->addWidget(_icons);   // 1 = icons
    connect(viewAct, &QAction::triggered, this, [this] {
        const int next = _viewStack->currentIndex() == 0 ? 1 : 0;
        _viewStack->setCurrentIndex(next);
        // Keep the freshly shown view rooted at the current dir.
        const QModelIndex root = _model->index(_current);
        _details->setRootIndex(root);
        _icons->setRootIndex(root);
    });

    // --- places pane ---
    _places = new QListWidget(this);
    _places->setMaximumWidth(200);
    _places->setFrameShape(QFrame::NoFrame);
    for (const Place &p : places()) {
        auto *item = new QListWidgetItem(QIcon::fromTheme(p.icon), p.name, _places);
        item->setData(Qt::UserRole, p.path);
    }
    connect(_places, &QListWidget::itemClicked, this, [this](QListWidgetItem *item) {
        navigateTo(item->data(Qt::UserRole).toString());
    });

    auto *split = new QSplitter(Qt::Horizontal, this);
    split->addWidget(_places);
    split->addWidget(_viewStack);
    split->setStretchFactor(0, 0);
    split->setStretchFactor(1, 1);
    setCentralWidget(split);

    statusBar();
    navigateTo(initialDir());
}

void SefeWindow::navigateTo(const QString &dir, bool record) {
    const QString path = QDir::cleanPath(dir);
    _current = path;
    _model->setRootPath(path); // ensure the model watches the target
    const QModelIndex root = _model->index(path);
    _details->setRootIndex(root);
    _icons->setRootIndex(root);

    _address->setPath(path);
    setWindowTitle(helm::sefe::windowTitle(path)); // free fn, not QWidget::windowTitle()
    highlightPlace(path);
    statusBar()->showMessage(path);

    if (record) {
        // Drop any forward history, then push this dir.
        while (_history.size() > _histIndex + 1)
            _history.removeLast();
        _history.append(path);
        _histIndex = _history.size() - 1;
    }
    updateNavActions();
}

void SefeWindow::openIndex(const QModelIndex &index) {
    const QString path = _model->filePath(index);
    if (_model->isDir(index))
        navigateTo(path);
    else
        QDesktopServices::openUrl(QUrl::fromLocalFile(path)); // slice 4 routes via Customs
}

void SefeWindow::goBack() {
    if (_histIndex > 0)
        navigateTo(_history.at(--_histIndex), /*record=*/false);
}

void SefeWindow::goForward() {
    if (_histIndex >= 0 && _histIndex < _history.size() - 1)
        navigateTo(_history.at(++_histIndex), /*record=*/false);
}

void SefeWindow::goUp() {
    const QString up = parentDir(_current);
    if (up != _current)
        navigateTo(up);
}

void SefeWindow::updateNavActions() {
    _backAct->setEnabled(_histIndex > 0);
    _fwdAct->setEnabled(_histIndex >= 0 && _histIndex < _history.size() - 1);
    _upAct->setEnabled(parentDir(_current) != _current);
}

void SefeWindow::highlightPlace(const QString &dir) {
    _places->clearSelection();
    for (int i = 0; i < _places->count(); ++i) {
        if (_places->item(i)->data(Qt::UserRole).toString() == dir) {
            _places->setCurrentRow(i);
            return;
        }
    }
    _places->setCurrentRow(-1);
}

} // namespace helm::sefe
