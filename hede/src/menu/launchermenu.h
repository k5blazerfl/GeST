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

// The Start menu. The layout is a setting (launcher/style, mirroring Open-Shell's
// Menu Style):
//   * win7_two_pane (default) — a two-pane pullout: left = Pinned → Recent →
//     "All apps" (or filtered results while searching) with search at the bottom;
//     right = a rail (user header, Control Center + Run, power).
//   * classic — a single dense column with a vertical caption strip; "All
//     Programs" flies out as a cascading category menu (rather than expanding in
//     place); power pinned at the bottom.
// Both share the app model, search, pins/recents, and power actions. Esc closes.
class LauncherMenu : public QWidget {
    Q_OBJECT
  public:
    explicit LauncherMenu(QWidget *parent = nullptr);

  protected:
    bool eventFilter(QObject *obj, QEvent *event) override;
    // Dismiss on a click anywhere outside the pullout. The top-level is a
    // full-screen transparent backdrop (main.cpp anchors it to all four edges),
    // so every outside click lands here — layer-shell gives no popup grab, and
    // QEvent::WindowDeactivate is unreliable on labwc (a KeyboardInteractivity=
    // OnDemand surface never takes seat focus on map, so it never deactivates).
    void mousePressEvent(QMouseEvent *event) override;

  private slots:
    void showActions(const QPoint &pos); // right-click → pin + jump-list actions

  private:
    void loadModel();                     // scan apps + $PATH + pins/recents
    void wireList();                      // connect the list's signals
    QWidget *buildLeftPane();             // win7: app list + search
    QWidget *buildRightPane();            // win7: user/system/power rail
    QWidget *buildPowerRow(QWidget *parent); // the 5 power buttons (shared)
    QWidget *buildClassicColumn();        // classic: single dense column
    QWidget *buildCaptionStrip();         // classic: vertical accent caption band
    void openAllPrograms();               // classic: cascading category fly-out
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

    QWidget *m_pullout;                   // the glass card; the top-level is a backdrop
    QLineEdit *m_search;
    QListWidget *m_list;
    QVector<DesktopEntry> m_all;
    QStringList m_pathExes;               // $PATH executables, cached for search
    QHash<QString, DesktopEntry> m_byId;  // id → entry, for pinned/recent lookup
    LauncherStore m_store;                // pins + usage
    bool m_showAllApps = false;           // "All apps" expanded in the Home view
    bool m_classic = false;               // launcher/style == "classic"
};

} // namespace helm
