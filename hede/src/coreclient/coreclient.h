#pragma once

#include <QObject>

class QDBusServiceWatcher;

namespace helm {

// The HeDE side of the Phase 2 read seam: a thin client for the unprivileged
// session service org.gentoo.gest.Shell (see docs/design/hede-phase2.md §2).
// Degrades gracefully when GeST isn't running (available()==false, count 0).
class CoreClient : public QObject {
    Q_OBJECT
  public:
    explicit CoreClient(QObject *parent = nullptr);

    int updateCount() const { return m_updateCount; }
    bool available() const { return m_available; }

  signals:
    void updateCountChanged(int count);
    void availabilityChanged(bool available);

  private slots:
    void onUpdatesChanged(uint count);

  private:
    void connectService();
    void fetch();
    void setAvailable(bool a);
    void setUpdateCount(int c);

    QDBusServiceWatcher *m_watcher;
    int m_updateCount = 0;
    bool m_available = false;
};

} // namespace helm
