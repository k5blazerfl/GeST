#include "throbber.h"

#include <QMouseEvent>
#include <QPainter>
#include <QTimer>

namespace helm::sefe {
namespace {
constexpr int kCalmMs = 110;       // moon speed — calm
constexpr int kLivelyMs = 78;      // moon speed — lively
constexpr int kMinVisibleMs = 700; // animate at least this long, even for instant work
} // namespace

HelmThrobber::HelmThrobber(QWidget *parent) : QWidget(parent) {
    setCursor(Qt::PointingHandCursor);
    setToolTip(QStringLiteral("Seahorse"));
    _sheet = QPixmap(QStringLiteral(":/seahorse/throbber.png"));
    if (!_sheet.isNull()) {
        _fw = _sheet.width() / kCols;
        _fh = _sheet.height() / kRows;
    }
    _timer = new QTimer(this);
    _timer->setInterval(kCalmMs);
    connect(_timer, &QTimer::timeout, this, &HelmThrobber::tick);
}

HelmThrobber::~HelmThrobber() = default;

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

    // Settle only when we've cycled back to the full-moon rest frame, so it
    // always parks on the moon rather than mid-phase.
    if (!_active && _frame == kRestFrame) {
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
