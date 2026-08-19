#include "throbber.h"

#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QRadialGradient>
#include <QRandomGenerator>
#include <QTimer>
#include <QtMath>

namespace helm::sefe {
namespace {

constexpr int kFrameMs = 33;       // ~30 fps
constexpr int kMinVisibleMs = 650; // a couple of comets even for instant work
constexpr qreal kHorizon = 0.60;   // comets live above this fraction of the scene

// Draw one shooting star, in the spirit of the Netscape meteor: a tapering wedge
// tail fading through icy blue to nothing, a soft additive head bloom, and a
// bright white core. `head` is the leading point, `dir` a unit vector along
// travel, `len` the tail length, `life` in [0,1] the fade, `w` the head width.
void drawComet(QPainter &p, const QPointF &head, const QPointF &dir,
               qreal len, qreal life, qreal w) {
    const QPointF tip = head - dir * len;
    const QPointF perp(-dir.y(), dir.x());

    // tapering wedge: full width at the head, narrowing to a point at the tip
    QPainterPath wedge;
    wedge.moveTo(head + perp * (w * 0.5));
    wedge.lineTo(head - perp * (w * 0.5));
    wedge.lineTo(tip);
    wedge.closeSubpath();
    QLinearGradient g(head, tip);
    QColor bright(224, 242, 255); bright.setAlphaF(0.92 * life); // icy-white head
    QColor mid(150, 198, 255);    mid.setAlphaF(0.30 * life);    // pale blue body
    QColor gone(150, 198, 255);   gone.setAlphaF(0.0);           // fades out
    g.setColorAt(0.0, bright);
    g.setColorAt(0.5, mid);
    g.setColorAt(1.0, gone);
    p.setPen(Qt::NoPen);
    p.setBrush(g);
    p.drawPath(wedge);

    // soft head bloom — additive is safe here (it sits over the dark sky)
    p.setCompositionMode(QPainter::CompositionMode_Plus);
    const qreal br = w * 2.3;
    QRadialGradient rg(head, br);
    QColor glow(170, 214, 255); glow.setAlphaF(0.55 * life);
    rg.setColorAt(0.0, glow);
    glow.setAlphaF(0.0);
    rg.setColorAt(1.0, glow);
    p.setBrush(rg);
    p.drawEllipse(head, br, br);
    p.setCompositionMode(QPainter::CompositionMode_SourceOver);

    // bright white core
    QColor core(255, 255, 255); core.setAlphaF(life);
    p.setBrush(core);
    p.drawEllipse(head, w * 0.52, w * 0.52);
}

} // namespace

HelmThrobber::HelmThrobber(QWidget *parent) : QWidget(parent) {
    setCursor(Qt::PointingHandCursor);
    setToolTip(QStringLiteral("Seahorse"));
    _base = QPixmap(QStringLiteral(":/seahorse/base.png"));
    _timer = new QTimer(this);
    _timer->setInterval(kFrameMs);
    connect(_timer, &QTimer::timeout, this, &HelmThrobber::tick);
}

HelmThrobber::~HelmThrobber() = default;

const QPixmap &HelmThrobber::scaled(int px) {
    if (!_scaled.isNull() && _scaledPx == px)
        return _scaled;
    _scaled = _base.isNull()
                  ? QPixmap()
                  : _base.scaled(px, px, Qt::KeepAspectRatio, Qt::SmoothTransformation);
    _scaledPx = px;
    return _scaled;
}

void HelmThrobber::begin(const QString &activity) {
    _activity = activity;
    setToolTip(activity.isEmpty() ? QStringLiteral("Seahorse") : activity);
    ++_busy;
    if (!_timer->isActive()) {
        _shownSince.start();
        _sinceSpawn = 1000; // let the first comet fall promptly
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
    // tick() empties the sky once settled (honours the minimum-visible span).
}

void HelmThrobber::maybeSpawn(qreal S) {
    const int interval = _intensity == Intensity::Lively ? 10 : 20; // frames
    const int cap = _intensity == Intensity::Lively ? 3 : 2;
    if (++_sinceSpawn < interval || _comets.size() >= cap)
        return;
    if (QRandomGenerator::global()->bounded(100) < 30) // jitter — not metronomic
        return;
    _sinceSpawn = 0;

    auto *rng = QRandomGenerator::global();
    // Fall down-and-across; half the comets lean right, half left.
    const bool right = rng->bounded(2) == 0;
    const qreal ang = qDegreesToRadians(right ? 32.0 + rng->bounded(24)     // 32–56°
                                              : 124.0 + rng->bounded(24));   // 124–148°
    const qreal flightFrames = 13.0 + rng->bounded(6);   // ~0.45–0.63s
    const qreal speed = S * 0.058;
    Comet c;
    c.pos = QPointF(rng->generateDouble() * S, rng->generateDouble() * S * 0.10);
    c.vel = QPointF(std::cos(ang) * speed, std::sin(ang) * speed);
    c.progress = 0.0;
    c.step = 1.0 / flightFrames;
    c.len = S * (0.28 + rng->generateDouble() * 0.16);
    _comets.push_back(c);
}

void HelmThrobber::tick() {
    const bool holdMin = _shownSince.isValid() && _shownSince.elapsed() < kMinVisibleMs;
    _active = _busy > 0 || holdMin;
    const qreal S = std::min(width(), height());

    if (_active)
        maybeSpawn(S);
    for (int i = _comets.size() - 1; i >= 0; --i) {
        Comet &c = _comets[i];
        c.pos += c.vel;
        c.progress += c.step;
        if (c.progress >= 1.0 || c.pos.y() > S * kHorizon + 6)
            _comets.remove(i);
    }

    update();

    if (!_active && _comets.isEmpty()) { // settled — quiet sky
        _shownSince.invalidate();
        _timer->stop();
        update();
    }
}

void HelmThrobber::paintEvent(QPaintEvent *) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::SmoothPixmapTransform, true);

    const qreal dpr = devicePixelRatioF();
    const qreal S = std::min(width(), height());
    const int px = std::max(1, int(S * dpr));
    const QPixmap &pm = scaled(px);
    const QPointF origin((width() - S) / 2.0, (height() - S) / 2.0);

    // --- the scene (static) ---
    if (!pm.isNull())
        p.drawPixmap(QRectF(origin, QSizeF(S, S)), pm, pm.rect());

    if (_comets.isEmpty())
        return;

    // --- shooting stars, in the sky above the horizon ---
    p.save();
    p.translate(origin);
    p.setClipRect(QRectF(0, 0, S, S * kHorizon)); // never over the planet
    for (const Comet &c : _comets) {
        const qreal sp = std::hypot(c.vel.x(), c.vel.y());
        if (sp <= 0.0001)
            continue;
        const QPointF dir = c.vel / sp;
        const qreal life = std::sin(M_PI * qBound(0.0, c.progress, 1.0)); // fade in/out
        // head width scales gently with tail length (longer ⇒ a touch bolder)
        const qreal w = std::max<qreal>(1.4, S * 0.05 * (0.75 + c.len / S));
        drawComet(p, c.pos, dir, c.len, life, w);
    }
    p.restore();
}

void HelmThrobber::mouseReleaseEvent(QMouseEvent *e) {
    if (e->button() == Qt::LeftButton && rect().contains(e->pos()))
        emit clicked();
}

} // namespace helm::sefe
