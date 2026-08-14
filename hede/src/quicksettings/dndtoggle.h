#pragma once

#include <QString>
#include <QToolButton>

class QDBusServiceWatcher;

namespace helm {

// --- pure logic (unit-tested) ---
QString dndIconName(bool on);

// Panel toggle: flips helm-notifyd's do-not-disturb over the HeDE notifications
// interface. Hidden when the daemon isn't running.
class DndToggle : public QToolButton {
    Q_OBJECT
  public:
    explicit DndToggle(QWidget *parent = nullptr);

  private slots:
    void onDndChanged(bool on);

  private:
    void refresh();
    void toggle();

    QDBusServiceWatcher *m_watcher;
};

} // namespace helm
