#pragma once

#include <QWidget>

namespace helm {

// The bottom bar. Phase 0: a launcher button on the left, a stretch in the
// middle (where the window list lands in Phase 1), and a clock on the right.
class Panel : public QWidget {
    Q_OBJECT
  public:
    explicit Panel(QWidget *parent = nullptr);
};

} // namespace helm
