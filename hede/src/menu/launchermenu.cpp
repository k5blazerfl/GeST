#include "launchermenu.h"

#include "config.h"
#include "launch.h"
#include "palette.h"
#include "power.h"

#include <QAction>
#include <QApplication>
#include <QEvent>
#include <QHBoxLayout>
#include <QIcon>
#include <QInputDialog>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
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
    setFixedSize(560, 480);

    // The acrylic pullout: objectName drives the #HelmPullout QSS (see
    // helm::styleSheet); styled + translucent so it reads as glass, with a flat
    // bottom edge that tucks against the bar (the pullout standard).
    setObjectName(QStringLiteral("HelmPullout"));
    setAttribute(Qt::WA_StyledBackground, true);
    setAttribute(Qt::WA_TranslucentBackground, true);

    auto *cols = new QHBoxLayout(this);
    cols->setContentsMargins(10, 10, 10, 10);
    cols->setSpacing(8);
    cols->addWidget(buildLeftPane(), 1);
    cols->addWidget(buildRightPane());

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

    m_all = scanDesktopEntries(defaultApplicationDirs());
    refilter(QString());

    connect(m_search, &QLineEdit::textChanged, this, &LauncherMenu::refilter);
    connect(m_list, &QListWidget::itemActivated, this, &LauncherMenu::launch);
    m_list->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(m_list, &QWidget::customContextMenuRequested, this, &LauncherMenu::showActions);

    return pane;
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

    // Power actions, bottom-right of the rail.
    auto *powerRow = new QWidget(rail);
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
    v->addWidget(powerRow);

    return rail;
}

void LauncherMenu::refilter(const QString &query) {
    m_list->clear();
    const QVector<DesktopEntry> matches = filterEntries(m_all, query);
    for (const DesktopEntry &e : matches) {
        auto *item = new QListWidgetItem(e.name, m_list);
        if (!e.comment.isEmpty())
            item->setToolTip(e.comment);
        if (!e.icon.isEmpty())
            item->setIcon(QIcon::fromTheme(e.icon));
        item->setData(kArgvRole, commandArgv(e));
        QStringList names, execs;
        for (const DesktopAction &a : e.actions) {
            names << a.name;
            execs << a.exec;
        }
        item->setData(kActionNamesRole, names);
        item->setData(kActionExecsRole, execs);
    }
    if (m_list->count() > 0)
        m_list->setCurrentRow(0);
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
    const QStringList argv = item->data(kArgvRole).toStringList();
    if (argv.isEmpty())
        return;
    launchAndQuit(argv.first(), argv.mid(1));
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
    const QStringList names = item->data(kActionNamesRole).toStringList();
    const QStringList execs = item->data(kActionExecsRole).toStringList();
    if (names.isEmpty())
        return;
    QMenu menu(this);
    for (int i = 0; i < names.size(); ++i) {
        const QString exec = execs.value(i);
        connect(menu.addAction(names[i]), &QAction::triggered, this, [this, exec] { run(exec); });
    }
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
            if (m_list->count() > 0)
                m_list->setCurrentRow(qMin(m_list->currentRow() + 1, m_list->count() - 1));
            return true;
        case Qt::Key_Up:
            if (m_list->count() > 0)
                m_list->setCurrentRow(qMax(m_list->currentRow() - 1, 0));
            return true;
        default:
            break;
        }
    }
    return QWidget::eventFilter(obj, event);
}

} // namespace helm
