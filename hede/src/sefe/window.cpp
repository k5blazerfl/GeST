#include "window.h"

#include "addressbar.h"
#include "archivemodel.h" // hold: browse-in-place (Hold H3)
#include "desktopentry.h" // helm-apps: scan + Exec argv (Open with)
#include "holdcore.h"     // hold-core: archive extract/create (Hold H2)
#include "job.h"          // hold::Job: cancellable, progress-reporting archive ops (A0)
#include "config.h"       // helm::Config: throbber intensity knob
#include "iconprovider.h"
#include "launch.h"       // helm-common: launchDetached
#include "ops.h"
#include "palette.h"      // helm::effectiveAccent (scene-less fallback fill)
#include "sefe.h"
#include "throbber.h"     // HelmThrobber: the Netscape-style busy light
#include "titlebar.h"     // HelmTitleBar: the client-side titlebar (frameless chrome)
#include "world.h"        // helm::loadWorld: the active biome's wallpaper scene

#include <QAbstractItemView>
#include <QDialogButtonBox>
#include <QAction>
#include <QApplication>
#include <QClipboard>
#include <QDrag>
#include <QDropEvent>
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
#include <QInputDialog>
#include <QKeyEvent>
#include <QKeySequence>
#include <QLabel>
#include <QLinearGradient>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPaintEvent>
#include <QProgressDialog>
#include <QWindow>
#include <QListView>
#include <QListWidget>
#include <QLocale>
#include <QMenu>
#include <QMenuBar>
#include <QMessageBox>
#include <QPushButton>
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

SefeWindow::SefeWindow(const QString &startPath, QWidget *parent) : QMainWindow(parent) {
    resize(960, 620);
    // The HeDE app-chrome contract: the shared shell stylesheet
    // (helm::styleSheet) tints #HelmAppWindow's menu bar, toolbar, address field,
    // Places pane and status bar with the world glass — "the chrome is the world"
    // — while the content body keeps the light/dark palette. SeFE is the template
    // for any future xdg-toplevel HeDE app. See docs/design/seahorse-appearance.md.
    setObjectName(QStringLiteral("HelmAppWindow"));

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
    _address->setObjectName(QStringLiteral("HelmAddressBar"));
    _address->setAttribute(Qt::WA_StyledBackground, true); // let QSS paint the field
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
    _arcExtractSelAct = op(QStringLiteral("Extract Selected…"), QKeySequence(),
                           &SefeWindow::extractSelectedEntries);
    _arcExtractAllAct = op(QStringLiteral("Extract All…"), QKeySequence(),
                           &SefeWindow::extractWholeArchive);
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
        // Archive drag-and-drop (A2): accept file drops on the viewport (add to the
        // archive) and start a custom drag-out from it. We drive both from
        // eventFilter, so the view's own DnD stays off.
        v->setAcceptDrops(true);
        v->viewport()->setAcceptDrops(true);
        v->viewport()->installEventFilter(this);
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
    _places->setObjectName(QStringLiteral("HelmAppPlaces")); // world-glass nav pane
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
    // A read-only pill on the right of the status bar, shown only while browsing
    // inside an archive (archives are read-only until the streaming manager lands —
    // see docs/design/archive-support.md).
    _readOnlyPill = new QLabel(QStringLiteral("🗜 Read-only"), this);
    _readOnlyPill->setObjectName(QStringLiteral("HelmReadOnlyPill"));
    _readOnlyPill->setVisible(false);
    statusBar()->addPermanentWidget(_readOnlyPill);
    buildSceneChrome();
    // Open the requested folder/archive (command line / file association), else Home.
    navigateTo(startPath.isEmpty() ? initialDir() : QDir::cleanPath(startPath));
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
    // Our own menu bar (not QMainWindow::menuBar()): buildSceneChrome() stacks it
    // under the client titlebar inside the header widget via setMenuWidget().
    _menuBar = new QMenuBar(this);
    QMenuBar *mb = _menuBar;

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

// --- frameless scene chrome (Phase D) ---
// "The chrome is the world, the content is glass." SeFE paints the active biome's
// wallpaper across the whole window and floats an opaque body panel inset within,
// so the scene forms one continuous painterly header + footer + side trim. Being
// frameless, it also draws its own titlebar and drives move/resize.

void SefeWindow::buildSceneChrome() {
    setWindowFlag(Qt::FramelessWindowHint, true);
    setAttribute(Qt::WA_TranslucentBackground, true);
    setProperty("helmScene", true); // opt into the scene-mode QSS overrides

    // Header: the client titlebar stacked above the menu bar, installed as the
    // main window's menu widget so the real QMenuBar keeps working.
    _titlebar = new HelmTitleBar(this);
    _titlebar->setTitle(QStringLiteral("Seahorse"));
    auto *header = new QWidget(this);
    header->setObjectName(QStringLiteral("HelmHeader"));
    auto *hv = new QVBoxLayout(header);
    hv->setContentsMargins(0, 0, 0, 0);
    hv->setSpacing(0);
    hv->addWidget(_titlebar);
    if (_menuBar)
        hv->addWidget(_menuBar);
    setMenuWidget(header);

    // Inset the body so the scene shows as a thin trim down the sides and along the
    // bottom; the body itself (#HelmAppBody) is an opaque panel that keeps the
    // light/dark content readable over any scene.
    if (QWidget *body = centralWidget()) {
        body->setObjectName(QStringLiteral("HelmAppBody"));
        body->setAttribute(Qt::WA_StyledBackground, true);
        auto *inset = new QWidget(this);
        inset->setObjectName(QStringLiteral("HelmAppBodyInset"));
        auto *iv = new QVBoxLayout(inset);
        iv->setContentsMargins(kResizeMargin, 3, kResizeMargin, kResizeMargin);
        iv->addWidget(body);
        setCentralWidget(inset); // reparents `body` into the inset container
    }

    setMouseTracking(true); // so the resize cursor updates as it crosses the trim
    loadScene();
}

void SefeWindow::loadScene() {
    const helm::Config cfg;
    _accent = helm::effectiveAccent(cfg);
    const helm::World world =
        helm::loadWorld(cfg.string(QStringLiteral("world/id"), QStringLiteral("harbor")));
    const QString path = world.wallpaperPath();
    QPixmap scene;
    if (!path.isEmpty())
        scene.load(path);
    _scene = scene;
    update();
}

int SefeWindow::headerHeight() const {
    // The top scene band: everything above the inset body (titlebar+menu+toolbar).
    if (const QWidget *c = centralWidget())
        return c->mapTo(this, QPoint(0, 0)).y();
    return 100;
}

int SefeWindow::footerHeight() const {
    // The bottom scene band: the status bar area below the inset body.
    if (const QWidget *c = centralWidget()) {
        const int bodyBottom = c->mapTo(this, QPoint(0, c->height())).y();
        return qMax(0, height() - bodyBottom);
    }
    return 28;
}

Qt::Edges SefeWindow::resizeEdgeAt(const QPoint &pos) const {
    Qt::Edges edges;
    if (pos.x() <= kResizeMargin)
        edges |= Qt::LeftEdge;
    else if (pos.x() >= width() - kResizeMargin)
        edges |= Qt::RightEdge;
    if (pos.y() <= kResizeMargin)
        edges |= Qt::TopEdge;
    else if (pos.y() >= height() - kResizeMargin)
        edges |= Qt::BottomEdge;
    return edges;
}

void SefeWindow::paintEvent(QPaintEvent *event) {
    QMainWindow::paintEvent(event);
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    p.setRenderHint(QPainter::SmoothPixmapTransform);

    const QRectF r = rect();
    constexpr qreal radius = 8.0;
    QPainterPath clip;
    clip.addRoundedRect(r, radius, radius);
    p.setClipPath(clip);

    // The world scene, cover-scaled and centred behind the whole window.
    if (!_scene.isNull()) {
        const QSize target = _scene.size().scaled(size(), Qt::KeepAspectRatioByExpanding);
        const QPixmap scaled =
            _scene.scaled(target, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation);
        p.drawPixmap(QPoint((width() - scaled.width()) / 2, (height() - scaled.height()) / 2),
                     scaled);
    } else {
        p.fillRect(r, _accent.isValid() ? _accent : helm::barTint(helm::harborAccent()));
    }

    // Legibility scrims: darken the scene under the header and footer so the light
    // chrome glyphs stay readable over any world.
    const int hh = headerHeight();
    if (hh > 0) {
        QLinearGradient top(0, 0, 0, hh);
        top.setColorAt(0.0, QColor(0, 0, 0, 155));
        top.setColorAt(1.0, QColor(0, 0, 0, 0));
        p.fillRect(QRectF(0, 0, width(), hh), top);
    }
    const int fh = footerHeight();
    if (fh > 0) {
        QLinearGradient bot(0, height() - fh, 0, height());
        bot.setColorAt(0.0, QColor(0, 0, 0, 0));
        bot.setColorAt(1.0, QColor(0, 0, 0, 140));
        p.fillRect(QRectF(0, height() - fh, width(), fh), bot);
    }

    // A hairline edge to define the rounded window against the desktop.
    p.setClipping(false);
    p.setBrush(Qt::NoBrush);
    p.setPen(QPen(QColor(255, 255, 255, 46), 1.0));
    p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius);
}

void SefeWindow::mousePressEvent(QMouseEvent *event) {
    // A press on the scene trim starts an interactive resize (frameless windows
    // have no server-side resize border); the titlebar handles move.
    if (event->button() == Qt::LeftButton) {
        const Qt::Edges edges = resizeEdgeAt(event->pos());
        if (edges) {
            if (QWindow *handle = windowHandle()) {
                handle->startSystemResize(edges);
                return;
            }
        }
    }
    QMainWindow::mousePressEvent(event);
}

void SefeWindow::mouseMoveEvent(QMouseEvent *event) {
    const Qt::Edges e = resizeEdgeAt(event->pos());
    Qt::CursorShape shape = Qt::ArrowCursor;
    if (((e & Qt::TopEdge) && (e & Qt::LeftEdge)) || ((e & Qt::BottomEdge) && (e & Qt::RightEdge)))
        shape = Qt::SizeFDiagCursor;
    else if (((e & Qt::TopEdge) && (e & Qt::RightEdge)) ||
             ((e & Qt::BottomEdge) && (e & Qt::LeftEdge)))
        shape = Qt::SizeBDiagCursor;
    else if (e & (Qt::LeftEdge | Qt::RightEdge))
        shape = Qt::SizeHorCursor;
    else if (e & (Qt::TopEdge | Qt::BottomEdge))
        shape = Qt::SizeVerCursor;
    setCursor(shape);
    QMainWindow::mouseMoveEvent(event);
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

void SefeWindow::runJob(const QString &title,
                        std::function<helm::hold::Result(const helm::hold::Progress &)> work,
                        std::function<QString(const helm::hold::Result &)> summary) {
    auto *job = new helm::hold::Job(title, this);
    // The dialog appears only if the op outlives the delay, so quick archives never
    // flash it; it drives cancel and shows the current entry.
    auto *dlg = new QProgressDialog(title, QStringLiteral("Cancel"), 0, 0, this);
    dlg->setWindowModality(Qt::WindowModal);
    dlg->setMinimumDuration(600);
    dlg->setAutoClose(false);
    dlg->setAutoReset(false);
    dlg->setValue(0);

    connect(job, &helm::hold::Job::progress, dlg,
            [dlg](qint64 done, qint64 total, const QString &name) {
                if (total > 0) {
                    if (dlg->maximum() != int(total))
                        dlg->setMaximum(int(total));
                    dlg->setValue(int(done));
                } else if (dlg->maximum() != 0) {
                    dlg->setRange(0, 0); // unknown total → indeterminate
                }
                dlg->setLabelText(name);
            });
    connect(dlg, &QProgressDialog::canceled, job, &helm::hold::Job::cancel);

    _throbber->begin(title);
    connect(job, &helm::hold::Job::finished, this,
            [this, dlg, job, summary](const helm::hold::Result &r) {
                _throbber->end();
                dlg->reset();
                dlg->deleteLater();
                job->deleteLater();
                const QString msg = summary(r);
                if (!msg.isEmpty())
                    statusBar()->showMessage(msg);
            });
    job->run(std::move(work));
}

// --- navigation ---

// Switch both views to `m` (only when it changes, to keep the details columns)
// then root them at `root`.
void SefeWindow::setViewModel(QAbstractItemModel *m, const QModelIndex &root) {
    if (_details->model() != m) {
        _details->setModel(m);
        _icons->setModel(m);
        _details->setColumnWidth(0, 320);
        _details->header()->setStretchLastSection(true);
    }
    _details->setRootIndex(root);
    _icons->setRootIndex(root);
}

// The address/title/status/history bookkeeping shared by every navigation, once
// the model is in place (synchronously, or after an async archive load).
void SefeWindow::finishNavigate(const QString &path, bool record) {
    _current = path;
    _address->setPath(path);
    setWindowTitle(helm::sefe::windowTitle(path));
    if (_titlebar) // frameless: mirror the title into the client titlebar
        _titlebar->setTitle(helm::sefe::windowTitle(path));
    highlightPlace(path);
    statusBar()->showMessage(path);
    if (_readOnlyPill) // only genuinely read-only formats (RAR/CBR) — writable archives edit in place
        _readOnlyPill->setVisible(_inArchive && _archiveModel &&
                                  !helm::hold::isWritableArchive(_archiveModel->archivePath()));

    if (record) {
        while (_history.size() > _histIndex + 1)
            _history.removeLast();
        _history.append(path);
        _histIndex = _history.size() - 1;
    }
    updateNavActions();
}

void SefeWindow::navigateTo(const QString &dir, bool record, bool forceReload) {
    const QString path = QDir::cleanPath(dir);
    const ArchiveSplit split = splitArchivePath(path);
    const quint64 gen = ++_navGen; // an in-flight archive load older than this is stale

    if (split.archive.isEmpty()) { // filesystem — synchronous
        _inArchive = false;
        _model->setRootPath(path);
        setViewModel(_model, _model->index(path));
        if (_archiveModel) { // left the archive — drop its model
            delete _archiveModel;
            _archiveModel = nullptr;
        }
        finishNavigate(path, record);
        return;
    }
    if (!forceReload && _archiveModel && _archiveModel->archivePath() == split.archive) {
        // already inside this archive — just re-root, no re-read
        _inArchive = true;
        setViewModel(_archiveModel, _archiveModel->indexForInner(split.inner));
        finishNavigate(path, record);
        return;
    }

    // A NEW archive: read its table of contents OFF the UI thread (a big or
    // network archive mustn't freeze the browse), then build the model + swap on
    // return. The throbber spins meanwhile; a newer navigation supersedes this one
    // via the generation guard.
    _throbber->begin(QStringLiteral("Reading %1…").arg(QFileInfo(split.archive).fileName()));
    auto *job = new helm::hold::Job(QStringLiteral("Reading"), this);
    auto listing = std::make_shared<helm::hold::Listing>();
    connect(job, &helm::hold::Job::finished, this,
            [this, path, split, record, gen, job, listing](const helm::hold::Result &r) {
                job->deleteLater();
                _throbber->end();
                if (gen != _navGen)
                    return; // superseded by a newer navigation — drop this load
                if (!r.ok) {
                    statusBar()->showMessage(QStringLiteral("Cannot open %1: %2")
                                                 .arg(QFileInfo(split.archive).fileName(), r.error));
                    return;
                }
                helm::hold::ArchiveModel *old = _archiveModel;
                _archiveModel = new helm::hold::ArchiveModel(split.archive, *listing);
                _inArchive = true;
                setViewModel(_archiveModel, _archiveModel->indexForInner(split.inner));
                delete old; // views now reference the new model
                finishNavigate(path, record);
            });
    job->run([split, listing](const helm::hold::Progress &) -> helm::hold::Result {
        *listing = helm::hold::list(split.archive); // the slow read, off-thread
        helm::hold::Result res;
        res.ok = listing->ok;
        if (!res.ok)
            res.error = listing->error;
        return res;
    });
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
    if (_inArchive) { // A2: rename an entry inside the archive (rewrite)
        const QStringList sel = selectedInnerEntries();
        if (sel.size() != 1)
            return; // one at a time
        const QString from = sel.first();
        const QString oldName = from.section(QLatin1Char('/'), -1);
        bool ok = false;
        const QString newName =
            QInputDialog::getText(this, QStringLiteral("Rename"), QStringLiteral("New name:"),
                                  QLineEdit::Normal, oldName, &ok)
                .trimmed();
        if (!ok || newName.isEmpty() || newName == oldName || newName.contains(QLatin1Char('/')))
            return;
        const QString parent =
            from.contains(QLatin1Char('/')) ? from.section(QLatin1Char('/'), 0, -2) + QLatin1Char('/')
                                            : QString();
        helm::hold::Edits e;
        e.rename.append({from, parent + newName});
        mutateArchive(e, QStringLiteral("Renaming %1…").arg(oldName));
        return;
    }
    QAbstractItemView *v = activeView();
    const QModelIndex idx = v ? v->currentIndex() : QModelIndex();
    if (idx.isValid())
        v->edit(idx.siblingAtColumn(0));
}

void SefeWindow::deleteSelected() {
    if (_inArchive) { // A2: remove entries from the archive (rewrite) — no Trash inside
        const QStringList inner = selectedInnerEntries();
        if (inner.isEmpty())
            return;
        const auto btn = QMessageBox::question(
            this, QStringLiteral("Delete from archive"),
            QStringLiteral("Permanently remove %1 item(s) from the archive? "
                           "This can't be undone.")
                .arg(inner.size()));
        if (btn != QMessageBox::Yes)
            return;
        helm::hold::Edits e;
        e.remove = inner;
        mutateArchive(e, QStringLiteral("Deleting %1 item(s)…").arg(inner.size()));
        return;
    }
    const QStringList paths = selectedPaths();
    if (paths.isEmpty())
        return;
    // Off the UI thread (throbber spins): trashing a big tree — or anything on a
    // slow/network mount — mustn't freeze the window. Del → Trash, Windows-style.
    runBusy(
        QStringLiteral("Deleting %1 item(s)…").arg(paths.size()),
        [paths]() -> QString {
            int ok = 0;
            for (const QString &p : paths)
                if (QFile::moveToTrash(p))
                    ++ok;
            return QStringLiteral("Moved %1 item(s) to Trash").arg(ok);
        },
        [this](const QString &msg) { statusBar()->showMessage(msg); });
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
    if (_inArchive) { // A2: add the clipboard's host files into the archive (rewrite)
        const QString innerDir = splitArchivePath(_current).inner;
        helm::hold::Edits e;
        for (const QString &src : _clip) {
            const QString base = QFileInfo(src).fileName();
            e.add.append({src, innerDir.isEmpty() ? base : innerDir + QLatin1Char('/') + base});
        }
        mutateArchive(e, QStringLiteral("Adding %1 item(s)…").arg(_clip.size()));
        return; // a filesystem "cut" isn't consumed — we copied INTO the archive
    }
    const QStringList clip = _clip;
    const bool cut = _clipCut;
    const QString dest = _current;
    // Copy/move runs off the UI thread (throbber spins): a large tree — or a
    // slow/network target — would otherwise freeze the window.
    runBusy(
        cut ? QStringLiteral("Moving %1 item(s)…").arg(clip.size())
            : QStringLiteral("Copying %1 item(s)…").arg(clip.size()),
        [clip, cut, dest]() -> QString {
            const QDir destDir(dest);
            QSet<QString> existing = entriesOf(dest);
            int ok = 0;
            for (const QString &src : clip) {
                const QString base = QFileInfo(src).fileName();
                if (cut && QFileInfo(src).absolutePath() == dest)
                    continue; // cut + paste into the same folder is a no-op
                // Disambiguate on any name collision. A copy into the source's own
                // folder collides (the source is already in `existing`) → "x - Copy".
                QString name = base;
                if (existing.contains(name))
                    name = copyName(base, existing);
                existing.insert(name);
                const QString target = destDir.filePath(name);
                if (cut ? moveItem(src, target) : copyRecursively(src, target))
                    ++ok;
            }
            return (cut ? QStringLiteral("Moved %1 item(s)") : QStringLiteral("Copied %1 item(s)"))
                .arg(ok);
        },
        [this, cut](const QString &msg) {
            statusBar()->showMessage(msg);
            if (cut) { // a move consumes the clipboard
                _clip.clear();
                _clipCut = false;
                _pasteAct->setEnabled(false);
            }
        });
}

void SefeWindow::newFolder() {
    if (_inArchive) { // A2: add an empty folder into the archive (rewrite)
        bool ok = false;
        const QString name =
            QInputDialog::getText(this, QStringLiteral("New folder"),
                                  QStringLiteral("Folder name:"), QLineEdit::Normal,
                                  QStringLiteral("New folder"), &ok)
                .trimmed();
        if (!ok || name.isEmpty() || name.contains(QLatin1Char('/')))
            return;
        // hold::rewrite ingests a HOST path, so add an empty temp dir at the target
        // inner path. The temp dir is held alive until the rewrite finishes.
        auto tmp = std::make_shared<QTemporaryDir>();
        if (!tmp->isValid())
            return;
        const QString innerDir = splitArchivePath(_current).inner;
        helm::hold::Edits e;
        e.add.append({tmp->path(), innerDir.isEmpty() ? name : innerDir + QLatin1Char('/') + name});
        mutateArchive(e, QStringLiteral("Adding %1…").arg(name), tmp);
        return;
    }
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

// A failed archive Result → a status message; a cancel reads as such, not a failure.
static QString archiveFailMsg(const QString &verb, const helm::hold::Result &r) {
    return r.error == QLatin1String("cancelled")
               ? QStringLiteral("%1 cancelled").arg(verb)
               : QStringLiteral("%1 failed: %2").arg(verb, r.error);
}

std::optional<helm::hold::Overwrite>
SefeWindow::resolveOverwrite(const QString &dest, const QStringList &relPaths) {
    bool collision = false;
    for (const QString &rel : relPaths) {
        const QString target = helm::hold::safeJoin(dest, rel);
        if (!target.isEmpty() && (QFileInfo::exists(target) || QFileInfo(target).isSymLink())) {
            collision = true;
            break;
        }
    }
    if (!collision)
        return helm::hold::Overwrite::Replace; // nothing there to overwrite — no prompt

    QMessageBox box(this);
    box.setIcon(QMessageBox::Question);
    box.setWindowTitle(QStringLiteral("Files already exist"));
    box.setText(QStringLiteral("Some items already exist in the destination."));
    box.setInformativeText(
        QStringLiteral("Replace them, keep both, or skip the ones that exist?"));
    QPushButton *replace = box.addButton(QStringLiteral("Replace"), QMessageBox::AcceptRole);
    QPushButton *both = box.addButton(QStringLiteral("Keep Both"), QMessageBox::ActionRole);
    QPushButton *skip = box.addButton(QStringLiteral("Skip"), QMessageBox::ActionRole);
    box.addButton(QMessageBox::Cancel);
    box.setDefaultButton(both); // the least destructive choice
    box.exec();

    QAbstractButton *clicked = box.clickedButton();
    if (clicked == replace)
        return helm::hold::Overwrite::Replace;
    if (clicked == both)
        return helm::hold::Overwrite::KeepBoth;
    if (clicked == skip)
        return helm::hold::Overwrite::Skip;
    return std::nullopt; // Cancel / closed
}

void SefeWindow::extractHere() {
    QStringList archives;
    for (const QString &p : selectedPaths())
        if (helm::hold::isArchive(p))
            archives << p;
    if (archives.isEmpty())
        return;
    const QString dest = _current;

    QStringList rels; // pre-scan every archive's entries for on-disk collisions
    for (const QString &archive : archives)
        for (const helm::hold::Entry &e : helm::hold::list(archive).entries)
            rels << e.path;
    const auto policy = resolveOverwrite(dest, rels);
    if (!policy)
        return; // cancelled
    const helm::hold::Overwrite ow = *policy;

    const QString one = QFileInfo(archives.first()).fileName();
    runJob(
        archives.size() == 1 ? QStringLiteral("Extracting %1…").arg(one)
                             : QStringLiteral("Extracting %1 archives…").arg(archives.size()),
        [archives, dest, ow](const helm::hold::Progress &p) -> helm::hold::Result {
            for (const QString &archive : archives) {
                const helm::hold::Result r = helm::hold::extractAll(archive, dest, p, {}, ow);
                if (!r.ok)
                    return r;
            }
            helm::hold::Result ok;
            ok.ok = true;
            return ok;
        },
        [archives, one](const helm::hold::Result &r) {
            if (!r.ok)
                return archiveFailMsg(QStringLiteral("Extract"), r);
            return archives.size() == 1 ? QStringLiteral("Extracted %1").arg(one)
                                        : QStringLiteral("Extracted %1 archives").arg(archives.size());
        });
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

    QStringList rels;
    for (const helm::hold::Entry &e : helm::hold::list(archive).entries)
        rels << e.path;
    const auto policy = resolveOverwrite(dest, rels);
    if (!policy)
        return; // cancelled
    const helm::hold::Overwrite ow = *policy;

    runJob(
        QStringLiteral("Extracting %1…").arg(QFileInfo(archive).fileName()),
        [archive, dest, ow](const helm::hold::Progress &p) {
            return helm::hold::extractAll(archive, dest, p, {}, ow);
        },
        [dest](const helm::hold::Result &r) {
            return r.ok ? QStringLiteral("Extracted to %1").arg(dest)
                        : archiveFailMsg(QStringLiteral("Extract"), r);
        });
}

// Rich archive ops, folded in from the former standalone Hold app: while browsing
// inside an archive, extract entries straight to a chosen folder. hold-core runs
// off the UI thread via runJob — a progress dialog with Cancel for the big ones.

QStringList SefeWindow::selectedInnerEntries() const {
    QStringList out;
    if (!_inArchive || !_archiveModel)
        return out;
    QAbstractItemView *v = activeView();
    if (!v || !v->selectionModel())
        return out;
    for (const QModelIndex &idx : v->selectionModel()->selectedIndexes()) {
        if (idx.column() != 0)
            continue;
        const QString inner = _archiveModel->innerPath(idx);
        if (!inner.isEmpty())
            out << inner;
    }
    return out;
}

void SefeWindow::extractSelectedEntries() {
    if (!_inArchive || !_archiveModel)
        return;
    const QStringList entries = selectedInnerEntries();
    if (entries.isEmpty())
        return;
    const QString dest =
        QFileDialog::getExistingDirectory(this, QStringLiteral("Extract selected to"), _current);
    if (dest.isEmpty())
        return;
    const QString archive = _archiveModel->archivePath();

    const auto policy = resolveOverwrite(dest, entries); // the selected paths ARE the targets
    if (!policy)
        return; // cancelled
    const helm::hold::Overwrite ow = *policy;

    runJob(
        QStringLiteral("Extracting %1 item(s)…").arg(entries.size()),
        [archive, entries, dest, ow](const helm::hold::Progress &p) {
            return helm::hold::extractEntries(archive, entries, dest, p, {}, ow); // one pass
        },
        [entries, dest](const helm::hold::Result &r) {
            return r.ok ? QStringLiteral("Extracted %1 item(s) to %2").arg(entries.size()).arg(dest)
                        : archiveFailMsg(QStringLiteral("Extract"), r);
        });
}

void SefeWindow::extractWholeArchive() {
    if (!_inArchive || !_archiveModel)
        return;
    const QString archive = _archiveModel->archivePath();
    const QString dest =
        QFileDialog::getExistingDirectory(this, QStringLiteral("Extract all to"), _current);
    if (dest.isEmpty())
        return;

    QStringList rels;
    for (const helm::hold::Entry &e : helm::hold::list(archive).entries)
        rels << e.path;
    const auto policy = resolveOverwrite(dest, rels);
    if (!policy)
        return; // cancelled
    const helm::hold::Overwrite ow = *policy;

    runJob(
        QStringLiteral("Extracting %1…").arg(QFileInfo(archive).fileName()),
        [archive, dest, ow](const helm::hold::Progress &p) {
            return helm::hold::extractAll(archive, dest, p, {}, ow);
        },
        [dest](const helm::hold::Result &r) {
            return r.ok ? QStringLiteral("Extracted to %1").arg(dest)
                        : archiveFailMsg(QStringLiteral("Extract"), r);
        });
}

void SefeWindow::mutateArchive(const helm::hold::Edits &edits, const QString &activity,
                              std::shared_ptr<QTemporaryDir> keepalive) {
    if (!_inArchive || !_archiveModel || edits.isEmpty())
        return;
    const QString archive = _archiveModel->archivePath();
    if (!helm::hold::isWritableArchive(archive)) {
        statusBar()->showMessage(QStringLiteral("This archive format is read-only"));
        return;
    }
    const QString reloadPath = _current;
    runJob(
        activity,
        [archive, edits, keepalive](const helm::hold::Progress &p) { // keepalive held until done
            return helm::hold::rewrite(archive, edits, p);
        },
        [this, reloadPath, activity](const helm::hold::Result &r) -> QString {
            if (r.ok) {
                // The archive changed on disk — re-read it (forceReload swaps the
                // model safely). navigateTo sets its own status.
                navigateTo(reloadPath, /*record=*/false, /*forceReload=*/true);
                return QString();
            }
            return archiveFailMsg(activity, r);
        });
}

void SefeWindow::compressSelection() {
    const QStringList sel = selectedPaths();
    if (sel.isEmpty())
        return;
    const QString name = compressTargetName(sel, entriesOf(_current));
    const QString dest = QDir(_current).filePath(name);
    runJob(
        QStringLiteral("Compressing to %1…").arg(name),
        [sel, dest](const helm::hold::Progress &p) { return helm::hold::create(sel, dest, p); },
        [name](const helm::hold::Result &r) {
            return r.ok ? QStringLiteral("Created %1").arg(name)
                        : archiveFailMsg(QStringLiteral("Compress"), r);
        });
}

void SefeWindow::showContextMenu(QAbstractItemView *view, const QPoint &pos) {
    const QModelIndex idx = view->indexAt(pos);
    QMenu menu(this);
    if (_inArchive) { // browse + (for writable formats) edit in place — A2
        const bool writable =
            _archiveModel && helm::hold::isWritableArchive(_archiveModel->archivePath());
        if (idx.isValid()) {
            QAction *open = menu.addAction(QStringLiteral("Open"));
            connect(open, &QAction::triggered, this, [this, idx] { openIndex(idx); });
            menu.addSeparator();
            menu.addAction(_arcExtractSelAct); // extract the selected entries
            if (writable) {
                menu.addSeparator();
                menu.addAction(_renameAct);
                menu.addAction(_deleteAct);
            }
        }
        if (writable) { // background: add into the archive here
            menu.addSeparator();
            menu.addAction(_newFolderAct);
            if (!_clip.isEmpty())
                menu.addAction(_pasteAct);
        }
        menu.addSeparator();
        menu.addAction(_arcExtractAllAct); // extract the whole archive
        menu.exec(view->viewport()->mapToGlobal(pos));
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

    // Archive drag-and-drop (A2), driven from the view viewports.
    const bool onViewport = _details && _icons && (watched == _details->viewport() ||
                                                    watched == _icons->viewport());
    if (onViewport && _inArchive) {
        const bool writable =
            _archiveModel && helm::hold::isWritableArchive(_archiveModel->archivePath());
        switch (event->type()) {
        case QEvent::MouseButtonPress: {
            auto *me = static_cast<QMouseEvent *>(event);
            if (me->button() == Qt::LeftButton)
                _dragStartPos = me->position().toPoint();
            break;
        }
        case QEvent::MouseMove: {
            auto *me = static_cast<QMouseEvent *>(event);
            if ((me->buttons() & Qt::LeftButton) && !_dragStartPos.isNull() &&
                (me->position().toPoint() - _dragStartPos).manhattanLength() >=
                    QApplication::startDragDistance() &&
                !selectedInnerEntries().isEmpty()) {
                _dragStartPos = QPoint();
                startArchiveDrag(); // extract-to-temp + a file-URL drag (blocking)
                return true;
            }
            break;
        }
        case QEvent::DragEnter:
        case QEvent::DragMove: {
            auto *de = static_cast<QDropEvent *>(event); // DragEnter/Move derive from it
            if (writable && de->mimeData()->hasUrls()) {
                de->acceptProposedAction();
                return true;
            }
            break;
        }
        case QEvent::Drop: {
            auto *de = static_cast<QDropEvent *>(event);
            if (writable && de->mimeData()->hasUrls()) {
                const QString innerDir = splitArchivePath(_current).inner;
                helm::hold::Edits e;
                for (const QUrl &u : de->mimeData()->urls()) {
                    if (!u.isLocalFile())
                        continue;
                    const QString src = u.toLocalFile();
                    const QString base = QFileInfo(src).fileName();
                    e.add.append(
                        {src, innerDir.isEmpty() ? base : innerDir + QLatin1Char('/') + base});
                }
                if (!e.add.isEmpty()) {
                    de->acceptProposedAction();
                    mutateArchive(e, QStringLiteral("Adding %1 item(s)…").arg(e.add.size()));
                    return true;
                }
            }
            break;
        }
        default:
            break;
        }
    }
    return QMainWindow::eventFilter(watched, event);
}

void SefeWindow::startArchiveDrag() {
    if (!_inArchive || !_archiveModel)
        return;
    const QStringList inner = selectedInnerEntries();
    if (inner.isEmpty())
        return;
    auto tmp = std::make_unique<QTemporaryDir>();
    if (!tmp->isValid())
        return;
    // Extract the dragged entries NOW — the drop target reads the files during the
    // (blocking) drag. Synchronous: a drag needs its data immediately.
    if (!helm::hold::extractEntries(_archiveModel->archivePath(), inner, tmp->path()).ok)
        return;
    QList<QUrl> urls;
    for (const QString &e : inner)
        urls << QUrl::fromLocalFile(QDir(tmp->path()).filePath(e));
    auto *mime = new QMimeData;
    mime->setUrls(urls);
    QDrag drag(this);
    drag.setMimeData(mime); // QDrag takes ownership
    drag.exec(Qt::CopyAction); // blocks; the temp dir is read before it auto-removes here
}

} // namespace helm::sefe
