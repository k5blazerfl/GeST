#pragma once

#include <QWidget>

class QHBoxLayout;

namespace helm {

// The bottom bar. Its applet lineup is built from hede.conf [panel] applets
// (via helm::PanelLayout), and it rebuilds itself in place when that file
// changes — the seam Barnacle (the panel editor) writes to.
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

  private:
    void buildApplets(); // (re)populate m_layout from [panel] applets

    QHBoxLayout *m_layout = nullptr;
};

} // namespace helm
