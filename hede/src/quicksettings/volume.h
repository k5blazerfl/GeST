#pragma once

#include <QString>
#include <QToolButton>

namespace helm {

struct VolumeState {
    bool available = false;
    int percent = 0;
    bool muted = false;
};

// --- pure logic (unit-tested) ---
// Parse `wpctl get-volume @DEFAULT_AUDIO_SINK@` → e.g. "Volume: 0.55 [MUTED]".
VolumeState parseWpctlVolume(const QString &out);
QString volumeIconName(int percent, bool muted);

// Panel applet: scroll to change volume, left-click to toggle mute. Talks to
// PipeWire via wpctl (direct-to-system; see hede-phase2.md §2). Hidden if wpctl
// is unavailable.
class VolumeApplet : public QToolButton {
    Q_OBJECT
  public:
    explicit VolumeApplet(QWidget *parent = nullptr);

  protected:
    void wheelEvent(QWheelEvent *e) override;
    void mouseReleaseEvent(QMouseEvent *e) override;

  private:
    void refresh();
    bool m_have = false;
};

} // namespace helm
