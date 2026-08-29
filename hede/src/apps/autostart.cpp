#include "autostart.h"

#include <QDir>
#include <QFile>
#include <QHash>
#include <QStandardPaths>

#include <algorithm>

namespace helm {

namespace {

QString readAll(const QString &path) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly | QIODevice::Text))
        return {};
    return QString::fromUtf8(f.readAll());
}

bool writeAll(const QString &path, const QString &text) {
    QDir().mkpath(QFileInfo(path).absolutePath());
    QFile f(path);
    if (!f.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text))
        return false;
    f.write(text.toUtf8());
    return true;
}

// Drop every Hidden= line; if hidden is set, insert Hidden=true right after
// [Desktop Entry] (or at the top if the header is missing).
QString withHidden(const QString &text, bool hidden) {
    QStringList out;
    for (const QString &line : text.split(QLatin1Char('\n'))) {
        const QString key = line.section(QLatin1Char('='), 0, 0).trimmed();
        if (key.compare(QStringLiteral("Hidden"), Qt::CaseInsensitive) == 0)
            continue;
        out.append(line);
    }
    if (hidden) {
        const int header = out.indexOf(QStringLiteral("[Desktop Entry]"));
        out.insert(header >= 0 ? header + 1 : 0, QStringLiteral("Hidden=true"));
    }
    while (!out.isEmpty() && out.last().trimmed().isEmpty())
        out.removeLast();
    return out.join(QLatin1Char('\n')) + QLatin1Char('\n');
}

} // namespace

QStringList defaultAutostartDirs() {
    QStringList dirs;
    dirs.append(QStandardPaths::writableLocation(QStandardPaths::ConfigLocation)
                + QStringLiteral("/autostart"));
    const QString configDirs = qEnvironmentVariable("XDG_CONFIG_DIRS", QStringLiteral("/etc/xdg"));
    const QStringList systems = configDirs.split(QLatin1Char(':'), Qt::SkipEmptyParts);
    for (const QString &dir : systems)
        dirs.append(dir + QStringLiteral("/autostart"));
    return dirs;
}

QVector<AutostartEntry> scanAutostart(const QStringList &dirs, const QString &desktop) {
    QHash<QString, AutostartEntry> byId; // first dir wins (user shadows system)
    for (int i = 0; i < dirs.size(); ++i) {
        const QDir dir(dirs.at(i));
        const QStringList files =
            dir.entryList({QStringLiteral("*.desktop")}, QDir::Files, QDir::Name);
        for (const QString &file : files) {
            const QString id = file.chopped(8); // ".desktop"
            if (byId.contains(id))
                continue;
            const QString path = dir.absoluteFilePath(file);
            AutostartEntry a;
            a.entry = parseDesktopEntry(readAll(path), id);
            a.file = path;
            a.system = i > 0;
            a.enabled = !a.entry.hidden;
            if (!a.entry.shownIn(desktop))
                continue; // would never run on this desktop — not listed
            byId.insert(id, a);
        }
    }
    QVector<AutostartEntry> out;
    out.reserve(byId.size());
    for (const AutostartEntry &a : byId)
        out.append(a);
    std::sort(out.begin(), out.end(), [](const AutostartEntry &a, const AutostartEntry &b) {
        return a.entry.name.toLower() < b.entry.name.toLower();
    });
    return out;
}

bool setAutostartEnabled(const AutostartEntry &entry, bool enabled, const QString &userDir) {
    const QString userFile = userDir + QLatin1Char('/') + entry.entry.id + QStringLiteral(".desktop");
    if (!enabled) {
        // A real user entry gets Hidden=true in place; a system entry gets a
        // minimal shadowing stub so the original stays untouched.
        if (!entry.system)
            return writeAll(userFile, withHidden(readAll(entry.file), true));
        return writeAll(userFile,
                        QStringLiteral("[Desktop Entry]\nHidden=true\n"));
    }
    if (!QFile::exists(userFile))
        return true; // nothing shadowing it — already enabled
    const QString unhidden = withHidden(readAll(userFile), false);
    // A pure shadowing stub (no Exec of its own) just gets removed so the
    // system entry shows through again.
    if (parseDesktopEntry(unhidden).exec.isEmpty())
        return QFile::remove(userFile);
    return writeAll(userFile, unhidden);
}

} // namespace helm
