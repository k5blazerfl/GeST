#include "trayitem.h"

#include <QCursor>
#include <QDBusConnection>
#include <QDBusInterface>
#include <QIcon>
#include <QMouseEvent>

namespace helm {

static constexpr auto kIface = "org.kde.StatusNotifierItem";

TrayItem::TrayItem(const QString &service, const QString &path, QWidget *parent)
    : QToolButton(parent), m_service(service), m_path(path) {
    setAutoRaise(true);
    setFixedSize(24, 24);
    setIconSize(QSize(18, 18));

    refresh();

    // Update when the item announces changes.
    QDBusConnection bus = QDBusConnection::sessionBus();
    for (const char *sig : {"NewIcon", "NewTitle", "NewStatus", "NewToolTip"})
        bus.connect(m_service, m_path, kIface, QLatin1String(sig), this, SLOT(refresh()));
}

void TrayItem::refresh() {
    QDBusInterface item(m_service, m_path, kIface, QDBusConnection::sessionBus());
    const QString iconName = item.property("IconName").toString();
    const QString title = item.property("Title").toString();
    if (!iconName.isEmpty())
        setIcon(QIcon::fromTheme(iconName));
    else if (icon().isNull())
        setIcon(QIcon::fromTheme(QStringLiteral("application-x-executable")));
    setToolTip(title.isEmpty() ? item.property("Id").toString() : title);
}

void TrayItem::mouseReleaseEvent(QMouseEvent *e) {
    const QPoint g = QCursor::pos();
    QDBusInterface item(m_service, m_path, kIface, QDBusConnection::sessionBus());
    if (e->button() == Qt::RightButton)
        item.asyncCall(QStringLiteral("ContextMenu"), g.x(), g.y());
    else if (e->button() == Qt::MiddleButton)
        item.asyncCall(QStringLiteral("SecondaryActivate"), g.x(), g.y());
    else
        item.asyncCall(QStringLiteral("Activate"), g.x(), g.y());
    QToolButton::mouseReleaseEvent(e);
}

} // namespace helm
