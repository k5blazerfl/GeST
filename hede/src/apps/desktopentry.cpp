#include "desktopentry.h"

#include <QDir>
#include <QFile>
#include <QProcess>
#include <QStandardPaths>

#include <algorithm>

namespace helm {

static bool toBool(const QString &v) {
    return v.compare(QStringLiteral("true"), Qt::CaseInsensitive) == 0;
}

DesktopEntry parseDesktopEntry(const QString &text, const QString &id) {
    DesktopEntry e;
    e.id = id;
    bool inGroup = false;
    const QStringList lines = text.split(QLatin1Char('\n'));
    for (QString line : lines) {
        line = line.trimmed();
        if (line.isEmpty() || line.startsWith(QLatin1Char('#')))
            continue;
        if (line.startsWith(QLatin1Char('['))) {
            inGroup = (line == QLatin1String("[Desktop Entry]"));
            continue;
        }
        if (!inGroup)
            continue;
        const int eq = line.indexOf(QLatin1Char('='));
        if (eq < 0)
            continue;
        const QString key = line.left(eq).trimmed();
        const QString value = line.mid(eq + 1).trimmed();
        if (key.contains(QLatin1Char('['))) // skip locale-suffixed keys (Name[fr])
            continue;
        if (key == QLatin1String("Name"))
            e.name = value;
        else if (key == QLatin1String("Exec"))
            e.exec = value;
        else if (key == QLatin1String("Icon"))
            e.icon = value;
        else if (key == QLatin1String("Comment"))
            e.comment = value;
        else if (key == QLatin1String("Type"))
            e.type = value;
        else if (key == QLatin1String("NoDisplay"))
            e.noDisplay = toBool(value);
        else if (key == QLatin1String("Hidden"))
            e.hidden = toBool(value);
        else if (key == QLatin1String("Terminal"))
            e.terminal = toBool(value);
    }
    return e;
}

QStringList defaultApplicationDirs() {
    QStringList dirs;
    const auto bases = QStandardPaths::standardLocations(QStandardPaths::ApplicationsLocation);
    // ApplicationsLocation already yields the per-user + system applications dirs
    // in priority order; keep unique.
    for (const QString &d : bases)
        if (!dirs.contains(d))
            dirs.append(d);
    return dirs;
}

static bool byName(const DesktopEntry &a, const DesktopEntry &b) {
    return a.name.compare(b.name, Qt::CaseInsensitive) < 0;
}

QVector<DesktopEntry> scanDesktopEntries(const QStringList &dirs) {
    QVector<DesktopEntry> out;
    QStringList seen;
    for (const QString &dirPath : dirs) {
        QDir dir(dirPath);
        if (!dir.exists())
            continue;
        const auto files = dir.entryList({QStringLiteral("*.desktop")}, QDir::Files, QDir::Name);
        for (const QString &fileName : files) {
            const QString id = fileName.left(fileName.size() - 8); // strip ".desktop"
            if (seen.contains(id)) // higher-priority dir already provided this id
                continue;
            QFile f(dir.filePath(fileName));
            if (!f.open(QIODevice::ReadOnly | QIODevice::Text))
                continue;
            const QString text = QString::fromUtf8(f.readAll());
            const DesktopEntry e = parseDesktopEntry(text, id);
            seen.append(id);
            if (e.type != QLatin1String("Application"))
                continue;
            if (e.noDisplay || e.hidden)
                continue;
            if (e.name.isEmpty() || e.exec.isEmpty())
                continue;
            out.append(e);
        }
    }
    std::sort(out.begin(), out.end(), byName);
    return out;
}

QVector<DesktopEntry> filterEntries(const QVector<DesktopEntry> &entries, const QString &query) {
    const QString q = query.trimmed();
    QVector<DesktopEntry> out;
    for (const DesktopEntry &e : entries) {
        if (q.isEmpty() || e.name.contains(q, Qt::CaseInsensitive) ||
            e.comment.contains(q, Qt::CaseInsensitive) || e.exec.contains(q, Qt::CaseInsensitive))
            out.append(e);
    }
    std::sort(out.begin(), out.end(), byName);
    return out;
}

QStringList commandArgv(const DesktopEntry &entry) {
    QString e = entry.exec;
    e.replace(QLatin1String("%%"), QLatin1String("\x01")); // protect literal percent
    static const QStringList codes = {
        QStringLiteral("%f"), QStringLiteral("%F"), QStringLiteral("%u"), QStringLiteral("%U"),
        QStringLiteral("%i"), QStringLiteral("%c"), QStringLiteral("%k"), QStringLiteral("%d"),
        QStringLiteral("%D"), QStringLiteral("%n"), QStringLiteral("%N"), QStringLiteral("%v"),
        QStringLiteral("%m")};
    for (const QString &c : codes)
        e.remove(c);
    e.replace(QLatin1String("\x01"), QLatin1String("%"));
    return QProcess::splitCommand(e.trimmed());
}

} // namespace helm
