#pragma once

#include <QWidget>

class QBoxLayout;

namespace helm {

// The panel bar. Its applet lineup is built from hede.conf [panel] applets and
// its edge from [panel] edge (via helm::PanelLayout); it rebuilds itself in
// place when that file changes — the seam Barnacle (the panel editor) writes to.
// The bar anchors to any screen edge: bottom/top run horizontal, left/right run
// vertical (the layout flips direction to match).
class Panel : public QWidget {
    Q_OBJECT
  public:
    explicit Panel(QWidget *parent = nullptr);

    // Watch hede.conf and reload() the bar when it changes. Call after show()
    // so the owner can re-anchor the surface on a live geometry change.
    void watchConfig();

  Q_SIGNALS:
    // Emitted after each in-place rebuild, so the owner can re-anchor the
    // layer-shell surface — re-reserving the exclusive zone for the current
    // height and re-pointing it at the current [panel] edge.
    void reloaded();

  public Q_SLOTS:
    // Re-read config and rebuild the applet layout (and height) in place.
    void reload();

  protected:
    // Paint the #HelmBar glass background — required because the bar is a
    // top-level WA_TranslucentBackground widget, which otherwise renders its
    // styled background fully transparent.
    void paintEvent(QPaintEvent *event) override;

  private:
    void buildApplets();   // (re)populate m_layout from [panel] applets
    void applyGeometry();   // orient + size the bar for the current [panel] edge

    QBoxLayout *m_layout = nullptr;
};

} // namespace helm
