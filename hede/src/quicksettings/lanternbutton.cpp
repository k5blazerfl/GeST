#include "lanternbutton.h"

#include "config.h"
#include "launch.h"
#include "palette.h"

#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusReply>
#include <QDBusServiceWatcher>
#include <QJsonArray>
#include <QJsonDocument>
#include <QPainter>

namespace helm {

// helm-notifyd's object + HeDE extension interface (kept in sync with src/notify
// and src/quicksettings/dndtoggle.cpp).
static constexpr auto kService = "org.freedesktop.Notifications";
static constexpr auto kPath = "/org/freedesktop/Notifications";
static constexpr auto kHedeIface = "org.gentoo.hede.Notifications";

QString lanternTooltip(int count) {
    if (count <= 0)
        return QObject::tr("Notifications");
    if (count == 1)
        return QObject::tr("1 notification");
    return QObject::tr("%1 notifications").arg(count);
}

LanternButton::LanternButton(QWidget *parent) : QToolButton(parent) {
    setAutoRaise(true);
    setFixedSize(24, 24);
    setIconSize(QSize(18, 18));
    setIcon(tintedIcon(QStringLiteral("notifications"), barGlyphColor(), QSize(18, 18)));

    QDBusConnection bus = QDBusConnection::sessionBus();
    m_watcher = new QDBusServiceWatcher(QString::fromLatin1(kService), bus,
                                        QDBusServiceWatcher::WatchForRegistration |
                                            QDBusServiceWatcher::WatchForUnregistration,
                                        this);
    connect(m_watcher, &QDBusServiceWatcher::serviceRegistered, this, [this] { refresh(); });
    connect(m_watcher, &QDBusServiceWatcher::serviceUnregistered, this,
            [this] { setVisible(false); });
    bus.connect(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                QString::fromLatin1(kHedeIface), QStringLiteral("NotificationAdded"), this,
                SLOT(onHistoryChanged()));
    bus.connect(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                QString::fromLatin1(kHedeIface), QStringLiteral("HistoryCleared"), this,
                SLOT(onHistoryChanged()));

    connect(this, &QToolButton::clicked, this, [this] { open(); });
    refresh();
}

void LanternButton::onHistoryChanged() { refresh(); }

void LanternButton::refresh() {
    QDBusInterface iface(QString::fromLatin1(kService), QString::fromLatin1(kPath),
                         QString::fromLatin1(kHedeIface), QDBusConnection::sessionBus());
    setVisible(iface.isValid());
    if (!iface.isValid())
        return;
    int count = 0;
    const QDBusReply<QString> reply = iface.call(QStringLiteral("GetHistory"));
    if (reply.isValid()) {
        const QJsonDocument doc = QJsonDocument::fromJson(reply.value().toUtf8());
        if (doc.isArray())
            count = doc.array().size();
    }
    m_count = count;
    setToolTip(lanternTooltip(count));
    update(); // repaint the dot
}

void LanternButton::open() { launchDetached(QStringLiteral("helm-lantern")); }

void LanternButton::paintEvent(QPaintEvent *e) {
    QToolButton::paintEvent(e);
    if (m_count <= 0)
        return;
    // A small accent dot in the top-right corner while there's unread history.
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    p.setPen(Qt::NoPen);
    p.setBrush(effectiveAccent(Config()));
    const int d = 7;
    p.drawEllipse(width() - d - 2, 2, d, d);
}

} // namespace helm
