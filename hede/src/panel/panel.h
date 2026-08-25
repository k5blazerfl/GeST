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
    // so a live height change can re-emit heightChanged to the owner.
    void watchConfig();

  Q_SIGNALS:
    // Emitted by reload() when [panel] height changed, so the owner can update
    // the layer-shell exclusive zone (the reserved strip) to match.
    void heightChanged(int height);

  public Q_SLOTS:
    // Re-read config and rebuild the applet layout (and height) in place.
    void reload();

  private:
    void buildApplets(); // (re)populate m_layout from [panel] applets

    QHBoxLayout *m_layout = nullptr;
    int m_height = 0;
};

} // namespace helm
