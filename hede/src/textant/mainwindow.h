#pragma once

#include <QWidget>
#include <QColor>

#include "settings.h"

class QTabBar;
class QStackedWidget;
class QFileSystemWatcher;
class Terminal;

// The Textant window: a tab bar over a stack of Terminals. The bar hides when a
// single tab is open. Owns the world-tint (applied to every tab) and re-tints
// live on a world switch.
class MainWindow : public QWidget {
    Q_OBJECT
public:
    explicit MainWindow(const Settings &cfg, QWidget *parent = nullptr);

protected:
    void paintEvent(QPaintEvent *ev) override;

private:
    void buildMenu();
    Terminal *addTab();
    void closeTab(int index);
    void selectRelative(int delta);
    Terminal *current() const;
    void zoomFont(int delta);
    void applyWorldTint();
    void syncChrome();                 // tab-bar visibility + window title

    Settings m_cfg;
    int m_fontSize = 11;
    QTabBar *m_tabbar = nullptr;
    QWidget *m_accentLine = nullptr;   // biome stripe, shown only when tabbed
    QStackedWidget *m_stack = nullptr;
    QFileSystemWatcher *m_watcher = nullptr;
    QColor m_fg { 0xe9, 0xee, 0xf6 };
    QColor m_bg { 0x0e, 0x17, 0x28 };
    QColor m_accent { 0x2f, 0x9c, 0x8f };
};
