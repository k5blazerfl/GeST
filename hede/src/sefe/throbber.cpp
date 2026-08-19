#include "throbber.h"

#include "palette.h" // helm::harborAccent — accent fallback

#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPalette>
#include <QRandomGenerator>
#include <QTimer>
#include <QtMath>

namespace helm::sefe {
namespace {

constexpr int kFrameMs = 33;      // ~30 fps
constexpr int kMinVisibleMs = 550; // deliberate throb even for instant work
constexpr qreal kSpinMax = 8.0;   // deg/frame ≈ 0.67 rev/s — a readable spin
constexpr qreal kEase = 0.14;     // spin ease-in / wind-down

// Linear blend of two colours (including alpha) by t in [0,1].
QColor mix(const QColor &a, const QColor &b, qreal t) {
    t = qBound(0.0, t, 1.0);
    return QColor::fromRgbF(a.redF() + (b.redF() - a.redF()) * t,
                            a.greenF() + (b.greenF() - a.greenF()) * t,
                            a.blueF() + (b.blueF() - a.blueF()) * t,
                            a.alphaF() + (b.alphaF() - a.alphaF()) * t);
}

} // namespace

HelmThrobber::HelmThrobber(QWidget *parent) : QWidget(parent) {
    setCursor(Qt::PointingHandCursor);
    setToolTip(QStringLiteral("Seahorse"));
    setAttribute(Qt::WA_Hover);
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

QColor HelmThrobber::glyph() const {
    QColor g = palette().color(QPalette::WindowText);
    g.setAlpha(130); // idle wheel rests dim — it's just a mark
    return g;
}

void HelmThrobber::begin(const QString &activity) {
    _activity = activity;
    setToolTip(activity.isEmpty() ? QStringLiteral("Seahorse") : activity);
    ++_busy;
    if (!_timer->isActive()) {
        _shownSince.start();
        _sinceSpawn = 1000; // let the first star appear promptly
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
    // tick() handles settling (honours the minimum-visible span + star cleanup).
}

void HelmThrobber::maybeSpawnStar() {
    const int interval = _intensity == Intensity::Lively ? 9 : 16; // frames
    const int cap = _intensity == Intensity::Lively ? 3 : 2;
    if (++_sinceSpawn < interval || _stars.size() >= cap)
        return;
    // A little jitter so the field never feels metronomic.
    if (QRandomGenerator::global()->bounded(100) < 35)
        return;
    _sinceSpawn = 0;

    const qreal w = width(), h = height();
    auto *rng = QRandomGenerator::global();
    // Shooting stars fall top-left → bottom-right across the sky behind the
    // wheel, at a shallow diagonal, each a touch different.
    const qreal ang = qDegreesToRadians(18.0 + rng->bounded(24)); // 18–42°
    const qreal speed = (w / 9.0) * (0.85 + rng->generateDouble() * 0.4);
    Star s;
    s.pos = QPointF(rng->generateDouble() * w * 0.5 - w * 0.15,   // start off/near left
                    rng->generateDouble() * h * 0.5 - h * 0.1);   // upper band
    s.vel = QPointF(std::cos(ang) * speed, std::sin(ang) * speed);
    s.life = 1.0;
    s.len = w * (0.45 + rng->generateDouble() * 0.25);
    _stars.push_back(s);
}

void HelmThrobber::tick() {
    const bool holdMin = _shownSince.isValid() && _shownSince.elapsed() < kMinVisibleMs;
    _spinning = _busy > 0 || holdMin;

    const qreal target = _spinning ? kSpinMax : 0.0;
    _spin += (target - _spin) * kEase;
    _angle = std::fmod(_angle + _spin, 360.0);

    if (_spinning)
        maybeSpawnStar();

    // Advance + cull stars.
    const QRectF bounds = rect().adjusted(-width() * 0.3, -height() * 0.3,
                                          width() * 0.3, height() * 0.3);
    for (int i = _stars.size() - 1; i >= 0; --i) {
        Star &s = _stars[i];
        s.pos += s.vel;
        s.life -= 0.11;
        if (s.life <= 0.0 || !bounds.contains(s.pos))
            _stars.remove(i);
    }

    update();
    stopIfSettled();
}

void HelmThrobber::stopIfSettled() {
    if (!_spinning && _spin < 0.05 && _stars.isEmpty()) {
        _spin = 0.0;
        _shownSince.invalidate();
        _timer->stop();
        update();
    }
}

void HelmThrobber::paintEvent(QPaintEvent *) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);

    const QPointF c(width() / 2.0, height() / 2.0);
    const qreal R = std::min(width(), height()) / 2.0 - 2.0;
    const QColor acc = accent();

    // --- shooting stars, behind the wheel ---
    for (const Star &s : _stars) {
        const QPointF tail = s.pos - s.vel / std::hypot(s.vel.x(), s.vel.y()) * s.len;
        QLinearGradient g(tail, s.pos);
        QColor head = acc;
        head.setAlphaF(s.life * (_intensity == Intensity::Lively ? 0.75 : 0.55));
        QColor faint = acc;
        faint.setAlpha(0);
        g.setColorAt(0.0, faint);
        g.setColorAt(1.0, head);
        QPen sp(QBrush(g), 1.6);
        sp.setCapStyle(Qt::RoundCap);
        p.setPen(sp);
        p.drawLine(tail, s.pos);
        // bright head dot
        p.setPen(Qt::NoPen);
        p.setBrush(head);
        p.drawEllipse(s.pos, 1.3, 1.3);
    }

    // --- the Helm (ship's wheel) ---
    // Colour eases from the dim idle glyph toward the biome accent as it spins.
    const qreal alive = qBound(0.0, _spin / kSpinMax, 1.0);
    const QColor wheel = mix(glyph(), acc, alive);

    p.save();
    p.translate(c);
    p.rotate(_angle);

    const qreal rimR = R * 0.72; // rim radius
    const qreal hubR = R * 0.18; // hub radius
    QPen rimPen(wheel, std::max<qreal>(1.4, R * 0.14));
    rimPen.setCapStyle(Qt::RoundCap);

    // rim
    p.setPen(rimPen);
    p.setBrush(Qt::NoBrush);
    p.drawEllipse(QPointF(0, 0), rimR, rimR);

    // eight spokes + handle pegs sticking out past the rim
    QPen spokePen(wheel, std::max<qreal>(1.2, R * 0.11));
    spokePen.setCapStyle(Qt::RoundCap);
    p.setPen(spokePen);
    for (int i = 0; i < 8; ++i) {
        const qreal a = qDegreesToRadians(i * 45.0);
        const QPointF dir(std::cos(a), std::sin(a));
        p.drawLine(dir * hubR, dir * rimR);           // spoke
        p.drawLine(dir * rimR, dir * (R * 0.98));      // handle peg
    }

    // hub
    p.setPen(Qt::NoPen);
    p.setBrush(wheel);
    p.drawEllipse(QPointF(0, 0), hubR, hubR);
    p.restore();
}

void HelmThrobber::mouseReleaseEvent(QMouseEvent *e) {
    if (e->button() == Qt::LeftButton && rect().contains(e->pos()))
        emit clicked();
}

} // namespace helm::sefe
