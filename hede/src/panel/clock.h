#pragma once

#include <QLabel>

class QTimer;

namespace helm {

// A clock label. Rendering is delegated to helm::formatClock (pure, tested);
// this class only owns the timer and the QLabel.
class Clock : public QLabel {
    Q_OBJECT
  public:
    explicit Clock(QWidget *parent = nullptr);

  private:
    void tick();
    QTimer *m_timer;
};

} // namespace helm
