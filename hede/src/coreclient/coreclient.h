#pragma once

#include <QObject>
#include <QString>

class QDBusServiceWatcher;

namespace helm {

// The HeDE side of the Phase 2 read seam: a thin client for the unprivileged
// session service org.gentoo.gest.Shell (see docs/design/hede-phase2.md §2).
// Degrades gracefully when GeST isn't running (available()==false, defaults).
class CoreClient : public QObject {
    Q_OBJECT
  public:
    explicit CoreClient(QObject *parent = nullptr);

    bool available() const { return m_available; }

    int updateCount() const { return m_updateCount; }

    bool networkConnected() const { return m_netConnected; }
    QString networkKind() const { return m_netKind; } // "ethernet" | "wifi" | "none"
    QString networkIface() const { return m_netIface; }

    bool batteryPresent() const { return m_batPresent; }
    int batteryPercent() const { return m_batPercent; }
    QString batteryStatus() const { return m_batStatus; }
    bool batteryCharging() const;

  signals:
    void availabilityChanged(bool available);
    void updateCountChanged(int count);
    void networkChanged();
    void batteryChanged();

  private slots:
    void refetch();

  private:
    void connectService();
    void setAvailable(bool a);

    QDBusServiceWatcher *m_watcher;
    bool m_available = false;
    int m_updateCount = 0;
    bool m_netConnected = false;
    QString m_netKind = QStringLiteral("none");
    QString m_netIface;
    bool m_batPresent = false;
    int m_batPercent = 0;
    QString m_batStatus = QStringLiteral("Unknown");
};

} // namespace helm
