#pragma once

#include <QVector>
#include <QWidget>

#include "desktopentry.h"

class QLineEdit;
class QListWidget;
class QListWidgetItem;

namespace helm {

// The Start menu: a search field over a results list of .desktop apps.
// Type to filter, Up/Down to move, Enter/click to launch, Esc to close.
class LauncherMenu : public QWidget {
    Q_OBJECT
  public:
    explicit LauncherMenu(QWidget *parent = nullptr);

  protected:
    bool eventFilter(QObject *obj, QEvent *event) override;

  private:
    void refilter(const QString &query);
    void launch(QListWidgetItem *item);

    QLineEdit *m_search;
    QListWidget *m_list;
    QVector<DesktopEntry> m_all;
};

} // namespace helm
