#include "format.h"

#include <QDateTime>

namespace helm {

QString entryTitle(const Notification &n) {
    const QString app = n.app.trimmed();
    const QString summary = n.summary.trimmed();
    if (!app.isEmpty() && !summary.isEmpty())
        return app + QStringLiteral(" — ") + summary;
    if (!summary.isEmpty())
        return summary;
    if (!app.isEmpty())
        return app;
    return QStringLiteral("(notification)");
}

QString relativeTime(const QDateTime &received, const QDateTime &now) {
    if (!received.isValid())
        return QString();
    const qint64 secs = received.secsTo(now);
    if (secs < 60) // includes small negative (clock skew)
        return QStringLiteral("just now");
    const qint64 mins = secs / 60;
    if (mins < 60)
        return QStringLiteral("%1m ago").arg(mins);
    const qint64 hours = mins / 60;
    if (hours < 24)
        return QStringLiteral("%1h ago").arg(hours);
    const qint64 days = hours / 24;
    if (days < 7)
        return QStringLiteral("%1d ago").arg(days);
    return received.date().toString(Qt::ISODate);
}

} // namespace helm
