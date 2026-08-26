#pragma once

#include <QString>
#include <QStringList>

// Lantern's glanceable-widget layer (docs/design/lantern.md, v2). Which widgets
// the drawer shows is config-driven (like Barnacle's [panel] applets); the
// per-widget data parsing/formatting lives here too, pure and unit-tested — the
// QWidgets that render it are in the exe.
namespace helm {

// The ordered widget ids from hede.conf [lantern] widgets (comma-separated,
// trimmed, lower-cased). Unset → the default {"system"}; an explicit empty value
// → no widgets.
QStringList lanternWidgetIds(const QString &configPath);

// --- system-info widget data (pure) ---

struct MemInfo {
    qint64 totalKb = 0;
    qint64 availableKb = 0;
};

// Parse MemTotal / MemAvailable (kB) out of /proc/meminfo text.
MemInfo parseMemInfo(const QString &procMeminfo);

// Rounded percent of `used` out of `total` (0 when total <= 0).
int usedPercent(qint64 used, qint64 total);

// A human byte size, decimal units: "512 B", "1.5 KB", "2.5 GB".
QString formatBytes(qint64 bytes);

// Seconds of uptime from the first field of /proc/uptime text.
qint64 parseUptimeSeconds(const QString &procUptime);

// "up 3h 20m" / "up 2d 4h" / "up 5m".
QString formatUptime(qint64 seconds);

} // namespace helm
