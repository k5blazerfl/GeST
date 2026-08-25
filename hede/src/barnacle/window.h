#pragma once

#include "editor.h"

#include <QString>
#include <QWidget>

class QListWidget;

namespace helm {

// Barnacle — the panel editor window (docs/design/barnacle.md). A compact,
// themed xdg-toplevel: an "On the bar" list you reorder and prune, and an
// "Available" list you add from. Every change writes hede.conf [panel] applets,
// and the bar rebuilds itself live (Panel::watchConfig). This is the same engine
// (PanelEditorModel) the Control Center door will later drive.
class BarnacleWindow : public QWidget {
    Q_OBJECT
  public:
    explicit BarnacleWindow(QWidget *parent = nullptr);

  private:
    void rebuildLists();    // repopulate both lists from the model
    void syncFromBarList(); // read the (possibly drag-reordered) order back out
    void addSelected();     // move the selected Available id onto the bar
    void removeSelected();  // drop the selected on-the-bar applet
    void applyNow();        // persist → the bar live-reloads

    PanelEditorModel m_model;
    QString m_configPath;
    QListWidget *m_barList = nullptr;
    QListWidget *m_availList = nullptr;
};

} // namespace helm
