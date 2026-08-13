#pragma once

#include <QDateTime>
#include <QString>

namespace helm {

// Pure, testable clock formatting. ampm=true → "3:07 PM" (Windows-familiar
// default); ampm=false → "15:07".
QString formatClock(const QDateTime &dt, bool ampm = true);

} // namespace helm
