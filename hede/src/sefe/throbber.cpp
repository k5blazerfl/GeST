#include "throbber.h"

#include "palette.h" // helm::harborAccent — accent fallback

#include <QMouseEvent>
#include <QPainter>
#include <QPalette>
#include <QRadialGradient>
#include <QTimer>
#include <QtMath>

namespace helm::sefe {
namespace {

constexpr int kFrameMs = 33;       // ~30 fps
constexpr int kMinVisibleMs = 550; // deliberate throb even for instant work
constexpr qreal kSpinMax = 7.0;    // deg/frame ≈ 0.58 rev/s — a stately spin
constexpr qreal kEase = 0.12;      // spin ease-in / wind-down

} // namespace

HelmThrobber::HelmThrobber(QWidget *parent) : QWidget(parent) {
    setCursor(Qt::PointingHandCursor);
    setToolTip(QStringLiteral("Seahorse"));
    _emblem = QImage(QStringLiteral(":/seahorse/emblem.png"));
    _timer = new QTimer(this);
    _timer->setInterval(kFrameMs);
    connect(_timer, &QTimer::timeout, this, &HelmThrobber::tick);
}

HelmThrobber::~HelmThrobber() = default;

QColor HelmThrobber::accent() const {
    QColor a = palette().highlight().color();
    if (!a.isValid() || a.alpha() == 0)
        a = helm::harborAccent();
    return a;
}

// Colourise the neutral grayscale emblem to `accent()` while keeping its
// luminance (glowing metal in the biome colour), then scale to `px`. Standard
// recolour recipe: multiply the accent through, then re-intersect the alpha.
const QPixmap &HelmThrobber::tinted(int px) {
    const QColor acc = accent();
    if (!_tinted.isNull() && _tintedFor == acc && _tintedPx == px)
        return _tinted;
    if (_emblem.isNull()) { // no art embedded — leave the cache null
        _tinted = QPixmap();
        _tintedFor = acc;
        _tintedPx = px;
        return _tinted;
    }
    QImage img = _emblem.convertToFormat(QImage::Format_ARGB32_Premultiplied);
    QPainter p(&img);
    p.setCompositionMode(QPainter::CompositionMode_Multiply);
    p.fillRect(img.rect(), acc);
    p.setCompositionMode(QPainter::CompositionMode_DestinationIn);
    p.drawImage(0, 0, _emblem); // restore the original (luminance) alpha
    p.end();
    _tinted = QPixmap::fromImage(
        img.scaled(px, px, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    _tintedFor = acc;
    _tintedPx = px;
    return _tinted;
}

void HelmThrobber::begin(const QString &activity) {
    _activity = activity;
    setToolTip(activity.isEmpty() ? QStringLiteral("Seahorse") : activity);
    ++_busy;
    if (!_timer->isActive()) {
        _shownSince.start();
        _timer->start();
    }
}

void HelmThrobber::end() {
    if (_busy > 0)
        --_busy;
    if (_busy == 0) {
        setToolTip(QStringLiteral("Seahorse"));
        _activity.clear();
    }
    // tick() handles settling (honours the minimum-visible span).
}

void HelmThrobber::tick() {
    const bool holdMin = _shownSince.isValid() && _shownSince.elapsed() < kMinVisibleMs;
    _spinning = _busy > 0 || holdMin;

    const qreal target = _spinning ? kSpinMax : 0.0;
    _spin += (target - _spin) * kEase;
    _angle = std::fmod(_angle + _spin, 360.0);
    if (_spinning)
        _pulse += 0.12; // bloom breathes while working

    update();

    if (!_spinning && _spin < 0.05) { // settled — rest
        _spin = 0.0;
        _shownSince.invalidate();
        _timer->stop();
        update();
    }
}

void HelmThrobber::paintEvent(QPaintEvent *) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::SmoothPixmapTransform, true);

    const QPointF c(width() / 2.0, height() / 2.0);
    const qreal alive = qBound(0.0, _spin / kSpinMax, 1.0);
    const QColor acc = accent();

    // --- accent bloom behind the emblem, breathing while busy ---
    if (alive > 0.01) {
        const qreal base = _intensity == Intensity::Lively ? 0.42 : 0.28;
        const qreal breathe = 0.5 + 0.5 * std::sin(_pulse);
        const qreal a = alive * base * (0.55 + 0.45 * breathe);
        const qreal r = std::min(width(), height()) * 0.62;
        QRadialGradient g(c, r);
        QColor glow = acc;
        glow.setAlphaF(a);
        g.setColorAt(0.0, glow);
        glow.setAlphaF(0.0);
        g.setColorAt(1.0, glow);
        p.setCompositionMode(QPainter::CompositionMode_Plus);
        p.fillRect(rect(), g);
        p.setCompositionMode(QPainter::CompositionMode_SourceOver);
    }

    // --- the emblem: rotate while busy, rest dim + still when idle ---
    const qreal dpr = devicePixelRatioF();
    const int px = int(std::min(width(), height()) * dpr);
    const QPixmap &pm = tinted(px);
    if (!pm.isNull()) {
        p.save();
        p.translate(c);
        p.rotate(_angle);
        p.setOpacity(0.45 + 0.55 * alive); // idle rests dim; brightens as it spins
        const qreal w = pm.width() / dpr, h = pm.height() / dpr;
        p.drawPixmap(QRectF(-w / 2.0, -h / 2.0, w, h), pm, pm.rect());
        p.restore();
    } else { // no art embedded — a dim accent dot so the berth is never empty
        p.setBrush(acc);
        p.setPen(Qt::NoPen);
        p.setOpacity(0.4 + 0.6 * alive);
        const qreal r = std::min(width(), height()) * 0.28;
        p.drawEllipse(c, r, r);
    }
}

void HelmThrobber::mouseReleaseEvent(QMouseEvent *e) {
    if (e->button() == Qt::LeftButton && rect().contains(e->pos()))
        emit clicked();
}

} // namespace helm::sefe
