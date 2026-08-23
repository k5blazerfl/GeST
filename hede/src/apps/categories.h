#pragma once

#include <QString>
#include <QStringList>

namespace helm {

// Map an entry's freedesktop Categories= list to a single display section for a
// classic / navigable Start menu (e.g. "Network" → "Internet", "AudioVideo" →
// "Multimedia"). The freedesktop *main* categories are matched in a fixed
// resolution priority (functional groups before the generic Settings/System/
// Utility buckets); the first match wins. Entries with no recognised main
// category fall to "Other". Pure — no I/O, so it is trivially unit-testable.
QString sectionForCategories(const QStringList &categories);

} // namespace helm
