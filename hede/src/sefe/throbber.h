#pragma once

#include <QColor>
#include <QElapsedTimer>
#include <QImage>
#include <QPixmap>
#include <QWidget>

class QTimer;

namespace helm::sefe {

// HelmThrobber — Seahorse's "old grey whistle test" busy light, in the spirit of
// Netscape Navigator's throbber: it rests on a static mark when idle and comes
// alive while the app is working, then settles. HeDE's mark is a rendered,
// glowing ship's-wheel / compass emblem (authored with the local Ollama→SDXL art
// pipeline, embedded as :/seahorse/emblem.png). The emblem ships as a NEUTRAL
// grayscale glow, so the widget tints it to the active biome accent — pulled
// live from the palette Highlight (kept current by applyAppearance()/
// watchAppearance()) — and, being radially symmetric, rotating it while busy
// gives a seamless loop with a soft accent bloom. Idle, it rests dim and still.
// Clicking it sails Home, like Netscape's throbber → home page.
//
// Busy is ref-counted: begin()/end() nest, so overlapping operations keep it
// spinning and it settles only when the last ends. A short minimum-visible span
// means even instant work gives a deliberate throb, not a flicker.
class HelmThrobber : public QWidget {
    Q_OBJECT
  public:
    // How strong the accent bloom is. Calm ships by default; Lively glows harder.
    // Read from hede.conf [seahorse] throbber.
    enum class Intensity { Calm, Lively };

    explicit HelmThrobber(QWidget *parent = nullptr);
    ~HelmThrobber() override;

    QSize sizeHint() const override { return {30, 30}; }

    void setIntensity(Intensity i) { _intensity = i; }

  public slots:
    // Enter the busy state (nestable). `activity` sets the tooltip, e.g.
    // "Extracting archive…"; empty restores the idle tooltip.
    void begin(const QString &activity = QString());
    // Leave the busy state. When the last begin() is balanced the wheel settles
    // (after the minimum-visible span).
    void end();

  signals:
    void clicked();

  protected:
    void paintEvent(QPaintEvent *) override;
    void mouseReleaseEvent(QMouseEvent *) override;

  private:
    void tick();               // one animation frame
    QColor accent() const;     // palette Highlight (the biome accent)
    // The emblem tinted to `accent()` at `px` device pixels, cached so we only
    // recolour when the accent or size actually changes.
    const QPixmap &tinted(int px);

    QTimer *_timer = nullptr;
    QElapsedTimer _shownSince; // guards the minimum-visible span
    QImage _emblem;            // neutral grayscale glow (alpha = luminance)
    QPixmap _tinted;           // cached tinted+scaled emblem
    QColor _tintedFor;         // accent the cache was built for
    int _tintedPx = 0;         // device px the cache was built for
    Intensity _intensity = Intensity::Calm;
    int _busy = 0;             // active begin() count
    bool _spinning = false;    // wheel is turning
    qreal _angle = 0.0;        // wheel rotation, degrees
    qreal _spin = 0.0;         // current angular speed (eased in/out)
    qreal _pulse = 0.0;        // glow-bloom phase, advances while busy
    QString _activity;         // current tooltip verb
};

} // namespace helm::sefe
