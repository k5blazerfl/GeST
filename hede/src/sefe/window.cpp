#include "window.h"

#include "addressbar.h"
#include "ops.h"
#include "sefe.h"

#include <QAbstractItemView>
#include <QAction>
#include <QApplication>
#include <QClipboard>
#include <QDateTime>
#include <QDesktopServices>
#include <QDialog>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFileSystemModel>
#include <QFormLayout>
#include <QFrame>
#include <QHeaderView>
#include <QIcon>
#include <QKeyEvent>
#include <QKeySequence>
#include <QLabel>
#include <QListView>
#include <QListWidget>
#include <QLocale>
#include <QMenu>
#include <QMimeData>
#include <QModelIndex>
#include <QSet>
#include <QShortcut>
#include <QSplitter>
#include <QStackedWidget>
#include <QStatusBar>
#include <QToolBar>
#include <QTreeView>
#include <QUrl>

namespace helm::sefe {

namespace {
QSet<QString> entriesOf(const QString &dir) {
    const QDir d(dir);
    const auto list = d.entryList(QDir::NoDotAndDotDot | QDir::AllEntries | QDir::Hidden
                                  | QDir::System);
    return QSet<QString>(list.begin(), list.end());
}
} // namespace

SefeWindow::SefeWindow(QWidget *parent) : QMainWindow(parent) {
    resize(960, 620);

    // Read/write now (slice 3). Edits happen only via our actions — the views
    // use no edit triggers, so clicks/keys never start an inline rename by
    // accident; F2 / context-menu "Rename" call view->edit() explicitly.
    _model = new QFileSystemModel(this);
    _model->setReadOnly(false);
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
    auto *editShortcut = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_L), this);
    connect(editShortcut, &QShortcut::activated, _address, &AddressBar::beginEdit);

    bar->addSeparator();
    auto *viewAct = bar->addAction(QIcon::fromTheme(QStringLiteral("view-list-details")),
                                   QStringLiteral("Toggle view"));

    // --- operation actions (shortcuts live window-wide; reused in menus) ---
    auto op = [this](const QString &text, const QKeySequence &keys, void (SefeWindow::*slot)()) {
        auto *a = new QAction(text, this);
        if (!keys.isEmpty())
            a->setShortcut(keys);
        if (slot)
            connect(a, &QAction::triggered, this, slot);
        addAction(a); // so the shortcut fires regardless of focus
        return a;
    };
    // Open has no window shortcut — Enter-to-open is handled by the view event
    // filter, so it never hijacks Return in the address bar's edit field.
    _openAct = op(QStringLiteral("Open"), QKeySequence(), nullptr);
    connect(_openAct, &QAction::triggered, this,
            [this] { openIndex(activeView()->currentIndex()); });
    _renameAct = op(QStringLiteral("Rename"), QKeySequence(Qt::Key_F2), &SefeWindow::renameSelected);
    _deleteAct = op(QStringLiteral("Delete"), QKeySequence::Delete, &SefeWindow::deleteSelected);
    _copyAct = op(QStringLiteral("Copy"), QKeySequence::Copy, nullptr);
    connect(_copyAct, &QAction::triggered, this, [this] { copySelected(false); });
    _cutAct = op(QStringLiteral("Cut"), QKeySequence::Cut, nullptr);
    connect(_cutAct, &QAction::triggered, this, [this] { copySelected(true); });
    _pasteAct = op(QStringLiteral("Paste"), QKeySequence::Paste, &SefeWindow::paste);
    _pasteAct->setEnabled(false);
    _newFolderAct = op(QStringLiteral("New folder"),
                       QKeySequence(Qt::CTRL | Qt::SHIFT | Qt::Key_N), &SefeWindow::newFolder);
    _refreshAct = op(QStringLiteral("Refresh"), QKeySequence(Qt::Key_F5), &SefeWindow::refresh);
    _propsAct = op(QStringLiteral("Properties"),
                   QKeySequence(Qt::ALT | Qt::Key_Return), &SefeWindow::showProperties);

    // --- details + icons views over the shared model ---
    auto initView = [this](QAbstractItemView *v) {
        v->setModel(_model);
        v->setSelectionMode(QAbstractItemView::ExtendedSelection);
        v->setEditTriggers(QAbstractItemView::NoEditTriggers);
        v->setContextMenuPolicy(Qt::CustomContextMenu);
        connect(v, &QAbstractItemView::doubleClicked, this, &SefeWindow::openIndex);
        connect(v, &QAbstractItemView::customContextMenuRequested, this,
                [this, v](const QPoint &p) { showContextMenu(v, p); });
        v->installEventFilter(this); // Return opens the current item
    };

    _details = new QTreeView(this);
    initView(_details);
    _details->setSortingEnabled(true);
    _details->sortByColumn(0, Qt::AscendingOrder);
    _details->setColumnWidth(0, 320);
    _details->header()->setStretchLastSection(true);

    _icons = new QListView(this);
    initView(_icons);
    _icons->setViewMode(QListView::IconMode);
    _icons->setResizeMode(QListView::Adjust);
    _icons->setWrapping(true);
    _icons->setSpacing(12);
    _icons->setUniformItemSizes(true);

    _viewStack = new QStackedWidget(this);
    _viewStack->addWidget(_details);
    _viewStack->addWidget(_icons);
    connect(viewAct, &QAction::triggered, this, [this] {
        _viewStack->setCurrentIndex(_viewStack->currentIndex() == 0 ? 1 : 0);
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

// --- navigation ---

void SefeWindow::navigateTo(const QString &dir, bool record) {
    const QString path = QDir::cleanPath(dir);
    _current = path;
    _model->setRootPath(path);
    const QModelIndex root = _model->index(path);
    _details->setRootIndex(root);
    _icons->setRootIndex(root);

    _address->setPath(path);
    setWindowTitle(helm::sefe::windowTitle(path));
    highlightPlace(path);
    statusBar()->showMessage(path);

    if (record) {
        while (_history.size() > _histIndex + 1)
            _history.removeLast();
        _history.append(path);
        _histIndex = _history.size() - 1;
    }
    updateNavActions();
}

void SefeWindow::openIndex(const QModelIndex &index) {
    if (!index.isValid())
        return;
    const QString path = _model->filePath(index);
    if (_model->isDir(index))
        navigateTo(path);
    else
        QDesktopServices::openUrl(QUrl::fromLocalFile(path)); // slice 4 routes via Customs
}

void SefeWindow::goBack() {
    if (_histIndex > 0)
        navigateTo(_history.at(--_histIndex), false);
}

void SefeWindow::goForward() {
    if (_histIndex >= 0 && _histIndex < _history.size() - 1)
        navigateTo(_history.at(++_histIndex), false);
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
    _places->setCurrentRow(-1);
    for (int i = 0; i < _places->count(); ++i) {
        if (_places->item(i)->data(Qt::UserRole).toString() == dir) {
            _places->setCurrentRow(i);
            return;
        }
    }
}

// --- operations ---

QAbstractItemView *SefeWindow::activeView() const {
    return qobject_cast<QAbstractItemView *>(_viewStack->currentWidget());
}

QStringList SefeWindow::selectedPaths() const {
    QStringList out;
    QAbstractItemView *v = activeView();
    if (!v || !v->selectionModel())
        return out;
    const auto rows = v->selectionModel()->selectedIndexes();
    for (const QModelIndex &idx : rows) {
        if (idx.column() == 0)
            out << _model->filePath(idx);
    }
    return out;
}

void SefeWindow::renameSelected() {
    QAbstractItemView *v = activeView();
    const QModelIndex idx = v ? v->currentIndex() : QModelIndex();
    if (idx.isValid())
        v->edit(idx.siblingAtColumn(0));
}

void SefeWindow::deleteSelected() {
    for (const QString &p : selectedPaths())
        QFile::moveToTrash(p); // Del → Trash (reversible), Windows-style
}

void SefeWindow::copySelected(bool cut) {
    _clip = selectedPaths();
    _clipCut = cut;
    QList<QUrl> urls;
    for (const QString &p : _clip)
        urls << QUrl::fromLocalFile(p);
    auto *mime = new QMimeData;
    mime->setUrls(urls);
    QApplication::clipboard()->setMimeData(mime);
    _pasteAct->setEnabled(!_clip.isEmpty());
}

void SefeWindow::paste() {
    if (_clip.isEmpty())
        return;
    const QDir dest(_current);
    QSet<QString> existing = entriesOf(_current);
    for (const QString &src : _clip) {
        const QString base = QFileInfo(src).fileName();
        if (_clipCut && QFileInfo(src).absolutePath() == _current)
            continue; // cut + paste into the same folder is a no-op
        // Disambiguate on any name collision. A copy into the source's own folder
        // collides because the source itself is already in `existing` → "x - Copy".
        QString name = base;
        if (existing.contains(name))
            name = copyName(base, existing);
        existing.insert(name);
        const QString target = dest.filePath(name);
        if (_clipCut)
            moveItem(src, target);
        else
            copyRecursively(src, target);
    }
    if (_clipCut) {
        _clip.clear();
        _clipCut = false;
        _pasteAct->setEnabled(false);
    }
}

void SefeWindow::newFolder() {
    const QString name = newFolderName(entriesOf(_current));
    if (!QDir(_current).mkdir(name))
        return;
    const QModelIndex idx = _model->index(QDir(_current).filePath(name));
    if (idx.isValid()) {
        QAbstractItemView *v = activeView();
        v->setCurrentIndex(idx);
        v->edit(idx.siblingAtColumn(0)); // rename the fresh folder immediately
    }
}

void SefeWindow::refresh() {
    navigateTo(_current, false); // re-root the views on the current dir
}

void SefeWindow::showProperties() {
    const QStringList sel = selectedPaths();
    const QString path = sel.isEmpty() ? _current : sel.first();
    const QFileInfo fi(path);

    auto *dlg = new QDialog(this);
    dlg->setAttribute(Qt::WA_DeleteOnClose);
    dlg->setWindowTitle(fi.fileName() + QStringLiteral(" — Properties"));
    auto *form = new QFormLayout(dlg);
    form->addRow(QStringLiteral("Name:"), new QLabel(fi.fileName(), dlg));
    form->addRow(QStringLiteral("Location:"), new QLabel(fi.absolutePath(), dlg));
    form->addRow(QStringLiteral("Type:"),
                 new QLabel(fi.isDir() ? QStringLiteral("Folder") : QStringLiteral("File"), dlg));
    if (!fi.isDir())
        form->addRow(QStringLiteral("Size:"),
                     new QLabel(QLocale().formattedDataSize(fi.size()), dlg));
    form->addRow(QStringLiteral("Modified:"),
                 new QLabel(fi.lastModified().toString(Qt::TextDate), dlg));
    dlg->show();
}

void SefeWindow::showContextMenu(QAbstractItemView *view, const QPoint &pos) {
    const QModelIndex idx = view->indexAt(pos);
    QMenu menu(this);
    if (idx.isValid()) {
        menu.addAction(_openAct);
        menu.addSeparator();
        menu.addAction(_cutAct);
        menu.addAction(_copyAct);
        menu.addSeparator();
        menu.addAction(_renameAct);
        menu.addAction(_deleteAct);
        menu.addSeparator();
        menu.addAction(_propsAct);
    } else {
        _pasteAct->setEnabled(!_clip.isEmpty());
        menu.addAction(_newFolderAct);
        menu.addAction(_pasteAct);
    }
    menu.exec(view->viewport()->mapToGlobal(pos));
}

bool SefeWindow::eventFilter(QObject *watched, QEvent *event) {
    if ((watched == _details || watched == _icons) && event->type() == QEvent::KeyPress) {
        auto *ke = static_cast<QKeyEvent *>(event);
        if (ke->key() == Qt::Key_Return || ke->key() == Qt::Key_Enter) {
            openIndex(static_cast<QAbstractItemView *>(watched)->currentIndex());
            return true;
        }
    }
    return QMainWindow::eventFilter(watched, event);
}

} // namespace helm::sefe
