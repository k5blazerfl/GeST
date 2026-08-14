#include "launchermenu.h"

#include <QAction>
#include <QApplication>
#include <QEvent>
#include <QIcon>
#include <QKeyEvent>
#include <QLineEdit>
#include <QListWidget>
#include <QMenu>
#include <QProcess>
#include <QVBoxLayout>

namespace helm {

static constexpr int kArgvRole = Qt::UserRole;
static constexpr int kActionNamesRole = Qt::UserRole + 1;
static constexpr int kActionExecsRole = Qt::UserRole + 2;

LauncherMenu::LauncherMenu(QWidget *parent)
    : QWidget(parent), m_search(new QLineEdit(this)), m_list(new QListWidget(this)) {
    setFixedSize(360, 480);

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(8, 8, 8, 8);
    layout->setSpacing(6);
    m_search->setPlaceholderText(tr("Search applications…"));
    m_search->setClearButtonEnabled(true);
    m_search->installEventFilter(this);
    layout->addWidget(m_search);
    layout->addWidget(m_list, 1);

    m_all = scanDesktopEntries(defaultApplicationDirs());
    refilter(QString());

    connect(m_search, &QLineEdit::textChanged, this, &LauncherMenu::refilter);
    connect(m_list, &QListWidget::itemActivated, this, &LauncherMenu::launch);

    m_list->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(m_list, &QWidget::customContextMenuRequested, this, &LauncherMenu::showActions);

    m_search->setFocus();
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

void LauncherMenu::launch(QListWidgetItem *item) {
    if (!item)
        return;
    const QStringList argv = item->data(kArgvRole).toStringList();
    if (argv.isEmpty())
        return;
    QProcess::startDetached(argv.first(), argv.mid(1));
    qApp->quit();
}

void LauncherMenu::run(const QString &exec) {
    const QStringList argv = commandArgv(exec);
    if (argv.isEmpty())
        return;
    QProcess::startDetached(argv.first(), argv.mid(1));
    qApp->quit();
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
