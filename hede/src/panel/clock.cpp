#include "clock.h"

#include "timefmt.h"

#include <QDateTime>
#include <QTimer>

namespace helm {

Clock::Clock(QWidget *parent) : QLabel(parent), m_timer(new QTimer(this)) {
    connect(m_timer, &QTimer::timeout, this, &Clock::tick);
    tick();
    m_timer->start(1000); // Phase 0: a plain 1s tick; minute-alignment can come later
}

void Clock::tick() {
    setText(formatClock(QDateTime::currentDateTime()));
}

} // namespace helm
