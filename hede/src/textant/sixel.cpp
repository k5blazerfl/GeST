#include "sixel.h"

#include <QHash>

#include <algorithm>

namespace {

int readUint(const char *p, int &i, int n) {
    int v = 0;
    while (i < n && p[i] >= '0' && p[i] <= '9') {
        v = v * 10 + (p[i] - '0');
        ++i;
    }
    return v;
}

int clamp255(int v) { return std::clamp(v, 0, 255); }

// HLS (H 0-360, L 0-100, S 0-100) as used by sixel colour system 1.
QRgb hlsToRgb(int h, int l, int s) {
    const double H = h / 360.0, L = l / 100.0, S = s / 100.0;
    const auto hue = [](double m1, double m2, double hh) {
        if (hh < 0) hh += 1;
        if (hh > 1) hh -= 1;
        if (hh * 6 < 1) return m1 + (m2 - m1) * 6 * hh;
        if (hh * 2 < 1) return m2;
        if (hh * 3 < 2) return m1 + (m2 - m1) * (2.0 / 3 - hh) * 6;
        return m1;
    };
    if (S == 0)
        return qRgb(clamp255(int(L * 255)), clamp255(int(L * 255)), clamp255(int(L * 255)));
    const double m2 = L <= 0.5 ? L * (1 + S) : L + S - L * S;
    const double m1 = 2 * L - m2;
    return qRgb(clamp255(int(hue(m1, m2, H + 1.0 / 3) * 255)),
                clamp255(int(hue(m1, m2, H) * 255)),
                clamp255(int(hue(m1, m2, H - 1.0 / 3) * 255)));
}

} // namespace

QImage decodeSixel(const QByteArray &payload) {
    const char *p = payload.constData();
    const int n = payload.size();
    if (n <= 0)
        return QImage();

    // Pass 1 — measure. x advances on every sixel char / repeat; bands on '-'.
    int x = 0, band = 0, maxX = 0, maxBand = 0;
    for (int i = 0; i < n;) {
        const unsigned char ch = static_cast<unsigned char>(p[i]);
        if (ch == '#' || ch == '"') {
            ++i;
            while (i < n && ((p[i] >= '0' && p[i] <= '9') || p[i] == ';'))
                ++i;
        } else if (ch == '!') {
            ++i;
            const int rep = readUint(p, i, n);
            if (i < n) ++i;          // the repeated sixel char
            x += std::max(1, rep);
            maxX = std::max(maxX, x);
        } else if (ch == '$') {
            x = 0; ++i;
        } else if (ch == '-') {
            x = 0; ++band; maxBand = std::max(maxBand, band); ++i;
        } else if (ch >= 0x3F && ch <= 0x7E) {
            ++x; maxX = std::max(maxX, x); ++i;
        } else {
            ++i;
        }
    }

    const int W = std::max(1, maxX);
    const int H = (maxBand + 1) * 6;
    if (W > 8192 || H > 8192)
        return QImage();             // refuse absurd sizes

    QImage img(W, H, QImage::Format_ARGB32);
    img.fill(Qt::transparent);

    // Pass 2 — plot.
    QHash<int, QRgb> pal;
    QRgb cur = qRgb(255, 255, 255);
    x = 0; band = 0;

    const auto plot = [&](int bits) {
        if (x < 0 || x >= W)
            return;
        for (int b = 0; b < 6; ++b)
            if (bits & (1 << b)) {
                const int py = band * 6 + b;
                if (py < H)
                    img.setPixel(x, py, cur);
            }
    };

    for (int i = 0; i < n;) {
        const unsigned char ch = static_cast<unsigned char>(p[i]);
        if (ch == '#') {
            ++i;
            const int reg = readUint(p, i, n);
            if (i < n && p[i] == ';') {
                ++i;
                const int sys = readUint(p, i, n);
                int a = 0, b = 0, c = 0;
                if (i < n && p[i] == ';') { ++i; a = readUint(p, i, n); }
                if (i < n && p[i] == ';') { ++i; b = readUint(p, i, n); }
                if (i < n && p[i] == ';') { ++i; c = readUint(p, i, n); }
                cur = (sys == 1) ? hlsToRgb(a, b, c)
                                 : qRgb(clamp255(a * 255 / 100),
                                        clamp255(b * 255 / 100),
                                        clamp255(c * 255 / 100));
                pal.insert(reg, cur);
            } else {
                cur = pal.value(reg, qRgb(255, 255, 255));
            }
        } else if (ch == '"') {
            ++i;
            while (i < n && ((p[i] >= '0' && p[i] <= '9') || p[i] == ';'))
                ++i;
        } else if (ch == '!') {
            ++i;
            const int rep = std::max(1, readUint(p, i, n));
            if (i < n) {
                const unsigned char sc = static_cast<unsigned char>(p[i]);
                ++i;
                if (sc >= 0x3F && sc <= 0x7E) {
                    const int bits = sc - 0x3F;
                    for (int r = 0; r < rep; ++r) { plot(bits); ++x; }
                }
            }
        } else if (ch == '$') {
            x = 0; ++i;
        } else if (ch == '-') {
            x = 0; ++band; ++i;
        } else if (ch >= 0x3F && ch <= 0x7E) {
            plot(ch - 0x3F); ++x; ++i;
        } else {
            ++i;
        }
    }

    return img;
}
