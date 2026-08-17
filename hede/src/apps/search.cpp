#include "search.h"

#include <QDir>
#include <QFileInfo>

#include <algorithm>

namespace helm {

int fuzzyScore(const QString &textIn, const QString &queryIn) {
    const QString text = textIn.toLower();
    const QString query = queryIn.toLower();
    if (query.isEmpty())
        return 0;
    if (query.size() > text.size())
        return -1;

    int score = 0;
    int ti = 0;
    int streak = 0;
    for (const QChar qc : query) {
        bool found = false;
        while (ti < text.size()) {
            if (text.at(ti) == qc) {
                int bonus = 1;
                if (ti == 0)
                    bonus += 5; // matches the very start
                else if (!text.at(ti - 1).isLetterOrNumber())
                    bonus += 3; // word boundary (after space/-/_/.)
                if (streak > 0)
                    bonus += 2 * streak; // consecutive run
                score += bonus;
                ++streak;
                ++ti;
                found = true;
                break;
            }
            streak = 0;
            ++ti;
        }
        if (!found)
            return -1; // a query char never appeared → no match
    }
    return score;
}

QVector<DesktopEntry> rankEntries(const QVector<DesktopEntry> &entries, const QString &query) {
    if (query.isEmpty())
        return entries;
    struct Scored {
        int score;
        const DesktopEntry *e;
    };
    QVector<Scored> scored;
    for (const DesktopEntry &e : entries) {
        const int s = std::max(fuzzyScore(e.name, query), fuzzyScore(e.id, query));
        if (s >= 0)
            scored.push_back({s, &e});
    }
    std::stable_sort(scored.begin(), scored.end(), [](const Scored &a, const Scored &b) {
        if (a.score != b.score)
            return a.score > b.score;
        return a.e->name.compare(b.e->name, Qt::CaseInsensitive) < 0;
    });
    QVector<DesktopEntry> out;
    out.reserve(scored.size());
    for (const Scored &s : scored)
        out.push_back(*s.e);
    return out;
}

QStringList pathExecutables() {
    QStringList names;
    const QString path = qEnvironmentVariable("PATH");
    for (const QString &dir : path.split(QLatin1Char(':'), Qt::SkipEmptyParts)) {
        QDir d(dir);
        if (!d.exists())
            continue;
        for (const QFileInfo &fi :
             d.entryInfoList(QDir::Files | QDir::Executable | QDir::NoDotAndDotDot))
            names << fi.fileName();
    }
    names.removeDuplicates();
    names.sort();
    return names;
}

QStringList matchingExecutables(const QStringList &all, const QString &query, int limit) {
    if (query.isEmpty())
        return {};
    struct Scored {
        int score;
        QString name;
    };
    QVector<Scored> scored;
    for (const QString &n : all) {
        const int s = fuzzyScore(n, query);
        if (s >= 0)
            scored.push_back({s, n});
    }
    std::stable_sort(scored.begin(), scored.end(), [](const Scored &a, const Scored &b) {
        if (a.score != b.score)
            return a.score > b.score;
        return a.name < b.name;
    });
    QStringList out;
    for (const Scored &s : scored) {
        if (out.size() >= limit)
            break;
        out << s.name;
    }
    return out;
}

} // namespace helm
