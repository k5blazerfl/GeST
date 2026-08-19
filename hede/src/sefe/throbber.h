#pragma once

#include <QColor>
#include <QElapsedTimer>
#include <QVector>
#include <QWidget>

class QTimer;

namespace helm::sefe {

// HelmThrobber — Seahorse's "old grey whistle test" busy light, in the spirit of
// Netscape Navigator's throbber: it rests on a static mark when idle and comes
// alive while the app is working, then settles again. HeDE's mark is a ship's
// wheel (a Helm), so the wheel *spins* while busy and sparse shooting stars
// streak past it — the wheel is always the legible anchor; the stars are the
// accent. It self-tints from the widget palette's Highlight (the active biome
// accent, kept live by applyAppearance()/watchAppearance()), and — like
// Netscape's throbber going to the home page — clicking it emits clicked().
//
// Busy is ref-counted: begin()/end() nest, so overlapping operations keep it
// spinning and it settles only when the last one ends. A short minimum-visible
// span means even instant work gives a deliberate throb rather than a flicker.
class HelmThrobber : public QWidget {
    Q_OBJECT
  public:
    // How lively the shooting stars are. Calm ships by default (few, dim);
    // Lively is the busier field. Read from hede.conf [seahorse] throbber.
    enum class Intensity { Calm, Lively };

    explicit HelmThrobber(QWidget *parent = nullptr);
    ~HelmThrobber() override;

    QSize sizeHint() const override { return {28, 28}; }

    void setIntensity(Intensity i) { _intensity = i; }

  public slots:
    // Enter the busy state (nestable). `activity` sets the tooltip, e.g.
    // "Extracting archive…"; empty restores the idle tooltip.
    void begin(const QString &activity = QString());
    // Leave the busy state. When the last begin() is balanced the wheel settles
    // (after the minimum-visible span) and the stars finish streaking out.
    void end();

  signals:
    void clicked();

  protected:
    void paintEvent(QPaintEvent *) override;
    void mouseReleaseEvent(QMouseEvent *) override;

  private:
    struct Star {
        QPointF pos;   // current head position, in widget coordinates
        QPointF vel;   // per-frame travel
        qreal life;    // 1.0 → 0.0; fades and is culled at 0
        qreal len;     // tail length, in px
    };

    void tick();          // one animation frame
    void maybeSpawnStar(); // spawn subject to intensity + cap
    void stopIfSettled();  // stop the timer once idle and stars have cleared
    QColor accent() const; // palette Highlight (the biome accent)
    QColor glyph() const;  // idle wheel colour (dim WindowText)

    QTimer *_timer = nullptr;
    QElapsedTimer _shownSince; // guards the minimum-visible span
    QVector<Star> _stars;
    Intensity _intensity = Intensity::Calm;
    int _busy = 0;         // active begin() count
    bool _spinning = false; // wheel is turning + stars spawn
    qreal _angle = 0.0;    // wheel rotation, degrees
    qreal _spin = 0.0;     // current angular speed (eased in/out)
    int _sinceSpawn = 0;   // frames since the last star
    QString _activity;     // current tooltip verb
};

} // namespace helm::sefe
