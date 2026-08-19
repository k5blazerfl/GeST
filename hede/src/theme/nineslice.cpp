#include "nineslice.h"

namespace helm {

QList<SliceRect> nineSliceBorder(QSize s, QMargins m, QRect d) {
    QList<SliceRect> out;
    const int sw = s.width(), sh = s.height();
    const int l = m.left(), r = m.right(), t = m.top(), b = m.bottom();

    const int dl = d.left(), dt = d.top();
    const int dr = d.left() + d.width();  // one past the right edge
    const int db = d.top() + d.height();  // one past the bottom edge
    const int dx1 = dl + l, dx2 = dr - r; // inner column bounds
    const int dy1 = dt + t, dy2 = db - b; // inner row bounds

    auto add = [&](QRect src, QRect dst) {
        if (src.width() > 0 && src.height() > 0 && dst.width() > 0 && dst.height() > 0)
            out.append({src, dst});
    };

    // corners (native size)
    add(QRect(0, 0, l, t), QRect(dl, dt, l, t));                     // top-left
    add(QRect(sw - r, 0, r, t), QRect(dx2, dt, r, t));              // top-right
    add(QRect(0, sh - b, l, b), QRect(dl, dy2, l, b));             // bottom-left
    add(QRect(sw - r, sh - b, r, b), QRect(dx2, dy2, r, b));       // bottom-right
    // edges (stretched)
    add(QRect(l, 0, sw - l - r, t), QRect(dx1, dt, dx2 - dx1, t)); // top
    add(QRect(l, sh - b, sw - l - r, b), QRect(dx1, dy2, dx2 - dx1, b)); // bottom
    add(QRect(0, t, l, sh - t - b), QRect(dl, dy1, l, dy2 - dy1)); // left
    add(QRect(sw - r, t, r, sh - t - b), QRect(dx2, dy1, r, dy2 - dy1)); // right

    return out;
}

} // namespace helm
