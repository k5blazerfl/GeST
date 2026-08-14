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

UpdatePill::UpdatePill(QWidget *parent) : QToolButton(parent), m_client(new CoreClient(this)) {
    setAutoRaise(true);
    setToolButtonStyle(Qt::ToolButtonTextOnly);
    apply(m_client->updateCount());
    connect(m_client, &CoreClient::updateCountChanged, this, &UpdatePill::apply);
}

void UpdatePill::apply(int count) {
    setText(updatePillText(count));
    setToolTip(count > 0 ? tr("%n update(s) available — open GeST", nullptr, count) : QString());
    setVisible(updatePillVisible(count));
}

} // namespace helm
