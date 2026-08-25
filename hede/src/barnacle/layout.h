#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// Read/write the ordered [panel] applets list in a hede.conf INI. The single
// engine the bar (helm-panel) reads and the Barnacle editor writes, so the two
// never drift on format or defaults.
class PanelLayout {
  public:
    // The applet ids from [panel] applets in `configPath`, normalised. An absent
    // or empty value yields the built-in default lineup (helm::defaultApplets).
    static QStringList read(const QString &configPath);

    // Overwrite [panel] applets in `configPath` with `applets` (comma-joined).
    // An empty list clears the key, so the bar falls back to the default lineup.
    // Returns false if the INI could not be written.
    static bool write(const QString &configPath, const QStringList &applets);

    // Normalise a raw comma-separated value: split, trim, lower-case, drop
    // empties. Shared by read() and the editor so the parsing rules never drift.
    static QStringList parse(const QString &raw);
};

} // namespace helm
