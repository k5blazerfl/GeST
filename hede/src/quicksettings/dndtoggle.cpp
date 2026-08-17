#include "dndtoggle.h"

#include "palette.h"

#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusServiceWatcher>
#include <QIcon>

namespace helm {

// Kept in sync with src/notify (org.freedesktop.Notifications object + the HeDE
// extension interface it also exports).
static constexpr auto kService = "org.freedesktop.Notifications";
static constexpr auto kPath = "/org/freedesktop/Notifications";
static constexpr auto kHedeIface = "org.gentoo.hede.Notifications";

QString dndIconName(bool on) {
    return on ? QStringLiteral("notifications-disabled") : QStringLiteral("notifications");
}

DndToggle::DndToggle(QWidget *parent) : QToolButton(parent) {
    setAutoRaise(true);
    setCheckable(true);
    setFixedSize(24, 24);
    setIconSize(QSize(18, 18));

    QDBusConnection bus = QDBusConnection::sessionBus();
    m_watcher = new QDBusServiceWatcher(QString::fromLatin1(kService), bus,
                                        QDBusServiceWatcher::WatchForRegistration |
                                            QDBusServiceWatcher::WatchForUnregistration,
                                        this);
    connect(m_watcher, &QDBusServiceWatcher::serviceRegistered, this, [this] { refresh(); });
    connect(m_watcher, &QDBusServiceWatcher::serviceUnregistered, this,
            [this] { setVisible(false); });
    bus.connect(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                QString::fromLatin1(kHedeIface), QStringLiteral("DoNotDisturbChanged"), this,
                SLOT(onDndChanged(bool)));

    connect(this, &QToolButton::clicked, this, [this] { toggle(); });
    refresh();
}

void DndToggle::onDndChanged(bool on) {
    setChecked(on);
    setIcon(helm::tintedIcon(dndIconName(on), helm::barGlyphColor(), QSize(18, 18)));
    setToolTip(on ? tr("Do Not Disturb: on") : tr("Do Not Disturb: off"));
    setVisible(true);
}

void DndToggle::refresh() {
    QDBusInterface iface(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                         QString::fromLatin1(kHedeIface), QDBusConnection::sessionBus());
    setVisible(iface.isValid());
    if (!iface.isValid())
        return;
    onDndChanged(iface.property("DoNotDisturb").toBool());
}

void DndToggle::toggle() {
    QDBusInterface iface(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                         QString::fromLatin1(kHedeIface), QDBusConnection::sessionBus());
    if (iface.isValid())
        iface.asyncCall(QStringLiteral("SetDoNotDisturb"), !isChecked());
}

} // namespace helm
