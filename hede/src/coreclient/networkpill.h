#pragma once

#include <QString>
#include <QToolButton>

namespace helm {

class CoreClient;

// --- pure logic (unit-tested) ---
QString networkIconName(bool connected, const QString &kind);
QString networkTooltip(bool connected, const QString &kind, const QString &iface);

// Panel indicator: a network icon (wired / wireless / offline) with a tooltip.
class NetworkPill : public QToolButton {
    Q_OBJECT
  public:
    explicit NetworkPill(CoreClient *client, QWidget *parent = nullptr);

  private:
    void apply();
    CoreClient *m_client;
};

} // namespace helm
