#pragma once

#include <QColor>
#include <QRect>
#include <QSize>
#include <QString>

namespace helm {

class Config;

// How an image is placed on the output.
enum class Fit { Fill, Fit, Stretch, Center, Tile };

Fit parseFit(const QString &s); // unknown → Fill

// Destination rect to draw a scaled image into `target` for the given fit.
// (Tile is handled by the painter; here it returns the image at native size.)
QRect computeImageTarget(QSize image, QSize target, Fit fit);

struct Wallpaper {
    bool useImage = false;
    QColor color;
    QString imagePath;
    Fit fit = Fit::Fill;
};

// Read [wallpaper] mode/color/image/fit from config. The default mode is
// "world": the active biome (hede.conf [world] id, default "harbor") supplies
// the scene, so a fresh system comes up on its world wallpaper rather than the
// flat navy. mode=image uses wallpaper/image; mode=color is the base only.
// The abyss navy (#0a1633) is the base colour and the fallback if the image is
// missing.
Wallpaper loadWallpaper(const Config &cfg);

} // namespace helm
