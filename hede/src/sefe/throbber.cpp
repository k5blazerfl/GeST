#include "throbber.h"

#include "palette.h" // helm::harborAccent — accent fallback

#include <QFile>
#include <QMouseEvent>
#include <QPainter>
#include <QPalette>
#include <QRadialGradient>
#include <QSvgRenderer>
#include <QTimer>
#include <QtMath>

namespace helm::sefe {
namespace {

constexpr int kFrameMs = 33;       // ~30 fps
constexpr int kMinVisibleMs = 550; // deliberate throb even for instant work
constexpr qreal kSpinMax = 6.0;    // deg/frame ≈ 0.5 rev/s — a stately wheel
constexpr qreal kEase = 0.12;      // spin ease-in / wind-down

} // namespace

HelmThrobber::HelmThrobber(QWidget *parent) : QWidget(parent) {
    setCursor(Qt::PointingHandCursor);
    setToolTip(QStringLiteral("Seahorse"));
    QFile f(QStringLiteral(":/seahorse/wheel.svg"));
    if (f.open(QIODevice::ReadOnly))
        _svg = f.readAll();
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

// Rasterise the wheel SVG at `px` device pixels, tinted to accent() by
// substituting the accent hex for the SVG's `currentColor`. Cached so we only
// re-render when the accent or size actually changes.
const QPixmap &HelmThrobber::tinted(int px) {
    const QColor acc = accent();
    if (!_tinted.isNull() && _tintedFor == acc && _tintedPx == px)
        return _tinted;
    px = std::max(1, px);
    QPixmap pm(px, px);
    pm.fill(Qt::transparent);
    if (!_svg.isEmpty()) {
        QByteArray svg = _svg;
        svg.replace("currentColor", acc.name(QColor::HexRgb).toUtf8());
        QSvgRenderer r(svg);
        QPainter p(&pm);
        p.setRenderHint(QPainter::Antialiasing, true);
        r.render(&p); // fills the pixmap (SVG viewBox is square)
    }
    _tinted = pm;
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
        _pulse += 0.11; // glow breathes while working

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

    // --- soft accent glow behind the wheel, breathing while busy (gentle:
    //     plain SourceOver at low alpha — no additive blend to blow out) ---
    if (alive > 0.01) {
        const qreal base = _intensity == Intensity::Lively ? 0.34 : 0.22;
        const qreal breathe = 0.5 + 0.5 * std::sin(_pulse);
        const qreal a = alive * base * (0.6 + 0.4 * breathe);
        const qreal r = std::min(width(), height()) * 0.58;
        QRadialGradient g(c, r);
        QColor glow = acc;
        glow.setAlphaF(a);
        g.setColorAt(0.0, glow);
        glow.setAlphaF(0.0);
        g.setColorAt(1.0, glow);
        p.fillRect(rect(), g);
    }

    // --- the wheel: crisp vector, rotate while busy, rest dim + still idle ---
    const qreal dpr = devicePixelRatioF();
    const int px = std::max(1, int(std::min(width(), height()) * dpr));
    const QPixmap &pm = tinted(px);
    const qreal side = std::min(width(), height());
    p.save();
    p.translate(c);
    p.rotate(_angle);
    p.setOpacity(0.5 + 0.5 * alive); // idle rests dim; brightens as it spins
    p.drawPixmap(QRectF(-side / 2.0, -side / 2.0, side, side), pm, pm.rect());
    p.restore();
}

void HelmThrobber::mouseReleaseEvent(QMouseEvent *e) {
    if (e->button() == Qt::LeftButton && rect().contains(e->pos()))
        emit clicked();
}

} // namespace helm::sefe
