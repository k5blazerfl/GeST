#pragma once

#include <QString>
#include <QToolButton>

namespace helm {

class CoreClient;

// --- pure logic (unit-tested) ---
QString batteryText(bool present, int percent, bool charging); // "" / "72%" / "⚡95%"

// Panel indicator: battery percentage (with a charging marker), hidden when
// there's no battery or the seam is unavailable.
class BatteryPill : public QToolButton {
    Q_OBJECT
  public:
    explicit BatteryPill(CoreClient *client, QWidget *parent = nullptr);

  private:
    void apply();
    CoreClient *m_client;
};

} // namespace helm
