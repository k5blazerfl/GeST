#pragma once

#include <QVector>
#include <QWidget>

#include "identitymap.h"
#include "toplevelmodel.h"

class QHBoxLayout;

namespace helm {

class ForeignToplevelManager;

// The window-list taskbar: one button per open toplevel. Left-click activates
// (or minimizes if already active); middle-click closes. Sits in the panel.
class TaskbarWidget : public QWidget {
    Q_OBJECT
  public:
    explicit TaskbarWidget(QWidget *parent = nullptr);

  private:
    void onChanged(const Toplevel &t);
    void onClosed(const QString &key);
    void rebuild();

    ForeignToplevelManager *m_manager;
    QVector<Toplevel> m_items;
    QHBoxLayout *m_layout;
    IdentityResolver m_identity;
};

} // namespace helm
