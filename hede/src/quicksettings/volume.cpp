#include "volume.h"

#include "palette.h"
#include "proc.h"

#include <QIcon>
#include <QMouseEvent>
#include <QTimer>
#include <QWheelEvent>

namespace helm {

static constexpr auto kSink = "@DEFAULT_AUDIO_SINK@";

VolumeState parseWpctlVolume(const QString &out) {
    // "Volume: 0.55" or "Volume: 0.55 [MUTED]"
    const int colon = out.indexOf(QLatin1Char(':'));
    if (!out.startsWith(QLatin1String("Volume:")) || colon < 0)
        return {};
    VolumeState st;
    st.muted = out.contains(QLatin1String("[MUTED]"));
    const QString rest = out.mid(colon + 1).trimmed();
    const QString num = rest.section(QLatin1Char(' '), 0, 0);
    bool ok = false;
    const double frac = num.toDouble(&ok);
    if (!ok)
        return {};
    st.available = true;
    st.percent = qBound(0, qRound(frac * 100.0), 100);
    return st;
}

QString volumeIconName(int percent, bool muted) {
    if (muted || percent <= 0)
        return QStringLiteral("audio-volume-muted");
    if (percent < 34)
        return QStringLiteral("audio-volume-low");
    if (percent < 67)
        return QStringLiteral("audio-volume-medium");
    return QStringLiteral("audio-volume-high");
}

VolumeApplet::VolumeApplet(QWidget *parent) : QToolButton(parent) {
    setAutoRaise(true);
    setFixedSize(24, 24);
    setIconSize(QSize(18, 18));
    m_have = haveProgram(QStringLiteral("wpctl"));
    refresh();
    if (m_have) {
        auto *t = new QTimer(this);
        connect(t, &QTimer::timeout, this, &VolumeApplet::refresh);
        t->start(2000);
    }
}

void VolumeApplet::wheelEvent(QWheelEvent *e) {
    if (!m_have)
        return;
    const QString step = e->angleDelta().y() > 0 ? QStringLiteral("5%+") : QStringLiteral("5%-");
    runCapture(QStringLiteral("wpctl"),
               {QStringLiteral("set-volume"), QString::fromLatin1(kSink), step});
    refresh();
}

void VolumeApplet::mouseReleaseEvent(QMouseEvent *e) {
    if (m_have && e->button() == Qt::LeftButton) {
        runCapture(QStringLiteral("wpctl"), {QStringLiteral("set-mute"), QString::fromLatin1(kSink),
                                             QStringLiteral("toggle")});
        refresh();
    }
    QToolButton::mouseReleaseEvent(e);
}

void VolumeApplet::refresh() {
    if (!m_have) {
        setVisible(false);
        return;
    }
    const VolumeState st = parseWpctlVolume(runCapture(
        QStringLiteral("wpctl"), {QStringLiteral("get-volume"), QString::fromLatin1(kSink)}));
    setVisible(st.available);
    if (!st.available)
        return;
    setIcon(helm::tintedIcon(volumeIconName(st.percent, st.muted), helm::barGlyphColor(),
                             QSize(18, 18)));
    setToolTip(st.muted ? tr("Muted") : QStringLiteral("%1%").arg(st.percent));
}

} // namespace helm
