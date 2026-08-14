#pragma once

#include <QPixmap>
#include <QWidget>

#include "wallpaper.h"

namespace helm {

// Fills an output with the wallpaper: a solid colour base, optionally an image
// drawn per the fit mode.
class BackgroundWidget : public QWidget {
    Q_OBJECT
  public:
    explicit BackgroundWidget(const Wallpaper &wp, QWidget *parent = nullptr);

  protected:
    void paintEvent(QPaintEvent *event) override;

  private:
    Wallpaper m_wp;
    QPixmap m_pixmap;
};

} // namespace helm
