#pragma once

#include <QString>
#include <QToolButton>

namespace helm {

// --- pure logic (unit-tested) ---
// Parse `brightnessctl -m` → "name,class,current,NN%,max"; returns percent or -1.
int parseBrightnessPercent(const QString &out);

// Panel applet: scroll to change screen brightness. Talks to the backlight via
// brightnessctl (unprivileged through logind/udev; direct-to-system, see
// hede-phase2.md §2). Hidden if brightnessctl / a backlight device is absent.
class BrightnessApplet : public QToolButton {
    Q_OBJECT
  public:
    explicit BrightnessApplet(QWidget *parent = nullptr);

  protected:
    void wheelEvent(QWheelEvent *e) override;

  private:
    void refresh();
    bool m_have = false;
};

} // namespace helm
