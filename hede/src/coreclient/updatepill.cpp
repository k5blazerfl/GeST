#include "updatepill.h"

#include "coreclient.h"

#include "config.h"

#include "launch.h"

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

QStringList settingsEmbedArgs(const QString &moduleId) {
    return {QStringLiteral("--embed"), moduleId};
}

UpdatePill::UpdatePill(CoreClient *client, QWidget *parent)
    : QToolButton(parent), m_client(client) {
    setAutoRaise(true);
    setToolButtonStyle(Qt::ToolButtonTextOnly);
    setCursor(Qt::PointingHandCursor);
    apply();
    connect(m_client, &CoreClient::updateCountChanged, this, [this] { apply(); });
    // Click → open the Software module (embedded GeST frontend, Phase 2d).
    connect(this, &QToolButton::clicked, this, [] {
        const QString cmd =
            Config().string(QStringLiteral("settings/command"), QStringLiteral("gest-settings"));
        helm::launchDetached(cmd, settingsEmbedArgs(QStringLiteral("software")));
    });
}

void UpdatePill::apply() {
    const int count = m_client->updateCount();
    setText(updatePillText(count));
    setToolTip(count > 0 ? tr("%n update(s) available — open GeST", nullptr, count) : QString());
    setVisible(updatePillVisible(count));
}

} // namespace helm
