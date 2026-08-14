#include "networkpill.h"

#include "coreclient.h"

#include <QIcon>

namespace helm {

QString networkIconName(bool connected, const QString &kind) {
    if (!connected)
        return QStringLiteral("network-offline");
    return kind == QLatin1String("wifi") ? QStringLiteral("network-wireless")
                                         : QStringLiteral("network-wired");
}

QString networkTooltip(bool connected, const QString &kind, const QString &iface) {
    if (!connected)
        return QStringLiteral("Offline");
    const QString label =
        kind == QLatin1String("wifi") ? QStringLiteral("Wi-Fi") : QStringLiteral("Wired");
    return iface.isEmpty() ? label : QStringLiteral("%1 (%2)").arg(label, iface);
}

NetworkPill::NetworkPill(CoreClient *client, QWidget *parent)
    : QToolButton(parent), m_client(client) {
    setAutoRaise(true);
    setFixedSize(24, 24);
    setIconSize(QSize(18, 18));
    apply();
    connect(m_client, &CoreClient::networkChanged, this, [this] { apply(); });
    connect(m_client, &CoreClient::availabilityChanged, this, [this] { apply(); });
}

void NetworkPill::apply() {
    setIcon(
        QIcon::fromTheme(networkIconName(m_client->networkConnected(), m_client->networkKind())));
    setToolTip(networkTooltip(m_client->networkConnected(), m_client->networkKind(),
                              m_client->networkIface()));
    setVisible(m_client->available());
}

} // namespace helm
