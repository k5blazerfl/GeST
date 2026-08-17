#include "brightness.h"

#include "palette.h"
#include "proc.h"

#include <QIcon>
#include <QTimer>
#include <QWheelEvent>

namespace helm {

int parseBrightnessPercent(const QString &out) {
    // "amdgpu_bl1,backlight,120,47%,255"
    const QStringList fields = out.split(QLatin1Char(','));
    if (fields.size() < 4)
        return -1;
    QString pct = fields[3].trimmed();
    if (pct.endsWith(QLatin1Char('%')))
        pct.chop(1);
    bool ok = false;
    const int value = pct.toInt(&ok);
    return ok ? qBound(0, value, 100) : -1;
}

BrightnessApplet::BrightnessApplet(QWidget *parent) : QToolButton(parent) {
    setAutoRaise(true);
    setFixedSize(24, 24);
    setIconSize(QSize(18, 18));
    m_have = haveProgram(QStringLiteral("brightnessctl"));
    refresh();
    if (m_have) {
        auto *t = new QTimer(this);
        connect(t, &QTimer::timeout, this, &BrightnessApplet::refresh);
        t->start(5000);
    }
}

void BrightnessApplet::wheelEvent(QWheelEvent *e) {
    if (!m_have)
        return;
    const QString step = e->angleDelta().y() > 0 ? QStringLiteral("5%+") : QStringLiteral("5%-");
    runCapture(QStringLiteral("brightnessctl"), {QStringLiteral("set"), step});
    refresh();
}

void BrightnessApplet::refresh() {
    if (!m_have) {
        setVisible(false);
        return;
    }
    const int pct =
        parseBrightnessPercent(runCapture(QStringLiteral("brightnessctl"), {QStringLiteral("-m")}));
    setVisible(pct >= 0);
    if (pct < 0)
        return;
    setIcon(helm::tintedIcon(QStringLiteral("display-brightness"), helm::barGlyphColor(),
                             QSize(18, 18)));
    setToolTip(QStringLiteral("%1%").arg(pct));
}

} // namespace helm
