#include "categories.h"

#include <QVector>

#include <utility>

namespace helm {

QString sectionForCategories(const QStringList &categories) {
    // Freedesktop main categories → menu section, in resolution priority order:
    // functional groups first, then the generic Settings/System/Utility buckets,
    // so an app tagged e.g. "Utility;System;" lands in the more specific bucket
    // and "AudioVideo;Audio;" resolves once. Category names are case-sensitive
    // PascalCase per the spec, so exact matching is correct.
    static const QVector<std::pair<QString, QString>> table = {
        {QStringLiteral("Game"), QStringLiteral("Games")},
        {QStringLiteral("Development"), QStringLiteral("Development")},
        {QStringLiteral("Graphics"), QStringLiteral("Graphics")},
        {QStringLiteral("AudioVideo"), QStringLiteral("Multimedia")},
        {QStringLiteral("Audio"), QStringLiteral("Multimedia")},
        {QStringLiteral("Video"), QStringLiteral("Multimedia")},
        {QStringLiteral("Office"), QStringLiteral("Office")},
        {QStringLiteral("Network"), QStringLiteral("Internet")},
        {QStringLiteral("Science"), QStringLiteral("Science")},
        {QStringLiteral("Education"), QStringLiteral("Education")},
        {QStringLiteral("Settings"), QStringLiteral("Settings")},
        {QStringLiteral("System"), QStringLiteral("System")},
        {QStringLiteral("Utility"), QStringLiteral("Accessories")},
    };
    for (const auto &entry : table)
        if (categories.contains(entry.first))
            return entry.second;
    return QStringLiteral("Other");
}

} // namespace helm
