#pragma once

#include <QString>
#include <QToolButton>

class QDBusServiceWatcher;

namespace helm {

// --- pure logic (unit-tested) ---
// The bell's tooltip for a given history count.
QString lanternTooltip(int count);

// Panel applet: the notification bell. Opens the Lantern notification center
// (helm-lantern) on click, and carries an accent dot while the history is
// non-empty. A D-Bus client of org.gentoo.hede.Notifications (slice 2): it counts
// GetHistory and refreshes on NotificationAdded/HistoryCleared. Hidden when
// helm-notifyd isn't running (like DndToggle).
class LanternButton : public QToolButton {
    Q_OBJECT
  public:
    explicit LanternButton(QWidget *parent = nullptr);

  protected:
    void paintEvent(QPaintEvent *e) override; // overlay the unread dot

  private slots:
    void onHistoryChanged();

  private:
    void refresh(); // recount + visibility
    void open();    // launch helm-lantern

    int m_count = 0;
    QDBusServiceWatcher *m_watcher = nullptr;
};

} // namespace helm
