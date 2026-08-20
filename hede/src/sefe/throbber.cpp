#include "throbber.h"

#include <QDate>
#include <QMouseEvent>
#include <QPainter>
#include <QTimer>
#include <QtMath>

namespace helm::sefe {
namespace {
constexpr int kCalmMs = 210;       // moon speed — calm (~6.3s per moon cycle)
constexpr int kLivelyMs = 145;     // moon speed — lively
constexpr int kMinVisibleMs = 800; // animate at least this long, even for instant work
} // namespace

HelmThrobber::HelmThrobber(QWidget *parent) : QWidget(parent) {
    setCursor(Qt::PointingHandCursor);
    setToolTip(QStringLiteral("Seahorse"));
    _sheet = QPixmap(QStringLiteral(":/seahorse/throbber.png"));
    if (!_sheet.isNull()) {
        _fw = _sheet.width() / kCols;
        _fh = _sheet.height() / kRows;
    }
    _frame = restFrame(); // idle at tonight's moon from the start
    _timer = new QTimer(this);
    _timer->setInterval(kCalmMs);
    connect(_timer, &QTimer::timeout, this, &HelmThrobber::tick);
}

HelmThrobber::~HelmThrobber() = default;

// The sprite frame whose moon best matches tonight's phase. The moon age comes
// from a known new moon (2000-01-06, JD 2451549.5) mod the synodic month
// (29.530588853 d): t=0 is new, t=0.5 is full. The art's phases are NOT linear
// (new sits near frame 14–15 and never goes fully dark), so rather than a
// formula we match today's target illumination + lit side against each frame's
// MEASURED values and take the nearest.
int HelmThrobber::restFrame() const {
    // Measured from the sprite: per-frame illumination (0..1) and waxing (lit on
    // the right) vs waning (lit on the left).
    static constexpr float kIllum[kCount] = {
        0.99f, 0.97f, 0.84f, 0.58f, 0.39f, 0.33f, 0.34f, 0.31f, 0.27f, 0.27f,
        0.24f, 0.23f, 0.20f, 0.12f, 0.11f, 0.11f, 0.18f, 0.25f, 0.28f, 0.31f,
        0.34f, 0.45f, 0.64f, 0.76f, 0.84f, 0.86f, 0.88f, 0.91f, 0.96f, 1.00f};
    static constexpr bool kWaxing[kCount] = {
        true, true, false, false, false, false, false, false, false, false,
        false, false, false, false, false, false, true, true, true, true,
        true, true, true, true, true, true, true, true, true, true};

    constexpr double kSynodic = 29.530588853;
    double t = std::fmod(QDate::currentDate().toJulianDay() - 2451549.5, kSynodic) / kSynodic;
    if (t < 0.0)
        t += 1.0;
    const double targetIllum = (1.0 - std::cos(2.0 * M_PI * t)) / 2.0;
    const bool targetWaxing = t < 0.5; // new → full is waxing (lit on the right)

    int best = 0;
    double bestCost = 1e9;
    for (int f = 0; f < kCount; ++f) {
        double cost = std::abs(double(kIllum[f]) - targetIllum);
        // Prefer the correct lit side, except near full/new where it's ambiguous.
        if (kWaxing[f] != targetWaxing && targetIllum > 0.05 && targetIllum < 0.95)
            cost += 2.0;
        if (cost < bestCost) {
            bestCost = cost;
            best = f;
        }
    }
    return best;
}

void HelmThrobber::setIntensity(Intensity i) {
    _timer->setInterval(i == Intensity::Lively ? kLivelyMs : kCalmMs);
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
    // tick() parks the loop on the rest frame once it comes back around.
}

void HelmThrobber::tick() {
    const bool holdMin = _shownSince.isValid() && _shownSince.elapsed() < kMinVisibleMs;
    _active = _busy > 0 || holdMin;

    _frame = (_frame + 1) % kCount;
    update();

    // Settle only when we've cycled back to tonight's moon, so it parks on the
    // real current phase rather than mid-cycle.
    if (!_active && _frame == restFrame()) {
        _shownSince.invalidate();
        _timer->stop();
    }
}

void HelmThrobber::paintEvent(QPaintEvent *) {
    if (_sheet.isNull() || _fw == 0)
        return;
    QPainter p(this);
    p.setRenderHint(QPainter::SmoothPixmapTransform, true);
    const qreal side = std::min(width(), height());
    const QRectF target((width() - side) / 2.0, (height() - side) / 2.0, side, side);
    const QRectF src((_frame % kCols) * _fw, (_frame / kCols) * _fh, _fw, _fh);
    p.drawPixmap(target, _sheet, src);
}

void HelmThrobber::mouseReleaseEvent(QMouseEvent *e) {
    if (e->button() == Qt::LeftButton && rect().contains(e->pos()))
        emit clicked();
}

} // namespace helm::sefe
