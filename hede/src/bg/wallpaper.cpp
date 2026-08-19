#include "wallpaper.h"

#include "config.h"
#include "world.h"

#include <algorithm>

namespace helm {

Fit parseFit(const QString &s) {
    const QString v = s.trimmed().toLower();
    // "cover"/"contain" are the helm.world/0.1 vocabulary (CSS-style); they map
    // onto Fill/Fit so world specs and [wallpaper] config share one enum.
    if (v == QLatin1String("fit") || v == QLatin1String("contain"))
        return Fit::Fit;
    if (v == QLatin1String("stretch"))
        return Fit::Stretch;
    if (v == QLatin1String("center"))
        return Fit::Center;
    if (v == QLatin1String("tile"))
        return Fit::Tile;
    return Fit::Fill; // includes "fill" and "cover"
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
    w.color = QColor(cfg.string(QStringLiteral("wallpaper/color"), QStringLiteral("#0a1633")));
    if (!w.color.isValid())
        w.color = QColor(QStringLiteral("#0a1633"));

    // Modes: "world" (default) draws the active biome's scene; "image" draws an
    // explicit wallpaper/image; "color" is the flat base only.
    const QString mode = cfg.string(QStringLiteral("wallpaper/mode"), QStringLiteral("world"));
    const QString fitCfg = cfg.string(QStringLiteral("wallpaper/fit")); // empty if unset
    QString worldFit;

    if (mode.compare(QLatin1String("image"), Qt::CaseInsensitive) == 0) {
        w.imagePath = cfg.string(QStringLiteral("wallpaper/image"));
        w.useImage = !w.imagePath.isEmpty();
    } else if (mode.compare(QLatin1String("color"), Qt::CaseInsensitive) == 0) {
        w.useImage = false;
    } else { // "world" — the biome supplies the scene
        const World world = loadWorld(cfg.string(QStringLiteral("world/id"), QStringLiteral("harbor")));
        w.imagePath = world.wallpaperPath();
        w.useImage = !w.imagePath.isEmpty();
        worldFit = world.wallpaperFit;
    }

    // Fit precedence: an explicit [wallpaper] fit wins, then the world's fit,
    // then fill/cover.
    const QString fit = !fitCfg.isEmpty()   ? fitCfg
                        : !worldFit.isEmpty() ? worldFit
                                              : QStringLiteral("fill");
    w.fit = parseFit(fit);
    return w;
}

} // namespace helm
