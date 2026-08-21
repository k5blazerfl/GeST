#pragma once

#include <QHash>
#include <QVector>
#include <QWidget>

#include "desktopentry.h"
#include "launcherstore.h"

class QLineEdit;
class QListWidget;
class QListWidgetItem;

namespace helm {

// The Start menu: a Windows-7-style two-pane pullout. Left = Pinned → Recent →
// "All apps" (or the filtered results while searching), with search at the
// bottom. Right = a rail: user header, Control Center + Run, and power actions.
// Esc closes.
class LauncherMenu : public QWidget {
    Q_OBJECT
  public:
    explicit LauncherMenu(QWidget *parent = nullptr);

  protected:
    bool eventFilter(QObject *obj, QEvent *event) override;
    // Paint the #HelmPullout glass background — the pullout is a top-level
    // WA_TranslucentBackground widget, which otherwise renders fully transparent.
    void paintEvent(QPaintEvent *event) override;
    // Dismiss the menu when it loses window activation (clicked outside / focus
    // moved away). A layer-shell surface gets no implicit popup grab, so without
    // this the pullout stays open after losing focus.
    bool event(QEvent *event) override;

  private slots:
    void showActions(const QPoint &pos); // right-click → pin + jump-list actions

  private:
    QWidget *buildLeftPane();
    QWidget *buildRightPane();
    void rebuild();                       // repopulate the list for the current state
    void refilter(const QString &);       // search text changed → rebuild
    void addHeader(const QString &text);
    void addAppItem(const DesktopEntry &e);
    void addCommandItem(const QString &binary); // a $PATH executable result
    void addFileItem(const QString &path);       // a file-index (plocate) result
    void launch(QListWidgetItem *item);
    void run(const QString &exec);
    void launchAndQuit(const QString &program, const QStringList &args = {});
    void openRun();                       // Run… prompt
    void moveSelection(int dir);          // Up/Down, skipping non-app rows

    QLineEdit *m_search;
    QListWidget *m_list;
    QVector<DesktopEntry> m_all;
    QStringList m_pathExes;               // $PATH executables, cached for search
    QHash<QString, DesktopEntry> m_byId;  // id → entry, for pinned/recent lookup
    LauncherStore m_store;                // pins + usage
    bool m_showAllApps = false;           // "All apps" expanded in the Home view
};

} // namespace helm
