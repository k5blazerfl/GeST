#include "backgroundwidget.h"

#include <QPainter>

namespace helm {

BackgroundWidget::BackgroundWidget(const Wallpaper &wp, QWidget *parent)
    : QWidget(parent), m_wp(wp) {
    if (m_wp.useImage)
        m_pixmap = QPixmap(m_wp.imagePath); // null if it fails to load → colour base shows
}

void BackgroundWidget::paintEvent(QPaintEvent *) {
    QPainter p(this);
    p.fillRect(rect(), m_wp.color); // base colour (and fallback if the image is null)

    if (m_wp.useImage && !m_pixmap.isNull()) {
        p.setRenderHint(QPainter::SmoothPixmapTransform, true);
        if (m_wp.fit == Fit::Tile) {
            p.drawTiledPixmap(rect(), m_pixmap);
        } else {
            const QRect dst = computeImageTarget(m_pixmap.size(), size(), m_wp.fit);
            p.drawPixmap(dst, m_pixmap);
        }
    }
}

} // namespace helm
