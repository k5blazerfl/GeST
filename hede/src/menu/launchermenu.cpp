#include "launchermenu.h"

#include "categories.h"
#include "config.h"
#include "launch.h"
#include "palette.h"
#include "power.h"
#include "search.h"

#include <QAction>
#include <QApplication>
#include <QCursor>
#include <QDateTime>
#include <QEvent>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QIcon>
#include <QInputDialog>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMap>
#include <QMenu>
#include <QProcess>
#include <QPushButton>
#include <QSysInfo>
#include <QToolButton>
#include <QVBoxLayout>

namespace helm {

static constexpr int kArgvRole = Qt::UserRole;
static constexpr int kActionNamesRole = Qt::UserRole + 1;
static constexpr int kActionExecsRole = Qt::UserRole + 2;
static constexpr int kAppIdRole = Qt::UserRole + 3;
static constexpr int kKindRole = Qt::UserRole + 4; // 0 = app, 1 = "all apps" expander

namespace {

// A rail icon button (Control Center / Run): tinted glyph + label, left-aligned.
QToolButton *railButton(const QString &icon, const QString &label, QWidget *parent) {
    auto *b = new QToolButton(parent);
    b->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
    b->setIcon(helm::tintedIcon(icon, helm::barGlyphColor(), QSize(18, 18)));
    b->setIconSize(QSize(18, 18));
    b->setText(label);
    b->setCursor(Qt::PointingHandCursor);
    b->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    return b;
}

// A power button: icon only, tooltip label.
QToolButton *powerButton(const QString &icon, const QString &tip, QWidget *parent) {
    auto *b = new QToolButton(parent);
    b->setIcon(helm::tintedIcon(icon, helm::barGlyphColor(), QSize(18, 18)));
    b->setIconSize(QSize(18, 18));
    b->setToolTip(tip);
    b->setCursor(Qt::PointingHandCursor);
    return b;
}

} // namespace

LauncherMenu::LauncherMenu(QWidget *parent)
    : QWidget(parent), m_search(new QLineEdit(this)), m_list(new QListWidget(this)) {
    m_classic = Config().string(QStringLiteral("launcher/style"),
                                QStringLiteral("win7_two_pane"))
                == QLatin1String("classic");

    // The acrylic pullout: objectName drives the #HelmPullout QSS (see
    // helm::styleSheet); styled + translucent so it reads as glass, with a flat
    // bottom edge that tucks against the bar (the pullout standard). Both styles
    // share this shell; the caption strip is a child (#HelmClassicCaption).
    setObjectName(QStringLiteral("HelmPullout"));
    setAttribute(Qt::WA_StyledBackground, true);
    setAttribute(Qt::WA_TranslucentBackground, true);

    if (m_classic) {
        setFixedSize(300, 520); // taller, narrower single column
        auto *cols = new QHBoxLayout(this);
        cols->setContentsMargins(0, 0, 10, 0); // caption bleeds to the left edge
        cols->setSpacing(8);
        cols->addWidget(buildCaptionStrip());
        cols->addWidget(buildClassicColumn(), 1);
    } else {
        setFixedSize(560, 480);
        auto *cols = new QHBoxLayout(this);
        cols->setContentsMargins(10, 10, 10, 10);
        cols->setSpacing(8);
        cols->addWidget(buildLeftPane(), 1);
        cols->addWidget(buildRightPane());
    }

    // Search focus is a setting (tokens.launcher.search.focus): "auto" focuses
    // the search on open (type immediately, the default); "tab" leaves focus on
    // the list (arrow to navigate) and the search is reached with Tab.
    if (Config().string(QStringLiteral("launcher/search_focus"), QStringLiteral("auto"))
        == QLatin1String("tab"))
        m_list->setFocus();
    else
        m_search->setFocus();
}

QWidget *LauncherMenu::buildLeftPane() {
    auto *pane = new QWidget(this);
    auto *v = new QVBoxLayout(pane);
    v->setContentsMargins(0, 0, 0, 0);
    v->setSpacing(6);

    v->addWidget(m_list, 1);

    // Search anchored at the bottom (the launcher standard).
    m_search->setPlaceholderText(tr("Search applications…"));
    m_search->setClearButtonEnabled(true);
    m_search->installEventFilter(this);
    v->addWidget(m_search);

    loadModel();
    rebuild();
    wireList();

    return pane;
}

void LauncherMenu::loadModel() {
    m_all = scanDesktopEntries(defaultApplicationDirs());
    m_pathExes = pathExecutables(); // cached once; search filters this per keystroke
    for (const DesktopEntry &e : m_all)
        m_byId.insert(e.id, e);
    m_store = loadStore();
    if (m_store.pinned.isEmpty())
        m_store.pinned = defaultPins(m_byId.keys());
}

void LauncherMenu::wireList() {
    connect(m_search, &QLineEdit::textChanged, this, &LauncherMenu::refilter);
    connect(m_list, &QListWidget::itemActivated, this, &LauncherMenu::launch);
    m_list->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(m_list, &QWidget::customContextMenuRequested, this, &LauncherMenu::showActions);
}

QWidget *LauncherMenu::buildRightPane() {
    auto *rail = new QWidget(this);
    rail->setObjectName(QStringLiteral("HelmMenuRail"));
    rail->setFixedWidth(180);
    auto *v = new QVBoxLayout(rail);
    v->setContentsMargins(8, 4, 4, 4);
    v->setSpacing(4);

    // Header: avatar + user@host.
    auto *header = new QWidget(rail);
    auto *h = new QHBoxLayout(header);
    h->setContentsMargins(0, 0, 0, 6);
    h->setSpacing(8);
    auto *avatar = new QLabel(header);
    avatar->setPixmap(
        helm::tintedIcon(QStringLiteral("avatar-default"), helm::barGlyphColor(), QSize(28, 28))
            .pixmap(28, 28));
    h->addWidget(avatar);
    const QString user = qEnvironmentVariable("USER", QStringLiteral("root"));
    auto *who = new QLabel(QStringLiteral("%1@%2").arg(user, QSysInfo::machineHostName()), header);
    h->addWidget(who, 1);
    v->addWidget(header);

    // System: Control Center + Run.
    auto *cc = railButton(QStringLiteral("preferences-system"), tr("Control Center"), rail);
    connect(cc, &QToolButton::clicked, this, [this] {
        const QString cmd =
            Config().string(QStringLiteral("settings/command"), QStringLiteral("gest-settings"));
        launchAndQuit(cmd);
    });
    v->addWidget(cc);

    auto *runBtn = railButton(QStringLiteral("system-run"), tr("Run…"), rail);
    connect(runBtn, &QToolButton::clicked, this, &LauncherMenu::openRun);
    v->addWidget(runBtn);

    v->addStretch(1);
    v->addWidget(buildPowerRow(rail)); // power actions, bottom-right

    return rail;
}

QWidget *LauncherMenu::buildPowerRow(QWidget *parent) {
    auto *powerRow = new QWidget(parent);
    auto *p = new QHBoxLayout(powerRow);
    p->setContentsMargins(0, 0, 0, 0);
    p->setSpacing(2);
    p->addStretch(1);
    struct P {
        const char *icon;
        const char *tip;
        PowerAction action;
    };
    const P powers[] = {
        {"system-suspend", QT_TR_NOOP("Sleep"), PowerAction::Suspend},
        {"system-lock-screen", QT_TR_NOOP("Lock"), PowerAction::Lock},
        {"system-log-out", QT_TR_NOOP("Log out"), PowerAction::LogOut},
        {"system-reboot", QT_TR_NOOP("Restart"), PowerAction::Reboot},
        {"system-shutdown", QT_TR_NOOP("Shut down"), PowerAction::PowerOff},
    };
    for (const P &pw : powers) {
        auto *b = powerButton(QString::fromLatin1(pw.icon), tr(pw.tip), powerRow);
        const PowerAction action = pw.action;
        connect(b, &QToolButton::clicked, this, [this, action] {
            invokePower(action);
            qApp->quit();
        });
        p->addWidget(b);
    }
    return powerRow;
}

// classic: a vertical accent caption band down the left edge (Open-Shell's
// signature caption strip). v1 is the accent fallback + the ⎈ mark; the per-biome
// start-art render + "Linux <kernel>" caption are a follow-up (asset packaging).
QWidget *LauncherMenu::buildCaptionStrip() {
    auto *strip = new QWidget(this);
    strip->setObjectName(QStringLiteral("HelmClassicCaption"));
    strip->setAttribute(Qt::WA_StyledBackground, true);
    strip->setFixedWidth(40);
    auto *v = new QVBoxLayout(strip);
    v->setContentsMargins(0, 8, 0, 10);
    v->addStretch(1);
    auto *mark = new QLabel(QString::fromUtf8("⎈"), strip);
    mark->setAlignment(Qt::AlignHCenter);
    QFont f = mark->font();
    f.setPointSizeF(f.pointSizeF() * 1.5);
    f.setBold(true);
    mark->setFont(f);
    v->addWidget(mark);
    return strip;
}

// classic: one dense column — the app list (Pinned → Recent → "All Programs ▸"),
// search at the bottom, then a compact action strip (Control Center, Run, power).
QWidget *LauncherMenu::buildClassicColumn() {
    auto *pane = new QWidget(this);
    auto *v = new QVBoxLayout(pane);
    v->setContentsMargins(0, 10, 0, 10);
    v->setSpacing(6);

    v->addWidget(m_list, 1);

    m_search->setPlaceholderText(tr("Search…"));
    m_search->setClearButtonEnabled(true);
    m_search->installEventFilter(this);
    v->addWidget(m_search);

    // Action strip: Control Center + Run on the left, power on the right.
    auto *actions = new QWidget(pane);
    auto *h = new QHBoxLayout(actions);
    h->setContentsMargins(0, 0, 0, 0);
    h->setSpacing(2);
    auto *cc = railButton(QStringLiteral("preferences-system"), tr("Control Center"), actions);
    cc->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    connect(cc, &QToolButton::clicked, this, [this] {
        const QString cmd =
            Config().string(QStringLiteral("settings/command"), QStringLiteral("gest-settings"));
        launchAndQuit(cmd);
    });
    h->addWidget(cc);
    auto *runBtn = railButton(QStringLiteral("system-run"), tr("Run…"), actions);
    runBtn->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    connect(runBtn, &QToolButton::clicked, this, &LauncherMenu::openRun);
    h->addWidget(runBtn);
    h->addStretch(1);
    h->addWidget(buildPowerRow(actions));
    v->addWidget(actions);

    loadModel();
    rebuild();
    wireList();

    return pane;
}

// classic: "All Programs" fly-out — apps grouped into cascading category submenus
// (via helm::sectionForCategories). QMenu gives native cascade + keyboard nav.
void LauncherMenu::openAllPrograms() {
    QMap<QString, QVector<const DesktopEntry *>> bySection; // QMap → sections A→Z
    for (const DesktopEntry &e : m_all)                     // m_all is name-sorted
        bySection[sectionForCategories(e.categories)].append(&e);

    QMenu menu(this);
    for (auto it = bySection.constBegin(); it != bySection.constEnd(); ++it) {
        QMenu *sub = menu.addMenu(it.key());
        for (const DesktopEntry *e : it.value()) {
            QAction *a = sub->addAction(QIcon::fromTheme(e->icon), e->name);
            const QStringList argv = commandArgv(*e);
            const QString id = e->id;
            connect(a, &QAction::triggered, this, [this, argv, id] {
                if (!id.isEmpty()) {
                    recordLaunch(m_store, id, QDateTime::currentSecsSinceEpoch());
                    saveStore(m_store);
                }
                if (!argv.isEmpty())
                    launchAndQuit(argv.first(), argv.mid(1));
            });
        }
    }
    if (!menu.isEmpty())
        menu.exec(QCursor::pos());
}

void LauncherMenu::refilter(const QString &) {
    m_showAllApps = false; // typing leaves the expanded All-apps view
    rebuild();
}

void LauncherMenu::addHeader(const QString &text) {
    auto *h = new QListWidgetItem(text.toUpper(), m_list);
    h->setFlags(Qt::NoItemFlags); // not selectable/navigable
    QFont f = h->font();
    f.setBold(true);
    f.setPointSizeF(f.pointSizeF() * 0.85);
    h->setFont(f);
    h->setForeground(QColor(0x7f, 0x9a, 0xa2)); // dim, on the acrylic
}

void LauncherMenu::addAppItem(const DesktopEntry &e) {
    auto *item = new QListWidgetItem(e.name, m_list);
    if (!e.comment.isEmpty())
        item->setToolTip(e.comment);
    if (!e.icon.isEmpty())
        item->setIcon(QIcon::fromTheme(e.icon));
    item->setData(kArgvRole, commandArgv(e));
    item->setData(kAppIdRole, e.id);
    item->setData(kKindRole, 0);
    QStringList names, execs;
    for (const DesktopAction &a : e.actions) {
        names << a.name;
        execs << a.exec;
    }
    item->setData(kActionNamesRole, names);
    item->setData(kActionExecsRole, execs);
}

void LauncherMenu::addCommandItem(const QString &binary) {
    auto *item = new QListWidgetItem(binary, m_list);
    item->setIcon(helm::tintedIcon(QStringLiteral("system-run"), helm::barGlyphColor(), QSize(18, 18)));
    item->setToolTip(tr("Run %1").arg(binary));
    item->setData(kArgvRole, QStringList{binary}); // launch the bare command
    item->setData(kKindRole, 0);
    // No app id → not usage-tracked (it isn't a .desktop app).
}

void LauncherMenu::addFileItem(const QString &path) {
    auto *item = new QListWidgetItem(QFileInfo(path).fileName(), m_list);
    item->setIcon(helm::tintedIcon(QStringLiteral("text-x-generic"), helm::barGlyphColor(),
                                   QSize(18, 18)));
    item->setToolTip(path);
    item->setData(kArgvRole, QStringList{QStringLiteral("xdg-open"), path}); // open in the handler
    item->setData(kKindRole, 0);
}

void LauncherMenu::rebuild() {
    m_list->clear();
    const QString query = m_search->text();

    if (!query.isEmpty()) {
        // Searching: fuzzy-ranked apps, then matching $PATH commands.
        for (const DesktopEntry &e : rankEntries(m_all, query))
            addAppItem(e);
        const QStringList cmds = matchingExecutables(m_pathExes, query);
        if (!cmds.isEmpty()) {
            addHeader(tr("Commands"));
            for (const QString &c : cmds)
                addCommandItem(c);
        }
        const QStringList files = fileIndexMatches(query);
        if (!files.isEmpty()) {
            addHeader(tr("Files"));
            for (const QString &f : files)
                addFileItem(f);
        }
    } else if (m_showAllApps) {
        for (const DesktopEntry &e : m_all) // scanDesktopEntries is name-sorted
            addAppItem(e);
    } else {
        // The Home view: Pinned → Recent → an "All apps" expander.
        QStringList shown;
        if (!m_store.pinned.isEmpty()) {
            addHeader(tr("Pinned"));
            for (const QString &id : m_store.pinned)
                if (m_byId.contains(id)) {
                    addAppItem(m_byId.value(id));
                    shown << id;
                }
        }
        const QStringList recent = recentIds(m_store, 6, m_store.pinned);
        if (!recent.isEmpty()) {
            addHeader(tr("Recent"));
            for (const QString &id : recent)
                if (m_byId.contains(id)) {
                    addAppItem(m_byId.value(id));
                    shown << id;
                }
        }
        // win7 expands All-apps in place (kind 1); classic flies out a cascading
        // category menu (kind 2).
        auto *all = new QListWidgetItem(m_classic ? tr("All Programs  ▸") : tr("All apps  ▸"),
                                        m_list);
        all->setData(kKindRole, m_classic ? 2 : 1);
    }

    // Select the first navigable (app / expander) row.
    for (int i = 0; i < m_list->count(); ++i)
        if (m_list->item(i)->flags() & Qt::ItemIsSelectable) {
            m_list->setCurrentRow(i);
            break;
        }
}

void LauncherMenu::launchAndQuit(const QString &program, const QStringList &args) {
    if (program.isEmpty())
        return;
    helm::launchDetached(program, args);
    qApp->quit();
}

void LauncherMenu::openRun() {
    bool ok = false;
    const QString cmd =
        QInputDialog::getText(this, tr("Run"), tr("Open:"), QLineEdit::Normal, QString(), &ok);
    if (!ok || cmd.trimmed().isEmpty())
        return;
    const QStringList argv = QProcess::splitCommand(cmd);
    if (argv.isEmpty())
        return;
    launchAndQuit(argv.first(), argv.mid(1));
}

void LauncherMenu::launch(QListWidgetItem *item) {
    if (!item)
        return;
    const int kind = item->data(kKindRole).toInt();
    if (kind == 1) { // win7 "All apps" → expand in place
        m_showAllApps = true;
        rebuild();
        return;
    }
    if (kind == 2) { // classic "All Programs" → cascading category fly-out
        openAllPrograms();
        return;
    }
    const QStringList argv = item->data(kArgvRole).toStringList();
    if (argv.isEmpty())
        return;
    const QString id = item->data(kAppIdRole).toString();
    if (!id.isEmpty()) {
        recordLaunch(m_store, id, QDateTime::currentSecsSinceEpoch());
        saveStore(m_store);
    }
    launchAndQuit(argv.first(), argv.mid(1));
}

void LauncherMenu::moveSelection(int dir) {
    const int n = m_list->count();
    if (n == 0)
        return;
    int row = m_list->currentRow();
    for (int i = 0; i < n; ++i) {
        row += dir;
        if (row < 0 || row >= n)
            return; // at an edge — keep the current selection
        if (m_list->item(row)->flags() & Qt::ItemIsSelectable) {
            m_list->setCurrentRow(row);
            return;
        }
    }
}

void LauncherMenu::run(const QString &exec) {
    const QStringList argv = commandArgv(exec);
    if (argv.isEmpty())
        return;
    launchAndQuit(argv.first(), argv.mid(1));
}

void LauncherMenu::showActions(const QPoint &pos) {
    QListWidgetItem *item = m_list->itemAt(pos);
    if (!item)
        return;
    QMenu menu(this);

    const QString id = item->data(kAppIdRole).toString();
    if (!id.isEmpty()) {
        const bool pinned = m_store.pinned.contains(id);
        connect(menu.addAction(pinned ? tr("Unpin from Start") : tr("Pin to Start")),
                &QAction::triggered, this, [this, id] {
                    togglePin(m_store, id);
                    saveStore(m_store);
                    rebuild();
                });
    }

    const QStringList names = item->data(kActionNamesRole).toStringList();
    const QStringList execs = item->data(kActionExecsRole).toStringList();
    if (!names.isEmpty()) {
        menu.addSeparator();
        for (int i = 0; i < names.size(); ++i) {
            const QString exec = execs.value(i);
            connect(menu.addAction(names[i]), &QAction::triggered, this,
                    [this, exec] { run(exec); });
        }
    }
    if (!menu.isEmpty())
        menu.exec(m_list->mapToGlobal(pos));
}

bool LauncherMenu::eventFilter(QObject *obj, QEvent *event) {
    if (obj == m_search && event->type() == QEvent::KeyPress) {
        auto *ke = static_cast<QKeyEvent *>(event);
        switch (ke->key()) {
        case Qt::Key_Escape:
            qApp->quit();
            return true;
        case Qt::Key_Return:
        case Qt::Key_Enter:
            launch(m_list->currentItem());
            return true;
        case Qt::Key_Down:
            moveSelection(+1);
            return true;
        case Qt::Key_Up:
            moveSelection(-1);
            return true;
        default:
            break;
        }
    }
    return QWidget::eventFilter(obj, event);
}

} // namespace helm
