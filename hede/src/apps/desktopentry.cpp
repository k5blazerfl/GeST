#include "desktopentry.h"

#include <QDir>
#include <QFile>
#include <QHash>
#include <QMap>
#include <QProcess>
#include <QStandardPaths>

#include <algorithm>

namespace helm {

using Group = QHash<QString, QString>;

static bool toBool(const QString &v) {
    return v.compare(QStringLiteral("true"), Qt::CaseInsensitive) == 0;
}

// Parse the whole file into groups; locale-suffixed keys (Name[fr]) are dropped.
static QMap<QString, Group> parseGroups(const QString &text) {
    QMap<QString, Group> groups;
    QString current;
    for (QString line : text.split(QLatin1Char('\n'))) {
        line = line.trimmed();
        if (line.isEmpty() || line.startsWith(QLatin1Char('#')))
            continue;
        if (line.startsWith(QLatin1Char('[')) && line.endsWith(QLatin1Char(']'))) {
            current = line.mid(1, line.size() - 2);
            continue;
        }
        if (current.isEmpty())
            continue;
        const int eq = line.indexOf(QLatin1Char('='));
        if (eq < 0)
            continue;
        const QString key = line.left(eq).trimmed();
        if (key.contains(QLatin1Char('['))) // skip locale-suffixed keys
            continue;
        groups[current].insert(key, line.mid(eq + 1).trimmed());
    }
    return groups;
}

DesktopEntry parseDesktopEntry(const QString &text, const QString &id) {
    const QMap<QString, Group> groups = parseGroups(text);
    const Group main = groups.value(QStringLiteral("Desktop Entry"));

    DesktopEntry e;
    e.id = id;
    e.name = main.value(QStringLiteral("Name"));
    e.exec = main.value(QStringLiteral("Exec"));
    e.icon = main.value(QStringLiteral("Icon"));
    e.comment = main.value(QStringLiteral("Comment"));
    e.type = main.value(QStringLiteral("Type"));
    e.noDisplay = toBool(main.value(QStringLiteral("NoDisplay")));
    e.hidden = toBool(main.value(QStringLiteral("Hidden")));
    e.terminal = toBool(main.value(QStringLiteral("Terminal")));

    const QString actions = main.value(QStringLiteral("Actions"));
    for (const QString &aid : actions.split(QLatin1Char(';'), Qt::SkipEmptyParts)) {
        const Group g = groups.value(QStringLiteral("Desktop Action ") + aid);
        if (g.isEmpty())
            continue;
        e.actions.append({aid, g.value(QStringLiteral("Name")), g.value(QStringLiteral("Exec"))});
    }
    return e;
}

QStringList defaultApplicationDirs() {
    QStringList dirs;
    for (const QString &d : QStandardPaths::standardLocations(QStandardPaths::ApplicationsLocation))
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
        for (const QString &fileName :
             dir.entryList({QStringLiteral("*.desktop")}, QDir::Files, QDir::Name)) {
            const QString id = fileName.left(fileName.size() - 8); // strip ".desktop"
            if (seen.contains(id))
                continue;
            QFile f(dir.filePath(fileName));
            if (!f.open(QIODevice::ReadOnly | QIODevice::Text))
                continue;
            const DesktopEntry e = parseDesktopEntry(QString::fromUtf8(f.readAll()), id);
            seen.append(id);
            if (e.type != QLatin1String("Application") || e.noDisplay || e.hidden)
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

QStringList commandArgv(const QString &exec) {
    QString e = exec;
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

QStringList commandArgv(const DesktopEntry &entry) {
    return commandArgv(entry.exec);
}

} // namespace helm
