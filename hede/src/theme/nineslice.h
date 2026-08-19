#pragma once

#include <QList>
#include <QMargins>
#include <QRect>
#include <QSize>

namespace helm {

// One source→destination rectangle pair for a nine-patch piece.
struct SliceRect {
    QRect src;
    QRect dst;
};

// The eight border pieces (four corners + four edges) of a nine-patch image of
// size `src` with `insets`, mapped onto destination rect `dst`. The centre is
// deliberately omitted — in HeDE's frames it is transparent and the app content
// shows through. Corners keep their native size; edges stretch along their run.
// Degenerate pieces (zero width/height) are skipped. Pure geometry — unit tested
// and shared by the helm Qt decoration plugin.
QList<SliceRect> nineSliceBorder(QSize src, QMargins insets, QRect dst);

} // namespace helm
