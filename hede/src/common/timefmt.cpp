#include "timefmt.h"

namespace helm {

QString formatClock(const QDateTime &dt, bool ampm) {
    return dt.time().toString(ampm ? QStringLiteral("h:mm AP") : QStringLiteral("HH:mm"));
}

} // namespace helm
