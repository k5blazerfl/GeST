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

// Read [wallpaper] mode/color/image/fit from config (defaults: the HeDE abyss
// navy, no image).
Wallpaper loadWallpaper(const Config &cfg);

} // namespace helm
