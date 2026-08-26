#pragma once

#include <QWidget>

class QLabel;

namespace helm {

// The "system" Lantern widget: a small glance card showing root-filesystem disk
// usage, memory usage, and uptime. Reads QStorageInfo + /proc/meminfo +
// /proc/uptime through the pure helpers in widgets.h, refreshing on a slow timer
// while the drawer is open.
class LanternSysinfo : public QWidget {
    Q_OBJECT
  public:
    explicit LanternSysinfo(QWidget *parent = nullptr);

  private:
    void refresh();

    QLabel *m_disk = nullptr;
    QLabel *m_memory = nullptr;
    QLabel *m_uptime = nullptr;
};

} // namespace helm
