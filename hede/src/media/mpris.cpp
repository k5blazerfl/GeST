#include "mpris.h"

#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusInterface>
#include <QDBusReply>
#include <QDBusVariant>
#include <QHBoxLayout>
#include <QIcon>
#include <QLabel>
#include <QToolButton>

namespace helm {

static constexpr auto kPath = "/org/mpris/MediaPlayer2";
static constexpr auto kPlayerIface = "org.mpris.MediaPlayer2.Player";
static constexpr auto kPropsIface = "org.freedesktop.DBus.Properties";

bool isMprisService(const QString &busName) {
    return busName.startsWith(QLatin1String("org.mpris.MediaPlayer2."));
}

QString formatTrack(const QString &title, const QString &artist) {
    if (title.isEmpty())
        return QString();
    return artist.isEmpty() ? title : artist + QStringLiteral(" — ") + title;
}

QString playPauseIconName(const QString &playbackStatus) {
    return playbackStatus == QLatin1String("Playing") ? QStringLiteral("media-playback-pause")
                                                      : QStringLiteral("media-playback-start");
}

static QVariant unwrap(QVariant v) {
    if (v.canConvert<QDBusVariant>())
        v = v.value<QDBusVariant>().variant();
    return v;
}

MprisApplet::MprisApplet(QWidget *parent)
    : QWidget(parent), m_prev(new QToolButton(this)), m_playPause(new QToolButton(this)),
      m_next(new QToolButton(this)), m_title(new QLabel(this)) {
    auto *layout = new QHBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);
    for (QToolButton *b : {m_prev, m_playPause, m_next})
        b->setAutoRaise(true);
    m_prev->setIcon(QIcon::fromTheme(QStringLiteral("media-skip-backward")));
    m_next->setIcon(QIcon::fromTheme(QStringLiteral("media-skip-forward")));
    m_title->setMaximumWidth(180);
    layout->addWidget(m_title);
    layout->addWidget(m_prev);
    layout->addWidget(m_playPause);
    layout->addWidget(m_next);

    connect(m_prev, &QToolButton::clicked, this, [this] { call(QStringLiteral("Previous")); });
    connect(m_playPause, &QToolButton::clicked, this,
            [this] { call(QStringLiteral("PlayPause")); });
    connect(m_next, &QToolButton::clicked, this, [this] { call(QStringLiteral("Next")); });

    connect(QDBusConnection::sessionBus().interface(), &QDBusConnectionInterface::NameOwnerChanged,
            this, &MprisApplet::onNameOwnerChanged);

    pickPlayer();
}

void MprisApplet::onNameOwnerChanged(const QString &name, const QString &, const QString &) {
    if (isMprisService(name))
        pickPlayer();
}

void MprisApplet::pickPlayer() {
    const QDBusReply<QStringList> names =
        QDBusConnection::sessionBus().interface()->registeredServiceNames();
    QString chosen;
    if (names.isValid()) {
        for (const QString &n : names.value()) {
            if (isMprisService(n)) {
                chosen = n;
                break;
            }
        }
    }
    if (chosen != m_player) {
        m_player = chosen;
        if (!m_player.isEmpty())
            QDBusConnection::sessionBus().connect(
                m_player, QString::fromLatin1(kPath), QString::fromLatin1(kPropsIface),
                QStringLiteral("PropertiesChanged"), this, SLOT(onPropertiesChanged()));
    }
    refresh();
}

void MprisApplet::onPropertiesChanged() {
    refresh();
}

void MprisApplet::refresh() {
    if (m_player.isEmpty()) {
        setVisible(false);
        return;
    }
    QDBusInterface props(m_player, QString::fromLatin1(kPath), QString::fromLatin1(kPropsIface),
                         QDBusConnection::sessionBus());

    const QString status =
        unwrap(QDBusReply<QDBusVariant>(props.call(QStringLiteral("Get"),
                                                   QString::fromLatin1(kPlayerIface),
                                                   QStringLiteral("PlaybackStatus")))
                   .value()
                   .variant())
            .toString();
    m_playPause->setIcon(QIcon::fromTheme(playPauseIconName(status)));

    QString title, artist;
    const QVariant mdv = QDBusReply<QDBusVariant>(props.call(QStringLiteral("Get"),
                                                             QString::fromLatin1(kPlayerIface),
                                                             QStringLiteral("Metadata")))
                             .value()
                             .variant();
    if (mdv.canConvert<QDBusArgument>()) {
        QVariantMap md;
        mdv.value<QDBusArgument>() >> md;
        title = unwrap(md.value(QStringLiteral("xesam:title"))).toString();
        artist = unwrap(md.value(QStringLiteral("xesam:artist"))).toStringList().value(0);
    }
    const QString track = formatTrack(title, artist);
    m_title->setText(track);
    m_title->setToolTip(track);
    setVisible(true);
}

void MprisApplet::call(const QString &method) {
    if (m_player.isEmpty())
        return;
    QDBusInterface(m_player, QString::fromLatin1(kPath), QString::fromLatin1(kPlayerIface),
                   QDBusConnection::sessionBus())
        .asyncCall(method);
}

} // namespace helm
