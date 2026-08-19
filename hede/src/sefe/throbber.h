#pragma once

#include <QColor>
#include <QElapsedTimer>
#include <QPixmap>
#include <QVector>
#include <QWidget>

class QTimer;

namespace helm::sefe {

// HelmThrobber — Seahorse's "old grey whistle test" busy light, faithful to
// Netscape Navigator's: a static mark that comes alive while the app works, then
// settles. The mark is a ship's wheel over a planet in a teal starfield (a clean
// base scene, :/seahorse/base.png). Like Netscape's throbber the SCENE holds
// still — what animates is the sky: while busy, shooting stars streak across it
// on smooth procedural trajectories (bright head + fading tail), then the sky
// empties when work ends. Clicking it sails Home, like Netscape's → home page.
//
// Busy is ref-counted: begin()/end() nest, so overlapping operations keep the
// stars falling; they stop only when the last ends (after a minimum-visible
// span, so instant work still gives a couple of comets, not a flicker).
class HelmThrobber : public QWidget {
    Q_OBJECT
  public:
    // How busy the sky gets. Calm ships by default (sparse comets); Lively is a
    // denser meteor shower. Read from hede.conf [seahorse] throbber.
    enum class Intensity { Calm, Lively };

    explicit HelmThrobber(QWidget *parent = nullptr);
    ~HelmThrobber() override;

    QSize sizeHint() const override { return {40, 40}; }

    void setIntensity(Intensity i) { _intensity = i; }

  public slots:
    // Enter the busy state (nestable). `activity` sets the tooltip, e.g.
    // "Extracting archive…"; empty restores the idle tooltip.
    void begin(const QString &activity = QString());
    // Leave the busy state; the sky empties once the last begin() is balanced
    // (after the minimum-visible span).
    void end();

  signals:
    void clicked();

  protected:
    void paintEvent(QPaintEvent *) override;
    void mouseReleaseEvent(QMouseEvent *) override;

  private:
    struct Comet {
        QPointF pos;   // head, in the base-square's local coords (0..S)
        QPointF vel;   // per-frame travel
        qreal progress = 0.0; // 0→1 across its flight (drives fade)
        qreal step = 0.0;     // progress increment per frame
        qreal len = 0.0;      // tail length, px
    };

    void tick();           // one animation frame
    void maybeSpawn(qreal S); // spawn a comet subject to intensity + cap
    const QPixmap &scaled(int px); // base scaled to the widget, cached

    QTimer *_timer = nullptr;
    QElapsedTimer _shownSince; // guards the minimum-visible span
    QPixmap _base;             // the scene (wheel + planet + starfield)
    QPixmap _scaled;           // cached scaled scene
    int _scaledPx = 0;
    QVector<Comet> _comets;
    Intensity _intensity = Intensity::Calm;
    int _busy = 0;             // active begin() count
    bool _active = false;      // busy (or within the minimum-visible span)
    int _sinceSpawn = 0;       // frames since the last comet
    QString _activity;         // current tooltip verb
};

} // namespace helm::sefe
