#include "mainwindow.h"

#include "terminal.h"

#include "config.h"     // helm::Config
#include "palette.h"    // helm::effectiveAccent / barTint

#include <QFileSystemWatcher>
#include <QKeySequence>
#include <QPainter>
#include <QPaintEvent>
#include <QShortcut>
#include <QStackedWidget>
#include <QTabBar>
#include <QVBoxLayout>

MainWindow::MainWindow(const Settings &cfg, QWidget *parent)
    : QWidget(parent), m_cfg(cfg) {
    setWindowTitle(QStringLiteral("Textant"));
    if (cfg.opacity < 0.999)
        setAttribute(Qt::WA_TranslucentBackground);

    m_tabbar = new QTabBar(this);
    m_tabbar->setExpanding(false);
    m_tabbar->setTabsClosable(true);
    m_tabbar->setMovable(true);
    m_tabbar->setDrawBase(false);
    m_tabbar->setDocumentMode(true);
    m_tabbar->setElideMode(Qt::ElideRight);
    m_tabbar->setFocusPolicy(Qt::NoFocus);

    m_stack = new QStackedWidget(this);

    auto *lay = new QVBoxLayout(this);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(0);
    lay->addWidget(m_tabbar);
    lay->addWidget(m_stack, 1);

    connect(m_tabbar, &QTabBar::currentChanged, this, [this](int i) {
        if (i >= 0) {
            m_stack->setCurrentIndex(i);
            if (auto *w = m_stack->widget(i))
                w->setFocus();
        }
        syncChrome();
    });
    connect(m_tabbar, &QTabBar::tabCloseRequested, this,
            [this](int i) { closeTab(i); });

    const auto add = new QShortcut(QKeySequence(QStringLiteral("Ctrl+Shift+T")), this);
    connect(add, &QShortcut::activated, this, [this] { addTab(); });
    const auto close = new QShortcut(QKeySequence(QStringLiteral("Ctrl+Shift+W")), this);
    connect(close, &QShortcut::activated, this,
            [this] { closeTab(m_tabbar->currentIndex()); });
    const auto next = new QShortcut(QKeySequence(QStringLiteral("Ctrl+PgDown")), this);
    connect(next, &QShortcut::activated, this, [this] { selectRelative(+1); });
    const auto prev = new QShortcut(QKeySequence(QStringLiteral("Ctrl+PgUp")), this);
    connect(prev, &QShortcut::activated, this, [this] { selectRelative(-1); });

    applyWorldTint();

    m_watcher = new QFileSystemWatcher(this);
    const helm::Config hc;
    m_watcher->addPath(hc.path());
    connect(m_watcher, &QFileSystemWatcher::fileChanged, this,
            [this](const QString &path) {
                applyWorldTint();
                if (!m_watcher->files().contains(path))
                    m_watcher->addPath(path);
            });

    addTab();
}

Terminal *MainWindow::addTab() {
    auto *t = new Terminal(m_cfg);
    t->setWorldColors(m_fg, m_bg);
    const int idx = m_stack->addWidget(t);
    m_tabbar->insertTab(idx, t->title());

    connect(t, &Terminal::titleChanged, this, [this, t](const QString &title) {
        const int i = m_stack->indexOf(t);
        if (i >= 0) {
            m_tabbar->setTabText(i, title);
            if (i == m_tabbar->currentIndex())
                setWindowTitle(title);
        }
    });
    connect(t, &Terminal::finished, this,
            [this, t] { closeTab(m_stack->indexOf(t)); });

    m_tabbar->setCurrentIndex(idx);
    m_stack->setCurrentIndex(idx);
    t->startShell();
    t->setFocus();
    syncChrome();
    return t;
}

void MainWindow::closeTab(int index) {
    if (index < 0 || index >= m_stack->count())
        return;
    QWidget *w = m_stack->widget(index);
    m_tabbar->removeTab(index);
    m_stack->removeWidget(w);
    w->deleteLater();
    if (m_stack->count() == 0) {
        close();
        return;
    }
    syncChrome();
    if (auto *cur = m_stack->currentWidget())
        cur->setFocus();
}

void MainWindow::selectRelative(int delta) {
    const int n = m_tabbar->count();
    if (n <= 1)
        return;
    m_tabbar->setCurrentIndex((m_tabbar->currentIndex() + delta + n) % n);
}

void MainWindow::syncChrome() {
    m_tabbar->setVisible(m_tabbar->count() > 1);
    const int i = m_tabbar->currentIndex();
    if (auto *t = qobject_cast<Terminal *>(m_stack->widget(i)))
        setWindowTitle(t->title());
}

void MainWindow::applyWorldTint() {
    const helm::Config hc;
    m_accent = helm::effectiveAccent(hc);
    m_bg = helm::barTint(m_accent);
    for (int i = 0; i < m_stack->count(); ++i)
        if (auto *t = qobject_cast<Terminal *>(m_stack->widget(i)))
            t->setWorldColors(m_fg, m_bg);

    const QColor tabBg = m_bg.lighter(150);
    const QColor tabSel = m_bg.lighter(210);
    m_tabbar->setStyleSheet(QStringLiteral(
        "QTabBar{background:transparent;}"
        "QTabBar::tab{background:%1;color:#e9eef6;padding:5px 12px;margin-right:2px;"
        "border-top-left-radius:6px;border-top-right-radius:6px;max-width:240px;}"
        "QTabBar::tab:selected{background:%2;}")
        .arg(tabBg.name(), tabSel.name()));
    update();
}

void MainWindow::paintEvent(QPaintEvent *ev) {
    QPainter p(this);
    QColor bg = m_bg;
    if (m_cfg.opacity < 0.999) {
        bg.setAlphaF(m_cfg.opacity);
        p.setCompositionMode(QPainter::CompositionMode_Source);
    }
    p.fillRect(ev->rect(), bg);
}
