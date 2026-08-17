#pragma once

#include <QVector>
#include <QWidget>

#include "desktopentry.h"

class QLineEdit;
class QListWidget;
class QListWidgetItem;

namespace helm {

// The Start menu: a Windows-7-style two-pane pullout. Left = the app list with
// search at the bottom (type to filter, Up/Down to move, Enter/click to launch).
// Right = a rail: user header, Control Center + Run, and the power actions.
// Esc closes.
class LauncherMenu : public QWidget {
    Q_OBJECT
  public:
    explicit LauncherMenu(QWidget *parent = nullptr);

  protected:
    bool eventFilter(QObject *obj, QEvent *event) override;

  private slots:
    void showActions(const QPoint &pos); // right-click → jump-list actions

  private:
    QWidget *buildLeftPane();
    QWidget *buildRightPane();
    void refilter(const QString &query);
    void launch(QListWidgetItem *item);
    void run(const QString &exec);
    void launchAndQuit(const QString &program, const QStringList &args = {});
    void openRun(); // Run… prompt

    QLineEdit *m_search;
    QListWidget *m_list;
    QVector<DesktopEntry> m_all;
};

} // namespace helm
