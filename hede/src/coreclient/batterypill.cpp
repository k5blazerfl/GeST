#include "batterypill.h"

#include "coreclient.h"

namespace helm {

QString batteryText(bool present, int percent, bool charging) {
    if (!present)
        return QString();
    const QString prefix = charging ? QString::fromUtf8("\xE2\x9A\xA1") : QString(); // ⚡
    return prefix + QString::number(percent) + QStringLiteral("%");
}

BatteryPill::BatteryPill(CoreClient *client, QWidget *parent)
    : QToolButton(parent), m_client(client) {
    setAutoRaise(true);
    setToolButtonStyle(Qt::ToolButtonTextOnly);
    apply();
    connect(m_client, &CoreClient::batteryChanged, this, [this] { apply(); });
    connect(m_client, &CoreClient::availabilityChanged, this, [this] { apply(); });
}

void BatteryPill::apply() {
    setText(batteryText(m_client->batteryPresent(), m_client->batteryPercent(),
                        m_client->batteryCharging()));
    setToolTip(m_client->batteryPresent() ? m_client->batteryStatus() : QString());
    setVisible(m_client->available() && m_client->batteryPresent());
}

} // namespace helm
