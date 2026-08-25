#pragma once

#include <QWidget>

class QCheckBox;
class QEvent;
class QKeyEvent;
class QVBoxLayout;

namespace helm {

class LanternClient;

// Lantern — the notification center window (docs/design/lantern.md). A right-edge
// slide-out: a header (title + Do-Not-Disturb toggle + Clear all) over a scrollable
// list of history entries, newest first. A one-shot surface (like helm-menu):
// launched by a trigger, dismissed on Esc or click-away. Live-refreshes off the
// daemon's D-Bus signals while open.
class LanternWindow : public QWidget {
    Q_OBJECT
  public:
    explicit LanternWindow(QWidget *parent = nullptr);

  protected:
    void keyPressEvent(QKeyEvent *e) override; // Esc closes
    bool event(QEvent *e) override;            // click-away (deactivate) closes

  private:
    void rebuild(); // repopulate the list from the daemon's history

    LanternClient *m_client = nullptr;
    QVBoxLayout *m_list = nullptr; // the entries column (trailing stretch kept)
    QCheckBox *m_dnd = nullptr;
    bool m_activated = false; // don't dismiss on the deactivate before first show
};

} // namespace helm
