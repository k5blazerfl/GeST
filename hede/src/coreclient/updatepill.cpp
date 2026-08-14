#include "updatepill.h"

#include "coreclient.h"

namespace helm {

QString updatePillText(int count) {
    if (count <= 0)
        return QString();
    if (count == 1)
        return QStringLiteral("1 update");
    return QStringLiteral("%1 updates").arg(count);
}

bool updatePillVisible(int count) {
    return count > 0;
}

UpdatePill::UpdatePill(CoreClient *client, QWidget *parent)
    : QToolButton(parent), m_client(client) {
    setAutoRaise(true);
    setToolButtonStyle(Qt::ToolButtonTextOnly);
    apply();
    connect(m_client, &CoreClient::updateCountChanged, this, [this] { apply(); });
}

void UpdatePill::apply() {
    const int count = m_client->updateCount();
    setText(updatePillText(count));
    setToolTip(count > 0 ? tr("%n update(s) available — open GeST", nullptr, count) : QString());
    setVisible(updatePillVisible(count));
}

} // namespace helm
