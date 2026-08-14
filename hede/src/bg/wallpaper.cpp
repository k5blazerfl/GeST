#include "wallpaper.h"

#include "config.h"

#include <algorithm>

namespace helm {

Fit parseFit(const QString &s) {
    const QString v = s.trimmed().toLower();
    if (v == QLatin1String("fit"))
        return Fit::Fit;
    if (v == QLatin1String("stretch"))
        return Fit::Stretch;
    if (v == QLatin1String("center"))
        return Fit::Center;
    if (v == QLatin1String("tile"))
        return Fit::Tile;
    return Fit::Fill;
}

QRect computeImageTarget(QSize image, QSize target, Fit fit) {
    if (image.isEmpty() || target.isEmpty())
        return QRect(QPoint(0, 0), target);

    switch (fit) {
    case Fit::Stretch:
        return QRect(QPoint(0, 0), target);
    case Fit::Center:
        return QRect(
            QPoint((target.width() - image.width()) / 2, (target.height() - image.height()) / 2),
            image);
    case Fit::Tile:
        return QRect(QPoint(0, 0), image);
    case Fit::Fit:
    case Fit::Fill: {
        const double sx = double(target.width()) / image.width();
        const double sy = double(target.height()) / image.height();
        const double s = (fit == Fit::Fit) ? std::min(sx, sy) : std::max(sx, sy);
        const QSize scaled(qRound(image.width() * s), qRound(image.height() * s));
        return QRect(
            QPoint((target.width() - scaled.width()) / 2, (target.height() - scaled.height()) / 2),
            scaled);
    }
    }
    return QRect(QPoint(0, 0), target);
}

Wallpaper loadWallpaper(const Config &cfg) {
    Wallpaper w;
    const QString mode = cfg.string(QStringLiteral("wallpaper/mode"), QStringLiteral("color"));
    w.color = QColor(cfg.string(QStringLiteral("wallpaper/color"), QStringLiteral("#0a1633")));
    if (!w.color.isValid())
        w.color = QColor(QStringLiteral("#0a1633"));
    w.imagePath = cfg.string(QStringLiteral("wallpaper/image"));
    w.fit = parseFit(cfg.string(QStringLiteral("wallpaper/fit"), QStringLiteral("fill")));
    w.useImage =
        (mode.compare(QLatin1String("image"), Qt::CaseInsensitive) == 0) && !w.imagePath.isEmpty();
    return w;
}

} // namespace helm
