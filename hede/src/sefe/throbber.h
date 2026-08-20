#pragma once

#include <QElapsedTimer>
#include <QPixmap>
#include <QWidget>

class QTimer;

namespace helm::sefe {

// HelmThrobber — Seahorse's "old grey whistle test" busy light: a pixel-art
// Helm wheel under a cycling moon over a twinkling starfield. Faithful to
// Netscape's throbber — a static mark that comes alive while the app works, then
// settles. The animation is a 30-frame sprite sheet (:/seahorse/throbber.png,
// 6×5 grid): while busy it plays the loop (the moon runs its phases, the sky and
// wheel carry a hand-placed "nightly snapshot" wobble); idle it rests on the
// frame matching TONIGHT'S real moon phase (restFrame()), so a resting Seahorse
// shows the actual moon over the Helm. Clicking it sails Home, like Netscape's.
//
// Busy is ref-counted: begin()/end() nest, so overlapping operations keep it
// playing; it settles only when the last ends — and then only once the loop
// comes back around to the rest frame, so it always parks on tonight's moon
// (after a minimum-visible span, so instant work still animates rather than
// flickering).
class HelmThrobber : public QWidget {
    Q_OBJECT
  public:
    // Playback speed. Calm ships by default; Lively runs the moon faster.
    // Read from hede.conf [seahorse] throbber.
    enum class Intensity { Calm, Lively };

    explicit HelmThrobber(QWidget *parent = nullptr);
    ~HelmThrobber() override;

    QSize sizeHint() const override { return {38, 38}; }

    void setIntensity(Intensity i);

  public slots:
    // Enter the busy state (nestable). `activity` sets the tooltip, e.g.
    // "Extracting archive…"; empty restores the idle tooltip.
    void begin(const QString &activity = QString());
    // Leave the busy state; the loop finishes back to the full-moon rest frame.
    void end();

  signals:
    void clicked();

  protected:
    void paintEvent(QPaintEvent *) override;
    void mouseReleaseEvent(QMouseEvent *) override;

  private:
    void tick();            // advance one sprite frame
    int restFrame() const;  // the sprite frame matching tonight's real moon phase

    static constexpr int kCols = 6;
    static constexpr int kRows = 5;
    static constexpr int kCount = 30;

    QTimer *_timer = nullptr;
    QElapsedTimer _shownSince; // guards the minimum-visible span
    QPixmap _sheet;            // the 6×5 sprite sheet
    int _fw = 0, _fh = 0;      // frame size within the sheet
    int _frame = 0;            // set to restFrame() at construction
    int _busy = 0;             // active begin() count
    bool _active = false;      // busy (or within the minimum-visible span)
    QString _activity;         // current tooltip verb
};

} // namespace helm::sefe
