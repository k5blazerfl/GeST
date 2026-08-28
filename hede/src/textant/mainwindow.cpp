#include "mainwindow.h"

#include "terminal.h"

#include "config.h"     // helm::Config
#include "palette.h"    // helm::effectiveAccent / barTint

#include <QAction>
#include <QFileSystemWatcher>
#include <QKeySequence>
#include <QMenu>
#include <QMenuBar>
#include <QMessageBox>
#include <QPainter>
#include <QPaintEvent>
#include <QStackedWidget>
#include <QTabBar>
#include <QVBoxLayout>

#include <algorithm>
#include <functional>

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

    m_accentLine = new QWidget(this);
    m_accentLine->setFixedHeight(3);
    m_accentLine->hide();                 // only shown when the tab bar is
    m_stack = new QStackedWidget(this);

    auto *lay = new QVBoxLayout(this);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(0);
    lay->addWidget(m_tabbar);
    lay->addWidget(m_accentLine);
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

    m_fontSize = m_cfg.fontSize;
    buildMenu();
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

void MainWindow::buildMenu() {
    auto *mb = new QMenuBar(this);
    mb->setStyleSheet(QStringLiteral(
        "QMenuBar{background:#1a1b1e;color:#e9eef6;}"
        "QMenuBar::item{padding:4px 10px;background:transparent;}"
        "QMenuBar::item:selected{background:rgba(255,255,255,0.12);border-radius:4px;}"));
    const auto item = [this](QMenu *m, const QString &text, const QString &sc,
                             std::function<void()> fn) {
        QAction *a = m->addAction(text);
        if (!sc.isEmpty())
            a->setShortcut(QKeySequence(sc));
        connect(a, &QAction::triggered, this, std::move(fn));
        return a;
    };

    QMenu *file = mb->addMenu(tr("&File"));
    item(file, tr("New &Tab"), QStringLiteral("Ctrl+Shift+T"), [this] { addTab(); });
    item(file, tr("&Close Tab"), QStringLiteral("Ctrl+Shift+W"),
         [this] { closeTab(m_tabbar->currentIndex()); });
    file->addSeparator();
    item(file, tr("&Quit"), QStringLiteral("Ctrl+Q"), [this] { close(); });

    QMenu *edit = mb->addMenu(tr("&Edit"));
    item(edit, tr("&Copy"), QStringLiteral("Ctrl+Shift+C"),
         [this] { if (auto *t = current()) t->copy(); });
    item(edit, tr("&Paste"), QStringLiteral("Ctrl+Shift+V"),
         [this] { if (auto *t = current()) t->paste(); });

    QMenu *view = mb->addMenu(tr("&View"));
    item(view, tr("Zoom &In"), QStringLiteral("Ctrl++"), [this] { zoomFont(+1); });
    item(view, tr("Zoom &Out"), QStringLiteral("Ctrl+-"), [this] { zoomFont(-1); });
    item(view, tr("&Reset Zoom"), QStringLiteral("Ctrl+0"),
         [this] { m_fontSize = m_cfg.fontSize; zoomFont(0); });

    QMenu *tabs = mb->addMenu(tr("&Tabs"));
    item(tabs, tr("&Next Tab"), QStringLiteral("Ctrl+PgDown"), [this] { selectRelative(+1); });
    item(tabs, tr("&Previous Tab"), QStringLiteral("Ctrl+PgUp"), [this] { selectRelative(-1); });

    QMenu *help = mb->addMenu(tr("&Help"));
    item(help, tr("&About Textant"), QString(), [this] {
        QMessageBox::about(this, tr("About Textant"),
                           tr("<b>Textant</b> — the HeDE terminal.<br>"
                              "A sextant sighting your prompt. libvterm + Qt."));
    });

    layout()->setMenuBar(mb);
}

Terminal *MainWindow::current() const {
    return qobject_cast<Terminal *>(m_stack->currentWidget());
}

void MainWindow::zoomFont(int delta) {
    m_fontSize = std::clamp(m_fontSize + delta, 6, 48);
    for (int i = 0; i < m_stack->count(); ++i)
        if (auto *t = qobject_cast<Terminal *>(m_stack->widget(i)))
            t->applyFont(m_cfg.fontFamily, m_fontSize);
}

Terminal *MainWindow::addTab() {
    auto *t = new Terminal(m_cfg);
    t->setWorldColors(m_fg, m_bg);
    t->setAccent(m_accent);
    if (m_fontSize != m_cfg.fontSize)
        t->applyFont(m_cfg.fontFamily, m_fontSize);
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
    const bool tabbed = m_tabbar->count() > 1;
    m_tabbar->setVisible(tabbed);
    if (m_accentLine)
        m_accentLine->setVisible(tabbed);   // stripe only while tabbed
    const int i = m_tabbar->currentIndex();
    if (auto *t = qobject_cast<Terminal *>(m_stack->widget(i)))
        setWindowTitle(t->title());
}

void MainWindow::applyWorldTint() {
    const helm::Config hc;
    m_accent = helm::effectiveAccent(hc);
    // Neutral Konsole-dark charcoal — the biome shows in the accents (cursor,
    // selection, active tab), never by washing the surface.
    m_bg = QColor(0x1a, 0x1b, 0x1e);
    for (int i = 0; i < m_stack->count(); ++i)
        if (auto *tw = qobject_cast<Terminal *>(m_stack->widget(i))) {
            tw->setWorldColors(m_fg, m_bg);
            tw->setAccent(m_accent);
        }

    if (m_accentLine)
        m_accentLine->setStyleSheet(
            QStringLiteral("background:%1;").arg(m_accent.name()));

    const QColor tabBg = m_bg.lighter(170);
    const QColor tabSel = m_accent.darker(130);
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
