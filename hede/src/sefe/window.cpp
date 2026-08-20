#include "window.h"

#include "addressbar.h"
#include "archivemodel.h" // hold: browse-in-place (Hold H3)
#include "desktopentry.h" // helm-apps: scan + Exec argv (Open with)
#include "holdcore.h"     // hold-core: archive extract/create (Hold H2)
#include "config.h"       // helm::Config: throbber intensity knob
#include "iconprovider.h"
#include "launch.h"       // helm-common: launchDetached
#include "ops.h"
#include "sefe.h"
#include "throbber.h"     // HelmThrobber: the Netscape-style busy light

#include <QAbstractItemView>
#include <QDialogButtonBox>
#include <QAction>
#include <QApplication>
#include <QClipboard>
#include <QThread>
#include <QSizePolicy>
#include <utility>
#include <QDateTime>
#include <QDesktopServices>
#include <QDialog>
#include <QDir>
#include <QFileDialog>
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
#include <QMenuBar>
#include <QMessageBox>
#include <QMimeData>
#include <QMimeDatabase>
#include <QModelIndex>
#include <QSet>
#include <QShortcut>
#include <QSplitter>
#include <QStackedWidget>
#include <QStatusBar>
#include <QTemporaryDir>
#include <QToolBar>
#include <QTreeView>
#include <QUrl>
#include <QVBoxLayout>

#include <algorithm>

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
    _iconProvider = new ThumbnailIconProvider;
    _model->setIconProvider(_iconProvider); // image thumbnails; not owned by the model
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
    _viewToggleAct = bar->addAction(QIcon::fromTheme(QStringLiteral("view-list-details")),
                                    QStringLiteral("Toggle view"));

    // --- the Helm throbber, pinned top-right (Netscape's spot) ---
    auto *spacer = new QWidget(this);
    spacer->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    bar->addWidget(spacer);
    _throbber = new HelmThrobber(this);
    if (helm::Config().string(QStringLiteral("seahorse/throbber"),
                              QStringLiteral("calm")).compare(
            QStringLiteral("lively"), Qt::CaseInsensitive) == 0)
        _throbber->setIntensity(HelmThrobber::Intensity::Lively);
    // Clicking the throbber sails Home — like Netscape's throbber → home page.
    connect(_throbber, &HelmThrobber::clicked, this,
            [this] { navigateTo(QDir::homePath()); });
    bar->addWidget(_throbber);

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
    _openWithAct = op(QStringLiteral("Open with…"), QKeySequence(), &SefeWindow::openWith);
    _drydockAct = op(QStringLiteral("Run in Drydock"), QKeySequence(), &SefeWindow::runInDrydock);
    _shareAct = op(QStringLiteral("Share this folder to the session"), QKeySequence(),
                   &SefeWindow::shareFolder);
    _copyPathAct = op(QStringLiteral("Copy location"),
                      QKeySequence(Qt::CTRL | Qt::SHIFT | Qt::Key_C), &SefeWindow::copyPaths);
    _extractHereAct = op(QStringLiteral("Extract here"), QKeySequence(), &SefeWindow::extractHere);
    _extractToAct = op(QStringLiteral("Extract to…"), QKeySequence(), &SefeWindow::extractTo);
    _compressAct = op(QStringLiteral("Compress to .zip"), QKeySequence(),
                      &SefeWindow::compressSelection);
    _holdAct = op(QStringLiteral("Open with Hold"), QKeySequence(), &SefeWindow::openInHold);
    _selectAllAct = op(QStringLiteral("Select all"), QKeySequence::SelectAll, nullptr);
    connect(_selectAllAct, &QAction::triggered, this,
            [this] { if (auto *v = activeView()) v->selectAll(); });

    buildMenuBar(); // File/Edit/View/Go/Tools/Help over the same actions

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
    // Right-click the header to show/hide columns (Name stays).
    _details->header()->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(_details->header(), &QWidget::customContextMenuRequested, this,
            [this](const QPoint &p) {
                QMenu menu(this);
                for (int col = 1; col < _model->columnCount(); ++col) {
                    QAction *a = menu.addAction(
                        _model->headerData(col, Qt::Horizontal).toString());
                    a->setCheckable(true);
                    a->setChecked(!_details->isColumnHidden(col));
                    connect(a, &QAction::toggled, this,
                            [this, col](bool on) { _details->setColumnHidden(col, !on); });
                }
                menu.exec(_details->header()->mapToGlobal(p));
            });

    _icons = new QListView(this);
    initView(_icons);
    _icons->setViewMode(QListView::IconMode);
    _icons->setIconSize(QSize(64, 64)); // room for image thumbnails
    _icons->setResizeMode(QListView::Adjust);
    _icons->setWrapping(true);
    _icons->setSpacing(12);
    _icons->setUniformItemSizes(true);

    _viewStack = new QStackedWidget(this);
    _viewStack->addWidget(_details);
    _viewStack->addWidget(_icons);
    connect(_viewToggleAct, &QAction::triggered, this, [this] {
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

SefeWindow::~SefeWindow() {
    _model->setIconProvider(nullptr); // stop the model using it before we free it
    delete _iconProvider;
    delete _archiveModel;
    delete _extractTemp;
}

// The default menu bar. Every entry is one of the QActions already built in the
// constructor, so the menu bar, the toolbar, and the right-click menu all drive
// the same action (shortcuts stay in sync). Only two actions are menu-only: the
// Menu Bar toggle and About.
void SefeWindow::buildMenuBar() {
    QMenuBar *mb = menuBar();

    QMenu *file = mb->addMenu(QStringLiteral("&File"));
    file->addAction(_newFolderAct);
    file->addAction(_openAct);
    file->addAction(_openWithAct);
    file->addSeparator();
    file->addAction(_extractHereAct);
    file->addAction(_extractToAct);
    file->addAction(_compressAct);
    file->addSeparator();
    file->addAction(_propsAct);
    QAction *closeAct = file->addAction(QStringLiteral("Close"));
    closeAct->setShortcut(QKeySequence::Close); // Ctrl+W
    connect(closeAct, &QAction::triggered, this, &QWidget::close);

    QMenu *edit = mb->addMenu(QStringLiteral("&Edit"));
    edit->addAction(_cutAct);
    edit->addAction(_copyAct);
    edit->addAction(_pasteAct);
    edit->addSeparator();
    edit->addAction(_renameAct);
    edit->addAction(_deleteAct);
    edit->addSeparator();
    edit->addAction(_copyPathAct);
    edit->addAction(_selectAllAct);

    QMenu *view = mb->addMenu(QStringLiteral("&View"));
    view->addAction(_viewToggleAct);
    view->addAction(_refreshAct);
    view->addSeparator();
    _menuBarAct = view->addAction(QStringLiteral("Menu &Bar"));
    _menuBarAct->setCheckable(true);
    _menuBarAct->setChecked(true);
    _menuBarAct->setShortcut(QKeySequence(Qt::CTRL | Qt::Key_M));
    connect(_menuBarAct, &QAction::toggled, mb, &QWidget::setVisible);
    addAction(_menuBarAct); // window-wide, so Ctrl+M restores a hidden bar

    QMenu *go = mb->addMenu(QStringLiteral("&Go"));
    go->addAction(_backAct);
    go->addAction(_fwdAct);
    go->addAction(_upAct);
    go->addSeparator();
    for (const Place &p : places()) {
        QAction *a = go->addAction(QIcon::fromTheme(p.icon), p.name);
        const QString path = p.path;
        connect(a, &QAction::triggered, this, [this, path] { navigateTo(path); });
    }

    QMenu *tools = mb->addMenu(QStringLiteral("&Tools"));
    tools->addAction(_drydockAct);
    tools->addAction(_shareAct);
    tools->addSeparator();
    tools->addAction(_holdAct);

    QMenu *help = mb->addMenu(QStringLiteral("&Help"));
    QAction *about = help->addAction(QStringLiteral("&About Seahorse"));
    connect(about, &QAction::triggered, this, &SefeWindow::showAbout);
}

void SefeWindow::showAbout() {
    QMessageBox::about(
        this, QStringLiteral("About Seahorse"),
        QStringLiteral("<b>Seahorse</b> — the Seahorse File Explorer (SeFE)<br>"
                       "HeDE's native file manager.<br><br>"
                       "Browse your hold — with archive browse-in-place, and "
                       "Drydock / Gangway / Hold interop."));
}

template <class Work, class Done>
void SefeWindow::runBusy(const QString &activity, Work work, Done done) {
    _throbber->begin(activity);
    auto *thread = QThread::create(
        [this, work = std::move(work), done = std::move(done)]() mutable {
            auto payload = work(); // hold-core runs here, off the UI thread
            // Deliver the result on the UI thread. If the window is gone by now,
            // Qt drops this queued call (receiver destroyed) — no dangling use.
            QMetaObject::invokeMethod(
                this,
                [this, payload = std::move(payload), done = std::move(done)]() mutable {
                    done(payload);
                    _throbber->end();
                },
                Qt::QueuedConnection);
        });
    connect(thread, &QThread::finished, thread, &QThread::deleteLater);
    thread->start();
}

// --- navigation ---

void SefeWindow::navigateTo(const QString &dir, bool record) {
    const QString path = QDir::cleanPath(dir);
    const ArchiveSplit split = splitArchivePath(path);

    // Switch both views to `m` (only when it actually changes, to keep the
    // details columns) then root them at `root`.
    auto useModel = [this](QAbstractItemModel *m, const QModelIndex &root) {
        if (_details->model() != m) {
            _details->setModel(m);
            _icons->setModel(m);
            _details->setColumnWidth(0, 320);
            _details->header()->setStretchLastSection(true);
        }
        _details->setRootIndex(root);
        _icons->setRootIndex(root);
    };

    if (split.archive.isEmpty()) { // filesystem
        _inArchive = false;
        _model->setRootPath(path);
        useModel(_model, _model->index(path));
        if (_archiveModel) { // left the archive — drop its model
            delete _archiveModel;
            _archiveModel = nullptr;
        }
    } else { // inside an archive
        if (!_archiveModel || _archiveModel->archivePath() != split.archive) {
            helm::hold::ArchiveModel *old = _archiveModel;
            _archiveModel = new helm::hold::ArchiveModel(split.archive);
            useModel(_archiveModel, _archiveModel->indexForInner(split.inner));
            delete old; // views no longer reference it
        } else {
            useModel(_archiveModel, _archiveModel->indexForInner(split.inner));
        }
        _inArchive = true;
    }

    _current = path;
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
    if (_inArchive && _archiveModel) { // inside an archive
        const QString inner = _archiveModel->innerPath(index);
        if (_archiveModel->isDir(index))
            navigateTo(_archiveModel->archivePath() + QLatin1Char('/') + inner);
        else
            openArchiveEntry(inner);
        return;
    }
    const QString path = _model->filePath(index);
    if (_model->isDir(index))
        navigateTo(path);
    else if (isWindowsExecutable(path))
        helm::launchDetached(QStringLiteral("drydock"), {QStringLiteral("open"), path});
    else if (helm::hold::isArchive(path))
        navigateTo(path); // walk into the archive (browse-in-place)
    else
        QDesktopServices::openUrl(QUrl::fromLocalFile(path));
}

void SefeWindow::openArchiveEntry(const QString &inner) {
    if (!_archiveModel)
        return;
    if (!_extractTemp)
        _extractTemp = new QTemporaryDir; // session-lifetime scratch for opened entries
    if (!_extractTemp->isValid())
        return;
    const QString archive = _archiveModel->archivePath();
    const QString tempDir = _extractTemp->path();
    // Extract the one entry on a worker thread (the throbber spins), then open
    // it once it lands.
    runBusy(
        QStringLiteral("Opening %1…").arg(QFileInfo(inner).fileName()),
        [archive, inner, tempDir]() -> QString {
            const helm::hold::Result r = helm::hold::extract(archive, inner, tempDir);
            return r.ok ? QString() : r.error; // empty == success
        },
        [this, inner, tempDir](const QString &error) {
            if (error.isEmpty())
                QDesktopServices::openUrl(
                    QUrl::fromLocalFile(QDir(tempDir).filePath(inner)));
            else
                statusBar()->showMessage(QStringLiteral("Open failed: %1").arg(error));
        });
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
    if (_inArchive)
        return out; // archive browsing is read-only — filesystem ops don't apply
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

void SefeWindow::openWith() {
    const QStringList sel = selectedPaths();
    if (sel.isEmpty())
        return;
    const QString file = sel.first();

    QDialog dlg(this);
    dlg.setWindowTitle(QStringLiteral("Open with"));
    auto *layout = new QVBoxLayout(&dlg);
    layout->addWidget(new QLabel(
        QStringLiteral("Open “%1” with:").arg(QFileInfo(file).fileName()), &dlg));

    auto *list = new QListWidget(&dlg);
    const QVector<helm::DesktopEntry> entries =
        helm::scanDesktopEntries(helm::defaultApplicationDirs());
    const QString mime = QMimeDatabase().mimeTypeForFile(file).name();

    QList<helm::DesktopEntry> apps; // selectable rows; item UserRole = index here
    auto valid = [](const helm::DesktopEntry &e) {
        return !e.noDisplay && !e.hidden && !e.exec.isEmpty();
    };
    auto addApp = [&](const helm::DesktopEntry &e) {
        auto *it = new QListWidgetItem(QIcon::fromTheme(e.icon), e.name, list);
        it->setData(Qt::UserRole, apps.size());
        apps.push_back(e);
    };
    // Recommended (declared handlers for this file's MIME type) first...
    QSet<QString> recommended;
    for (const helm::DesktopEntry &e : helm::handlersForMimeType(entries, mime)) {
        if (valid(e)) {
            addApp(e);
            recommended.insert(e.id);
        }
    }
    // ...then a non-selectable divider and every other app.
    if (!apps.isEmpty()) {
        auto *sep = new QListWidgetItem(QStringLiteral("— All applications —"), list);
        sep->setFlags(Qt::NoItemFlags);
    }
    for (const helm::DesktopEntry &e : entries) {
        if (valid(e) && !recommended.contains(e.id))
            addApp(e);
    }
    layout->addWidget(list);

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Open | QDialogButtonBox::Cancel, &dlg);
    layout->addWidget(buttons);
    connect(buttons, &QDialogButtonBox::accepted, &dlg, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dlg, &QDialog::reject);
    connect(list, &QListWidget::itemDoubleClicked, &dlg, &QDialog::accept);

    if (dlg.exec() != QDialog::Accepted)
        return;
    QListWidgetItem *chosen = list->currentItem();
    const QVariant which = chosen ? chosen->data(Qt::UserRole) : QVariant();
    if (!which.isValid())
        return; // nothing selected, or the divider
    QStringList argv = helm::commandArgv(apps.at(which.toInt()));
    if (argv.isEmpty())
        return;
    argv.append(file); // commandArgv strips %f/%u — append the target ourselves
    helm::launchDetached(argv.first(), argv.mid(1));
}

void SefeWindow::runInDrydock() {
    const QStringList sel = selectedPaths();
    if (!sel.isEmpty())
        helm::launchDetached(QStringLiteral("drydock"), {QStringLiteral("open"), sel.first()});
}

void SefeWindow::shareFolder() {
    // Share the selected folder, else the folder we're viewing.
    QString folder = _current;
    const QStringList sel = selectedPaths();
    if (sel.size() == 1 && QFileInfo(sel.first()).isDir())
        folder = sel.first();
    helm::launchDetached(QStringLiteral("gangway"), {QStringLiteral("share"), folder});
}

void SefeWindow::copyPaths() {
    const QStringList sel = selectedPaths();
    if (!sel.isEmpty())
        QApplication::clipboard()->setText(sel.join(QLatin1Char('\n')));
}

// H2: quick archive actions over hold-core. Synchronous for now — a progress /
// off-thread pass is a later polish; large archives will block until then.

void SefeWindow::extractHere() {
    QStringList archives;
    for (const QString &p : selectedPaths())
        if (helm::hold::isArchive(p))
            archives << p;
    if (archives.isEmpty())
        return;
    const QString dest = _current;
    runBusy(
        archives.size() == 1
            ? QStringLiteral("Extracting %1…").arg(QFileInfo(archives.first()).fileName())
            : QStringLiteral("Extracting %1 archives…").arg(archives.size()),
        [archives, dest]() -> QString {
            int ok = 0;
            for (const QString &archive : archives) {
                const helm::hold::Result r = helm::hold::extractAll(archive, dest);
                if (!r.ok)
                    return QStringLiteral("Extract failed: %1").arg(r.error);
                ++ok;
            }
            return ok == 1 ? QStringLiteral("Extracted %1").arg(QFileInfo(archives.first()).fileName())
                           : QStringLiteral("Extracted %1 archives").arg(ok);
        },
        [this](const QString &msg) { statusBar()->showMessage(msg); });
}

void SefeWindow::extractTo() {
    const QStringList sel = selectedPaths();
    const auto it = std::find_if(sel.begin(), sel.end(), helm::hold::isArchive);
    if (it == sel.end())
        return;
    const QString dest =
        QFileDialog::getExistingDirectory(this, QStringLiteral("Extract to"), _current);
    if (dest.isEmpty())
        return;
    const QString archive = *it;
    runBusy(
        QStringLiteral("Extracting %1…").arg(QFileInfo(archive).fileName()),
        [archive, dest]() -> QString {
            const helm::hold::Result r = helm::hold::extractAll(archive, dest);
            return r.ok ? QStringLiteral("Extracted to %1").arg(dest)
                        : QStringLiteral("Extract failed: %1").arg(r.error);
        },
        [this](const QString &msg) { statusBar()->showMessage(msg); });
}

void SefeWindow::openInHold() {
    const QStringList sel = selectedPaths();
    if (!sel.isEmpty())
        helm::launchDetached(QStringLiteral("hold"), {sel.first()});
}

void SefeWindow::compressSelection() {
    const QStringList sel = selectedPaths();
    if (sel.isEmpty())
        return;
    const QString name = compressTargetName(sel, entriesOf(_current));
    const QString dest = QDir(_current).filePath(name);
    runBusy(
        QStringLiteral("Compressing to %1…").arg(name),
        [sel, dest, name]() -> QString {
            const helm::hold::Result r = helm::hold::create(sel, dest);
            return r.ok ? QStringLiteral("Created %1").arg(name)
                        : QStringLiteral("Compress failed: %1").arg(r.error);
        },
        [this](const QString &msg) { statusBar()->showMessage(msg); });
}

void SefeWindow::showContextMenu(QAbstractItemView *view, const QPoint &pos) {
    const QModelIndex idx = view->indexAt(pos);
    QMenu menu(this);
    if (_inArchive) { // read-only browsing: just Open the clicked entry
        if (idx.isValid()) {
            QAction *open = menu.addAction(QStringLiteral("Open"));
            connect(open, &QAction::triggered, this, [this, idx] { openIndex(idx); });
            menu.exec(view->viewport()->mapToGlobal(pos));
        }
        return;
    }
    if (idx.isValid()) {
        const bool isDir = _model->isDir(idx);
        const QString path = _model->filePath(idx);
        menu.addAction(_openAct);
        if (!isDir) {
            menu.addAction(_openWithAct);
            if (isWindowsExecutable(path))
                menu.addAction(_drydockAct);
            if (helm::hold::isArchive(path)) {
                menu.addAction(_extractHereAct);
                menu.addAction(_extractToAct);
                menu.addAction(_holdAct);
            }
        }
        if (isDir)
            menu.addAction(_shareAct); // share this folder to the session
        menu.addAction(_compressAct);  // compress the selection to a .zip
        menu.addSeparator();
        menu.addAction(_cutAct);
        menu.addAction(_copyAct);
        menu.addAction(_copyPathAct);
        menu.addSeparator();
        menu.addAction(_renameAct);
        menu.addAction(_deleteAct);
        menu.addSeparator();
        menu.addAction(_propsAct);
    } else {
        _pasteAct->setEnabled(!_clip.isEmpty());
        menu.addAction(_newFolderAct);
        menu.addAction(_pasteAct);
        menu.addSeparator();
        menu.addAction(_shareAct); // share the current folder to the session
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
