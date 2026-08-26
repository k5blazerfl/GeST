#include "widgets.h"

#include <QLatin1Char>
#include <QSettings>

namespace helm {

QStringList lanternWidgetIds(const QString &configPath) {
    QSettings s(configPath, QSettings::IniFormat);
    if (!s.contains(QStringLiteral("lantern/widgets")))
        return {QStringLiteral("system")}; // default lineup when unconfigured
    const QString raw = s.value(QStringLiteral("lantern/widgets")).toString();
    QStringList out;
    for (const QString &tok : raw.split(QLatin1Char(','), Qt::SkipEmptyParts)) {
        const QString id = tok.trimmed().toLower();
        if (!id.isEmpty())
            out.append(id);
    }
    return out; // an explicit empty value → no widgets
}

MemInfo parseMemInfo(const QString &procMeminfo) {
    MemInfo m;
    const QStringList lines = procMeminfo.split(QLatin1Char('\n'));
    for (const QString &line : lines) {
        if (line.startsWith(QLatin1String("MemTotal:")))
            m.totalKb = line.section(QLatin1Char(':'), 1).trimmed().split(QLatin1Char(' ')).first().toLongLong();
        else if (line.startsWith(QLatin1String("MemAvailable:")))
            m.availableKb = line.section(QLatin1Char(':'), 1).trimmed().split(QLatin1Char(' ')).first().toLongLong();
    }
    return m;
}

int usedPercent(qint64 used, qint64 total) {
    if (total <= 0)
        return 0;
    return static_cast<int>((used * 100 + total / 2) / total); // rounded
}

QString formatBytes(qint64 bytes) {
    static const char *units[] = {"B", "KB", "MB", "GB", "TB"};
    double v = static_cast<double>(bytes);
    int u = 0;
    while (v >= 1000.0 && u < 4) {
        v /= 1000.0;
        ++u;
    }
    const int prec = (u == 0 || v >= 100.0) ? 0 : 1;
    return QStringLiteral("%1 %2").arg(v, 0, 'f', prec).arg(QLatin1String(units[u]));
}

qint64 parseUptimeSeconds(const QString &procUptime) {
    const QString first = procUptime.trimmed().split(QLatin1Char(' ')).value(0);
    return static_cast<qint64>(first.toDouble());
}

QString formatUptime(qint64 seconds) {
    if (seconds < 0)
        seconds = 0;
    const qint64 d = seconds / 86400;
    const qint64 h = (seconds % 86400) / 3600;
    const qint64 m = (seconds % 3600) / 60;
    if (d > 0)
        return QStringLiteral("up %1d %2h").arg(d).arg(h);
    if (h > 0)
        return QStringLiteral("up %1h %2m").arg(h).arg(m);
    return QStringLiteral("up %1m").arg(m);
}

} // namespace helm
