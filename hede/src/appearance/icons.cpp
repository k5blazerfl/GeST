#include "palette.h"

#include <QPainter>
#include <QPixmap>

// Recolour bar glyphs to one flat colour (tokens.skin_model.mask_recolor): mask
// the icon's alpha with the colour so applet icons read as a single light
// monochrome family on the dark glass bar, whatever icon theme is installed.

namespace helm {

QColor barGlyphColor() {
    return QColor(QStringLiteral("#eaf1f3")); // light glyphs on the world-navy bar
}

QIcon tintedIcon(const QString &themeName, const QColor &color, const QSize &size) {
    const QIcon base = QIcon::fromTheme(themeName);
    if (base.isNull())
        return base;
    QPixmap pm = base.pixmap(size);
    if (pm.isNull())
        return base;

    QPixmap out(pm.size());
    out.setDevicePixelRatio(pm.devicePixelRatio());
    out.fill(Qt::transparent);
    QPainter p(&out);
    p.drawPixmap(0, 0, pm);
    p.setCompositionMode(QPainter::CompositionMode_SourceIn);
    p.fillRect(out.rect(), color);
    p.end();
    return QIcon(out);
}

} // namespace helm
