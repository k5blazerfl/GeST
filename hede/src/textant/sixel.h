#pragma once

#include <QByteArray>
#include <QImage>

// Decode a sixel payload (the bytes between the DCS `q` and the terminating ST)
// into an ARGB image. Self-contained — no libsixel. Handles the colour
// introducer (#Pc / #Pc;sys;x;y;z, RGB and HLS), RLE (!Pn), carriage return ($),
// band newline (-), and raster attributes ("). Returns a null image on garbage.
QImage decodeSixel(const QByteArray &payload);
